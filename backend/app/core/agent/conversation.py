"""会话管理器 —— 生命周期 + LangChain 消息集成。

负责 Conversation（会话）和 Message（消息）的持久化管理，
并把数据库中的消息与 LangChain 消息对象相互转换，
供 LangGraph Agent 使用。
"""

import json
import uuid
from typing import Any

from sqlmodel import Session, col, func, select

from app.core.db.models import Conversation, Message
from app.core.db.sqlmodel_models import get_datetime_utc


class ConversationManager:
    """管理 Conversation / Message 的增删改查以及 LangChain 集成。"""

    def __init__(self, session: Session):
        self.session = session

    # ── Conversation 增删改查 ────────────────────────────────────

    def create_conversation(
        self,
        *,
        session_id: str,
        user_id: uuid.UUID,
        title: str = "新对话",
        persona_id: uuid.UUID | None = None,
    ) -> Conversation:
        """创建一条新会话。

        参数:
            session_id: 前端生成的会话标识（字符串）。
            user_id: 所属用户的 ID。
            title: 会话标题，默认为「新对话」。
            persona_id: 关联的智能体（persona）ID，可空。

        返回:
            已写入数据库并刷新后的 Conversation 对象。
        """
        obj = Conversation(
            session_id=session_id,
            user_id=user_id,
            title=title,
            persona_id=persona_id,
        )
        self.session.add(obj)
        self.session.commit()
        self.session.refresh(obj)
        return obj

    def get_conversation(
        self, conv_id: uuid.UUID, user_id: uuid.UUID
    ) -> Conversation | None:
        """按 ID 和所属用户查询单个会话。

        参数:
            conv_id: 会话 ID。
            user_id: 所属用户的 ID（用于校验归属）。

        返回:
            匹配的 Conversation 对象；不存在时返回 None。
        """
        stmt = (
            select(Conversation)
            .where(
                Conversation.id == conv_id,
                Conversation.user_id == user_id,
            )
        )
        return self.session.exec(stmt).one_or_none()

    def list_conversations(
        self, user_id: uuid.UUID, skip: int = 0, limit: int = 20
    ) -> tuple[list[Conversation], int]:
        """分页列出某用户的会话，按更新时间倒序。

        参数:
            user_id: 所属用户的 ID。
            skip: 跳过的条数（分页偏移）。
            limit: 返回的最大条数。

        返回:
            元组 (会话列表, 总条数)。
        """
        cnt_stmt = (
            select(func.count())
            .select_from(Conversation)
            .where(Conversation.user_id == user_id)
        )
        total = self.session.exec(cnt_stmt).one()
        stmt = (
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(col(Conversation.updated_at).desc())
            .offset(skip)
            .limit(limit)
        )
        return list(self.session.exec(stmt).all()), total

    def delete_conversation(self, conv_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """删除指定会话（含归属校验）。

        参数:
            conv_id: 会话 ID。
            user_id: 所属用户的 ID。

        返回:
            删除成功返回 True；会话不存在返回 False。
        """
        obj = self.get_conversation(conv_id, user_id)
        if obj:
            self.session.delete(obj)
            self.session.commit()
            return True
        return False

    # ── Message 增删改查 ─────────────────────────────────────────

    def add_message(
        self,
        conv_id: uuid.UUID,
        role: str,
        content: Any,
        tool_calls: list[dict] | None = None,
        tool_call_id: str | None = None,
    ) -> Message:
        """向会话中持久化一条消息。

        参数:
            conv_id: 所属会话 ID。
            role: 消息角色（system / user / assistant / tool）。
            content: 消息内容；dict 原样保存，其余类型包装为 {"text": ...}。
            tool_calls: 工具调用列表（assistant 角色使用）。
            tool_call_id: 工具调用 ID（tool 角色使用，与请求一一对应）。

        返回:
            已写入数据库并刷新后的 Message 对象。

        副作用:
            刷新所属会话的 updated_at —— 会话列表按最近活跃倒序排列，
            不刷新的话聊了很多轮的会话会一直停在首次发言时的位置。
        """
        # 序列化内容为 JSON 安全的 dict
        if isinstance(content, dict):
            content_json = content
        else:
            content_json = {"text": str(content)}

        obj = Message(
            conversation_id=conv_id,
            role=role,
            content=content_json,
            tool_calls=tool_calls,
            tool_call_id=tool_call_id,
        )
        self.session.add(obj)

        # 显式赋一次值才会触发 UPDATE（行没变化时 SQLAlchemy 不会写库，
        # 列上的 onupdate 也就不会生效）
        conversation = self.session.get(Conversation, conv_id)
        if conversation:
            conversation.updated_at = get_datetime_utc()

        self.session.commit()
        self.session.refresh(obj)
        return obj

    def get_messages(
        self,
        conv_id: uuid.UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Message]:
        """按时间正序分页查询某会话的全部消息。

        参数:
            conv_id: 所属会话 ID。
            skip: 跳过的条数。
            limit: 返回的最大条数，默认为 50。

        返回:
            按创建时间升序排列的 Message 列表。
        """
        stmt = (
            select(Message)
            .where(Message.conversation_id == conv_id)
            .order_by(col(Message.created_at).asc())
            .offset(skip)
            .limit(limit)
        )
        return list(self.session.exec(stmt).all())

    def count_messages(self, conv_id: uuid.UUID) -> int:
        """统计某会话的消息总条数。

        参数:
            conv_id: 所属会话 ID。

        返回:
            消息数量（int）。
        """
        stmt = (
            select(func.count())
            .select_from(Message)
            .where(Message.conversation_id == conv_id)
        )
        return self.session.exec(stmt).one()

    # ── LangChain 集成 ───────────────────────────────────────────

    def get_langchain_messages(self, conv_id: uuid.UUID) -> list[Any]:
        """把数据库消息转换为 LangChain 消息对象。

        角色映射规则：
        - "system"    → SystemMessage
        - "user"      → HumanMessage
        - "assistant" → AIMessage
        - "tool"      → ToolMessage

        参数:
            conv_id: 所属会话 ID。

        返回:
            LangChain Message 对象列表（按创建时间升序）。
        """
        from langchain_core.messages import (
            AIMessage,
            HumanMessage,
            SystemMessage,
            ToolMessage,
        )

        role_map = {
            "system": SystemMessage,
            "user": HumanMessage,
            "assistant": AIMessage,
            "tool": ToolMessage,
        }

        stmt = (
            select(Message)
            .where(Message.conversation_id == conv_id)
            .order_by(col(Message.created_at).asc())
        )
        rows = self.session.exec(stmt).all()

        messages: list[Any] = []
        for row in rows:
            cls = role_map.get(row.role)
            if cls is None:
                continue

            content = row.content
            if isinstance(content, str):
                text = content
            elif isinstance(content, dict):
                text = content.get("text") or next(iter(content.values()), "") if content else ""
            else:
                text = json.dumps(content)

            if row.role == "tool" and row.tool_call_id:
                msg = cls(content=text, tool_call_id=row.tool_call_id)
            elif row.role == "assistant" and row.tool_calls:
                msg = cls(content=text, tool_calls=row.tool_calls)
            else:
                msg = cls(content=text)

            messages.append(msg)

        return messages

    def get_context_messages(
        self,
        conv_id: uuid.UUID,
        max_tokens: int = 120000,
        max_turns: int = 20,
    ) -> list[Any]:
        """获取最近的上下文消息，并受 token 数 / 轮数上限约束。

        返回最近 N 轮、且不超过 token 预算的 LangChain 消息对象。
        token 为粗略估算：约 4 个字符记作 1 个 token。
        System 消息始终包含；非 system 消息按时间倒序截取后反转回正序。

        参数:
            conv_id: 所属会话 ID。
            max_tokens: token 预算上限，默认为 120000。
            max_turns: 最多保留的轮数，默认为 20。

        返回:
            截断后的 LangChain Message 列表（时间正序）。
        """
        from langchain_core.messages import SystemMessage

        # 单独取出 system 消息（始终包含）
        stmt_system = (
            select(Message)
            .where(
                Message.conversation_id == conv_id,
                Message.role == "system",
            )
        )
        system_msgs = list(self.session.exec(stmt_system).all())

        # 取最近的若干条非 system 消息（最新在前）
        stmt_recent = (
            select(Message)
            .where(
                Message.conversation_id == conv_id,
                Message.role != "system",
            )
            .order_by(col(Message.created_at).desc())
            .limit(max_turns)
        )
        recent_rows = list(self.session.exec(stmt_recent).all())
        recent_rows.reverse()  # 反转回时间正序

        # 转换为 LangChain 消息并估算 token
        all_messages = self._messages_to_langchain(system_msgs + recent_rows)

        # 按 token 预算截断
        total_tokens = 0
        truncated: list[Any] = []
        for msg in all_messages:
            # 粗略的 token 估算
            if hasattr(msg, "content"):
                content_str = msg.content if isinstance(msg.content, str) else json.dumps(msg.content)
                est_tokens = max(1, len(content_str) // 4)
            else:
                est_tokens = 10

            if total_tokens + est_tokens > max_tokens and truncated:
                break

            total_tokens += est_tokens
            truncated.append(msg)

        return truncated

    def _messages_to_langchain(self, msgs: list[Message]) -> list[Any]:
        """把一批 Message 行转换为 LangChain 消息对象。

        参数:
            msgs: 数据库 Message 对象列表。

        返回:
            LangChain Message 列表（顺序与入参一致）。
        """
        from langchain_core.messages import (
            AIMessage,
            HumanMessage,
            SystemMessage,
            ToolMessage,
        )

        role_map = {
            "system": SystemMessage,
            "user": HumanMessage,
            "assistant": AIMessage,
            "tool": ToolMessage,
        }

        result = []
        for row in msgs:
            cls = role_map.get(row.role)
            if cls is None:
                continue

            content = row.content
            if isinstance(content, str):
                text = content
            elif isinstance(content, dict):
                text = content.get("text") or next(iter(content.values()), "") if content else ""
            else:
                text = json.dumps(content)

            if row.role == "tool" and row.tool_call_id:
                msg = cls(content=text, tool_call_id=row.tool_call_id)
            elif row.role == "assistant" and row.tool_calls:
                msg = cls(content=text, tool_calls=row.tool_calls)
            else:
                msg = cls(content=text)

            result.append(msg)

        return result
