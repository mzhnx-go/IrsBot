"""Agent WebSocket 真实 API 集成测试

真实依赖：OPENAI_API_KEY + OPENAI_BASE_URL（否则跳过）。
验证 WebSocket 端点全链路：WS 连接 → 鉴权 → Agent 流式 → 真实 LLM → 翻译转发。

与单元测试（test_agent_ws.py，mock 掉 Agent）不同，这里 patch 的是
ProviderManager.get_chat_model，让它返回真实 ChatOpenAI —— 这样既能绕过
"测试库没有默认 ProviderConfig" 的限制，又真正调用了 LLM API。

运行方式（在 backend 目录下）：
    python -m pytest ../tests -m "integration" -v -k ws
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from app.core.agent.graph import create_compiled_agent_graph
from app.core.agent.state import AgentState
from app.core.config import settings
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI


def has_openai_key() -> bool:
    return bool(settings.OPENAI_API_KEY)


def _real_llm() -> ChatOpenAI:
    """构造真实 LLM，供 ProviderManager.get_chat_model 返回。"""
    return ChatOpenAI(
        model=settings.DEFAULT_LLM_MODEL,
        temperature=0,
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL or None,
    )


@pytest.mark.integration
@pytest.mark.skipif(
    not has_openai_key(),
    reason="需要 OPENAI_API_KEY 配置",
)
def test_ws_real_api_streams_text_and_done(client, superuser_token_headers):
    """真实 API：WS 连接后应收到 text_chunk 与 done

    覆盖 WS 端点 → 鉴权 → Agent 流式 → 真实 LLM → 事件翻译 全链路。
    """
    token = superuser_token_headers["Authorization"].split(" ", 1)[1]

    # 方案 A：严格校验要求会话已存在且属于当前用户。
    # 先 POST /conversations 建会话拿 UUID，再连 WS（否则全新 UUID 会被拒绝）。
    resp = client.post(
        "/api/v1/agent/conversations",
        json={"title": "ws-instream-test"},
        headers=superuser_token_headers,
    )
    assert resp.status_code == 200, f"建会话失败: {resp.text}"
    conv_id = resp.json()["id"]

    with patch(
        "app.core.agent.provider.ProviderManager.get_chat_model",
        return_value=_real_llm(),
    ):
        with client.websocket_connect(
            f"/api/v1/agent/chat/ws/{conv_id}?token={token}",
        ) as ws:
            ws.send_json({"type": "message", "content": "你好，请只回复一个字：好"})

            received_text = False
            received_done = False
            # 防止假流式一直不发 done 导致死等，给一个合理上限
            for _ in range(200):
                msg = ws.receive_json()
                if msg["type"] == "text_chunk" and msg["content"]:
                    received_text = True
                elif msg["type"] == "done":
                    received_done = True
                    break

            assert received_text, "应至少收到一个非空 text_chunk"
            assert received_done, "Agent 流结束应收到 done"


@pytest.mark.integration
@pytest.mark.skipif(
    not has_openai_key(),
    reason="需要 OPENAI_API_KEY 配置",
)
@pytest.mark.asyncio
async def test_agent_stream_real_api(db):
    """真实 API：Agent.stream 直接产出流式事件

    不经过 WS，聚焦验证 Agent 层流式事件确实来自真实 LLM API。
    作为 WS 集成测试的补充，便于单独排查 Agent 层问题。
    """
    from app.core.agent.agent import Agent

    with patch(
        "app.core.agent.provider.ProviderManager.get_chat_model",
        return_value=_real_llm(),
    ):
        agent = Agent(session=db, conversation_id=str(uuid.uuid4()), user_id="integration")
        event_types = set()
        async for event in agent.stream("1+1等于几？只回答数字"):
            event_types.add(event.get("event", ""))

    # 真实流式至少应包含 LLM 流与图生命周期事件
    assert "on_chat_model_stream" in event_types
    assert "on_chain_start" in event_types


@pytest.mark.integration
@pytest.mark.skipif(
    not has_openai_key(),
    reason="需要 OPENAI_API_KEY 配置",
)
@pytest.mark.asyncio
async def test_graph_real_api_executes_tools():
    """真实 API：LLM 真实调用并执行工具（ReAct 循环）

    无任何 patch，LLM 与工具执行全部真实。
    验证 call_tools_node：LLM 决定调用 → 工具真实执行 → ToolMessage 注入。
    """
    @tool
    def get_current_time() -> str:
        """获取当前时间（无外部依赖的真实工具）"""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    graph = create_compiled_agent_graph()
    initial_state: AgentState = {
        "messages": [HumanMessage(content="现在几点了？请使用 get_current_time 工具回答")],
        "tools": [get_current_time],
        "llm": _real_llm(),
        "knowledge_base": None,
        "max_steps": 5,
        "step_count": 0,
        "conversation_id": "test-integration-tool",
        "user_id": "integration",
    }

    result = await graph.ainvoke(initial_state)

    messages = result["messages"]
    # 至少应存在一条 ToolMessage，证明工具被真实执行
    tool_msgs = [m for m in messages if isinstance(m, ToolMessage)]
    assert tool_msgs, "LLM 应触发工具调用并产生 ToolMessage"
    assert tool_msgs[-1].content  # 工具返回了真实结果

    # 调试用：打印整轮消息，查看 Agent 的真实回复。
    # content / tool_calls / additional_kwargs 三者兼顾：
    # 普通回复看 content，工具调用看 tool_calls，
    # 换 reasoning 模型（如 DeepSeek-R1）后思考内容会出现在 additional_kwargs。
    print("\n===== Agent 本轮消息 =====")
    for i, m in enumerate(messages):
        print(f"[{i}] {type(m).__name__}: {m.content or m.tool_calls or m.additional_kwargs}")
    print("===========================")


@pytest.mark.integration
@pytest.mark.skipif(
    not has_openai_key(),
    reason="需要 OPENAI_API_KEY 配置",
)
@pytest.mark.asyncio
async def test_graph_real_api_injects_skills():
    """真实 API：Skill 提示词被注入 SystemMessage

    patch 仅替换 SkillManager 的提示词来源（模拟"已注册技能"），
    验证 inject_skills_node 把技能清单作为 SystemMessage 注入图。
    """
    fake_skills_prompt = "[可用技能清单] web_search: 网页搜索; code_runner: 执行代码"

    graph = create_compiled_agent_graph()
    initial_state: AgentState = {
        "messages": [HumanMessage(content="1+1等于几？只回答数字")],
        "tools": [],
        "llm": _real_llm(),
        "knowledge_base": None,
        "max_steps": 5,
        "step_count": 0,
        "conversation_id": "test-integration-skill",
        "user_id": "integration",
    }

    with patch(
        "app.core.skills.manager.SkillManager.instance",
        return_value=MagicMock(build_skills_prompt=lambda: fake_skills_prompt),
    ):
        result = await graph.ainvoke(initial_state)

    sys_msgs = [
        m for m in result["messages"]
        if isinstance(m, SystemMessage) and fake_skills_prompt in m.content
    ]
    assert sys_msgs, "Skill 提示词应作为 SystemMessage 注入到对话中"


@pytest.mark.integration
@pytest.mark.skipif(
    not has_openai_key(),
    reason="需要 OPENAI_API_KEY 配置",
)
@pytest.mark.asyncio
async def test_graph_real_api_long_conversation():
    """真实 API：长对话中 Agent 记住上下文

    构造多轮历史消息 + 一个依赖上下文的提问，
    验证 Agent 在长对话里能正确引用之前的约定。
    同时打印整轮消息，便于观察真实回复。
    """
    graph = create_compiled_agent_graph()
    initial_state: AgentState = {
        "messages": [
            HumanMessage(content="我喜欢吃香蕉"),
            AIMessage(content="好的，记住了，你喜欢吃香蕉。"),
            HumanMessage(content="我还喜欢打篮球，运动前要吃一根香蕉补充能量。"),
            AIMessage(content="明白了，你喜欢打篮球，运动前会吃香蕉补充能量。"),
            HumanMessage(content="我喜欢的水果是什么？"),
        ],
        "tools": [],
        "llm": _real_llm(),
        "knowledge_base": None,
        "max_steps": 5,
        "step_count": 0,
        "conversation_id": "test-integration-long",
        "user_id": "integration",
    }

    result = await graph.ainvoke(initial_state)
    messages = result["messages"]

    # 最终 AI 回复应能追溯到"香蕉"（来自前几轮上下文，而非本轮提问）
    final_ai = [m for m in messages if isinstance(m, AIMessage)][-1]
    assert "香蕉" in final_ai.content, f"长对话应记住上下文，实际回复: {final_ai.content}"

    # 打印整轮消息，查看 Agent 在长对话中的完整表现
    print("\n===== 长对话整轮消息 =====")
    for i, m in enumerate(messages):
        print(f"[{i}] {type(m).__name__}: {m.content or m.tool_calls or m.additional_kwargs}")
    print("===========================")


@pytest.mark.integration
@pytest.mark.skipif(
    not has_openai_key(),
    reason="需要 OPENAI_API_KEY 配置",
)
def test_ws_real_api_persists_messages(client, superuser_token_headers, db):
    """真实 API：WS 对话后，上下文记忆链路应把消息落库

    覆盖本次 WS 记忆改造的闭环：路由把用户消息（user）和 AI 回复
    （assistant）都写入数据库。这是"刷新后恢复历史"的关键前提，
    也是防止将来重构 WS 时把持久化改丢的回归保险。

    注意：该会话初始为空，Agent 首轮没有可召回的历史，是单轮对话；
    但它验证了 -> add_message(user) -> stream -> add_message(assistant)
    这条完整落库链路真实生效。
    """
    from app.core.agent.conversation import ConversationManager

    token = superuser_token_headers["Authorization"].split(" ", 1)[1]

    # 方案 A：严格校验要求会话必须已存在且属于当前用户。
    # 前端流程是先 POST /conversations 建会话拿 UUID，再连 WS。
    # 这里模拟同样流程，否则全新 UUID 会被路由当作"无效会话"拒绝。
    resp = client.post(
        "/api/v1/agent/conversations",
        json={"title": "ws-integration-test"},
        headers=superuser_token_headers,
    )
    assert resp.status_code == 200, f"建会话失败: {resp.text}"
    conv_id = resp.json()["id"]

    with patch(
        "app.core.agent.provider.ProviderManager.get_chat_model",
        return_value=_real_llm(),
    ):
        with client.websocket_connect(
            f"/api/v1/agent/chat/ws/{conv_id}?token={token}",
        ) as ws:
            ws.send_json({"type": "message", "content": "你好，请只回复一个字：好"})

            received_done = False
            for _ in range(200):
                msg = ws.receive_json()
                if msg["type"] == "done":
                    received_done = True
                    break
            assert received_done, "对话应正常结束并收到 done"

    # 流结束后，从数据库反查该会话的消息，验证 user + assistant 都已落库
    mgr = ConversationManager(session=db)
    messages = mgr.get_messages(conv_id=uuid.UUID(conv_id))

    roles = [m.role for m in messages]
    print(f"\n===== WS 对话后落库的消息 role = {roles} =====")

    assert "user" in roles, f"用户消息未落库，实际 roles: {roles}"
    assert "assistant" in roles, f"AI 回复未落库，实际 roles: {roles}"
    # AI 回复里应包含真实回复内容（非空）
    assistant_msgs = [m for m in messages if m.role == "assistant"]
    assert assistant_msgs and assistant_msgs[-1].content.get("text"), "AI 回复内容不应为空"


@pytest.mark.integration
@pytest.mark.skipif(
    not has_openai_key(),
    reason="需要 OPENAI_API_KEY 配置",
)
def test_ws_real_api_reconnect_restores_history(client, superuser_token_headers, db):
    """真实 API：重连后收到 history 事件，能恢复历史消息

    完整覆盖 Task 10.4 前端剩余部分：
    1) 首轮 WS 对话写入 user + assistant 到库
    2) 断开重连
    3) 建连后路由推送 {"type": "history", "messages": [...]}
    4) history 里应包含上一轮的 user 消息，前端据此恢复气泡

    这是"刷新页面不丢历史"的前端配合契约，也是防重构回归保险。
    """
    from app.core.agent.conversation import ConversationManager

    token = superuser_token_headers["Authorization"].split(" ", 1)[1]

    resp = client.post(
        "/api/v1/agent/conversations",
        json={"title": "ws-history-restore-test"},
        headers=superuser_token_headers,
    )
    assert resp.status_code == 200, f"建会话失败: {resp.text}"
    conv_id = resp.json()["id"]

    with patch(
        "app.core.agent.provider.ProviderManager.get_chat_model",
        return_value=_real_llm(),
    ):
        # ── 第一段连接：发一轮消息，让 user + assistant 落库 ──
        with client.websocket_connect(
            f"/api/v1/agent/chat/ws/{conv_id}?token={token}",
        ) as ws:
            # 建连第一条是 history（空会话）
            hist0 = ws.receive_json()
            assert hist0["type"] == "history" and hist0["messages"] == []

            ws.send_json({"type": "message", "content": "请只回复两个字：你好啊"})

            done = False
            for _ in range(200):
                msg = ws.receive_json()
                if msg["type"] == "done":
                    done = True
                    break
            assert done, "第一轮应正常结束"

        # ── 第二段连接：重连后应收到 history 并含上一轮 user 消息 ──
        with client.websocket_connect(
            f"/api/v1/agent/chat/ws/{conv_id}?token={token}",
        ) as ws:
            hist = ws.receive_json()
            assert hist["type"] == "history", f"重连应推送 history，实际 {hist}"
            contents = [h["content"] for h in hist["messages"]]
            roles = [h["role"] for h in hist["messages"]]
            print(f"\n===== 重连收到的历史 messages = {hist['messages']} =====")
            assert any("你好啊" in c for c in contents), f"history 应含上一轮 user 消息，实际 {contents}"
            assert "user" in roles and "assistant" in roles, f"history 应含 user/assistant，实际 {roles}"

    # 兜底断言：库里确实落了 user + assistant（与 history 一致）
    mgr = ConversationManager(session=db)
    stored = mgr.get_messages(conv_id=uuid.UUID(conv_id))
    stored_roles = [m.role for m in stored]
    assert "user" in stored_roles and "assistant" in stored_roles, f"落库角色异常: {stored_roles}"
