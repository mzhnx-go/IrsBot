"""Persona 管理 REST API 测试（Phase 15.2c 补测）。

覆盖：
- POST   /agent/personas                       创建（默认字段 / 最小合法输入）
- GET    /agent/personas                       列表只含本人
- GET    /agent/personas/{id}                  详情 / 不存在 404 / 越权 404
- PATCH  /agent/personas/{id}                  局部更新（只改提供字段）/ 越权 404
- DELETE /agent/personas/{id}                  删除 / 重复删 404 / 越权 404
- PATCH  /agent/conversations/{id}/persona     绑定 / 解绑（null）/ 人设不存在 404 / 会话不存在 404
- DELETE persona                               删除人设自动解绑引用会话

走真实路由 + 测试数据库；不依赖外部 LLM，故不打 integration 标记。
"""

import uuid

from app.core.config import settings
from fastapi.testclient import TestClient
from sqlmodel import Session

PERSONAS = f"{settings.API_V1_STR}/agent/personas"
CONVERSATIONS = f"{settings.API_V1_STR}/agent/conversations"


def _create_persona(
    client: TestClient,
    headers: dict,
    name: str = "测试人设",
    prompt: str = "你是一位测试助手。",
    **extra,
) -> dict:
    res = client.post(
        PERSONAS, headers=headers, json={"name": name, "prompt": prompt, **extra}
    )
    assert res.status_code == 201, res.text
    return res.json()


def _create_conversation(client: TestClient, headers: dict) -> dict:
    res = client.post(CONVERSATIONS, headers=headers, json={})
    assert res.status_code == 200, res.text
    return res.json()


# ── POST /agent/personas ─────────────────────────────────────


def test_create_persona_defaults(client: TestClient, superuser_token_headers: dict):
    data = _create_persona(client, superuser_token_headers)
    assert data["name"] == "测试人设"
    assert data["prompt"] == "你是一位测试助手。"
    assert data["tools"] == []
    assert data["is_active"] is True
    assert data["avatar"] is None
    assert data["default_provider_id"] is None
    assert data["created_at"] is not None


def test_create_persona_full_fields(client: TestClient, superuser_token_headers: dict):
    provider_id = str(uuid.uuid4())
    data = _create_persona(
        client,
        superuser_token_headers,
        name="知识库助手",
        prompt="只回答知识库内的问题。",
        avatar="🤖",
        default_provider_id=provider_id,
        tools=["knowledge_base_query"],
        is_active=False,
    )
    assert data["avatar"] == "🤖"
    assert data["default_provider_id"] == provider_id
    assert data["tools"] == ["knowledge_base_query"]
    assert data["is_active"] is False


def test_create_persona_rejects_empty_name_and_prompt(
    client: TestClient, superuser_token_headers: dict
):
    res = client.post(
        PERSONAS, headers=superuser_token_headers, json={"name": "", "prompt": "x"}
    )
    assert res.status_code == 422
    res = client.post(
        PERSONAS, headers=superuser_token_headers, json={"name": "x", "prompt": ""}
    )
    assert res.status_code == 422


def test_create_persona_requires_auth(client: TestClient):
    res = client.post(PERSONAS, json={"name": "x", "prompt": "y"})
    assert res.status_code == 401


# ── GET /agent/personas ──────────────────────────────────────


def test_list_personas_only_own(
    client: TestClient, superuser_token_headers: dict, normal_user_token_headers: dict
):
    mine = _create_persona(client, superuser_token_headers, name="超管的人设")
    _create_persona(client, normal_user_token_headers, name="普通用户的人设")

    res = client.get(PERSONAS, headers=superuser_token_headers)
    assert res.status_code == 200
    names = [p["name"] for p in res.json()]
    assert "超管的人设" in names
    assert "普通用户的人设" not in names

    res = client.get(PERSONAS, headers=normal_user_token_headers)
    names = [p["name"] for p in res.json()]
    assert "普通用户的人设" in names
    assert "超管的人设" not in names
    assert mine["id"] not in [p["id"] for p in res.json()]


# ── GET /agent/personas/{id} ─────────────────────────────────


def test_get_persona_detail(client: TestClient, superuser_token_headers: dict):
    created = _create_persona(client, superuser_token_headers)
    res = client.get(f"{PERSONAS}/{created['id']}", headers=superuser_token_headers)
    assert res.status_code == 200
    assert res.json()["id"] == created["id"]


def test_get_persona_not_found(client: TestClient, superuser_token_headers: dict):
    res = client.get(f"{PERSONAS}/{uuid.uuid4()}", headers=superuser_token_headers)
    assert res.status_code == 404


def test_get_persona_of_other_user_404(
    client: TestClient, superuser_token_headers: dict, normal_user_token_headers: dict
):
    created = _create_persona(client, normal_user_token_headers)
    res = client.get(f"{PERSONAS}/{created['id']}", headers=superuser_token_headers)
    assert res.status_code == 404


# ── PATCH /agent/personas/{id} ───────────────────────────────


def test_update_persona_partial(client: TestClient, superuser_token_headers: dict):
    created = _create_persona(client, superuser_token_headers, prompt="原始提示词")
    res = client.patch(
        f"{PERSONAS}/{created['id']}",
        headers=superuser_token_headers,
        json={"name": "改名后"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "改名后"
    assert data["prompt"] == "原始提示词"  # 未提供的字段保持不变


def test_update_persona_of_other_user_404(
    client: TestClient, superuser_token_headers: dict, normal_user_token_headers: dict
):
    created = _create_persona(client, normal_user_token_headers)
    res = client.patch(
        f"{PERSONAS}/{created['id']}",
        headers=superuser_token_headers,
        json={"name": "劫持"},
    )
    assert res.status_code == 404
    # 确认未被修改
    res = client.get(f"{PERSONAS}/{created['id']}", headers=normal_user_token_headers)
    assert res.json()["name"] == "测试人设"


# ── DELETE /agent/personas/{id} ──────────────────────────────


def test_delete_persona(client: TestClient, superuser_token_headers: dict):
    created = _create_persona(client, superuser_token_headers)
    res = client.delete(f"{PERSONAS}/{created['id']}", headers=superuser_token_headers)
    assert res.status_code == 200
    res = client.get(f"{PERSONAS}/{created['id']}", headers=superuser_token_headers)
    assert res.status_code == 404
    # 重复删 404
    res = client.delete(f"{PERSONAS}/{created['id']}", headers=superuser_token_headers)
    assert res.status_code == 404


def test_delete_persona_of_other_user_404(
    client: TestClient, superuser_token_headers: dict, normal_user_token_headers: dict
):
    created = _create_persona(client, normal_user_token_headers)
    res = client.delete(f"{PERSONAS}/{created['id']}", headers=superuser_token_headers)
    assert res.status_code == 404


# ── PATCH /agent/conversations/{id}/persona ──────────────────


def test_bind_and_unbind_persona(
    client: TestClient, superuser_token_headers: dict
):
    persona = _create_persona(client, superuser_token_headers)
    conv = _create_conversation(client, superuser_token_headers)

    res = client.patch(
        f"{CONVERSATIONS}/{conv['id']}/persona",
        headers=superuser_token_headers,
        json={"persona_id": persona["id"]},
    )
    assert res.status_code == 200
    assert res.json()["persona_id"] == persona["id"]

    res = client.patch(
        f"{CONVERSATIONS}/{conv['id']}/persona",
        headers=superuser_token_headers,
        json={"persona_id": None},
    )
    assert res.status_code == 200
    assert res.json()["persona_id"] is None


def test_bind_persona_not_found(
    client: TestClient, superuser_token_headers: dict
):
    conv = _create_conversation(client, superuser_token_headers)
    res = client.patch(
        f"{CONVERSATIONS}/{conv['id']}/persona",
        headers=superuser_token_headers,
        json={"persona_id": str(uuid.uuid4())},
    )
    assert res.status_code == 404


def test_bind_persona_to_missing_conversation_404(
    client: TestClient, superuser_token_headers: dict
):
    persona = _create_persona(client, superuser_token_headers)
    res = client.patch(
        f"{CONVERSATIONS}/{uuid.uuid4()}/persona",
        headers=superuser_token_headers,
        json={"persona_id": persona["id"]},
    )
    assert res.status_code == 404


def test_bind_other_users_persona_404(
    client: TestClient, superuser_token_headers: dict, normal_user_token_headers: dict
):
    others = _create_persona(client, normal_user_token_headers)
    conv = _create_conversation(client, superuser_token_headers)
    res = client.patch(
        f"{CONVERSATIONS}/{conv['id']}/persona",
        headers=superuser_token_headers,
        json={"persona_id": others["id"]},
    )
    assert res.status_code == 404


# ── 删除人设自动解绑 ─────────────────────────────────────────


def test_delete_persona_unbinds_conversations(
    client: TestClient, superuser_token_headers: dict
):
    persona = _create_persona(client, superuser_token_headers)
    conv = _create_conversation(client, superuser_token_headers)
    client.patch(
        f"{CONVERSATIONS}/{conv['id']}/persona",
        headers=superuser_token_headers,
        json={"persona_id": persona["id"]},
    )

    res = client.delete(f"{PERSONAS}/{persona['id']}", headers=superuser_token_headers)
    assert res.status_code == 200

    res = client.get(CONVERSATIONS, headers=superuser_token_headers)
    assert res.status_code == 200
    target = [c for c in res.json() if c["id"] == conv["id"]]
    assert len(target) == 1
    assert target[0]["persona_id"] is None
