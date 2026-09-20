"""Provider 余额查询 —— 用同一个 API Key 调各服务商的余额/额度接口。

只覆盖「用同一个 API Key 就能查余额」的服务商（按 base_url 主机识别）：
DeepSeek / 硅基流动 / Kimi(Moonshot) / OpenRouter。

其余服务商（OpenAI、Anthropic、Gemini、阿里云百炼等）**不提供**此类接口，
一律返回 supported=False + 原因说明 —— 不假装支持、不返回猜测值。
阿里云百炼的账户余额只能走 BSS OpenAPI（需阿里云 AK/SK 签名），是另一套凭据体系。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

#: 余额接口超时（秒）；上游偶发慢，但不应让 UI 长时间等待
_TIMEOUT = 10.0


class ProviderBalanceOut(BaseModel):
    """归一化后的余额查询结果（各服务商字段口径不同，统一到这里）。"""

    supported: bool
    provider: str | None = None
    currency: str | None = None
    #: 剩余可用额度
    remaining: float | None = None
    #: 账户总额（部分服务商才有意义）
    total: float | None = None
    #: 已用量（OpenRouter 等按累计用量计费的服务商）
    used: float | None = None
    #: 人类可读摘要（赠金/充值拆分、账户状态等）
    detail: str | None = None
    #: 查询失败原因（鉴权失败、网络错误等）；supported=True 时才可能非空
    error: str | None = None


def _root_url(base_url: str) -> str:
    """从 base_url 取服务根地址：剥掉尾部斜杠与 API 版本/网关路径。

    base_url 可能写成 `https://x/v1`、`https://x/compatible-mode/v1`、
    `https://openrouter.ai/api/v1`（多段）——逐个后缀剥离直到无可剥，
    再由各适配器拼自己认识的具体路径，避免出现 `/api/api/v1/...` 这类重复段。
    """
    url = base_url.strip().rstrip("/")
    while True:
        for suffix in ("/v1", "/compatible-mode", "/api"):
            if url.endswith(suffix):
                url = url[: -len(suffix)]
                break
        else:
            return url.rstrip("/")


def _to_float(value: object) -> float | None:
    """上游金额字段可能是字符串（DeepSeek 返回 "110.00"），统一转 float。"""
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _money(amount: float | None, currency: str | None) -> str:
    """金额格式化：人民币用 ¥，其余用 $ 前缀。"""
    if amount is None:
        return "-"
    symbol = "¥" if currency == "CNY" else "$"
    return f"{symbol}{amount:.2f}"


# ── 各服务商适配器 ────────────────────────────────────────────


async def _query_deepseek(
    client: httpx.AsyncClient, root: str, api_key: str
) -> ProviderBalanceOut:
    """DeepSeek: GET /user/balance（注意不在 /v1 下）。"""
    res = await client.get(
        f"{root}/user/balance", headers={"Authorization": f"Bearer {api_key}"}
    )
    res.raise_for_status()
    data = res.json()
    infos = data.get("balance_infos") or []
    if not infos:
        return ProviderBalanceOut(
            supported=True,
            provider="deepseek",
            detail="账户未返回余额信息",
        )
    info = infos[0]
    currency = info.get("currency")
    remaining = _to_float(info.get("total_balance"))
    parts = []
    granted = _to_float(info.get("granted_balance"))
    topped = _to_float(info.get("topped_up_balance"))
    if granted is not None:
        parts.append(f"赠金 {_money(granted, currency)}")
    if topped is not None:
        parts.append(f"充值 {_money(topped, currency)}")
    if not data.get("is_available", True):
        parts.append("账户余额不足")
    return ProviderBalanceOut(
        supported=True,
        provider="deepseek",
        currency=currency,
        remaining=remaining,
        detail=" ｜ ".join(parts) or None,
    )


async def _query_siliconflow(
    client: httpx.AsyncClient, root: str, api_key: str
) -> ProviderBalanceOut:
    """硅基流动: GET /v1/user/info。"""
    res = await client.get(
        f"{root}/v1/user/info", headers={"Authorization": f"Bearer {api_key}"}
    )
    res.raise_for_status()
    payload = res.json()
    data = payload.get("data") or {}
    remaining = _to_float(data.get("totalBalance"))
    parts = []
    gift = _to_float(data.get("balance"))
    charge = _to_float(data.get("chargeBalance"))
    if gift is not None:
        parts.append(f"赠金 {_money(gift, 'CNY')}")
    if charge is not None:
        parts.append(f"充值 {_money(charge, 'CNY')}")
    return ProviderBalanceOut(
        supported=True,
        provider="siliconflow",
        currency="CNY",
        remaining=remaining,
        detail=" ｜ ".join(parts) or None,
    )


async def _query_moonshot(
    client: httpx.AsyncClient, root: str, api_key: str
) -> ProviderBalanceOut:
    """Kimi(Moonshot): GET /v1/users/me/balance。"""
    res = await client.get(
        f"{root}/v1/users/me/balance",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    res.raise_for_status()
    payload = res.json()
    data = payload.get("data") or {}
    currency = "CNY"
    remaining = _to_float(data.get("available_balance"))
    parts = []
    voucher = _to_float(data.get("voucher_balance"))
    cash = _to_float(data.get("cash_balance"))
    if voucher is not None:
        parts.append(f"代金券 {_money(voucher, currency)}")
    if cash is not None:
        parts.append(f"现金 {_money(cash, currency)}")
    return ProviderBalanceOut(
        supported=True,
        provider="moonshot",
        currency=currency,
        remaining=remaining,
        detail=" ｜ ".join(parts) or None,
    )


async def _query_openrouter(
    client: httpx.AsyncClient, root: str, api_key: str
) -> ProviderBalanceOut:
    """OpenRouter: GET /api/v1/credits（给的是「总额 + 累计用量」）。"""
    res = await client.get(
        f"{root}/api/v1/credits", headers={"Authorization": f"Bearer {api_key}"}
    )
    res.raise_for_status()
    data = (res.json() or {}).get("data") or {}
    total = _to_float(data.get("total_credits"))
    used = _to_float(data.get("total_usage"))
    remaining = None if total is None or used is None else round(total - used, 6)
    detail = None
    if total is not None and used is not None:
        detail = f"已用 {_money(used, 'USD')} / 总额 {_money(total, 'USD')}"
    return ProviderBalanceOut(
        supported=True,
        provider="openrouter",
        currency="USD",
        remaining=remaining,
        total=total,
        used=used,
        detail=detail,
    )


_Adapter = Callable[[httpx.AsyncClient, str, str], Awaitable[ProviderBalanceOut]]

#: 主机名 → (服务商标识, 适配器)。按主机精确匹配，避免误伤自定义中转站。
_VENDORS: dict[str, tuple[str, _Adapter]] = {
    "api.deepseek.com": ("deepseek", _query_deepseek),
    "api.siliconflow.cn": ("siliconflow", _query_siliconflow),
    "api.siliconflow.com": ("siliconflow", _query_siliconflow),
    "api.moonshot.cn": ("moonshot", _query_moonshot),
    "openrouter.ai": ("openrouter", _query_openrouter),
}

#: 明确知道「有账户体系但没有可用余额接口」的服务商 → 给出具体指引
_NO_API_HINT: dict[str, str] = {
    "dashscope.aliyuncs.com": (
        "阿里云百炼不提供余额接口；账户余额请在阿里云控制台「费用中心」查看"
    ),
    "api.openai.com": "OpenAI 未开放余额查询接口；请在 OpenAI 平台账单页查看",
    "api.anthropic.com": "Anthropic 未开放余额查询接口；请在 Console 账单页查看",
    "generativelanguage.googleapis.com": (
        "Google Gemini 未开放余额查询接口；请在 Google Cloud 结算页查看"
    ),
}


def detect_vendor(base_url: str | None) -> tuple[str, _Adapter] | None:
    """按 base_url 主机识别服务商；未收录的返回 None。"""
    if not base_url:
        return None
    host = (urlparse(base_url).hostname or "").lower()
    return _VENDORS.get(host)


def _unsupported_reason(base_url: str | None) -> str:
    """给出「为什么查不了」的具体原因，而不是一句笼统的「不支持」。"""
    if not base_url:
        return "该模型源未填写 API 地址，无法识别服务商，暂不支持余额查询"
    host = (urlparse(base_url).hostname or "").lower()
    if host in _NO_API_HINT:
        return _NO_API_HINT[host]
    return (
        f"暂不支持查询 {host or base_url} 的余额"
        "（目前支持 DeepSeek / 硅基流动 / Kimi / OpenRouter）"
    )


async def query_balance(
    *, base_url: str | None, api_key: str
) -> ProviderBalanceOut:
    """查询余额。返回归一化结果；不支持的服务商返回 supported=False + 原因。"""
    vendor = detect_vendor(base_url)
    if vendor is None:
        return ProviderBalanceOut(supported=False, detail=_unsupported_reason(base_url))

    provider, adapter = vendor
    root = _root_url(base_url or "")
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            return await adapter(client, root, api_key)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status in (401, 403):
            message = "API Key 无效或无权限查询余额"
        elif status == 429:
            message = "查询过于频繁，请稍后再试"
        else:
            message = f"服务商返回错误（HTTP {status}）"
        return ProviderBalanceOut(
            supported=True, provider=provider, error=message
        )
    except httpx.TimeoutException:
        return ProviderBalanceOut(
            supported=True, provider=provider, error="查询超时，请稍后再试"
        )
    except httpx.HTTPError:
        return ProviderBalanceOut(
            supported=True, provider=provider, error="无法连接到服务商，请检查网络"
        )
    except (ValueError, KeyError):
        return ProviderBalanceOut(
            supported=True, provider=provider, error="服务商返回了无法解析的响应"
        )
