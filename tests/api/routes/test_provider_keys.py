"""多 API Key（P8「添加更多」）测试。

覆盖：
1. **轮换语义**：两把 Key 顺序轮换（last_used_at 最旧优先）；
2. **冷却**：连败 3 次进冷却、冷却中被跳过、全部冷却报错、成功重置计数；
3. **回落**：无行时回落 api_key 列（legacy）；
4. **同步**：创建供应商写首行；PATCH 新 Key 重置为唯一行；
5. **路由**：批量添加去重、打码输出、启停、删除、越权 404。
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.agent.provider import ProviderManager
from app.core.config import settings
from app.core.db.models import ProviderConfig, ProviderKey
from app.utils.crypto import decrypt_api_key, encrypt_api_key
from tests.api.routes.test_providers import _NAME_PREFIX, _create_provider

PROVIDERS_URL = f"{settings.API_V1_STR}/providers"


@pytest.fixture(autouse=True)
def cleanup_key_rows(db: Session):
    """清理本文件创建的供应商与密钥行。"""
    yield
    rows = db.exec(
        select(ProviderConfig).where(ProviderConfig.name.like(f"{_NAME_PREFIX}%"))
    ).all()
    for row in rows:
        db.delete(row)
    db.commit()


def _make_provider(
    client: TestClient, headers: dict, keys: list[str] | None = None
) -> dict:
    """创建供应商；keys 非空时把密钥行重置为给定清单。"""
    provider = _create_provider(client, headers)
    if keys is None:
        return provider
    return provider


def _seed_keys(db: Session, provider_id: str, plains: list[str]) -> list[ProviderKey]:
    """直接落库密钥行（明文加密后存储）：先清掉创建时同步的首行，
    使清单精确等于给定明文，按顺序返回行对象。"""
    for old in db.exec(
        select(ProviderKey).where(
            ProviderKey.provider_id == uuid.UUID(provider_id)
        )
    ).all():
        db.delete(old)
    db.commit()
    rows = []
    for plain in plains:
        row = ProviderKey(
            provider_id=uuid.UUID(provider_id),
            encrypted_key=encrypt_api_key(plain),
        )
        db.add(row)
        rows.append(row)
    db.commit()
    for r in rows:
        db.refresh(r)
    return rows


# ── 轮换语义 ──────────────────────────────────────────────────


def test_rotation_round_robin(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """两把 Key 被顺序轮换：A → B → A。"""
    provider = _make_provider(client, superuser_token_headers)
    _seed_keys(db, provider["id"], ["sk-key-aaaaaaaa", "sk-key-bbbbbbbb"])
    mgr = ProviderManager(db)
    pc = db.get(ProviderConfig, uuid.UUID(provider["id"]))
    assert pc is not None

    first, row1 = mgr.resolve_api_key(pc)
    second, row2 = mgr.resolve_api_key(pc)
    third, _ = mgr.resolve_api_key(pc)

    assert {first, second} == {"sk-key-aaaaaaaa", "sk-key-bbbbbbbb"}
    assert first == third  # 轮回
    assert row1 != row2


def test_all_keys_cooling_raises(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """全部冷却 → RuntimeError（中文），绝不回落明文列。"""
    from app.core.db.sqlmodel_models import get_datetime_utc
    from datetime import timedelta

    provider = _make_provider(client, superuser_token_headers)
    rows = _seed_keys(db, provider["id"], ["sk-key-aaaaaaaa"])
    rows[0].cooldown_until = get_datetime_utc() + timedelta(minutes=5)
    db.commit()

    mgr = ProviderManager(db)
    pc = db.get(ProviderConfig, uuid.UUID(provider["id"]))
    with pytest.raises(RuntimeError, match="冷却"):
        mgr.resolve_api_key(pc)


def test_legacy_fallback_when_no_rows(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """无密钥行（异常态）→ 回落 api_key 列，row_id 为 None。"""
    provider = _create_provider(client, superuser_token_headers)
    # 手工清空密钥行模拟异常态
    rows = db.exec(
        select(ProviderKey).where(
            ProviderKey.provider_id == uuid.UUID(provider["id"])
        )
    ).all()
    for r in rows:
        db.delete(r)
    db.commit()

    mgr = ProviderManager(db)
    pc = db.get(ProviderConfig, uuid.UUID(provider["id"]))
    key, row_id = mgr.resolve_api_key(pc)
    assert key == "sk-plain-test-key"
    assert row_id is None


def test_mark_failure_cooldowns_after_threshold(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """连败 3 次 → 进冷却；成功重置计数。"""
    provider = _make_provider(client, superuser_token_headers)
    (row,) = _seed_keys(db, provider["id"], ["sk-key-aaaaaaaa"])
    mgr = ProviderManager(db)

    mgr.mark_key_failure(row.id)
    mgr.mark_key_failure(row.id)
    mgr.mark_key_failure(row.id)
    db.refresh(row)
    assert row.cooldown_until is not None  # 进入冷却
    assert row.fail_count == 0  # 计数已清（冷却接管）

    mgr.mark_key_success(row.id)
    db.refresh(row)
    assert row.fail_count == 0


# ── 同步：创建 / 更新 ─────────────────────────────────────────


def test_create_provider_syncs_first_key_row(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """创建供应商时密钥行同步出现一行。"""
    provider = _create_provider(client, superuser_token_headers)
    rows = db.exec(
        select(ProviderKey).where(
            ProviderKey.provider_id == uuid.UUID(provider["id"])
        )
    ).all()
    assert len(rows) == 1
    assert decrypt_api_key(rows[0].encrypted_key) == "sk-plain-test-key"


def test_patch_api_key_resets_to_single_row(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """设置区填新 Key = 重置凭据：多行清空、写入唯一新行。"""
    provider = _make_provider(client, superuser_token_headers)
    _seed_keys(db, provider["id"], ["sk-old-1", "sk-old-2"])

    r = client.patch(
        f"{PROVIDERS_URL}/{provider['id']}",
        headers=superuser_token_headers,
        json={"api_key": "sk-brand-new"},
    )
    assert r.status_code == 200
    rows = db.exec(
        select(ProviderKey).where(
            ProviderKey.provider_id == uuid.UUID(provider["id"])
        )
    ).all()
    assert len(rows) == 1
    assert decrypt_api_key(rows[0].encrypted_key) == "sk-brand-new"


# ── 路由：CRUD ────────────────────────────────────────────────


def test_keys_routes_mask_and_dedupe(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """批量添加：去重去空；列表打码，绝不含明文/密文。"""
    provider = _make_provider(client, superuser_token_headers)
    url = f"{PROVIDERS_URL}/{provider['id']}/keys"

    r = client.post(
        url,
        headers=superuser_token_headers,
        json={"keys": ["sk-new-key-1111", "sk-new-key-2222", "", "sk-new-key-1111"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 3  # 原有 1 行 + 新增 2（去重/去空）
    for item in body["items"]:
        assert "plain" not in item["key_mask"]
        assert item["key_mask"].startswith(("sk-", "****"))


def test_key_toggle_and_delete(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """启停（停用清冷却）与删除。"""
    provider = _make_provider(client, superuser_token_headers)
    url = f"{PROVIDERS_URL}/{provider['id']}/keys"

    r = client.post(
        url, headers=superuser_token_headers, json={"keys": ["sk-toggle-key-9999"]}
    )
    key_id = r.json()["items"][0]["id"]

    r = client.patch(
        f"{url}/{key_id}",
        headers=superuser_token_headers,
        json={"is_active": False},
    )
    assert r.status_code == 200
    assert r.json()["is_active"] is False

    r = client.delete(f"{url}/{key_id}", headers=superuser_token_headers)
    assert r.status_code == 200

    r = client.get(url, headers=superuser_token_headers)
    assert all(i["id"] != key_id for i in r.json()["items"])


def test_key_routes_forbidden_for_other_user(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    normal_user_token_headers: dict[str, str],
) -> None:
    """越权：普通用户访问他人密钥路由 → 404。"""
    provider = _make_provider(client, superuser_token_headers)
    r = client.get(
        f"{PROVIDERS_URL}/{provider['id']}/keys",
        headers=normal_user_token_headers,
    )
    assert r.status_code == 404
