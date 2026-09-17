"""Unit tests for Agent platform data models (SQLModel)."""

import uuid

import pytest
from sqlmodel import SQLModel

from app.core.db.models import (
    ProviderConfig,
    Conversation,
    Message,
    KnowledgeBase,
    Document,
    MCPServer,
    Skill,
    Persona,
    AgentRun,
)


class TestMetadata:
    def test_all_tables_registered(self):
        """All 9 agent table names should be registered in SQLModel.metadata."""
        expected = {
            "provider_configs",
            "conversations",
            "messages",
            "knowledge_bases",
            "documents",
            "mcp_servers",
            "skills",
            "personas",
            "agent_runs",
        }
        actual = set(SQLModel.metadata.tables.keys())
        assert expected <= actual


class TestProviderConfig:
    def test_create_instance_explicit(self):
        obj = ProviderConfig(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            name="test-provider",
            provider_type="openai",
            api_key="sk-test",
            model_name="gpt-4o",
            is_active=True,
            is_default=False,
            fallback_order=1,
            config={"timeout": 30},
        )
        assert obj.name == "test-provider"
        assert obj.is_active is True
        assert obj.config == {"timeout": 30}

    def test_column_defaults_applied_in_python(self):
        """SQLModel 在 Python 侧应用默认值（SQLAlchemy 时代由 DB server_default 填充）。"""
        obj = ProviderConfig()
        assert obj.is_active is True
        assert obj.config == {}


class TestConversation:
    def test_create_instance(self):
        conv = Conversation(
            id=uuid.uuid4(),
            session_id="sess-123",
            user_id=uuid.uuid4(),
            title="Test Conversation",
        )
        assert conv.title == "Test Conversation"
        assert conv.session_id == "sess-123"

    def test_default_title(self):
        conv = Conversation()
        assert conv.title == "新对话"


class TestMessage:
    def test_create_instance(self):
        msg = Message(
            id=uuid.uuid4(),
            conversation_id=uuid.uuid4(),
            role="user",
            content={"text": "Hello"},
        )
        assert msg.role == "user"
        assert msg.content == {"text": "Hello"}

    def test_tool_message(self):
        msg = Message(
            role="tool",
            content={"result": "done"},
            tool_call_id="call_abc",
        )
        assert msg.role == "tool"
        assert msg.tool_call_id == "call_abc"


class TestKnowledgeBase:
    def test_create_instance(self):
        kb = KnowledgeBase(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            name="My KB",
            chunk_size=400,
            retrieval_mode="tool",
        )
        assert kb.name == "My KB"
        assert kb.chunk_size == 400
        assert kb.retrieval_mode == "tool"

    def test_defaults_are_python_level(self):
        kb = KnowledgeBase()
        assert kb.chunk_size == 500


class TestDocument:
    def test_create_instance(self):
        doc = Document(
            id=uuid.uuid4(),
            kb_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            filename="readme.pdf",
            file_path="/tmp/readme.pdf",
            file_type="pdf",
            status="done",
            chunks_count=10,
            file_size=1024,
        )
        assert doc.filename == "readme.pdf"
        assert doc.status == "done"


class TestMCPServer:
    def test_create_instance(self):
        server = MCPServer(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            name="test-server",
            transport_type="sse",
            url="http://localhost:8080",
            args=["--verbose"],
            env_vars={"KEY": "val"},
            tools=[{"name": "search"}],
        )
        assert server.name == "test-server"
        assert server.transport_type == "sse"
        assert server.args == ["--verbose"]

    def test_stdio_server(self):
        server = MCPServer(
            transport_type="stdio",
            command="python",
            args=["server.py"],
        )
        assert server.command == "python"


class TestSkill:
    def test_create_instance(self):
        skill = Skill(
            id=uuid.uuid4(),
            name="code-review",
            description="Review code changes",
            path="/skills/code-review",
            source_type="local",
            is_active=True,
        )
        assert skill.name == "code-review"
        assert skill.source_type == "local"


class TestPersona:
    def test_create_instance(self):
        persona = Persona(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            name="Assistant",
            prompt="You are a helpful assistant.",
            tools=["web_search"],
            is_active=True,
        )
        assert persona.name == "Assistant"
        assert persona.tools == ["web_search"]

    def test_default_tools(self):
        persona = Persona()
        assert persona.tools == []


class TestAgentRun:
    def test_create_instance(self):
        run = AgentRun(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            status="running",
            input_text="Hello",
            tool_calls_made=0,
            tokens_used=100,
        )
        assert run.status == "running"
        assert run.input_text == "Hello"
        assert run.tool_calls_made == 0

    def test_completed_run(self):
        run = AgentRun(
            status="completed",
            input_text="Search for X",
            output_text="Here is the result...",
            tool_calls_made=2,
            tokens_used=1500,
            duration_ms=3200,
        )
        assert run.status == "completed"
        assert run.duration_ms == 3200
