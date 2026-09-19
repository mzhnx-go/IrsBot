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
