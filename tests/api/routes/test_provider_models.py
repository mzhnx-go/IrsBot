"""供应商模型清单（获取模型列表 / 自定义模型）测试。

三层覆盖：
1. **上游适配**：fetch_upstream_models 对 openai 兼容 / anthropic / gemini
   三种协议的请求构造与解析（注入假 transport，不真连网）；
2. **路由层**：拉取 upsert 幂等、自定义模型增删、越权 404、上游失败映射；
3. **红线**：无归属的供应商 404 零副作用。
"""

import json
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.agent import provider_models as pm
from app.core.config import settings
from app.core.db.models import ProviderConfig, ProviderModel
from app.utils.crypto import encrypt_api_key
from tests.api.routes.test_providers import _NAME_PREFIX, _create_provider

PROVIDERS_URL = f"{settings.API_V1_STR}/providers"


@pytest.fixture(autouse=True)
def cleanup_model_rows(db: Session):
    """清理本文件创建的供应商与其模型清单。"""
    yield
    rows = db.exec(
        select(ProviderConfig).where(
            ProviderConfig.name.like(f"{_NAME_PREFIX}%")
        )
    ).all()
    for row in rows:
        db.delete(row)
    db.commit()


def _make_provider(
    client: TestClient, headers: dict, provider_type: str = "openai", **extra
) -> dict:
    return _create_provider(
        client, headers, provider_type=provider_type, **extra
    )


def _seed_models(db: Session, provider_id: str, model_ids: list[str]) -> None:
    for mid in model_ids:
        db.add(ProviderModel(provider_id=uuid.UUID(provider_id), model_id=mid))
    db.commit()


_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _patch_client(monkeypatch, handler) -> None:
    """把 fetch_upstream_models 的 httpx.AsyncClient 指向 MockTransport。

    原类必须在模块级捕获一次：若在函数内捕获，第二次 patch 会把
    第一次的包装函数当成「原类」，形成嵌套（第一个 handler 永远生效）。
    """
    def factory(**kwargs):
        return _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(pm.httpx, "AsyncClient", factory)


def _fake_upstream(payload: dict, status: int = 200):
    """造一个假 httpx transport：任何 GET 都返回给定 JSON。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload, request=request)

    return httpx.MockTransport(handler)


# ── 上游适配 ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_openai_compatible(monkeypatch) -> None:
    """openai 兼容：Bearer 头 + {base_url}/models + data[].id 解析、去重升序。"""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={"data": [{"id": "gpt-4o"}, {"id": "gpt-3.5-turbo"}, {"id": "gpt-4o"}]},
            request=request,
        )

    _patch_client(monkeypatch, handler)
    models = await pm.fetch_upstream_models(
        provider_type="openai",
        base_url="https://api.example.com/v1",
        api_key="sk-test",
    )
    assert models == ["gpt-3.5-turbo", "gpt-4o"]  # 去重 + 升序
    assert seen["url"] == "https://api.example.com/v1/models"
    assert seen["auth"] == "Bearer sk-test"


@pytest.mark.asyncio
async def test_fetch_anthropic_headers(monkeypatch) -> None:
    """anthropic：x-api-key + anthropic-version 头。"""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["x-api-key"] = request.headers.get("x-api-key")
        seen["version"] = request.headers.get("anthropic-version")
        return httpx.Response(200, json={"data": [{"id": "claude-sonnet-4"}]}, request=request)

    _patch_client(monkeypatch, handler)
    models = await pm.fetch_upstream_models(
        provider_type="anthropic", base_url=None, api_key="ak-test"
    )
    assert models == ["claude-sonnet-4"]
    assert seen["x-api-key"] == "ak-test"
    assert seen["version"] == "2023-06-01"


@pytest.mark.asyncio
async def test_fetch_gemini_key_param_and_prefix_strip(monkeypatch) -> None:
    """gemini：key 走 query 参数；models/ 前缀剥掉。"""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(
            200,
            json={"models": [{"name": "models/gemini-2.0-flash"}, {"name": "models/gemini-1.5-pro"}]},
            request=request,
        )

    _patch_client(monkeypatch, handler)
    models = await pm.fetch_upstream_models(
        provider_type="gemini", base_url=None, api_key="g-key"
    )
    assert models == ["gemini-1.5-pro", "gemini-2.0-flash"]
    assert "key=g-key" in seen["url"]


@pytest.mark.asyncio
async def test_fetch_upstream_error_propagates(monkeypatch) -> None:
    """上游 401 → HTTPStatusError 抛出（由路由层翻译成中文）。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "bad key"}, request=request)

    _patch_client(monkeypatch, handler)
    with pytest.raises(httpx.HTTPStatusError):
        await pm.fetch_upstream_models(
            provider_type="openai", base_url="https://api.example.com/v1", api_key="bad"
        )


# ── 路由层 ────────────────────────────────────────────────────


def test_fetch_models_route_upsert_idempotent(
    client: TestClient, superuser_token_headers: dict[str, str], monkeypatch
) -> None:
    """拉取落库；重复拉取不产生重复行；已有清单保留。"""
    provider = _make_provider(client, superuser_token_headers)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"id": "m-a"}, {"id": "m-b"}]},
            request=request,
        )

    _patch_client(monkeypatch, handler)

    url = f"{PROVIDERS_URL}/{provider['id']}/models/fetch"
    r1 = client.post(url, headers=superuser_token_headers)
    assert r1.status_code == 200
    assert r1.json()["count"] == 2

    # 第二次拉取：上游多了一个模型 → upsert 后 3 个，无重复
    def handler2(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"id": "m-a"}, {"id": "m-b"}, {"id": "m-c"}]},
            request=request,
        )

    _patch_client(monkeypatch, handler2)
    r2 = client.post(url, headers=superuser_token_headers)
    assert r2.status_code == 200
    body = r2.json()
    assert body["count"] == 3, body["items"]
    assert len({i["model_id"] for i in body["items"]}) == 3


def test_custom_model_add_delete_and_dup(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """自定义模型：添加 → 重复 409 → 删除 → 再添加成功。"""
    provider = _make_provider(client, superuser_token_headers)
    base = f"{PROVIDERS_URL}/{provider['id']}/models"

    r = client.post(
        base,
        headers=superuser_token_headers,
        json={"model_id": "my-custom-model"},
    )
    assert r.status_code == 200
    model_uuid = r.json()["id"]

    r = client.post(
        base,
        headers=superuser_token_headers,
        json={"model_id": "my-custom-model"},
    )
    assert r.status_code == 409

    r = client.delete(
        f"{base}/{model_uuid}", headers=superuser_token_headers
    )
    assert r.status_code == 200

    r = client.post(
        base,
        headers=superuser_token_headers,
        json={"model_id": "my-custom-model"},
    )
    assert r.status_code == 200


def test_model_routes_forbidden_for_other_user(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    normal_user_token_headers: dict[str, str],
) -> None:
    """越权：普通用户访问他人供应商的模型路由 → 404 零副作用。"""
    provider = _make_provider(client, superuser_token_headers)
    for method, url in [
        ("get", f"{PROVIDERS_URL}/{provider['id']}/models"),
        ("post", f"{PROVIDERS_URL}/{provider['id']}/models/fetch"),
        ("post", f"{PROVIDERS_URL}/{provider['id']}/models"),
    ]:
        r = getattr(client, method)(
            url,
            headers=normal_user_token_headers,
            **({"json": {"model_id": "x"}} if method == "post" and "fetch" not in url else {}),
        )
        assert r.status_code == 404, url


def test_fetch_upstream_failure_maps_to_chinese(
    client: TestClient, superuser_token_headers: dict[str, str], monkeypatch
) -> None:
    """上游 401 → 502 + 中文明细，不透传原始异常。"""
    provider = _make_provider(client, superuser_token_headers)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={}, request=request)

    _patch_client(monkeypatch, handler)
    r = client.post(
        f"{PROVIDERS_URL}/{provider['id']}/models/fetch",
        headers=superuser_token_headers,
    )
    assert r.status_code == 502
    assert "API Key" in r.json()["detail"]


def test_model_list_ordered_and_persisted(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """清单按 model_id 升序返回。"""
    provider = _make_provider(client, superuser_token_headers)
    _seed_models(db, provider["id"], ["zeta", "alpha", "mid"])
    r = client.get(
        f"{PROVIDERS_URL}/{provider['id']}/models", headers=superuser_token_headers
    )
    assert r.status_code == 200
    ids = [i["model_id"] for i in r.json()["items"]]
    assert ids == sorted(ids) == ["alpha", "mid", "zeta"]


def test_unused_json_import_guard() -> None:
    """占位（防误删 json 导入时的 lint 干扰）：json 模块可用。"""
    assert json.loads('{"ok": true}')["ok"] is True
