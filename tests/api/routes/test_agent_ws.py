"""Agent WebSocket 聊天路由测试

验证 WS 聊天链路：收上行消息 → mock Agent 流式产出 → 翻译转发 → done 收尾。
不依赖真实 LLM 与数据库查询（Agent 被整体 mock）。

"""

from types import SimpleNamespace
from unittest.mock import patch


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
