"""LangGraph Agent 图测试

验证状态图的节点执行、条件路由和循环逻辑。

"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.core.agent.graph import create_compiled_agent_graph
from app.core.agent.nodes import (
    call_tools_node,
    inject_knowledge_node,
    inject_skills_node,
    invoke_llm_node,
    should_continue,
)
from app.core.agent.state import AgentState
from app.core.config import settings
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI


@pytest.mark.asyncio
async def test_inject_knowledge_node_returns_empty():
    """inject_knowledge 目前是空实现，应返回空字典"""
    state: AgentState = {
        "messages": [HumanMessage(content="你好")],
        "tools": [],
        "llm": None,
        "knowledge_base": None,

        "max_steps": 15,
        "step_count": 0,
        "conversation_id": "test",
        "user_id": "test",
    }
    result = await inject_knowledge_node(state)
    assert result == {}


@pytest.mark.asyncio
async def test_inject_skills_node_no_skills(tmp_path, monkeypatch):
    """skills 目录为空时，inject_skills 返回空字典"""
    from app.core.skills.manager import SkillManager

    # 替换单例，指向空目录（避免受真实 skills/ 目录影响）
    monkeypatch.setattr(
        SkillManager, "_instance", SkillManager(skills_dir=str(tmp_path))
    )

    state: AgentState = {
        "messages": [HumanMessage(content="你好")],
        "tools": [],
        "llm": None,
        "knowledge_base": None,
        "max_steps": 15,
        "step_count": 0,
        "conversation_id": "test",
        "user_id": "test",
    }
    result = await inject_skills_node(state)
    assert result == {}


@pytest.mark.asyncio
async def test_inject_skills_node_with_skills(tmp_path, monkeypatch):
    """有 Skill 时，inject_skills 注入包含清单的 SystemMessage"""
    from app.core.skills.manager import SkillManager

    # 造一个测试 Skill
    d = tmp_path / "demo-skill"
    d.mkdir()
    (d / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: 演示技能\n---\n# 演示指令",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        SkillManager, "_instance", SkillManager(skills_dir=str(tmp_path))
    )

    state: AgentState = {
        "messages": [HumanMessage(content="你好")],
        "tools": [],
        "llm": None,
        "knowledge_base": None,
        "max_steps": 15,
        "step_count": 0,
        "conversation_id": "test",
        "user_id": "test",
    }
    result = await inject_skills_node(state)

    # 应注入 1 条 SystemMessage，包含技能清单
    assert len(result["messages"]) == 1
    assert isinstance(result["messages"][0], SystemMessage)
    assert "demo-skill" in result["messages"][0].content
    assert "演示技能" in result["messages"][0].content
    # 渐进式披露：清单不包含完整指令
    assert "演示指令" not in result["messages"][0].content


@pytest.mark.asyncio
async def test_invoke_llm_node_without_tools():
    """invoke_llm 在没有工具时，直接调用 LLM"""
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(
        return_value=AIMessage(content="你好！有什么可以帮助你的？")
    )
    state: AgentState = {
        "messages": [HumanMessage(content="你好")],
        "tools": [],
        "llm": mock_llm,
        "knowledge_base": None,

        "max_steps": 15,
        "step_count": 0,
        "conversation_id": "test",
        "user_id": "test",
    }

    result = await invoke_llm_node(state)

    assert len(result["messages"]) == 1
    assert result["messages"][0].content == "你好！有什么可以帮助你的？"
    mock_llm.ainvoke.assert_awaited_once()


def test_should_continue_with_tool_calls():
    """LLM 请求了工具调用，应返回 'tools'"""
    state: AgentState = {
        "messages": [
            HumanMessage(content="北京天气怎么样"),
            AIMessage(
                content="",
                tool_calls=[{"name": "get_weather", "args": {"city": "北京"}, "id": "call_1"}],
            ),
        ],
        "tools": [],
        "llm": None,
        "knowledge_base": None,

        "max_steps": 15,
        "step_count": 0,
        "conversation_id": "test",
        "user_id": "test",
    }
    assert should_continue(state) == "tools"


def test_should_continue_without_tool_calls():
    """LLM 没有请求工具调用 → 应返回 'end'"""
    state: AgentState = {
        "messages": [
            HumanMessage(content="你好"),
            AIMessage(content="你好！有什么可以帮助你的？"),
        ],
        "tools": [],
        "llm": None,
        "knowledge_base": None,

        "max_steps": 15,
        "step_count": 0,
        "conversation_id": "test",
        "user_id": "test",
    }
    assert should_continue(state) == "end"


def test_should_continue_max_steps_reached():
    """步数超过最大值 → 应强制返回 'end'"""
    state: AgentState = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[{"name": "some_tool", "args": {}, "id": "call_1"}],
            ),
        ],
        "tools": [],
        "llm": None,
        "knowledge_base": None,

        "max_steps": 5,
        "step_count": 5,
        "conversation_id": "test",
        "user_id": "test",
    }
    assert should_continue(state) == "end"


@pytest.mark.asyncio
async def test_call_tools_node():
    """call_tools_node 应正确执行工具并返回 ToolMessage"""
    mock_tool = MagicMock()
    mock_tool.name = "get_weather"

    with patch("app.core.agent.nodes.ToolExecutor") as MockExecutor:
        mock_executor = AsyncMock()
        mock_executor.execute = AsyncMock(return_value="晴转多云，32°C")
        MockExecutor.return_value = mock_executor

        state: AgentState = {
            "messages": [
                HumanMessage(content="北京天气怎么样"),
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "get_weather", "args": {"city": "北京"}, "id": "call_1"}
                    ],
                ),
            ],
            "tools": [mock_tool],
            "llm": None,
            "knowledge_base": None,

            "max_steps": 15,
            "step_count": 0,
            "conversation_id": "test",
            "user_id": "test",
        }
        result = await call_tools_node(state)

        assert len(result["messages"]) == 1
        assert isinstance(result["messages"][0], ToolMessage)
        assert result["messages"][0].content == "晴转多云，32°C"
        assert result["messages"][0].tool_call_id == "call_1"
        assert result["step_count"] == 1


@pytest.mark.asyncio
async def test_call_tools_node_tool_not_found():
    """工具不存在时，应返回错误信息"""
    state: AgentState = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "nonexistent_tool", "args": {}, "id": "call_1"}
                ],
            ),
        ],
        "tools": [],
        "llm": None,
        "knowledge_base": None,

        "max_steps": 15,
        "step_count": 0,
        "conversation_id": "test",
        "user_id": "test",
    }
    with patch("app.core.agent.nodes.ToolExecutor"):
        result = await call_tools_node(state)
        assert len(result["messages"]) == 1
        assert "不存在" in result["messages"][0].content

def has_openai_key():
    return bool(settings.OPENAI_API_KEY)

@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.skipif(
    not has_openai_key(),
    reason="需要 OPENAI_API_KEY 配置",
)
async def test_graph_real_api_no_tools():
    """真实API测试: LLM直接回答(不需要工具)
    验证 LangGraph 图能正确连接OpenAI 并获取回复。
    """
    llm = ChatOpenAI(
        model=settings.DEFAULT_LLM_MODEL,
        temperature=0,
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL or None,
    )

    graph = create_compiled_agent_graph()

    initial_state: AgentState = {
        "messages": [HumanMessage(content="1+1等于几？只回答数字")],
        "tools": [],
        "llm": llm,
        "knowledge_base": None,

        "max_steps": 5,
        "step_count": 0,
        "conversation_id": "test-integration",
        "user_id": "test-integration",
    }

    result = await graph.ainvoke(initial_state)

    assert "messages" in result
    assert len(result["messages"]) >= 2

    last_message = result["messages"][-1]
    assert isinstance(last_message, AIMessage)
    assert last_message.content
    print(f"\n✅ LLM 回复: {last_message.content}")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.skipif(
    not has_openai_key(),
    reason="需要 OPENAI_API_KEY 配置",
)
async def test_graph_real_api_with_tool():
    """真实 API 测试：LLM 调用工具后回答

    验证 LangGraph 的 ReAct 循环：
    LLM → 决定调用工具 → 执行工具 → LLM 总结回复
    """
    from langchain_core.tools import tool

    @tool
    def get_current_time() -> str:
        """获取当前时间"""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    llm = ChatOpenAI(
        model=settings.DEFAULT_LLM_MODEL,
        temperature=0,
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL or None,
    )

    graph = create_compiled_agent_graph()

    initial_state: AgentState = {
        "messages": [HumanMessage(content="现在几点了？")],
        "tools": [get_current_time],
        "llm": llm,
        "knowledge_base": None,

        "max_steps": 5,
        "step_count": 0,
        "conversation_id": "test-integration",
        "user_id": "test-integration",
    }

    result = await graph.ainvoke(initial_state)

    assert "messages" in result
    messages = result["messages"]
    assert len(messages) >= 3

    last_message = messages[-1]
    assert isinstance(last_message, AIMessage)
    assert last_message.content
    print(f"\n✅ LLM 最终回复: {last_message.content}")
    print(f"✅ 消息总数: {len(messages)}")
    for i, msg in enumerate(messages):
        content_preview = msg.content[:80] if msg.content else "(tool_calls)"
        print(f"  [{i}] {type(msg).__name__}: {content_preview}")
