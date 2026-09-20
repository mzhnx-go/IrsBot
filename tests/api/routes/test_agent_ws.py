"""Agent WebSocket 聊天路由测试

验证 WS 聊天链路：收上行消息 → mock Agent 流式产出 → 翻译转发 → done 收尾。
不依赖真实 LLM 与数据库查询（Agent 被整体 mock）。

"""

from types import SimpleNamespace
from unittest.mock import patch


async def fake_slow_stream(content, history=None):
    """吐一个文字块后卡在长睡眠里，等着被 interrupt 取消。

    总时长有上限（600 × 50ms = 30s），即使取消逻辑失效测试也会结束，
    届时 done 不带 interrupted 标记 → 断言失败而不是永久挂死。
    """
    import asyncio

    yield {
        "event": "on_chat_model_stream",
        "data": {"chunk": SimpleNamespace(content="前半段")},
    }
    for _ in range(600):
        await asyncio.sleep(0.05)


async def fake_stream(content, history=None):
    """模拟 agent.stream：按编排吐出原始 LangGraph 事件

    与真实 Agent.stream(user_message, history) 签名一致，
    第一个事件是 LLM 文字块（应被翻译成 text_chunk），
    第二个是无关事件（应被 to_frontend_event 跳过）。
    """
    yield {
        "event": "on_chat_model_stream",
        "data": {"chunk": SimpleNamespace(content="你好")},
    }
    yield {"event": "on_chain_start", "data": {}}


async def fake_stream_with_tool(content, history=None):
    """模拟带工具调用的流：start 带 dict 入参，end 带 ToolMessage 式输出。"""
    yield {
        "event": "on_tool_start",
        "name": "kb_search",
        "data": {"input": {"query": "你好", "top_k": 3}},
    }
    yield {
        "event": "on_tool_end",
        "name": "kb_search",
        "data": {"output": SimpleNamespace(content="命中 2 条")},
    }
    yield {
        "event": "on_chat_model_stream",
        "data": {"chunk": SimpleNamespace(content="答案")},
    }


def test_chat_ws_streams_and_finishes(client, superuser_token_headers):
    """收上行消息后应依次收到 text_chunk 与 done，无关事件被跳过"""
    # WS 鉴权走 URL 查询参数（浏览器 WS API 不支持自定义请求头）
    token = superuser_token_headers["Authorization"].split(" ", 1)[1]

    # 方案 A：严格校验要求会话已存在且属于当前用户。
    # 先按前端流程 POST /conversations 建会话拿真实 UUID，再连 WS。
    resp = client.post(
        "/api/v1/agent/conversations",
        json={"title": "ws-unit-test"},
        headers=superuser_token_headers,
    )
    assert resp.status_code == 200, f"建会话失败: {resp.text}"
    conv_id = resp.json()["id"]

    # patch 导入处：agent_ws.py 里 `from app.core.agent.agent import Agent`
    with patch("app.api.routes.agent_ws.Agent") as mock_agent:
        # 把 mock 实例的 stream 换成假流（路由里 agent.stream(content) 调到的就是它）
        mock_agent.return_value.stream = fake_stream

        with client.websocket_connect(
            f"/api/v1/agent/chat/ws/{conv_id}?token={token}",
        ) as ws:
            # 建连成功后后端先推送 history 事件（此时会话无历史，为空数组）
            first = ws.receive_json()
            assert first == {"type": "history", "messages": []}

            ws.send_json({"type": "message", "content": "hi"})

            # 用户消息后，stream 产出的第一条就是翻译后的文字块
            second = ws.receive_json()
            assert second == {"type": "text_chunk", "content": "你好"}

            # Agent 流结束，路由补发 done（携带两条落库消息的真实 ID）
            third = ws.receive_json()
            assert third["type"] == "done"
            assert third["user_message_id"]
            assert third["assistant_message_id"]


def test_chat_ws_tool_events_carry_io_and_persist(
    client, superuser_token_headers
):
    """工具事件应带截断后的入参/结果下发；重连后 history 能还原工具轨迹"""
    token = superuser_token_headers["Authorization"].split(" ", 1)[1]
    resp = client.post(
        "/api/v1/agent/conversations",
        json={"title": "ws-tool-test"},
        headers=superuser_token_headers,
    )
    conv_id = resp.json()["id"]

    with patch("app.api.routes.agent_ws.Agent") as mock_agent:
        mock_agent.return_value.stream = fake_stream_with_tool
        with client.websocket_connect(
            f"/api/v1/agent/chat/ws/{conv_id}?token={token}",
        ) as ws:
            ws.receive_json()  # history（空）
            ws.send_json({"type": "message", "content": "hi"})

            start = ws.receive_json()
            assert start["type"] == "tool_call" and start["phase"] == "start"
            assert "kb_search" == start["name"]
            assert '"query"' in start["input"]  # dict 入参序列化为 JSON 文本

            end = ws.receive_json()
            assert end["type"] == "tool_call" and end["phase"] == "end"
            assert end["output"] == "命中 2 条"  # ToolMessage 取 .content

            ws.receive_json()  # text_chunk
            ws.receive_json()  # done

    # 重连：工具轨迹应从 content.tool_trace 还原
    with client.websocket_connect(
        f"/api/v1/agent/chat/ws/{conv_id}?token={token}",
    ) as ws:
        history = ws.receive_json()
        assistant = [m for m in history["messages"] if m["role"] == "assistant"][0]
        trace = assistant["tool_calls"]
        assert len(trace) == 1  # start/end 合并为一条
        assert trace[0]["name"] == "kb_search"
        assert trace[0]["phase"] == "end"
        assert trace[0]["output"] == "命中 2 条"


def test_chat_ws_interrupt_stops_and_persists_partial(
    client, superuser_token_headers
):
    """interrupt 应取消生成长流、落库已生成部分并回带 interrupted 标记的 done"""
    token = superuser_token_headers["Authorization"].split(" ", 1)[1]
    resp = client.post(
        "/api/v1/agent/conversations",
        json={"title": "ws-interrupt-test"},
        headers=superuser_token_headers,
    )
    conv_id = resp.json()["id"]

    import time

    with patch("app.api.routes.agent_ws.Agent") as mock_agent:
        mock_agent.return_value.stream = fake_slow_stream
        with client.websocket_connect(
            f"/api/v1/agent/chat/ws/{conv_id}?token={token}",
        ) as ws:
            ws.receive_json()  # history（空）
            ws.send_json({"type": "message", "content": "讲个超长的故事"})

            chunk = ws.receive_json()
            assert chunk == {"type": "text_chunk", "content": "前半段"}

            # 流还卡在后面（fake_slow_stream 会睡 30s），此时发中断
            t0 = time.monotonic()
            ws.send_json({"type": "interrupt"})

            done = ws.receive_json()
            assert done["type"] == "done"
            assert done.get("interrupted") is True
            assert done["user_message_id"]
            assert done["assistant_message_id"]
            # 中断应近乎立即生效，而不是等满 30s 自然结束
            assert time.monotonic() - t0 < 5.0

    # 重连：被中断的部分回复应带 stopped 标记还原
    with client.websocket_connect(
        f"/api/v1/agent/chat/ws/{conv_id}?token={token}",
    ) as ws:
        history = ws.receive_json()
        assistant = [m for m in history["messages"] if m["role"] == "assistant"][0]
        assert assistant["content"] == "前半段"
        assert assistant.get("stopped") is True


async def fake_failing_stream(content, history=None):
    """吐一个文字块后抛异常，模拟 LLM 中途失败"""
    yield {
        "event": "on_chat_model_stream",
        "data": {"chunk": SimpleNamespace(content="开头")},
    }
    raise RuntimeError("upstream 502")


def test_chat_ws_generation_error_sends_chinese_error_and_partial_persisted(
    client, superuser_token_headers
):
    """生成中途异常：下发中文 error + done；已生成部分照常落库"""
    token = superuser_token_headers["Authorization"].split(" ", 1)[1]
    resp = client.post(
        "/api/v1/agent/conversations",
        json={"title": "ws-error-test"},
        headers=superuser_token_headers,
    )
    conv_id = resp.json()["id"]

    with patch("app.api.routes.agent_ws.Agent") as mock_agent:
        mock_agent.return_value.stream = fake_failing_stream
        with client.websocket_connect(
            f"/api/v1/agent/chat/ws/{conv_id}?token={token}",
        ) as ws:
            ws.receive_json()  # history（空）
            ws.send_json({"type": "message", "content": "hi"})

            chunk = ws.receive_json()
            assert chunk["type"] == "text_chunk"

            err = ws.receive_json()
            assert err["type"] == "error"
            assert "生成失败" in err["message"]  # 中文提示
            assert "502" not in err["message"]  # 原始异常不外泄

            done = ws.receive_json()
            assert done["type"] == "done"
            assert done["assistant_message_id"]

    # 重连：部分回复应从落库历史还原
    with client.websocket_connect(
        f"/api/v1/agent/chat/ws/{conv_id}?token={token}",
    ) as ws:
        history = ws.receive_json()
        assistant = [m for m in history["messages"] if m["role"] == "assistant"][0]
        assert assistant["content"] == "开头"
