"""会话管理 REST API + WS 自动标题测试（Phase 15.1）。

覆盖：
- POST   /agent/conversations            建会话（默认标题 / 自定义标题）
- GET    /agent/conversations            列表只含本人会话、按 updated_at 倒序
- DELETE /agent/conversations/{id}       删除成功 / 重复删 404 / 越权删 404 / 消息级联删除
- WS     首条消息自动成标题（截断 20 字、换行压成空格），后续消息与自定义标题不覆盖

走真实路由 + 测试数据库；Agent 被整体 mock，不依赖外部 LLM，故不打 integration 标记。
"""

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from app.core.config import settings
from app.core.db.models import Message
from fastapi.testclient import TestClient
from sqlmodel import Session, select

BASE = f"{settings.API_V1_STR}/agent/conversations"


async def fake_stream(content, history=None):
    """模拟 Agent.stream：只产出一个文字块，供 WS 链路跑通。"""
    yield {
        "event": "on_chat_model_stream",
        "data": {"chunk": SimpleNamespace(content="收到")},
    }


def _create(client: TestClient, headers: dict, title: str | None = None) -> dict:
    """建会话并返回响应 JSON；title 为 None 时走默认标题。"""
    body = {} if title is None else {"title": title}
    res = client.post(BASE, headers=headers, json=body)
    assert res.status_code == 200, res.text
    return res.json()


def _send_ws_message(
    client: TestClient, headers: dict, conversation_id: str, content: str
) -> None:
    """连 WS 发一条消息并等 done（Agent 已 mock，不会真的调模型）。"""
    token = headers["Authorization"].split(" ", 1)[1]
    with patch("app.api.routes.agent_ws.Agent") as mock_agent:
        mock_agent.return_value.stream = fake_stream
        with client.websocket_connect(
            f"{settings.API_V1_STR}/agent/chat/ws/{conversation_id}?token={token}"
        ) as ws:
            ws.receive_json()  # history
            ws.send_json({"type": "message", "content": content})
            ws.receive_json()  # text_chunk
            ws.receive_json()  # done


# ── POST /agent/conversations ────────────────────────────────


def test_create_conversation_returns_full_fields(
    client: TestClient, superuser_token_headers: dict
) -> None:
    """建会话返回 id/title/session_id/created_at/updated_at（前端侧边栏都用到）"""
    created = _create(client, superuser_token_headers)

    assert created["title"] == "新对话"
    assert isinstance(created["session_id"], str) and created["session_id"]
    assert created["created_at"] is not None
    assert created["updated_at"] is not None


def test_create_conversation_accepts_custom_title(
    client: TestClient, superuser_token_headers: dict
) -> None:
    """显式传 title 时按传入值落库，不回落默认值"""
    created = _create(client, superuser_token_headers, title="我的自定义标题")
    assert created["title"] == "我的自定义标题"


# ── GET /agent/conversations ─────────────────────────────────


def test_list_conversations_only_own(
    client: TestClient,
    superuser_token_headers: dict,
    normal_user_token_headers: dict,
) -> None:
    """多租户隔离：普通用户列表里看不到超级用户的会话"""
    mine = _create(client, superuser_token_headers, title="超级用户的会话")

    items = client.get(BASE, headers=normal_user_token_headers).json()
    assert isinstance(items, list)
    assert all(item["id"] != mine["id"] for item in items)


def test_list_conversations_ordered_by_updated_at_desc(
    client: TestClient, superuser_token_headers: dict
) -> None:
    """新消息会让会话「浮」到列表最前（侧边栏按最近活跃排序）"""
    first = _create(client, superuser_token_headers, title="先建的")
    second = _create(client, superuser_token_headers, title="后建的")

    ids = [item["id"] for item in client.get(BASE, headers=superuser_token_headers).json()]
    assert ids.index(second["id"]) < ids.index(first["id"]), "新建的应排在前面"

    # 在「先建的」里发一条消息 → updated_at 刷新 → 它应反超到最前
    _send_ws_message(client, superuser_token_headers, first["id"], "唤醒旧会话")
    ids = [item["id"] for item in client.get(BASE, headers=superuser_token_headers).json()]
    assert ids.index(first["id"]) < ids.index(second["id"]), "有消息的会话应排到前面"


def test_list_conversations_pagination(
    client: TestClient, superuser_token_headers: dict
) -> None:
    """skip/limit 分页：limit=1 只返回一条，skip=1 换一条"""
    _create(client, superuser_token_headers, title="分页-1")
    _create(client, superuser_token_headers, title="分页-2")

    page1 = client.get(
        BASE, headers=superuser_token_headers, params={"skip": 0, "limit": 1}
    ).json()
    page2 = client.get(
        BASE, headers=superuser_token_headers, params={"skip": 1, "limit": 1}
    ).json()

    assert len(page1) == 1 and len(page2) == 1
    assert page1[0]["id"] != page2[0]["id"]


# ── DELETE /agent/conversations/{id} ─────────────────────────


def test_delete_conversation_removes_it_and_messages(
    client: TestClient, superuser_token_headers: dict, db: Session
) -> None:
    """删除成功返回提示语；会话消失，会话内消息随之级联删除"""
    created = _create(client, superuser_token_headers, title="待删除")
    _send_ws_message(client, superuser_token_headers, created["id"], "留下一条消息")

    conv_id = uuid.UUID(created["id"])
    with Session(db.get_bind()) as s:
        assert s.exec(select(Message).where(Message.conversation_id == conv_id)).all()

    res = client.delete(f"{BASE}/{created['id']}", headers=superuser_token_headers)
    assert res.status_code == 200
    assert res.json() == {"message": "对话已删除"}

    ids = [item["id"] for item in client.get(BASE, headers=superuser_token_headers).json()]
    assert created["id"] not in ids

    with Session(db.get_bind()) as s:
        assert not s.exec(
            select(Message).where(Message.conversation_id == conv_id)
        ).all(), "级联删除失效：消息仍留在库里"


def test_delete_conversation_twice_404(
    client: TestClient, superuser_token_headers: dict
) -> None:
    """重复删除同一条 → 404"""
    created = _create(client, superuser_token_headers)
    assert (
        client.delete(f"{BASE}/{created['id']}", headers=superuser_token_headers).status_code
        == 200
    )

    res = client.delete(f"{BASE}/{created['id']}", headers=superuser_token_headers)
    assert res.status_code == 404


def test_delete_conversation_not_found_404(
    client: TestClient, superuser_token_headers: dict
) -> None:
    """删除不存在的会话 → 404"""
    res = client.delete(f"{BASE}/{uuid.uuid4()}", headers=superuser_token_headers)
    assert res.status_code == 404


def test_delete_other_users_conversation_404(
    client: TestClient,
    superuser_token_headers: dict,
    normal_user_token_headers: dict,
) -> None:
    """多租户隔离（IDOR 防护）：普通用户删别人的会话 → 404 且数据还在"""
    created = _create(client, superuser_token_headers, title="别人的会话")

    res = client.delete(f"{BASE}/{created['id']}", headers=normal_user_token_headers)
    assert res.status_code == 404

    ids = [item["id"] for item in client.get(BASE, headers=superuser_token_headers).json()]
    assert created["id"] in ids, "越权删除不应真的删掉数据"


# ── PATCH /agent/conversations/{id}（重命名） ────────────────


def test_rename_conversation_ok(
    client: TestClient, superuser_token_headers: dict
) -> None:
    """重命名成功：返回新标题，列表里同步可见"""
    created = _create(client, superuser_token_headers)

    res = client.patch(
        f"{BASE}/{created['id']}",
        headers=superuser_token_headers,
        json={"title": "新的名字"},
    )
    assert res.status_code == 200
    assert res.json()["title"] == "新的名字"

    items = client.get(BASE, headers=superuser_token_headers).json()
    assert next(i["title"] for i in items if i["id"] == created["id"]) == "新的名字"


def test_rename_conversation_not_found_404(
    client: TestClient, superuser_token_headers: dict
) -> None:
    """重命名不存在的会话 → 404"""
    res = client.patch(
        f"{BASE}/{uuid.uuid4()}",
        headers=superuser_token_headers,
        json={"title": "x"},
    )
    assert res.status_code == 404


def test_rename_other_users_conversation_404(
    client: TestClient,
    superuser_token_headers: dict,
    normal_user_token_headers: dict,
) -> None:
    """多租户隔离：普通用户不能重命名别人的会话"""
    created = _create(client, superuser_token_headers)

    res = client.patch(
        f"{BASE}/{created['id']}",
        headers=normal_user_token_headers,
        json={"title": "抢名字"},
    )
    assert res.status_code == 404

    items = client.get(BASE, headers=superuser_token_headers).json()
    assert next(i["title"] for i in items if i["id"] == created["id"]) != "抢名字"


@pytest.mark.parametrize("bad_title", ["", "   "])
def test_rename_conversation_rejects_blank_title(
    client: TestClient, superuser_token_headers: dict, bad_title: str
) -> None:
    """空标题 / 纯空白标题 → 422 校验失败"""
    created = _create(client, superuser_token_headers)

    res = client.patch(
        f"{BASE}/{created['id']}",
        headers=superuser_token_headers,
        json={"title": bad_title},
    )
    assert res.status_code == 422


def test_ws_first_message_sets_title(
    client: TestClient, superuser_token_headers: dict
) -> None:
    """标题仍是默认值时，用首条消息前 20 字覆盖，换行压成空格"""
    created = _create(client, superuser_token_headers)
    raw = "帮我  分析一下这个财务报表里的异常项\n顺便看看现金流"

    _send_ws_message(client, superuser_token_headers, created["id"], raw)

    items = client.get(BASE, headers=superuser_token_headers).json()
    title = next(i["title"] for i in items if i["id"] == created["id"])
    assert title == "帮我  分析一下这个财务报表里的异常项 "
    assert len(title) <= 20


def test_ws_second_message_keeps_title(
    client: TestClient, superuser_token_headers: dict
) -> None:
    """只有首条消息能定标题，后续消息不覆盖"""
    created = _create(client, superuser_token_headers)

    _send_ws_message(client, superuser_token_headers, created["id"], "第一句")
    _send_ws_message(client, superuser_token_headers, created["id"], "完全不同的第二句")

    items = client.get(BASE, headers=superuser_token_headers).json()
    assert next(i["title"] for i in items if i["id"] == created["id"]) == "第一句"


def test_ws_custom_title_not_overwritten(
    client: TestClient, superuser_token_headers: dict
) -> None:
    """用户自建会话时传了标题 → 首条消息不能把它冲掉"""
    created = _create(client, superuser_token_headers, title="我的自定义标题")

    _send_ws_message(client, superuser_token_headers, created["id"], "随便说点什么")

    items = client.get(BASE, headers=superuser_token_headers).json()
    assert next(i["title"] for i in items if i["id"] == created["id"]) == "我的自定义标题"


@pytest.mark.parametrize("blank", ["   ", "\n\n"])
def test_ws_blank_first_message_keeps_default_title(
    client: TestClient, superuser_token_headers: dict, blank: str
) -> None:
    """纯空白首条消息：剥掉空白后为空，标题保持「新对话」不被清空"""
    created = _create(client, superuser_token_headers)

    _send_ws_message(client, superuser_token_headers, created["id"], blank)

    items = client.get(BASE, headers=superuser_token_headers).json()
    assert next(i["title"] for i in items if i["id"] == created["id"]) == "新对话"