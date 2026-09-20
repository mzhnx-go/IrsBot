"""上游模型列表拉取（「获取模型列表」功能的供应商侧实现）。

按供应商类型适配三种协议：
- openai 兼容：GET {base_url}/models（Bearer）
- anthropic：GET {base_url}/models（x-api-key + anthropic-version）
- gemini：GET {base_url}/models?key=（v1beta，models[].name 剥前缀）

只负责「从上游拉清单」，落库 upsert 在路由层完成。
高级配置（超时/代理/请求头）全部生效——与聊天同一条出站通道。
"""

import logging
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 120


def _default_base_url(provider_type: str) -> str:
    if provider_type == "anthropic":
        return "https://api.anthropic.com/v1"
    if provider_type == "gemini":
        return "https://generativelanguage.googleapis.com/v1beta"
    return "https://api.openai.com/v1"


def _client_kwargs(
    timeout_seconds: int | None,
    proxy_url: str | None,
    extra_headers: dict[str, str] | None,
) -> dict:
    return {
        "timeout": timeout_seconds or _DEFAULT_TIMEOUT,
        "follow_redirects": True,
        **({"proxy": proxy_url} if proxy_url else {}),
        **({"headers": extra_headers} if extra_headers else {}),
    }


async def fetch_upstream_models(
    *,
    provider_type: str,
    base_url: str | None,
    api_key: str,
    timeout_seconds: int | None = None,
    proxy_url: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> list[str]:
    """从上游拉取模型 ID 清单（升序去重返回）。

    Raises:
        httpx.TimeoutException / httpx.HTTPError / httpx.HTTPStatusError:
        由调用方翻译成中文错误，本函数不吞异常（调用方要区分失败原因）。
    """
    provider_type = provider_type.lower()
    url_root = (base_url or _default_base_url(provider_type)).rstrip("/")

    headers: dict[str, str] = {}
    if provider_type == "anthropic":
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    elif provider_type == "gemini":
        # gemini 用 query 参数带 Key
        url_root = f"{url_root}?key={api_key}"
    else:
        headers = {"Authorization": f"Bearer {api_key}"}

    async with httpx.AsyncClient(
        **_client_kwargs(timeout_seconds, proxy_url, extra_headers)
    ) as client:
        resp = await client.get(f"{url_root}/models", headers=headers)
        resp.raise_for_status()
        payload = resp.json()

    if provider_type == "gemini":
        items = [
            str(m.get("name", "")).removeprefix("models/")
            for m in payload.get("models", [])
        ]
    else:
        items = [str(m.get("id", "")) for m in payload.get("data", [])]

    models = sorted({i for i in items if i})
    logger.info(
        "上游模型列表拉取成功：%s 共 %d 个",
        urlparse(url_root).hostname,
        len(models),
    )
    return models
