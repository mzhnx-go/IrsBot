# 聊天 WebSocket 协议

| 项 | 值 |
|---|---|
| 版本 | 1.2 |
| 端点 | `ws://<host>/agent/chat/ws/{conversation_id}` |
| 后端实现 | `backend/app/api/routes/agent_ws.py` |
| 前端实现 | `frontend/src/hooks/useAgentChat.ts` |

数据格式为 JSON 文本帧，前端按下行事件的 `type` 字段分发处理。
鉴权走 URL 查询参数 `?token=<JWT>`（浏览器 WS API 不支持自定义请求头）。
心跳与错误事件尚未实现（计划：服务端 30s `ping`，错误 `{"type": "error", "message": "..."}`）。

## 上行（前端 → 后端）

```json
{ "type": "message", "content": "帮我写个冒泡排序" }
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `type` | string | 是 | 固定 `"message"` |
| `content` | string | 是 | 用户消息，最大 `MAX_USER_MESSAGE_LENGTH`（默认 4096） |

```json
{ "type": "interrupt" }
```

**interrupt** — 中断当前生成。后端 cancel 本轮任务、终止 LLM 流，
已生成的部分回复照常落库（`content.stopped = true`）并发 `done`（带 `interrupted: true`）。
若尚无 assistant 消息（还没产出任何内容），done 不带 `assistant_message_id`。
空闲时收到 interrupt 无副作用。

## 下行（后端 → 前端）

**history** — 会话历史（建连成功后后端立即推送一次，用于恢复已有对话）

```json
{
  "type": "history",
  "messages": [
    { "id": "uuid", "role": "user", "content": "你好" },
    { "id": "uuid", "role": "assistant", "content": "你好！",
      "tool_calls": [ { "name": "kb_search", "phase": "end", "input": "{...}", "output": "..." } ],
      "stopped": true }
  ]
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `messages` | array | 历史消息（仅含 user / assistant，按时间正序）；每条带数据库 `id`（消息级 REST 操作用），`assistant` 可能带 `tool_calls` 展示轨迹与 `stopped`（被中断的半成品）标记 |

**text_chunk** — AI 回复文字块（一条对话多条，按序追加渲染）

```json
{ "type": "text_chunk", "content": "你" }
```

**tool_call** — 工具调用（start/end 成对；前端按「同名最近一条未配对 start」合并为一行）

```json
{ "type": "tool_call", "name": "web_search", "phase": "start", "input": "{\"query\": \"北京天气\"}" }
{ "type": "tool_call", "name": "web_search", "phase": "end", "output": "晴，24℃" }
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `input` / `output` | string | 入参与结果的展示文本（JSON 序列化后截断至 4000 字符） |

**done** — 本轮结束，连接保持可继续发送

```json
{ "type": "done", "user_message_id": "uuid", "assistant_message_id": "uuid", "interrupted": true }
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `user_message_id` / `assistant_message_id` | string | 本轮两条落库消息的真实 ID；前端把本地乐观消息的 `dbId` 回填后才能删除/编辑重发/重新生成。拦截路径（限流/错误）的 done 不带 ID；中断时若没有任何产出则不带 `assistant_message_id` |
| `interrupted` | bool | 仅中断收尾时出现；前端给该条 assistant 消息打「已停止生成」标记 |

## 时序示例

```
前端 → {"type": "message", "content": "北京天气怎么样"}
后端 → {"type": "tool_call", "name": "get_weather", "phase": "start", "input": "..."}
后端 → {"type": "tool_call", "name": "get_weather", "phase": "end", "output": "..."}
后端 → {"type": "text_chunk", "content": "北京今天晴"}
后端 → {"type": "done", "user_message_id": "...", "assistant_message_id": "..."}
```

## 相关 REST（消息级操作）

- `GET  /api/v1/agent/conversations/{id}/messages` — 消息列表（含 id）
- `DELETE /api/v1/agent/conversations/{id}/messages/{message_id}` — 删除单条
- `POST /api/v1/agent/conversations/{id}/messages/truncate` — `{message_id, inclusive}`，编辑重发/重新生成的前置操作

## 变更记录

| 日期 | 变更 |
|---|---|
| 2026-09-13 | 初版：message / text_chunk / tool_call / done |
| 2026-09-15 | 新增 history 下行事件：建连后推送会话历史，前端据此恢复对话 |
| 2026-09-20 | 1.1：history 每条消息带真实 `id`；done 回传 `user_message_id`/`assistant_message_id`；tool_call 携带 `input`/`output`（截断 4000 字符）并随 assistant 消息落库（`content.tool_trace`） |
| 2026-09-20 | 1.2：新增上行 `interrupt`（中断当前生成，部分回复落库并带 `content.stopped`）；done 增加 `interrupted` 标记；history 条目透传 `stopped` |
