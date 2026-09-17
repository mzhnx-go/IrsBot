"""Agent 聊天 WebSocket 路由

前端协议约定（上行 = 前端 → 后端，下行 = 后端 → 前端）：

上行：
    {"type": "message", "content": "用户消息"}

下行：
    {"type": "history", "messages": [...]}
    {"type": "text_chunk", "content": "文字块"}
    {"type": "tool_call", "name": "工具名", "phase": "start" | "end"}
    {"type": "done"}

协议细节见 docs/protocols/chat-ws-protocol.md
"""
from uuid import UUID

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.api.deps import SessionDep, get_current_user_ws
from app.core.agent.agent import Agent
from app.core.db.sqlmodel_models import User
from app.core.agent.conversation import ConversationManager

router = APIRouter()


class WSMessageType:
    """WebSocket 协议消息类型（上行 = 前端 → 后端，下行 = 后端 → 前端）.

    与 docs/protocols/chat-ws-protocol.md 保持一致，避免魔法字符串。
    """

    # 上行：前端 → 后端
    USER_MESSAGE = "message"

    # 下行：后端 → 前端
    HISTORY = "history"
    TEXT_CHUNK = "text_chunk"
    TOOL_CALL = "tool_call"
    DONE = "done"


class WSMessageRole:
    """消息角色（数据库 Message.role）."""

    USER = "user"
    ASSISTANT = "assistant"


class WSMsgKey:
    """消息体里的固定键名."""

    TYPE = "type"
    CONTENT = "content"
    NAME = "name"
    PHASE = "phase"
    MESSAGES = "messages"
    ROLE = "role"
    TOOL_CALLS = "tool_calls"


class WSToolPhase:
    """工具调用阶段."""

    START = "start"
    END = "end"


def build_history_payload(msgs) -> dict:
    """把数据库 Message 行压缩成前端 history 事件。

    只保留前端可渲染的 user / assistant 消息及其文本；
    system / tool 消息不展示，跳过。
    """
    items = []
    for m in msgs:
        if m.role not in (WSMessageRole.USER, WSMessageRole.ASSISTANT):
            continue
        content = m.content
        if isinstance(content, dict):
            text = content.get("text") or ""
        else:
            text = str(content)
        item = {
            WSMsgKey.ROLE: m.role,
            WSMsgKey.CONTENT: text,
        }
        # assistant 若带工具调用元数据，一并下发便于前端还原
        if m.role == WSMessageRole.ASSISTANT and m.tool_calls:
            item[WSMsgKey.TOOL_CALLS] = m.tool_calls
        items.append(item)
    return {
        WSMsgKey.TYPE: WSMessageType.HISTORY,
        WSMsgKey.MESSAGES: items,
    }


def to_frontend_event(raw: dict) -> dict | None:
    """把 LangGraph 原始事件翻译成前端协议

    返回 None 表示该事件不需要转发给前端。
    """
    event_type = raw.get("event", "")

    if event_type == "on_chat_model_stream":
        chunk = raw["data"]["chunk"].content
        if not chunk:
            return None
        return {WSMsgKey.TYPE: WSMessageType.TEXT_CHUNK, WSMsgKey.CONTENT: chunk}

    elif event_type == "on_tool_start":
        return {
            WSMsgKey.TYPE: WSMessageType.TOOL_CALL,
            WSMsgKey.NAME: raw["name"],
            WSMsgKey.PHASE: WSToolPhase.START,
        }

    elif event_type == "on_tool_end":
        return {
            WSMsgKey.TYPE: WSMessageType.TOOL_CALL,
            WSMsgKey.NAME: raw["name"],
            WSMsgKey.PHASE: WSToolPhase.END,
        }

    else:
        return None

@router.websocket("/agent/chat/ws/{conversation_id}")
async def chat_ws(
    ws: WebSocket,
    conversation_id: str,
    session: SessionDep,
    current_user: User = Depends(get_current_user_ws),
):

    await ws.accept()
   

    conv_manager = ConversationManager(session)
    conversation = conv_manager.get_conversation(UUID(conversation_id), current_user.id)
    if not conversation:
        await ws.close(code=4404)
        return

    # 建连后先推送当前会话历史，前端据此恢复已有对话（刷新不丢消息）
    history_rows = conv_manager.get_messages(conversation.id)
    await ws.send_json(build_history_payload(history_rows))

    try:
        while True:
            data = await ws.receive_json()
            if data[WSMsgKey.TYPE] == WSMessageType.USER_MESSAGE:
                conv_manager.add_message(
                    conv_id=conversation.id,
                    role=WSMessageRole.USER,
                    content=data[WSMsgKey.CONTENT],
                )
                history = conv_manager.get_context_messages(conversation.id)

                agent = Agent(
                    session=session,
                    conversation_id=conversation_id,
                    user_id=str(current_user.id),
                )
                reply = ""


                async for event in agent.stream(data[WSMsgKey.CONTENT], history):
                    msg = to_frontend_event(event)
                    if msg is not None:
                        await ws.send_json(msg)
                        if msg[WSMsgKey.TYPE] == WSMessageType.TEXT_CHUNK:
                            reply += msg[WSMsgKey.CONTENT]

                conv_manager.add_message(
                    conv_id=conversation.id,
                    role=WSMessageRole.ASSISTANT,
                    content=reply,
                )
                await ws.send_json({WSMsgKey.TYPE: WSMessageType.DONE})
    except WebSocketDisconnect:
        pass
