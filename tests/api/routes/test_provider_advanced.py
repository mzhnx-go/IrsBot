"""供应商高级配置（超时 / 代理 / 自定义请求头）测试。

三层覆盖：
1. **路由层**：校验（超时越界 422、代理协议 400、请求头非字符串 422）、
   持久化往返、清除语义、越权 404；
2. **工厂层**：`get_chat_model` 把高级配置真实接线到 LangChain 模型实例
   （timeout / default_headers / http_client 代理），且配置变化使缓存失效；
3. **透传层**：`query_balance` 把高级配置传给 httpx.AsyncClient。

「后端真的有」的判断标准：改了配置后，发往上游的 HTTP 客户端参数随之变化。
"""

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.agent.provider import ProviderManager
from app.core.agent.provider_balance import ProviderBalanceOut, query_balance
from app.core.config import settings
from app.core.db.models import ProviderConfig
from tests.api.routes.test_providers import _NAME_PREFIX, _create_provider

PROVIDERS_URL = f"{settings.API_V1_STR}/providers"


def _patch_advanced(client: TestClient, headers: dict, provider_id: str, **fields):
    return client.patch(
        f"{PROVIDERS_URL}/{provider_id}", headers=headers, json=fields
    )


@pytest.fixture(autouse=True)
def cleanup_advanced_providers(db: Session):
    """本文件直接落库的供应商统一清理，避免污染其他用例。"""
    yield
    rows = db.exec(
        select(ProviderConfig).where(
            ProviderConfig.name.like(f"{_NAME_PREFIX}%")
        )
    ).all()
    for row in rows:
        db.delete(row)
    db.commit()


# ── 路由层：校验 ───────────────────────────────────────────────


def test_timeout_out_of_range_rejected(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """超时越界（4 / 601）→ 422，不落库。"""
    provider = _create_provider(client, superuser_token_headers)
    for bad in (4, 601):
        r = _patch_advanced(
            client, superuser_token_headers, provider["id"], timeout_seconds=bad
        )
        assert r.status_code == 422, bad


def test_proxy_scheme_validated(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """代理非 http(s) 协议 → 400；正确协议 → 200。"""
    provider = _create_provider(client, superuser_token_headers)
    r = _patch_advanced(
        client, superuser_token_headers, provider["id"], proxy_url="socks5://127.0.0.1:1080"
    )
    assert r.status_code == 400
    assert "http" in r.json()["detail"]

    r = _patch_advanced(
        client,
        superuser_token_headers,
        provider["id"],
        proxy_url="http://127.0.0.1:7890",
    )
    assert r.status_code == 200


def test_extra_headers_must_be_string_values(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """请求头值非字符串（int）→ 422。"""
    provider = _create_provider(client, superuser_token_headers)
    r = _patch_advanced(
        client,
        superuser_token_headers,
        provider["id"],
        extra_headers={"X-Retry": 3},
    )
    assert r.status_code == 422


# ── 路由层：持久化与清除 ───────────────────────────────────────


def test_advanced_config_roundtrip(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """PATCH 后 GET 返回三键；分次 PATCH 互不清除。"""
    provider = _create_provider(client, superuser_token_headers)
    r = _patch_advanced(
        client, superuser_token_headers, provider["id"], timeout_seconds=60
    )
    assert r.status_code == 200
    assert r.json()["timeout_seconds"] == 60

    r = _patch_advanced(
        client,
        superuser_token_headers,
        provider["id"],
        proxy_url="http://127.0.0.1:7890",
        extra_headers={"X-Trace": "t1"},
    )
    assert r.status_code == 200
    # 分次 PATCH：先设的超时仍在（config JSON 合并语义）
    assert r.json()["timeout_seconds"] == 60
    assert r.json()["proxy_url"] == "http://127.0.0.1:7890"
    assert r.json()["extra_headers"] == {"X-Trace": "t1"}

    r = client.get(PROVIDERS_URL, headers=superuser_token_headers)
    assert r.status_code == 200
    persisted = next(
        p for p in r.json() if p["id"] == provider["id"]
    )
    assert persisted["timeout_seconds"] == 60


def test_advanced_config_clear_semantics(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """代理空串 = 清除（GET 回 None）；headers 空 dict = 清空。"""
    provider = _create_provider(client, superuser_token_headers)
    _patch_advanced(
        client,
        superuser_token_headers,
        provider["id"],
        proxy_url="http://127.0.0.1:7890",
        extra_headers={"X-A": "1"},
    )
    r = _patch_advanced(
        client, superuser_token_headers, provider["id"], proxy_url=""
    )
    assert r.status_code == 200
    assert r.json()["proxy_url"] is None

    r = _patch_advanced(
        client, superuser_token_headers, provider["id"], extra_headers={}
    )
    assert r.status_code == 200
    assert r.json()["extra_headers"] == {}


def test_advanced_update_other_users_provider_404(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    normal_user_token_headers: dict[str, str],
) -> None:
    """越权：普通用户 PATCH 他人供应商 → 404 零副作用。"""
    provider = _create_provider(client, superuser_token_headers)
    r = _patch_advanced(
        client,
        normal_user_token_headers,
        provider["id"],
        timeout_seconds=60,
    )
    assert r.status_code == 404


# ── 工厂层：get_chat_model 真实接线 ───────────────────────────


def _make_provider_with_advanced(
    db: Session, user_id, **advanced
) -> "ProviderConfig":
    """直接落库一条带高级配置的供应商（绕过加密路由，聚焦工厂接线）。"""
    from app.core.db.models import ProviderConfig
    from app.utils.crypto import encrypt_api_key

    pc = ProviderConfig(
        user_id=user_id,
        name=f"{_NAME_PREFIX}adv-{advanced.get('timeout_seconds')}",
        provider_type="openai",
        api_key=encrypt_api_key("sk-advanced-test"),
        model_name="gpt-4o",
    )
    pc.apply_advanced_config(**advanced)
    db.add(pc)
    db.commit()
    db.refresh(pc)
    return pc


def test_get_chat_model_wires_timeout_and_headers(
    client: TestClient, db: Session, superuser_token_headers: dict[str, str]
) -> None:
    """超时与自定义请求头真实出现在 LangChain 模型实例上。"""
    me = client.get(
        f"{settings.API_V1_STR}/users/me", headers=superuser_token_headers
    ).json()
    pc = _make_provider_with_advanced(
        db,
        me["id"],
        timeout_seconds=77,
        extra_headers={"X-Custom-Trace": "irsbot"},
    )
    mgr = ProviderManager(db)
    model = mgr.get_chat_model(user_id=pc.user_id, provider_id=pc.id)

    assert model.request_timeout == 77
    assert model.default_headers.get("X-Custom-Trace") == "irsbot"


def test_get_chat_model_wires_proxy_http_client(
    client: TestClient, db: Session, superuser_token_headers: dict[str, str]
) -> None:
    """配置代理 → 模型实例挂上带 proxy 的 httpx 客户端。"""
    me = client.get(
        f"{settings.API_V1_STR}/users/me", headers=superuser_token_headers
    ).json()
    pc = _make_provider_with_advanced(
        db, me["id"], proxy_url="http://127.0.0.1:7890"
    )
    mgr = ProviderManager(db)
    model = mgr.get_chat_model(user_id=pc.user_id, provider_id=pc.id)

    http_client = getattr(model, "http_client", None)
    assert http_client is not None
    # httpx 0.28：代理经 mounts 挂到传输层连接池（httpcore URL）
    transport = next(iter(http_client._mounts.values()))
    proxy_url = transport._pool._proxy_url
    assert b"127.0.0.1" in proxy_url.host
    assert proxy_url.port == 7890


def test_config_change_invalidates_chat_cache(
    client: TestClient, db: Session, superuser_token_headers: dict[str, str]
) -> None:
    """改超时后必须拿到**新**模型实例（缓存键含高级配置签名）。"""
    me = client.get(
        f"{settings.API_V1_STR}/users/me", headers=superuser_token_headers
    ).json()
    pc = _make_provider_with_advanced(db, me["id"], timeout_seconds=30)
    mgr = ProviderManager(db)
    m1 = mgr.get_chat_model(user_id=pc.user_id, provider_id=pc.id)
    m2 = mgr.get_chat_model(user_id=pc.user_id, provider_id=pc.id)
    assert m1 is m2  # 未变：命中缓存

    pc.apply_advanced_config(timeout_seconds=88)
    db.commit()
    m3 = mgr.get_chat_model(user_id=pc.user_id, provider_id=pc.id)
    assert m3 is not m1
    assert m3.request_timeout == 88


# ── 透传层：余额查询客户端 ────────────────────────────────────


@pytest.mark.asyncio
async def test_query_balance_passes_advanced_to_httpx(monkeypatch) -> None:
    """高级配置被透传给 httpx.AsyncClient（超时/代理/请求头）。"""
    from app.core.agent import provider_balance

    captured: dict = {}

    async def fake_adapter(client: httpx.AsyncClient, root: str, api_key: str):
        return ProviderBalanceOut(supported=True, provider="deepseek")

    monkeypatch.setitem(
        provider_balance._VENDORS, "api.deepseek.com", ("deepseek", fake_adapter)
    )

    original_init = httpx.AsyncClient.__init__

    def _spy_init(self, **kwargs):
        captured.update(kwargs)
        original_init(self, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", _spy_init)

    result = await query_balance(
        base_url="https://api.deepseek.com/v1",
        api_key="sk-x",
        timeout_seconds=42,
        proxy_url="http://127.0.0.1:7890",
        extra_headers={"X-A": "1"},
    )
    assert result.supported is True
    assert captured["timeout"] == 42
    assert captured["proxy"] == "http://127.0.0.1:7890"
    assert captured["headers"] == {"X-A": "1"}
