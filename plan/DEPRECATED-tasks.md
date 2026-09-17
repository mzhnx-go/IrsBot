> ⚠️ **本文件已弃用（2026-09-17）**：任务分解基于「IM 机器人框架」旧定位，勾选状态也早已失真。当前任务与阶段以 [istbot-implement-plan.md](./istbot-implement-plan.md)（第四节 SC 清单）和 [PROGRESS.md](./PROGRESS.md) 为准。仅作历史参考保留。

# Tasks - IrsBot IM 机器人框架 Implementation

> 技术栈: LangChain + LangGraph, uv, SQLAlchemy 2.0, Alembic, FastAPI, React 19
>
> **项目定位**：面向本地用户的自托管 IM 机器人框架；Web 仅为控制台。
> **进度与完整计划见 [istbot-implement-plan.md](./istbot-implement-plan.md)**（本文件为任务拆解视图；Phase 11 起的任务以该文档第八节为准）

---

## Phase 1: 项目基础架构搭建

- [ ] **Task 1.0: 环境准备**
  - [ ] 安装 `uv`: `curl -LsSf https://astral.sh/uv/install.sh | sh`
  - [ ] `cd backend && uv sync --extra all` 安装所有依赖
  - [ ] `docker compose -f compose.yml -f compose.override.yml up -d` 启动 Milvus 基础设施
  - [ ] 验证 Milvus 健康检查通过 (etcd + MinIO + Milvus)
  - [ ] `alembic upgrade head` 对现有 SQLModel 模型无报错

- [ ] **Task 1.1: uv 依赖与配置初始化**
  - [ ] 更新 `backend/pyproject.toml` — 添加 `[project.optional-dependencies]` (langchain, rag, mcp, all)
  - [ ] 使用 `uv sync` 安装依赖，生成 `uv.lock`
  - [ ] 在 `core/config.py` 的 Settings 中添加 Agent 配置项 (API Keys, 开关, 阈值)
  - [ ] 创建 `.env.example`
  - [ ] 编写 `tests/core/test_config.py`
  - [ ] `uv run pytest tests/core/test_config.py` 通过
  - [ ] `uv run python -c "from app.core.config import settings"` 不报错

- [ ] **Task 1.2: Agent 数据模型 (SQLAlchemy 2.0)**
  - [ ] 创建 `backend/app/core/db_agents.py`
  - [ ] 实现 ProviderConfig 模型 (SQLAlchemy 2.0 Mapped 风格)
  - [ ] 实现 Conversation 模型 + Message 模型 (JSON 列存多态消息)
  - [ ] 实现 KnowledgeBase 模型 + Document 模型
  - [ ] 实现 MCPServer 模型
  - [ ] 实现 Skill 模型
  - [ ] 实现 Persona 模型
  - [ ] 实现 AgentRun 模型 (追踪)
  - [ ] 编写 `tests/core/db/test_models.py`
  - [ ] 更新 `alembic/env.py` — 导入 `AgentBase`，设置 `target_metadata = [SQLModel.metadata, AgentBase.metadata]`
  - [ ] `alembic revision --autogenerate -m "add_agent_platform_tables"`
  - [ ] `alembic upgrade head` 执行成功
  - [ ] 验证所有新表在 PostgreSQL 中正确创建

- [ ] **Task 1.3: Agent CRUD 层**
  - [ ] 创建 `backend/app/crud_agent.py` (复用现有 crud.py 模式)
  - [ ] 每个模型: create/get/get_multi/update/delete
  - [ ] 支持分页 + user_id 过滤 (数据归属校验)
  - [ ] 编写 `tests/core/db/test_crud_agent.py`
  - [ ] 每个模型至少 4 个 CRUD 测试用例

---

## Phase 2: 对话管理系统

- [ ] **Task 2.1: 对话管理器**
  - [ ] 创建 `backend/app/core/conversation/manager.py`
  - [ ] 实现 CRUD: create/get/list/delete conversation
  - [ ] 实现 add_message() — 持久化到 DB
  - [ ] 实现 get_langchain_messages() — DB JSON → LangChain Message 对象
  - [ ] 实现 get_context_messages() — 按 token 限制取最近消息
  - [ ] 编写 `tests/conversation/test_manager.py`
  - [ ] 验证: HumanMessage/AIMessage/ToolMessage 正确转换

- [ ] **Task 2.2: 上下文管理**
  - [ ] 创建 `backend/app/core/conversation/context.py`
  - [ ] 实现 ContextConfig (max_turns, max_context_tokens)
  - [ ] 利用 LangChain ConversationSummaryBuffer 做摘要压缩
  - [ ] 编写 `tests/conversation/test_context.py`
  - [ ] 验证截断策略 + SummaryBuffer 摘要生成

---

## Phase 3: Provider 系统 (LangChain 适配层)

- [ ] **Task 3.1: Provider 管理器**
  - [ ] 创建 `backend/app/core/provider/manager.py`
  - [ ] 使用 `langchain.chat_models.init_chat_model()` 动态创建 ChatModel
  - [ ] 实现 get_chat_model() — 按 provider_id 获取
  - [ ] 实现 get_embedding_model() — 获取 Embeddings 实例
  - [ ] 实现 chat_with_fallback() — 主 Provider 失败自动切换
  - [ ] 实现 reload_config() — 热重载 (清空缓存)
  - [ ] 实现 Provider CRUD (create/update/delete/list)
  - [ ] 编写 `tests/provider/test_manager.py`
  - [ ] 验证: Fallback 链 + 热重载

- [ ] **Task 3.2: 模型来源配置**
  - [ ] 创建 `backend/app/core/provider/sources.py` — MODEL_SOURCES 常量
  - [ ] 预定义 OpenAI / Anthropic / Gemini 的模型列表和能力

---

## Phase 4: Tool 系统 (LangChain Tool 集成)

- [ ] **Task 4.1: 工具注册中心**
  - [ ] 创建 `backend/app/core/tool/registry.py`
  - [ ] 实现 ToolRegistry 单例 (register/get_all/get_by_category)
  - [ ] 实现 @register_tool 装饰器 (等价于 @tool + 自动注册)
  - [ ] 编写 `tests/tool/test_registry.py`

- [ ] **Task 4.2: 内置工具集**
  - [ ] 创建 `backend/app/core/tool/builtins/__init__.py`
  - [ ] 实现 web_search — 使用 LangChain @tool
  - [ ] 实现 file_read / file_write
  - [ ] 实现 shell_execute
  - [ ] 实现 knowledge_base_query
  - [ ] 编写 `tests/tool/test_builtins.py`
  - [ ] 每个工具至少 2 个测试用例

- [ ] **Task 4.3: 工具执行器**
  - [ ] 创建 `backend/app/core/tool/executor.py`
  - [ ] 包装 LangChain Tool 执行，加超时控制 + 错误处理
  - [ ] 编写 `tests/tool/test_executor.py`

---

## Phase 5: MCP 协议集成

- [ ] **Task 5.1: MCP 客户端**
  - [ ] 创建 `backend/app/core/mcp_client/client.py`
  - [ ] 使用 `mcp` SDK 原生客户端
  - [ ] 实现 SSE / stdio / Streamable HTTP 连接
  - [ ] 实现 list_tools() + call_tool()
  - [ ] 实现自动重连 (指数退避)
  - [ ] 编写 `tests/mcp_client/test_client.py`

- [ ] **Task 5.2: MCP 安全机制**
  - [ ] 创建 `backend/app/core/mcp_client/security.py`
  - [ ] 白名单/黑名单/Shell 元字符/内联代码检测
  - [ ] 编写 `tests/mcp_client/test_security.py`

- [ ] **Task 5.3: MCP → LangChain Tool 桥接**
  - [ ] 创建 `backend/app/core/mcp_client/bridge.py`
  - [ ] 将 MCP tool 包装为 LangChain BaseTool
  - [ ] 批量注册到 ToolRegistry
  - [ ] 编写 `tests/mcp_client/test_bridge.py`

---

## Phase 6: Skill 系统

- [ ] **Task 6.1: Skill 管理器**
  - [ ] 创建 `backend/app/core/skills/manager.py`
  - [ ] 实现 scan_skills() / build_skills_prompt()
  - [ ] 实现 install_skill() / uninstall_skill()
  - [ ] 编写 `tests/skills/test_manager.py`

- [ ] **Task 6.2: Skill 安全**
  - [ ] 名称正则 / 路径穿越 / ZIP 安全校验
  - [ ] 编写 `tests/skills/test_security.py`

---

## Phase 7: RAG 知识库系统 (LangChain 集成)

- [ ] **Task 7.1: 文档处理**
  - [ ] 创建 `backend/app/core/knowledge_base/parsers.py`
  - [ ] 使用 LangChain DocumentLoaders (PyPDFLoader, TextLoader, etc.)
  - [ ] 创建 `backend/app/core/knowledge_base/chunkers.py`
  - [ ] 使用 LangChain TextSplitters (RecursiveCharacter, MarkdownHeader)
  - [ ] 编写 `tests/knowledge_base/test_parsers.py` + `test_chunkers.py`

- [ ] **Task 7.2: 向量存储和检索**
  - [ ] 创建 `backend/app/core/knowledge_base/vec_store.py`
  - [ ] 使用 LangChain Milvus 封装
  - [ ] 创建 `backend/app/core/knowledge_base/retrieval/` — BM25 + RRF
  - [ ] 编写 `tests/knowledge_base/test_vec_store.py` + `test_retrieval.py`

- [ ] **Task 7.3: 知识库管理**
  - [ ] 创建 `backend/app/core/knowledge_base/mgr.py`
  - [ ] 实现 upload → 解析 → 分块 → Embedding → Milvus
  - [ ] 实现 query() + get_retrieval_context()
  - [ ] 编写 `tests/knowledge_base/test_manager.py`

---

## Phase 8: Agent 引擎 (LangGraph 核心)

- [ ] **Task 8.1: LangGraph 状态图**
  - [ ] 创建 `backend/app/core/agent/state.py` — AgentState TypedDict
  - [ ] 创建 `backend/app/core/agent/graph.py` — StateGraph 定义
  - [ ] 定义节点: inject_knowledge, inject_skills, invoke_llm, call_tools
  - [ ] 定义条件路由: should_continue (有 tool_calls → call_tools, 否则 → END)
  - [ ] 编译图 (含 MemorySaver 检查点)
  - [ ] 编写 `tests/agent/test_graph.py`

- [ ] **Task 8.2: 节点函数**
  - [ ] 创建 `backend/app/core/agent/nodes.py`
  - [ ] inject_knowledge_node — RAG 注入
  - [ ] inject_skills_node — Skill 提示词注入
  - [ ] invoke_llm_node — LangChain ChatModel 调用 + bind_tools
  - [ ] call_tools_node — 执行工具 + 追加 ToolMessage
  - [ ] should_continue — 条件路由判断
  - [ ] 编写 `tests/agent/test_nodes.py`

- [ ] **Task 8.3: Agent Runner**
  - [ ] 创建 `backend/app/core/agent/runner.py`
  - [ ] 包装 CompiledGraph，使用 astream_events() 获取流式事件
  - [ ] 实现 run() — 流式输出 (AsyncGenerator)
  - [ ] 实现 run_sync() — 非流式
  - [ ] 实现 interrupt() — 中断运行
  - [ ] 编写 `tests/agent/test_runner.py`

- [ ] **Task 8.4: 检查点持久化**
  - [ ] 创建 `backend/app/core/agent/checkpoint.py`
  - [ ] 使用 SQLAlchemyStore 持久化 LangGraph 检查点到 PostgreSQL
  - [ ] 编写 `tests/agent/test_checkpoint.py`

- [ ] **Task 8.5: 端到端测试**
  - [ ] 编写 `tests/agent/test_e2e.py` — Mock LLM + Tool 验证完整 ReAct

---

## Phase 9: Pipeline 架构

- [ ] **Task 9.1: Pipeline 基础框架**
  - [ ] 创建 `backend/app/core/pipeline/base.py` — Stage ABC + PipelineContext
  - [ ] 创建 `backend/app/core/pipeline/scheduler.py` — PipelineScheduler
  - [ ] 编写 `tests/pipeline/test_scheduler.py`

- [ ] **Task 9.2: Pipeline 阶段**
  - [ ] 创建 `backend/app/core/pipeline/stages/`
  - [ ] RateLimitStage — 频率限制
  - [ ] PreProcessStage — 消息预处理
  - [ ] ProcessStage — 调用 AgentRunner
  - [ ] RespondStage — 结果发送
  - [ ] 编写 `tests/pipeline/test_pipeline.py`

---

## Phase 10: Web 聊天对话功能

- [ ] **Task 10.1: 后端 WebSocket API**
  - [ ] 创建 `backend/app/api/routes/agent/chat.py`
  - [ ] POST /agent/chat — 非流式
  - [ ] WS /agent/chat/ws/{conv_id} — 流式 (astream_events → ws.send_json)
  - [ ] 实现心跳保活 (ping/pong 每 30s)
  - [ ] 编写 `tests/api/test_agent_chat.py`

- [ ] **Task 10.2: 前端聊天页面**
  - [ ] 创建 `frontend/src/routes/_layout/agent-chat.tsx`
  - [ ] ChatWindow + ConversationsList + MessageBubble + ToolCallPanel
  - [ ] MessageBubble 使用 react-markdown 渲染 Markdown
  - [ ] useAgentChat hook (WebSocket + 自动重连 + 心跳)
  - [ ] 组件测试 + Playwright E2E

- [ ] **Task 10.3: 前端管理页面**
  - [ ] Provider / KB / MCP / Skill / Persona / Tools / Conversations 管理页
  - [ ] 每个页面至少一个 E2E 测试

- [ ] **Task 10.4: WS 通道上下文记忆**（高优先级，建议在 Task 10.3 之前实施）

  > 背景：`agent_ws.py` 当前每条消息都是全新单轮对话（`agent.stream` 未传 history），
  > 且用户消息 / AI 回复均未持久化到数据库。REST 版 chat 路由已有完整实现
  > （`add_message` + `get_context_messages`），本任务把同样的能力补到 WS 通道，
  > 使网页对话获得多轮记忆、刷新后可恢复历史。

  - [ ] `agent_ws.py`: 校验 conversation_id 属于当前用户（`crud.get_conversation`），无效则拒绝处理消息
  - [ ] `agent_ws.py`: 收到消息后 `ConversationManager.add_message()` 持久化用户消息
  - [ ] `agent_ws.py`: `get_context_messages()` 加载历史，传入 `agent.stream(content, history=...)`
  - [ ] `agent_ws.py`: 流结束后把最后一条 AIMessage 持久化（role="assistant"）
  - [ ] WS 协议新增下行事件 `{"type": "history", "messages": [...]}`（建连后推送当前会话历史）
  - [ ] 前端 `useAgentChat`: 处理 history 事件，初始化 messages（刷新后恢复对话）
  - [ ] 更新 `docs/protocols/chat-ws-protocol.md`（新增 history 事件定义）
  - [ ] 编写集成测试: 同一 WS 连接两轮对话，第二轮 AI 能记住第一轮内容
  - [ ] 编写集成测试: 断开重连后前端能收到 history 并恢复消息

- [ ] **Task 10.5: Provider 管理 REST API + 前端切换**（便捷更换 API，免改 `.env`）

  > 背景：`ProviderConfig` 表 + `ProviderManager` 的 CRUD / Fallback / 热重载
  > 已实现（Phase 3），但未暴露成 REST API，也无前端 UI。当前换 API 只能
  > 改 `.env` + 重启，无法运行时保存多套模型源并一键切换默认。
  > 本任务补齐"接口层 + 界面层"，让 Provider 便捷切换真正可用。

  - [ ] 新增 `backend/app/api/routes/providers.py`：`ProviderManager` CRUD 包成 REST API
    - [ ] `GET /agent/providers`（列出当前用户 providers）
    - [ ] `POST /agent/providers`（新增，写入 api_key/base_url/model/type）
    - [ ] `PATCH /agent/providers/{id}`（更新，含设置 `is_default`）
    - [ ] `DELETE /agent/providers/{id}`
    - [ ] 设置默认 provider 时：同一用户只有一条 `is_default=True`（互斥）
  - [ ] api_key 落库前 AES-256 加密（复用 `utils/crypto.py`，涉及 `config` 字段加密存储）
  - [ ] 路由依赖注入 `ProviderManager`（通过 session）
  - [ ] 集成测试: 创建 → 设默认 → 查列表验证 `is_default` 唯一性
  - [ ] 前端 `useProviders.ts` hook + `agent-providers.tsx` 管理页（保存多套、一键切换默认）
  - [ ] 前端设置默认后调用 `ProviderManager.reload_config()` 热重载，无需重启

---

## Phase 11 起：见 istbot-implement-plan.md

> 原 Phase 11（集成测试与优化）已并入新计划。按 IM 机器人框架定位重排后的 Phase 11–16 任务清单，
> 以 [istbot-implement-plan.md](./istbot-implement-plan.md) 第八节为准。摘要：

| 阶段 | 主题 | 优先级 |
|---|---|---|
| Phase 11 | 平台适配器抽象层 + 首个 IM 接入 | P0 ★ 产品定义 |
| Phase 12 | Pipeline 9 Stage 洋葱模型 + 事件总线 + 会话锁 | P0 ★ 关键路径 |
| Phase 13 | 插件（Star）体系 + 事件钩子 + 热重载 | P1 ★ 生态核心 |
| Phase 14 | IM 交互补强（多模态 / 主动推送 / Rerank / message·cron 工具） | P1 |
| Phase 15 | 控制台前端（平台接入 / 会话 / 插件页优先） | P1 |
| Phase 16 | 工程化与运维（统计 / Persona / 内容安全 / 备份） | P2 |

---

## Task 依赖关系图

```
Phase 1 (基础架构: uv + SQLAlchemy 模型 + CRUD)
  ↓
Phase 2 (对话管理: ConversationManager + LangChain Message 转换)
  ↓
Phase 3 (Provider: LangChain init_chat_model)
  ↓
Phase 4 (Tool: LangChain @tool + ToolRegistry)
  ↓
Phase 5 (MCP) ←→ Phase 6 (Skill) ←→ Phase 7 (RAG: LangChain Splitters + Milvus)
  ↓              ↓               ↓
  └──────────────┴───────────────┘
                 ↓
          Phase 8 (Agent: LangGraph StateGraph + Nodes)
                 ↓
          Phase 9 (Pipeline: 4 Stage 顺序执行)
                 ↓
          Phase 10 (Web 控制台: WebSocket + React 聊天)
                 ↓
          Phase 11 (平台适配器 + 首个 IM 接入)   ★ 产品定义
                 ↓
          Phase 12 (Pipeline 洋葱模型 + 事件总线)  ★ 关键路径
                 ↓
     ┌───────────┼───────────┐
     ▼           ▼           ▼
 Phase 13     Phase 14    Phase 15.1
 (插件体系)   (IM 交互)    (控制台架构)
     └───────────┼───────────┘
                 ▼
             Phase 16 (工程化与运维)
```
