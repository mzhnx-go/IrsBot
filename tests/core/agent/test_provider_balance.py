"""Provider 余额查询适配器单元测试（新功能：查询当前模型所剩额度）。

只测「解析与识别」逻辑，不联网：把模块内的 httpx.AsyncClient 换成假客户端，
断言请求 URL/鉴权头与各服务商响应到统一结果模型的映射。
"""

from typing import Any

import httpx
import pytest

from app.core.agent import provider_balance
from app.core.agent.provider_balance import (
    _root_url,
    detect_vendor,
    query_balance,
)


class _FakeResponse:
    def __init__(self, payload: Any, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.request = httpx.Request("GET", "https://example.test")

    def json(self) -> Any:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}", request=self.request, response=self
            )


def _install_fake_client(monkeypatch, responder) -> dict:
    """把 httpx.AsyncClient 换掉；responder 返回 _FakeResponse 或抛异常。"""
    calls: dict = {}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            calls["init"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, headers=None, **kwargs):
            calls["url"] = url
            calls["headers"] = headers or {}
            return responder()

    monkeypatch.setattr(provider_balance.httpx, "AsyncClient", FakeClient)
    return calls


def _ok(payload: Any):
    return lambda: _FakeResponse(payload)


def _status(code: int):
    return lambda: _FakeResponse({}, status_code=code)


def _raise(exc: Exception):
    def _boom():
        raise exc

    return _boom


# ── 纯函数：根地址与识别 ─────────────────────────────────────


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        ("https://api.deepseek.com", "https://api.deepseek.com"),
        ("https://api.deepseek.com/", "https://api.deepseek.com"),
        ("https://api.deepseek.com/v1", "https://api.deepseek.com"),
        ("https://api.siliconflow.cn/v1/", "https://api.siliconflow.cn"),
        ("https://openrouter.ai/api/v1", "https://openrouter.ai"),
        (
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "https://dashscope.aliyuncs.com",
        ),
    ],
)
def test_root_url_strips_version_suffix(base_url: str, expected: str):
    assert _root_url(base_url) == expected


def test_detect_vendor_by_host():
    assert detect_vendor("https://api.deepseek.com/v1")[0] == "deepseek"
    assert detect_vendor("https://api.moonshot.cn/v1")[0] == "moonshot"
    assert detect_vendor("https://dashscope.aliyuncs.com/compatible-mode/v1") is None
    assert detect_vendor(None) is None
    assert detect_vendor("https://my-proxy.internal/v1") is None


# ── DeepSeek ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_deepseek_parses_balance(monkeypatch):
    calls = _install_fake_client(
        monkeypatch,
        _ok(
            {
                "is_available": True,
                "balance_infos": [
                    {
                        "currency": "CNY",
                        "total_balance": "110.00",
                        "granted_balance": "10.00",
                        "topped_up_balance": "100.00",
                    }
                ],
            }
        ),
    )

    result = await query_balance(
        base_url="https://api.deepseek.com/v1", api_key="sk-ds"
    )

    assert result.supported is True
    assert result.provider == "deepseek"
    assert result.currency == "CNY"
    assert result.remaining == 110.0
    assert result.detail is not None and "赠金 ¥10.00" in result.detail
    assert result.error is None
    # 余额接口不在 /v1 下，且必须带 Bearer 鉴权
    assert calls["url"] == "https://api.deepseek.com/user/balance"
    assert calls["headers"]["Authorization"] == "Bearer sk-ds"


@pytest.mark.asyncio
async def test_deepseek_marks_unavailable_account(monkeypatch):
    _install_fake_client(
        monkeypatch,
        _ok(
            {
                "is_available": False,
                "balance_infos": [
                    {"currency": "CNY", "total_balance": "0.00"}
                ],
            }
        ),
    )

    result = await query_balance(
        base_url="https://api.deepseek.com", api_key="sk-ds"
    )
    assert result.remaining == 0.0
    assert result.detail is not None and "余额不足" in result.detail


# ── 硅基流动 ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_siliconflow_parses_balance(monkeypatch):
    calls = _install_fake_client(
        monkeypatch,
        _ok(
            {
                "code": 20000,
                "status": True,
                "data": {
                    "balance": "8.00",
                    "chargeBalance": "80.00",
                    "totalBalance": "88.00",
                },
            }
        ),
    )

    result = await query_balance(
        base_url="https://api.siliconflow.cn/v1", api_key="sk-sf"
    )
    assert result.provider == "siliconflow"
    assert result.currency == "CNY"
    assert result.remaining == 88.0
    assert result.detail is not None and "充值 ¥80.00" in result.detail
    assert calls["url"] == "https://api.siliconflow.cn/v1/user/info"


# ── Kimi ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_moonshot_parses_balance(monkeypatch):
    calls = _install_fake_client(
        monkeypatch,
        _ok(
            {
                "code": 0,
                "status": True,
                "data": {
                    "available_balance": 49.58,
                    "voucher_balance": 9.58,
                    "cash_balance": 40.0,
                },
            }
        ),
    )

    result = await query_balance(
        base_url="https://api.moonshot.cn/v1", api_key="sk-moon"
    )
    assert result.provider == "moonshot"
    assert result.remaining == 49.58
    assert result.detail is not None and "现金 ¥40.00" in result.detail
    assert calls["url"] == "https://api.moonshot.cn/v1/users/me/balance"


# ── OpenRouter ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_openrouter_computes_remaining(monkeypatch):
    calls = _install_fake_client(
        monkeypatch,
        _ok({"data": {"total_credits": 10.0, "total_usage": 2.5}}),
    )

    result = await query_balance(
        base_url="https://openrouter.ai/api/v1", api_key="sk-or"
    )
    assert result.provider == "openrouter"
    assert result.currency == "USD"
    assert result.total == 10.0
    assert result.used == 2.5
    assert result.remaining == 7.5
    assert calls["url"] == "https://openrouter.ai/api/v1/credits"


# ── 不支持的路径 ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unsupported_vendor_without_network(monkeypatch):
    """不支持的服务商不应发起任何网络请求。"""
    calls = _install_fake_client(monkeypatch, _ok({}))

    result = await query_balance(
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key="sk-qwen",
    )
    assert result.supported is False
    assert result.detail is not None and "阿里云" in result.detail
    assert "url" not in calls  # 没有发出请求


@pytest.mark.asyncio
async def test_unsupported_unknown_host_lists_supported_vendors(monkeypatch):
    _install_fake_client(monkeypatch, _ok({}))
    result = await query_balance(
        base_url="https://some-proxy.example.com/v1", api_key="sk-x"
    )
    assert result.supported is False
    assert result.detail is not None
    assert "DeepSeek" in result.detail


@pytest.mark.asyncio
async def test_unsupported_without_base_url(monkeypatch):
    _install_fake_client(monkeypatch, _ok({}))
    result = await query_balance(base_url=None, api_key="sk-x")
    assert result.supported is False
    assert result.detail is not None and "未填写 API 地址" in result.detail


# ── 上游异常映射 ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upstream_401_maps_to_readable_error(monkeypatch):
    _install_fake_client(monkeypatch, _status(401))
    result = await query_balance(
        base_url="https://api.deepseek.com", api_key="bad"
    )
    assert result.supported is True
    assert result.error == "API Key 无效或无权限查询余额"
    assert result.remaining is None


@pytest.mark.asyncio
async def test_upstream_timeout_maps_to_readable_error(monkeypatch):
    _install_fake_client(
        monkeypatch, _raise(httpx.TimeoutException("timed out"))
    )
    result = await query_balance(
        base_url="https://api.deepseek.com", api_key="sk"
    )
    assert result.error is not None and "超时" in result.error


@pytest.mark.asyncio
async def test_network_error_maps_to_readable_error(monkeypatch):
    _install_fake_client(monkeypatch, _raise(httpx.ConnectError("no route")))
    result = await query_balance(
        base_url="https://api.deepseek.com", api_key="sk"
    )
    assert result.error is not None and "无法连接" in result.error


@pytest.mark.asyncio
async def test_unparsable_payload_maps_to_readable_error(monkeypatch):
    _install_fake_client(monkeypatch, _ok(ValueError("not json")))
    result = await query_balance(
        base_url="https://api.deepseek.com", api_key="sk"
    )
    assert result.error is not None and "无法解析" in result.error
