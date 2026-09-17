# 聊天 WebSocket 协议

| 项 | 值 |
|---|---|
| 版本 | 1.0 |
| 端点 | `ws://<host>/agent/chat/ws/{conversation_id}` |
| 后端实现 | `backend/app/api/routes/agent_ws.py` |
| 前端实现 | Phase 10.2 `useAgentChat`（待实现） |

数据格式为 JSON 文本帧，前端按下行事件的 `type` 字段分发处理。
心跳与错误事件尚未实现（计划：服务端 30s `ping`，错误 `{"type": "error", "message": "..."}`）。

## 上行（前端 → 后端）

```json
{ "type": "message", "content": "帮我写个冒泡排序" }
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `type` | string | 是 | 固定 `"message"` |
| `content` | string | 是 | 用户消息，最大 `MAX_USER_MESSAGE_LENGTH`（默认 4096） |

## 下行（后端 → 前端）

**history** — 会话历史（建连成功后后端立即推送一次，用于恢复已有对话）

```json
{
  "type": "history",
  "messages": [
    { "role": "user", "content": "你好" },
    { "role": "assistant", "content": "你好！", "tool_calls": null }
  ]
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `messages` | array | 历史消息（仅含 user / assistant，按时间正序）；`assistant` 可能带 `tool_calls` |

**text_chunk** — AI 回复文字块（一条对话多条，按序追加渲染）

```json
{ "type": "text_chunk", "content": "你" }
```

**tool_call** — 工具调用状态（start/end 成对）

```json
{ "type": "tool_call", "name": "web_search", "phase": "start" }
{ "type": "tool_call", "name": "web_search", "phase": "end" }
```

**done** — 本轮结束，连接保持可继续发送

```json
{ "type": "done" }
```

## 时序示例

```
前端 → {"type": "message", "content": "北京天气怎么样"}
后端 → {"type": "tool_call", "name": "get_weather", "phase": "start"}
后端 → {"type": "tool_call", "name": "get_weather", "phase": "end"}
后端 → {"type": "text_chunk", "content": "北京今天晴"}
后端 → {"type": "done"}
```

## 变更记录

| 日期 | 变更 |
|---|---|
| 2026-09-13 | 初版：message / text_chunk / tool_call / done |
| 2026-09-15 | 新增 history 下行事件：建连后推送会话历史，前端据此恢复对话 |
