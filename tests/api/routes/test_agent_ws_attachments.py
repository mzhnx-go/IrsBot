"""WS 附件上行 + 落库 + history 回放测试（Phase 16 / S2）。

验证上行 `attachments: [{"id": ...}]` 全链路：
- 合法 att_id → 元数据由服务端从磁盘反推并随用户消息落库
- history 重连回放带 attachments（刷新后 chip/缩略图不丢）
- 非法/越权/超量 att_id → 以 text_chunk 说明原因 + done，且不落库
- 附件正文不参与上下文回放（get_context_messages 只取 text）

Agent 整体 mock，不依赖外部 LLM。
"""

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlmodel import Session

from app.core.agent.conversation import ConversationManager
from app.core.config import settings

CONV_BASE = f"{settings.API_V1_STR}/agent/conversations"
ATT_BASE = f"{settings.API_V1_STR}/agent/attachments"

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture(autouse=True)
def attach_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setattr(settings, "CHAT_ATTACHMENT_DIR", str(tmp_path))
    yield tmp_path


async def fake_stream(content, history=None):
    yield {
        "event": "on_chat_model_stream",
        "data": {"chunk": SimpleNamespace(content="收到")},
    }


def _token(headers: dict) -> str:
    return headers["Authorization"].split(" ", 1)[1]


def _create_conversation(client, headers: dict, title: str) -> str:
    res = client.post(CONV_BASE, headers=headers, json={"title": title})
    assert res.status_code == 200, res.text
    return res.json()["id"]


def _upload(client, headers: dict, conv_id: str, filename: str, payload: bytes):
    res = client.post(
        ATT_BASE,
        headers=headers,
        data={"conversation_id": conv_id},
        files={"file": (filename, payload, "application/octet-stream")},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _ws_url(conv_id: str, headers: dict) -> str:
    return f"{settings.API_V1_STR}/agent/chat/ws/{conv_id}?token={_token(headers)}"


def test_valid_attachment_is_persisted_and_replayed(
    client, superuser_token_headers, db: Session
):
    """合法附件：落库元数据由服务端反推；重连后 history 仍带它"""
    conv_id = _create_conversation(client, superuser_token_headers, "附件回放")
    uploaded = _upload(
        client, superuser_token_headers, conv_id, "财报.txt", "今年营收增长".encode()
    )

    with patch("app.api.routes.agent_ws.Agent") as mock_agent:
        mock_agent.return_value.stream = fake_stream
        with client.websocket_connect(_ws_url(conv_id, superuser_token_headers)) as ws:
            assert ws.receive_json()["messages"] == []
            ws.send_json(
                {
                    "type": "message",
                    "content": "看看这份文档",
                    "attachments": [{"id": uploaded["id"]}],
                }
            )
            assert ws.receive_json()["type"] == "text_chunk"
            assert ws.receive_json()["type"] == "done"

    # 落库：正文 + 服务端反推的元数据（文件名来自磁盘，不是客户端说了算）
    rows = ConversationManager(db).get_messages(
        __import__("uuid").UUID(conv_id)
    )
    user_row = next(r for r in rows if r.role == "user")
    assert user_row.content["text"] == "看看这份文档"
    atts = user_row.content["attachments"]
    assert len(atts) == 1
    assert atts[0]["id"] == uploaded["id"]
    assert atts[0]["filename"] == "财报.txt"
    assert atts[0]["kind"] == "document"
    assert atts[0]["size"] > 0

    # 重连：history 回放附件元数据
    with client.websocket_connect(_ws_url(conv_id, superuser_token_headers)) as ws:
        history = ws.receive_json()
    user_item = next(m for m in history["messages"] if m["role"] == "user")
    assert user_item["content"] == "看看这份文档"
    assert user_item["attachments"][0]["filename"] == "财报.txt"


def test_attachment_only_message_titles_from_filename(client, superuser_token_headers):
    """只发附件不打字时，会话标题退回用附件名，不会一直挂着「新对话」"""
    conv_id = _create_conversation(client, superuser_token_headers, "新对话")
    uploaded = _upload(
        client, superuser_token_headers, conv_id, "季度总结.txt", "季度总结".encode()
    )

    with patch("app.api.routes.agent_ws.Agent") as mock_agent:
        mock_agent.return_value.stream = fake_stream
        with client.websocket_connect(_ws_url(conv_id, superuser_token_headers)) as ws:
            ws.receive_json()
            ws.send_json({"type": "message", "attachments": [{"id": uploaded["id"]}]})
            ws.receive_json()
            ws.receive_json()

    listed = client.get(CONV_BASE, headers=superuser_token_headers).json()
    title = next(c["title"] for c in listed if c["id"] == conv_id)
    assert title == "季度总结.txt"


def test_unknown_attachment_id_is_rejected(client, superuser_token_headers):
    """不存在的 att_id：以 text_chunk 说明原因 + done，且不落用户消息"""
    conv_id = _create_conversation(client, superuser_token_headers, "非法附件")

    with patch("app.api.routes.agent_ws.Agent") as mock_agent:
        mock_agent.return_value.stream = fake_stream
        with client.websocket_connect(_ws_url(conv_id, superuser_token_headers)) as ws:
            assert ws.receive_json()["type"] == "history"
            ws.send_json(
                {
                    "type": "message",
                    "content": "你好",
                    "attachments": [{"id": "0" * 32}],
                }
            )
            first = ws.receive_json()
            assert first["type"] == "text_chunk"
            assert "附件" in first["content"]
            assert ws.receive_json()["type"] == "done"

    with client.websocket_connect(_ws_url(conv_id, superuser_token_headers)) as ws:
        history = ws.receive_json()
    assert history["messages"] == []


def test_other_users_attachment_is_rejected(
    client, superuser_token_headers, normal_user_token_headers
):
    """别人的 att_id 一律当作不存在（不外泄"这个 id 有效"）"""
    owner_conv = _create_conversation(client, superuser_token_headers, "我的会话")
    uploaded = _upload(
        client, superuser_token_headers, owner_conv, "a.txt", b"hello world"
    )
    intruder_conv = _create_conversation(
        client, normal_user_token_headers, "别人的会话"
    )

    with patch("app.api.routes.agent_ws.Agent") as mock_agent:
        mock_agent.return_value.stream = fake_stream
        with client.websocket_connect(
            _ws_url(intruder_conv, normal_user_token_headers)
        ) as ws:
            ws.receive_json()
            ws.send_json(
                {
                    "type": "message",
                    "content": "偷看一眼",
                    "attachments": [{"id": uploaded["id"]}],
                }
            )
            first = ws.receive_json()
            assert first["type"] == "text_chunk"
            assert "附件" in first["content"]


def test_too_many_attachments_rejected(client, superuser_token_headers):
    """超过单条上限直接拒绝，不做逐文件解析"""
    conv_id = _create_conversation(client, superuser_token_headers, "超量附件")
    over = [{"id": "0" * 32}] * 11

    with patch("app.api.routes.agent_ws.Agent") as mock_agent:
        mock_agent.return_value.stream = fake_stream
        with client.websocket_connect(_ws_url(conv_id, superuser_token_headers)) as ws:
            ws.receive_json()
            ws.send_json({"type": "message", "content": "看", "attachments": over})
            first = ws.receive_json()
            assert first["type"] == "text_chunk"
            assert "最多" in first["content"]


def test_document_text_not_replayed_into_context(
    client, superuser_token_headers, db: Session
):
    """上下文只取正文：附件正文（上万字）绝不回放进上下文"""
    import uuid

    conv_id = _create_conversation(client, superuser_token_headers, "上下文")
    body = "机密正文" * 500
    uploaded = _upload(
        client, superuser_token_headers, conv_id, "长文.txt", body.encode()
    )

    with patch("app.api.routes.agent_ws.Agent") as mock_agent:
        mock_agent.return_value.stream = fake_stream
        with client.websocket_connect(_ws_url(conv_id, superuser_token_headers)) as ws:
            ws.receive_json()
            ws.send_json(
                {
                    "type": "message",
                    "content": "摘要一下",
                    "attachments": [{"id": uploaded["id"]}],
                }
            )
            ws.receive_json()
            ws.receive_json()

    msgs = ConversationManager(db).get_context_messages(uuid.UUID(conv_id))
    joined = "".join(m.content if isinstance(m.content, str) else str(m.content) for m in msgs)
    assert "摘要一下" in joined
    assert "机密正文" not in joined
