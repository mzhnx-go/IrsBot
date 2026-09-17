"""Tests for ConversationManager."""

import uuid

import pytest
from sqlalchemy import event, text
from sqlmodel import Session

from app.core.agent.conversation import ConversationManager
from app.core.db.models import Conversation, Message
from app.core.db.engine import engine as db_engine


# Disable FK checks for tests that use synthetic user_ids not in the 'user' table.
@event.listens_for(db_engine, "begin")
def _disable_fk_on_begin(conn):
    conn.execute(text("SET session_replication_role = 'replica';"))


def _uid() -> uuid.UUID:
    return uuid.uuid4()


class TestConversationCRUD:
    def test_create(self, db: Session):
        mgr = ConversationManager(db)
        uid = _uid()
        conv = mgr.create_conversation(session_id="s1", user_id=uid, title="Hello")
        assert conv.title == "Hello"
        assert conv.user_id == uid
        assert conv.session_id == "s1"

    def test_get(self, db: Session):
        mgr = ConversationManager(db)
        uid = _uid()
        conv = mgr.create_conversation(session_id="s2", user_id=uid, title="GetMe")
        found = mgr.get_conversation(conv.id, uid)
        assert found is not None
        assert found.title == "GetMe"

    def test_list(self, db: Session):
        mgr = ConversationManager(db)
        uid = _uid()
        for i in range(5):
            mgr.create_conversation(session_id=f"s{i}", user_id=uid, title=f"C{i}")
        convs, total = mgr.list_conversations(uid)
        assert total == 5
        assert len(convs) == 5

    def test_delete(self, db: Session):
        mgr = ConversationManager(db)
        uid = _uid()
        conv = mgr.create_conversation(session_id="sd", user_id=uid)
        assert mgr.delete_conversation(conv.id, uid) is True
        assert mgr.get_conversation(conv.id, uid) is None

    def test_user_isolation(self, db: Session):
        mgr = ConversationManager(db)
        u1, u2 = _uid(), _uid()
        mgr.create_conversation(session_id="u1", user_id=u1, title="A")
        mgr.create_conversation(session_id="u2", user_id=u2, title="B")
        c1, _ = mgr.list_conversations(u1)
        c2, _ = mgr.list_conversations(u2)
        assert len(c1) == 1 and c1[0].title == "A"
        assert len(c2) == 1 and c2[0].title == "B"


class TestMessageCRUD:
    def test_add_message(self, db: Session):
        mgr = ConversationManager(db)
        uid = _uid()
        conv = mgr.create_conversation(session_id="sm", user_id=uid)
        msg = mgr.add_message(conv.id, "user", {"text": "Hi"})
        assert msg.role == "user"
        assert msg.content == {"text": "Hi"}

    def test_get_messages(self, db: Session):
        mgr = ConversationManager(db)
        uid = _uid()
        conv = mgr.create_conversation(session_id="gm", user_id=uid)
        mgr.add_message(conv.id, "user", {"text": "A"})
        mgr.add_message(conv.id, "assistant", {"text": "B"})
        msgs = mgr.get_messages(conv.id)
        assert len(msgs) == 2
        assert msgs[0].role == "user"
        assert msgs[1].role == "assistant"

    def test_count_messages(self, db: Session):
        mgr = ConversationManager(db)
        uid = _uid()
        conv = mgr.create_conversation(session_id="cm", user_id=uid)
        mgr.add_message(conv.id, "user", {"text": "x"})
        assert mgr.count_messages(conv.id) == 1

    def test_add_tool_message(self, db: Session):
        mgr = ConversationManager(db)
        uid = _uid()
        conv = mgr.create_conversation(session_id="tm", user_id=uid)
        msg = mgr.add_message(
            conv.id,
            "tool",
            {"result": "done"},
            tool_call_id="call_xyz",
        )
        assert msg.role == "tool"
        assert msg.tool_call_id == "call_xyz"


class TestLangChainIntegration:
    def test_get_langchain_messages_user_assistant(self, db: Session):
        from langchain_core.messages import HumanMessage, AIMessage

        mgr = ConversationManager(db)
        uid = _uid()
        conv = mgr.create_conversation(session_id="lc", user_id=uid)
        mgr.add_message(conv.id, "user", {"text": "Hello"})
        mgr.add_message(conv.id, "assistant", {"text": "Hi there"})

        msgs = mgr.get_langchain_messages(conv.id)
        assert len(msgs) == 2
        assert isinstance(msgs[0], HumanMessage)
        assert isinstance(msgs[1], AIMessage)
        assert msgs[0].content == "Hello"
        assert msgs[1].content == "Hi there"

    def test_get_langchain_messages_with_tool(self, db: Session):
        from langchain_core.messages import ToolMessage

        mgr = ConversationManager(db)
        uid = _uid()
        conv = mgr.create_conversation(session_id="lt", user_id=uid)
        mgr.add_message(
            conv.id,
            "tool",
            {"result": "search: found 3 results"},
            tool_call_id="call_123",
        )
        msgs = mgr.get_langchain_messages(conv.id)
        assert len(msgs) == 1
        assert isinstance(msgs[0], ToolMessage)
        assert msgs[0].content == "search: found 3 results"
        assert msgs[0].tool_call_id == "call_123"

    def test_get_langchain_messages_empty(self, db: Session):
        mgr = ConversationManager(db)
        uid = _uid()
        conv = mgr.create_conversation(session_id="le", user_id=uid)
        msgs = mgr.get_langchain_messages(conv.id)
        assert msgs == []

    def test_get_context_messages_basic(self, db: Session):
        mgr = ConversationManager(db)
        uid = _uid()
        conv = mgr.create_conversation(session_id="gc", user_id=uid)
        mgr.add_message(conv.id, "user", {"text": "Hello"})
        mgr.add_message(conv.id, "assistant", {"text": "Hi"})
        msgs = mgr.get_context_messages(conv.id, max_tokens=100000, max_turns=10)
        assert len(msgs) == 2

    def test_get_context_messages_respects_max_turns(self, db: Session):
        mgr = ConversationManager(db)
        uid = _uid()
        conv = mgr.create_conversation(session_id="gt", user_id=uid)
        for i in range(10):
            mgr.add_message(conv.id, "user", {"text": f"msg{i}"})
        msgs = mgr.get_context_messages(conv.id, max_tokens=100000, max_turns=3)
        assert len(msgs) <= 3

    def test_get_context_messages_respects_max_tokens(self, db: Session):
        mgr = ConversationManager(db)
        uid = _uid()
        conv = mgr.create_conversation(session_id="gk", user_id=uid)
        # Each message ~100 chars = ~25 tokens, 10 messages = ~250 tokens
        for i in range(10):
            mgr.add_message(conv.id, "user", {"text": "x" * 100})
        # Limit to ~50 tokens (~200 chars)
        msgs = mgr.get_context_messages(conv.id, max_tokens=50, max_turns=100)
        # Should have at most 2 messages (roughly)
        assert len(msgs) <= 3
