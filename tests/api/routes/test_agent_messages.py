"""消息级端点测试（Phase 15.1b 消息操作）。

覆盖：
- GET    /agent/conversations/{id}/messages            列表（时间正序、不含 system、content 拍平为文本）
- DELETE /agent/conversations/{id}/messages/{msg_id}   删除单条 / 不存在 404 / 跨会话 404
- POST   /agent/conversations/{id}/messages/truncate   截断（inclusive 两种口径）/ 锚点不存在 404

走真实路由 + 测试数据库；Agent 被整体 mock，不依赖外部 LLM，故不打 integration 标记。
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from app.core.config import settings
from fastapi.testclient import TestClient

BASE = f"{settings.API_V1_STR}/agent/conversations"
WS_BASE = f"{settings.API_V1_STR}/agent/chat/ws"


async def fake_stream(content, history=None, attachments=None):
    yield {
        "event": "on_chat_model_stream",
        "data": {"chunk": SimpleNamespace(content="回复:" + content)},
    }


def _roundtrip(client: TestClient, headers: dict, conv_id: str, content: str) -> dict:
    """WS 完整跑一轮，返回 done 事件（含两条落库消息的真实 ID）。"""
    token = headers["Authorization"].split(" ", 1)[1]
    with patch("app.api.routes.agent_ws.Agent") as mock_agent:
        mock_agent.return_value.stream = fake_stream
        with client.websocket_connect(f"{WS_BASE}/{conv_id}?token={token}") as ws:
            ws.receive_json()  # history
            ws.send_json({"type": "message", "content": content})
            ws.receive_json()  # text_chunk
            return ws.receive_json()  # done


def _new_conversation(client: TestClient, headers: dict) -> str:
    res = client.post(BASE, headers=headers, json={"title": "msg-test"})
    assert res.status_code == 200, res.text
    return res.json()["id"]


@pytest.fixture
def conv_with_two_rounds(client, superuser_token_headers):
    """两轮对话 → user/assistant/user/assistant 共 4 条消息"""
    conv_id = _new_conversation(client, superuser_token_headers)
    d1 = _roundtrip(client, superuser_token_headers, conv_id, "第一问")
    d2 = _roundtrip(client, superuser_token_headers, conv_id, "第二问")
    return conv_id, d1, d2


def test_list_messages_ordered_and_flattened(
    client, superuser_token_headers, conv_with_two_rounds
):
    conv_id, d1, _ = conv_with_two_rounds
    res = client.get(f"{BASE}/{conv_id}/messages", headers=superuser_token_headers)
    assert res.status_code == 200, res.text
    msgs = res.json()
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert msgs[0]["content"] == "第一问"
    assert msgs[1]["content"] == "回复:第一问"
    # ID 与 WS done 回传的一致（前端据此定位消息）
    assert msgs[0]["id"] == d1["user_message_id"]
    assert msgs[1]["id"] == d1["assistant_message_id"]


def test_list_messages_missing_conversation_404(
    client, superuser_token_headers
):
    import uuid

    res = client.get(
        f"{BASE}/{uuid.uuid4()}/messages", headers=superuser_token_headers
    )
    assert res.status_code == 404


def test_delete_single_message(client, superuser_token_headers, conv_with_two_rounds):
    conv_id, _, d2 = conv_with_two_rounds
    res = client.delete(
        f"{BASE}/{conv_id}/messages/{d2['assistant_message_id']}",
        headers=superuser_token_headers,
    )
    assert res.status_code == 200, res.text
    listing = client.get(
        f"{BASE}/{conv_id}/messages", headers=superuser_token_headers
    ).json()
    assert len(listing) == 3
    assert d2["assistant_message_id"] not in [m["id"] for m in listing]


def test_delete_message_wrong_conversation_404(
    client, superuser_token_headers, conv_with_two_rounds
):
    _, _, d2 = conv_with_two_rounds
    other = _new_conversation(client, superuser_token_headers)
    res = client.delete(
        f"{BASE}/{other}/messages/{d2['assistant_message_id']}",
        headers=superuser_token_headers,
    )
    assert res.status_code == 404


def test_truncate_inclusive_removes_anchor_and_tail(
    client, superuser_token_headers, conv_with_two_rounds
):
    conv_id, d1, _ = conv_with_two_rounds
    res = client.post(
        f"{BASE}/{conv_id}/messages/truncate",
        headers=superuser_token_headers,
        json={"message_id": d1["user_message_id"], "inclusive": True},
    )
    assert res.status_code == 200, res.text
    assert res.json()["deleted"] == 4
    listing = client.get(
        f"{BASE}/{conv_id}/messages", headers=superuser_token_headers
    ).json()
    assert listing == []


def test_truncate_exclusive_keeps_anchor(
    client, superuser_token_headers, conv_with_two_rounds
):
    conv_id, d1, _ = conv_with_two_rounds
    res = client.post(
        f"{BASE}/{conv_id}/messages/truncate",
        headers=superuser_token_headers,
        json={"message_id": d1["user_message_id"], "inclusive": False},
    )
    assert res.status_code == 200, res.text
    assert res.json()["deleted"] == 3
    listing = client.get(
        f"{BASE}/{conv_id}/messages", headers=superuser_token_headers
    ).json()
    assert [m["id"] for m in listing] == [d1["user_message_id"]]


def test_truncate_missing_anchor_404(
    client, superuser_token_headers, conv_with_two_rounds
):
    import uuid

    conv_id, _, _ = conv_with_two_rounds
    res = client.post(
        f"{BASE}/{conv_id}/messages/truncate",
        headers=superuser_token_headers,
        json={"message_id": str(uuid.uuid4()), "inclusive": True},
    )
    assert res.status_code == 404
