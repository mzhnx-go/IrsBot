"""Provider 管理 REST API 端点测试（Task 10.5）。

覆盖：CRUD 四端点、设默认互斥（验收标准）、api_key 加密落库、多租户隔离（IDOR）。
通过 TestClient 走真实路由 + 测试数据库，不依赖外部模型 API，故不打 integration 标记。
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.config import settings
from app.core.db.models import ProviderConfig

# 测试创建的 provider 统一用该前缀命名，便于 fixture 清理
_NAME_PREFIX = "test-p-"


@pytest.fixture(autouse=True)
def cleanup_test_providers(db: Session):
    """测试后：删除本文件创建的 provider，并恢复种子默认。

    init_db 会给 FIRST_SUPERUSER 建一条 name="default" 且 is_default=True
    的配置，集成测试依赖它；互斥测试会清掉它的默认标记，这里统一恢复。
    """
    yield
    rows = db.exec(
        select(ProviderConfig).where(ProviderConfig.name.like(f"{_NAME_PREFIX}%"))
    ).all()
    for row in rows:
        db.delete(row)
    seed = db.exec(
        select(ProviderConfig).where(ProviderConfig.name == "default")
    ).one_or_none()
    if seed:
        seed.is_default = True
        db.add(seed)
    db.commit()


def _create_provider(
    client: TestClient, headers: dict, name: str | None = None, **overrides
) -> dict:
    """POST 创建一条 provider，返回响应 JSON（断言成功）。"""
    body = {
        "name": name or f"{_NAME_PREFIX}{uuid.uuid4().hex[:8]}",
        "provider_type": "openai",
        "api_key": "sk-plain-test-key",
        "model_name": "gpt-4o",
        **overrides,
    }
    res = client.post(
        f"{settings.API_V1_STR}/providers", headers=headers, json=body
    )
    assert res.status_code == 200, res.text
    return res.json()


# ── POST /providers ──────────────────────────────────────────


def test_create_provider_masks_api_key_and_encrypts(
    client: TestClient, superuser_token_headers: dict, db: Session
) -> None:
    """创建成功：响应不含 api_key，数据库中是密文而非明文"""
    created = _create_provider(client, superuser_token_headers)

    assert "api_key" not in created
    assert created["is_default"] is False

    row = db.exec(
        select(ProviderConfig).where(ProviderConfig.id == uuid.UUID(created["id"]))
    ).one()
    assert row.api_key != "sk-plain-test-key"
    assert row.api_key.startswith("enc:v1:")


def test_create_default_clears_previous_default(
    client: TestClient, superuser_token_headers: dict, db: Session
) -> None:
    """互斥验收：连续创建两条默认 provider，全库该用户只保留最后一条默认"""
    a = _create_provider(client, superuser_token_headers, is_default=True)
    b = _create_provider(client, superuser_token_headers, is_default=True)

    row_a = db.exec(
        select(ProviderConfig).where(ProviderConfig.id == uuid.UUID(a["id"]))
    ).one()
    row_b = db.exec(
        select(ProviderConfig).where(ProviderConfig.id == uuid.UUID(b["id"]))
    ).one()
    assert row_a.is_default is False
    assert row_b.is_default is True


# ── GET /providers ───────────────────────────────────────────


def test_list_providers_masks_api_key(
    client: TestClient, superuser_token_headers: dict
) -> None:
    """列表返回所有字段但绝不含 api_key"""
    _create_provider(client, superuser_token_headers)

    res = client.get(
        f"{settings.API_V1_STR}/providers", headers=superuser_token_headers
    )
    assert res.status_code == 200
    items = res.json()
    assert isinstance(items, list)
    assert all("api_key" not in item for item in items)
    assert any(item["name"].startswith(_NAME_PREFIX) for item in items)


# ── PATCH /providers/{id} ────────────────────────────────────


def test_patch_sets_default_mutual_exclusive(
    client: TestClient, superuser_token_headers: dict, db: Session
) -> None:
    """PATCH 设默认：旧默认被清掉，响应同样不含 api_key"""
    a = _create_provider(client, superuser_token_headers, is_default=True)
    b = _create_provider(client, superuser_token_headers)

    res = client.patch(
        f"{settings.API_V1_STR}/providers/{b['id']}",
        headers=superuser_token_headers,
        json={"is_default": True},
    )
    assert res.status_code == 200
    assert res.json()["is_default"] is True
    assert "api_key" not in res.json()

    row_a = db.exec(
        select(ProviderConfig).where(ProviderConfig.id == uuid.UUID(a["id"]))
    ).one()
    assert row_a.is_default is False


def test_patch_encrypts_new_api_key(
    client: TestClient, superuser_token_headers: dict, db: Session
) -> None:
    """PATCH 更新 api_key：落库为密文"""
    created = _create_provider(client, superuser_token_headers)

    res = client.patch(
        f"{settings.API_V1_STR}/providers/{created['id']}",
        headers=superuser_token_headers,
        json={"api_key": "sk-new-plain"},
    )
    assert res.status_code == 200

    row = db.exec(
        select(ProviderConfig).where(ProviderConfig.id == uuid.UUID(created["id"]))
    ).one()
    assert row.api_key.startswith("enc:v1:")


def test_patch_not_found_404(
    client: TestClient, superuser_token_headers: dict
) -> None:
    """更新不存在的 provider → 404"""
    res = client.patch(
        f"{settings.API_V1_STR}/providers/{uuid.uuid4()}",
        headers=superuser_token_headers,
        json={"name": "x"},
    )
    assert res.status_code == 404


# ── DELETE /providers/{id} ───────────────────────────────────


def test_delete_provider_ok(
    client: TestClient, superuser_token_headers: dict
) -> None:
    """删除成功返回 {"ok": true}；再删同一条 → 404"""
    created = _create_provider(client, superuser_token_headers)

    res = client.delete(
        f"{settings.API_V1_STR}/providers/{created['id']}",
        headers=superuser_token_headers,
    )
    assert res.status_code == 200
    assert res.json() == {"ok": True}

    res = client.delete(
        f"{settings.API_V1_STR}/providers/{created['id']}",
        headers=superuser_token_headers,
    )
    assert res.status_code == 404


def test_delete_other_users_provider_404(
    client: TestClient,
    superuser_token_headers: dict,
    normal_user_token_headers: dict,
) -> None:
    """多租户隔离：普通用户不能删别人的 provider（IDOR 防护）"""
    created = _create_provider(client, superuser_token_headers)

    res = client.delete(
        f"{settings.API_V1_STR}/providers/{created['id']}",
        headers=normal_user_token_headers,
    )
    assert res.status_code == 404


def test_delete_default_promotes_successor(
    client: TestClient, superuser_token_headers: dict, db: Session
) -> None:
    """§10.6 d 回归：删除当前默认源后，该用户仍「有且仅有」1 条默认（自动补位）。

    修复前：行被删掉后没有任何接替者，列表里「默认」徽标凭空消失，
    且取默认源的链路会 RuntimeError。
    """
    a = _create_provider(client, superuser_token_headers, is_default=True)
    _create_provider(client, superuser_token_headers)

    res = client.delete(
        f"{settings.API_V1_STR}/providers/{a['id']}",
        headers=superuser_token_headers,
    )
    assert res.status_code == 200

    items = client.get(
        f"{settings.API_V1_STR}/providers", headers=superuser_token_headers
    ).json()
    defaults = [item for item in items if item["is_default"]]
    assert len(defaults) == 1, f"删默认后应恰好剩 1 条默认，实际 {len(defaults)} 条"
    assert defaults[0]["id"] != a["id"]
    assert defaults[0]["is_active"] is True, "接替者必须启用中，否则取默认仍会失败"


# ── DB 级部分唯一索引 ─────────────────────────────────────────


def test_default_unique_index_enforced_at_db_level(db: Session) -> None:
    """部分唯一索引兜底：绕过 API 直接往 DB 插第二条默认源必须被拒绝。

    应用层互斥清零防不住并发写；e7f8a9b0c1d2 迁移建的
    uq_provider_configs_default_per_user（postgresql_where=is_default）
    才是最终防线。
    """
    from sqlalchemy.exc import IntegrityError

    user_id = db.exec(
        select(ProviderConfig).where(ProviderConfig.name == "default")
    ).one().user_id

    dup = ProviderConfig(
        user_id=user_id,
        name=f"{_NAME_PREFIX}dup-default-{uuid.uuid4().hex[:8]}",
        provider_type="openai",
        api_key="enc:v1:test",
        model_name="gpt-4o",
        is_active=True,
        is_default=True,  # 该用户已有一条默认（种子 default），再插必须撞索引
    )
    db.add(dup)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


# ── GET /providers/{id}/balance ──────────────────────────────


def test_balance_unsupported_vendor_returns_reason(
    client: TestClient, superuser_token_headers: dict
) -> None:
    """阿里云百炼无余额接口 → 200 + supported=False + 具体指引。

    这是本机默认源的实际情况（DashScope），必须是可读提示而非 500。
    """
    created = _create_provider(
        client,
        superuser_token_headers,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    res = client.get(
        f"{settings.API_V1_STR}/providers/{created['id']}/balance",
        headers=superuser_token_headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["supported"] is False
    assert "阿里云" in body["detail"]


def test_balance_without_base_url_returns_reason(
    client: TestClient, superuser_token_headers: dict
) -> None:
    created = _create_provider(client, superuser_token_headers, base_url=None)
    res = client.get(
        f"{settings.API_V1_STR}/providers/{created['id']}/balance",
        headers=superuser_token_headers,
    )
    assert res.status_code == 200
    assert res.json()["supported"] is False


def test_balance_not_found_404(
    client: TestClient, superuser_token_headers: dict
) -> None:
    res = client.get(
        f"{settings.API_V1_STR}/providers/{uuid.uuid4()}/balance",
        headers=superuser_token_headers,
    )
    assert res.status_code == 404


def test_balance_other_users_provider_404(
    client: TestClient,
    superuser_token_headers: dict,
    normal_user_token_headers: dict,
) -> None:
    """多租户隔离：不能借查余额读取他人模型源的存在性（IDOR 防护）。"""
    created = _create_provider(client, superuser_token_headers)
    res = client.get(
        f"{settings.API_V1_STR}/providers/{created['id']}/balance",
        headers=normal_user_token_headers,
    )
    assert res.status_code == 404


def test_balance_requires_auth(client: TestClient) -> None:
    res = client.get(f"{settings.API_V1_STR}/providers/{uuid.uuid4()}/balance")
    assert res.status_code == 401


def test_balance_uses_stored_key_and_parses_upstream(
    client: TestClient, superuser_token_headers: dict, monkeypatch
) -> None:
    """端到端（假上游）：解密落库的 key 发给服务商，并把响应归一化。"""
    import httpx

    from app.core.agent import provider_balance

    captured: dict = {}

    class FakeResponse:
        status_code = 200
        request = httpx.Request("GET", "https://api.deepseek.com")

        def json(self):
            return {
                "is_available": True,
                "balance_infos": [
                    {
                        "currency": "CNY",
                        "total_balance": "42.50",
                        "granted_balance": "2.50",
                        "topped_up_balance": "40.00",
                    }
                ],
            }

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, headers=None, **kwargs):
            captured["url"] = url
            captured["headers"] = headers or {}
            return FakeResponse()

    monkeypatch.setattr(provider_balance.httpx, "AsyncClient", FakeClient)

    created = _create_provider(
        client,
        superuser_token_headers,
        api_key="sk-plain-balance-key",
        base_url="https://api.deepseek.com/v1",
    )
    res = client.get(
        f"{settings.API_V1_STR}/providers/{created['id']}/balance",
        headers=superuser_token_headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["supported"] is True
    assert body["provider"] == "deepseek"
    assert body["remaining"] == 42.5
    assert body["detail"] is not None and "赠金 ¥2.50" in body["detail"]
    # 落库的是密文，但发给上游的必须是解密后的明文 key
    assert captured["headers"]["Authorization"] == "Bearer sk-plain-balance-key"
    assert captured["url"] == "https://api.deepseek.com/user/balance"


# ── P5 能力维度（capability）──────────────────────────────────


def test_create_provider_with_capability(
    client: TestClient, superuser_token_headers: dict, db: Session
) -> None:
    """POST 带 capability：响应与库中都是该能力，而不是默认的 chat。"""
    created = _create_provider(
        client, superuser_token_headers, capability="embedding"
    )
    assert created["capability"] == "embedding"

    row = db.exec(
        select(ProviderConfig).where(ProviderConfig.id == uuid.UUID(created["id"]))
    ).one()
    assert row.capability == "embedding"


def test_create_provider_defaults_capability_to_chat(
    client: TestClient, superuser_token_headers: dict
) -> None:
    """不传 capability → chat（存量调用方的兼容行为）。"""
    created = _create_provider(client, superuser_token_headers)
    assert created["capability"] == "chat"


def test_create_invalid_capability_422(
    client: TestClient, superuser_token_headers: dict
) -> None:
    """能力取值受 Literal 约束，写错直接 422，不会落成脏数据。"""
    res = client.post(
        f"{settings.API_V1_STR}/providers",
        headers=superuser_token_headers,
        json={
            "name": f"{_NAME_PREFIX}bad-cap",
            "provider_type": "openai",
            "api_key": "sk-x",
            "model_name": "gpt-4o",
            "capability": "vision",
        },
    )
    assert res.status_code == 422, res.text


def test_list_providers_filters_by_capability(
    client: TestClient, superuser_token_headers: dict
) -> None:
    """?capability= 过滤只回该能力的源；不传则全部（含种子对话源）。"""
    emb = _create_provider(
        client, superuser_token_headers, capability="embedding"
    )
    chat = _create_provider(client, superuser_token_headers, capability="chat")

    res = client.get(
        f"{settings.API_V1_STR}/providers",
        headers=superuser_token_headers,
        params={"capability": "embedding"},
    )
    assert res.status_code == 200, res.text
    ids = [p["id"] for p in res.json()]
    assert emb["id"] in ids
    assert chat["id"] not in ids
    assert all(p["capability"] == "embedding" for p in res.json())

    # 不传筛选：两种能力都在
    all_ids = [
        p["id"]
        for p in client.get(
            f"{settings.API_V1_STR}/providers", headers=superuser_token_headers
        ).json()
    ]
    assert {emb["id"], chat["id"]} <= set(all_ids)


def test_embedding_default_does_not_clear_chat_default(
    client: TestClient, superuser_token_headers: dict, db: Session
) -> None:
    """给嵌入源设默认，不能清掉该用户的对话默认源（互斥按能力分维）。"""
    seed = db.exec(
        select(ProviderConfig).where(ProviderConfig.name == "default")
    ).one()
    assert seed.is_default is True, "前置：种子对话源默认应在"

    _create_provider(
        client, superuser_token_headers, capability="embedding", is_default=True
    )

    db.refresh(seed)
    assert seed.is_default is True, "对话默认源被跨能力清掉了（P5 回归点）"

    defaults = db.exec(
        select(ProviderConfig).where(
            ProviderConfig.user_id == seed.user_id,
            ProviderConfig.is_default.is_(True),
        )
    ).all()
    assert {r.capability for r in defaults} == {"chat", "embedding"}


def test_patch_cannot_change_capability(
    client: TestClient, superuser_token_headers: dict, db: Session
) -> None:
    """capability 创建后不可改：PATCH 里带上也被忽略（避免换能力撞默认索引）。"""
    created = _create_provider(
        client, superuser_token_headers, capability="tts"
    )
    res = client.patch(
        f"{settings.API_V1_STR}/providers/{created['id']}",
        headers=superuser_token_headers,
        json={"name": f"{_NAME_PREFIX}renamed", "capability": "chat"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["capability"] == "tts"

    row = db.exec(
        select(ProviderConfig).where(ProviderConfig.id == uuid.UUID(created["id"]))
    ).one()
    assert row.capability == "tts"
