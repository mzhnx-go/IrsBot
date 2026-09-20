"""Agent 聊天 WebSocket 路由

前端协议约定（上行 = 前端 → 后端，下行 = 后端 → 前端）：

上行：
    {"type": "message", "content": "用户消息"}

下行：
    {"type": "history", "messages": [{"id", "role", "content", "tool_calls"?}...]}
    {"type": "text_chunk", "content": "文字块"}
    {"type": "tool_call", "name": "工具名", "phase": "start" | "end"}
    {"type": "done", "user_message_id"?: "...", "assistant_message_id"?: "..."}

协议细节见 docs/protocols/chat-ws-protocol.md
"""
import json
from uuid import UUID

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.api.deps import SessionDep, get_current_user_ws
from app.core.agent.agent import Agent
from app.core.agent.conversation import ConversationManager
from app.core.db.sqlmodel_models import User
from app.core.pipeline import PipelineContext, run_entry_stages
from app.core.pipeline.base import EventKey

router = APIRouter()

# 新建会话时的默认标题。与 models.py 中 Conversation.title 的默认值保持一致：
# 标题还等于它，说明用户从没手动改过名，此时才允许被首条消息覆盖。
DEFAULT_CONVERSATION_TITLE = "新对话"

# 自动标题的最大长度（按字符截断，超出部分丢弃）
AUTO_TITLE_MAX_LEN = 20


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
    ID = "id"
    USER_MESSAGE_ID = "user_message_id"
    ASSISTANT_MESSAGE_ID = "assistant_message_id"
    INPUT = "input"
    OUTPUT = "output"


class WSToolPhase:
    """工具调用阶段."""

    START = "start"
    END = "end"


#: 工具入参/结果下发与落库的截断上限（字符）。
#: 工具输出可能是整个文件内容，不截断会把 WS 帧和 messages 表撑爆；
#: 折叠面板展示的是"发生了什么"，超长部分截断不影响理解。
TOOL_TRACE_MAX_CHARS = 4000


def _trace_text(value: object) -> str:
    """把工具入参/结果压成展示用字符串并截断。"""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            text = str(value)
    if len(text) > TOOL_TRACE_MAX_CHARS:
        return text[:TOOL_TRACE_MAX_CHARS] + "…（已截断）"
    return text


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
            WSMsgKey.ID: str(m.id),
            WSMsgKey.ROLE: m.role,
            WSMsgKey.CONTENT: text,
        }
        # assistant 若带工具调用轨迹，一并下发便于前端还原折叠面板。
        # 展示用轨迹存在 content.tool_trace（tool_calls 列留给 LangChain
        # 规范格式的真实调用，二者不能混用）；兼容直接写在列上的旧数据。
        if m.role == WSMessageRole.ASSISTANT:
            trace = content.get("tool_trace") if isinstance(content, dict) else None
            if trace:
                item[WSMsgKey.TOOL_CALLS] = trace
            elif m.tool_calls:
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
            WSMsgKey.INPUT: _trace_text(raw.get("data", {}).get("input")),
        }

    elif event_type == "on_tool_end":
        output = raw.get("data", {}).get("output")
        # ToolMessage 对象取 .content，普通返回值直接用
        content = getattr(output, "content", output)
        return {
            WSMsgKey.TYPE: WSMessageType.TOOL_CALL,
            WSMsgKey.NAME: raw["name"],
            WSMsgKey.PHASE: WSToolPhase.END,
            WSMsgKey.OUTPUT: _trace_text(content),
        }

    else:
        return None


def merge_tool_trace(trace: list[dict], event: dict) -> None:
    """把 tool_call 事件合并进落库用的轨迹列表。

    start 追加一条；end 回填到**同名最近一条未完成的 start**
    （连续/并行调用同一工具时按最近未配对的一条合并）。找不到就补一条 end。
    """
    if event[WSMsgKey.PHASE] == WSToolPhase.START:
        trace.append({
            WSMsgKey.NAME: event[WSMsgKey.NAME],
            WSMsgKey.PHASE: WSToolPhase.START,
            WSMsgKey.INPUT: event.get(WSMsgKey.INPUT, ""),
        })
        return
    for entry in reversed(trace):
        if (
            entry[WSMsgKey.NAME] == event[WSMsgKey.NAME]
            and entry[WSMsgKey.PHASE] == WSToolPhase.START
        ):
            entry[WSMsgKey.PHASE] = WSToolPhase.END
            entry[WSMsgKey.OUTPUT] = event.get(WSMsgKey.OUTPUT, "")
            return
    trace.append({
        WSMsgKey.NAME: event[WSMsgKey.NAME],
        WSMsgKey.PHASE: WSToolPhase.END,
        WSMsgKey.OUTPUT: event.get(WSMsgKey.OUTPUT, ""),
    })

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
                user_msg = conv_manager.add_message(
                    conv_id=conversation.id,
                    role=WSMessageRole.USER,
                    content=data[WSMsgKey.CONTENT],
                )
                # 首条消息自动成标题：让侧边栏不再是一堆「新对话」。
                # 两个条件缺一不可：
                #   1) 标题仍是默认值 —— 用户（或后续重命名功能）设过标题就不覆盖；
                #   2) 这是会话的第一条消息 —— add_message 刚写完，故 count == 1。
                if (
                    conversation.title == DEFAULT_CONVERSATION_TITLE
                    and conv_manager.count_messages(conversation.id) == 1
                ):
                    # 多行输入压成一行、去掉首尾空白，再截断到 20 字
                    title = (
                        str(data[WSMsgKey.CONTENT]).strip().replace("\n", " ")
                    )[:AUTO_TITLE_MAX_LEN]
                    if title:
                        # ORM 脏跟踪：改了属性，commit 即落库（updated_at 自动刷新）
                        conversation.title = title
                        session.commit()
                history = conv_manager.get_context_messages(conversation.id)

                # ── 前置 Stage（限流/会话开关/预处理）与 REST 共用同一实现 ──
                # WS 无法改 HTTP 状态码，命中拦截时以 text_chunk 说明原因
                # 再发 done，前端协议（history/text_chunk/tool_call/done）保持不变。
                context = await run_entry_stages(
                    PipelineContext(
                        user_id=current_user.id,
                        session_id=conversation_id,
                        conversation_id=conversation.id,
                        event_data={
                            EventKey.SESSION: session,
                            EventKey.CONVERSATION: conversation,
                            EventKey.USER_MESSAGE: data[WSMsgKey.CONTENT],
                            EventKey.HISTORY: history,
                        },
                    )
                )
                if context.event_data.get(EventKey.RATE_LIMITED):
                    await ws.send_json({
                        WSMsgKey.TYPE: WSMessageType.TEXT_CHUNK,
                        WSMsgKey.CONTENT: "请求过于频繁，请稍后再试。",
                    })
                    await ws.send_json({WSMsgKey.TYPE: WSMessageType.DONE})
                    continue
                if EventKey.ERROR in context.event_data:
                    await ws.send_json({
                        WSMsgKey.TYPE: WSMessageType.TEXT_CHUNK,
                        WSMsgKey.CONTENT: context.event_data[EventKey.ERROR],
                    })
                    await ws.send_json({WSMsgKey.TYPE: WSMessageType.DONE})
                    continue

                agent = Agent(
                    session=session,
                    conversation_id=conversation_id,
                    user_id=str(current_user.id),
                )
                reply = ""
                tool_trace: list[dict] = []


                async for event in agent.stream(
                    context.event_data[EventKey.USER_MESSAGE], history
                ):
                    msg = to_frontend_event(event)
                    if msg is not None:
                        await ws.send_json(msg)
                        if msg[WSMsgKey.TYPE] == WSMessageType.TEXT_CHUNK:
                            reply += msg[WSMsgKey.CONTENT]
                        elif msg[WSMsgKey.TYPE] == WSMessageType.TOOL_CALL:
                            merge_tool_trace(tool_trace, msg)

                # 工具轨迹存进 content.tool_trace：tool_calls 列会被
                # get_context_messages 转成 LangChain AIMessage.tool_calls，
                # 展示用轨迹格式不同，混写会污染发给模型的上下文
                assistant_msg = conv_manager.add_message(
                    conv_id=conversation.id,
                    role=WSMessageRole.ASSISTANT,
                    content=(
                        {"text": reply, "tool_trace": tool_trace}
                        if tool_trace
                        else reply
                    ),
                )
                # done 回传两条落库消息的真实 ID：
                # 前端消息操作（删除/编辑重发/重新生成）按 ID 调 REST，
                # 没有 ID 就只能整表重拉。
                await ws.send_json({
                    WSMsgKey.TYPE: WSMessageType.DONE,
                    WSMsgKey.USER_MESSAGE_ID: str(user_msg.id),
                    WSMsgKey.ASSISTANT_MESSAGE_ID: str(assistant_msg.id),
                })
    except WebSocketDisconnect:
        pass
