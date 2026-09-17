# Checklist - IrsBot IM 机器人框架 Implementation

> 技术栈: LangChain + LangGraph, uv, SQLAlchemy 2.0, Alembic, FastAPI, React 19
>
> **项目定位**：面向本地用户的自托管 IM 机器人框架；Web 仅为控制台。
> **进度与完整计划见 [istbot-implement-plan.md](./istbot-implement-plan.md)**（本文件为验收勾选视图；Phase 11 起的清单以该文档第八节为准）

---

## Phase 1: 项目基础架构搭建

- [ ] **1.0 环境准备**
  - [ ] `uv` 已安装并可用
  - [ ] `uv sync --extra all` 成功，生成 `uv.lock`
  - [ ] Milvus 基础设施 (etcd + MinIO + Milvus) Docker 启动且健康检查通过
  - [ ] `alembic upgrade head` 对现有 SQLModel 模型无报错

- [ ] **1.1 uv 依赖与配置**
  - [ ] pyproject.toml 包含 `[project.optional-dependencies]` (langchain, rag, mcp, all)
  - [ ] 版本锁定: langchain `<0.4.0`, langgraph `<0.3.0`
  - [ ] Settings 包含 LLM API Key / Agent 参数 / RAG 参数 / MCP 参数 / Skill 参数
  - [ ] .env.example 提供所有配置模板
  - [ ] `uv run pytest tests/core/test_config.py` 通过

- [ ] **1.2 SQLAlchemy 数据模型**
  - [ ] ProviderConfig 模型 (SQLAlchemy 2.0 Mapped 风格)
  - [ ] Conversation 模型 + Message 模型 (JSON 列)
  - [ ] KnowledgeBase + Document 模型
  - [ ] MCPServer 模型
  - [ ] Skill 模型
  - [ ] Persona 模型
  - [ ] AgentRun 模型
  - [ ] Alembic env.py 已配置双 metadata (SQLModel + AgentBase)
  - [ ] 单元测试 `tests/core/db/test_models.py` 通过
  - [ ] Alembic 迁移生成并应用到 PostgreSQL

- [ ] **1.3 Agent CRUD**
  - [ ] `crud_agent.py` 中每个模型有 CRUD 函数 (create/get/get_multi/update/delete)
  - [ ] 支持分页 + user_id 隔离
  - [ ] `tests/core/db/test_crud_agent.py` 通过 (每模型 ≥4 用例)

## Phase 2: 对话管理系统

- [ ] **2.1 对话管理器**
  - [ ] ConversationManager CRUD
  - [ ] add_message() 持久化
  - [ ] get_langchain_messages() — DB JSON → LangChain Message
  - [ ] get_context_messages() — token 限制
  - [ ] `tests/conversation/test_manager.py` 通过

- [ ] **2.2 上下文管理**
  - [ ] ContextConfig 数据类
  - [ ] LangChain ConversationSummaryBuffer 摘要压缩
  - [ ] `tests/conversation/test_context.py` 通过

## Phase 3: Provider 系统 (LangChain)

- [ ] **3.1 Provider 管理器**
  - [ ] 使用 `langchain.chat_models.init_chat_model()` 动态创建
  - [ ] get_chat_model() / get_embedding_model()
  - [ ] chat_with_fallback() — Fallback 链
  - [ ] reload_config() — 热重载
  - [ ] Provider CRUD
  - [ ] `tests/provider/test_manager.py` 通过

- [ ] **3.2 模型来源配置**
  - [ ] MODEL_SOURCES 预定义 OpenAI/Anthropic/Gemini

## Phase 4: Tool 系统 (LangChain Tool)

- [ ] **4.1 工具注册中心**
  - [ ] ToolRegistry 单例
  - [ ] @register_tool 装饰器 (= @tool + 自动注册)
  - [ ] `tests/tool/test_registry.py` 通过

- [ ] **4.2 内置工具集**
  - [ ] web_search / file_read / file_write / shell_execute / knowledge_base_query
  - [ ] 均使用 LangChain @tool 装饰器
  - [ ] 每个工具至少 2 个测试用例
  - [ ] `tests/tool/test_builtins.py` 通过

- [ ] **4.3 工具执行器**
  - [ ] 包装 LangChain Tool 执行 + 超时 + 错误处理
  - [ ] `tests/tool/test_executor.py` 通过

## Phase 5: MCP 协议集成

- [ ] **5.1 MCP 客户端**
  - [ ] 使用 `mcp` SDK 原生客户端
  - [ ] SSE / stdio / Streamable HTTP 连接
  - [ ] list_tools() + call_tool() + 自动重连
  - [ ] `tests/mcp_client/test_client.py` 通过

- [ ] **5.2 MCP 安全**
  - [ ] 白名单/黑名单/Shell 元字符/内联代码检测
  - [ ] `tests/mcp_client/test_security.py` 通过

- [ ] **5.3 MCP → LangChain Tool 桥接**
  - [ ] MCP tool 包装为 LangChain BaseTool
  - [ ] 批量注册到 ToolRegistry
  - [ ] `tests/mcp_client/test_bridge.py` 通过

## Phase 6: Skill 系统

- [ ] **6.1 Skill 管理器**
  - [ ] scan_skills() / build_skills_prompt() / install_skill()
  - [ ] 渐进式披露 (清单 → 按需读 SKILL.md)
  - [ ] `tests/skills/test_manager.py` 通过

- [ ] **6.2 Skill 安全**
  - [ ] 名称正则/路径穿越/ZIP 安全
  - [ ] `tests/skills/test_security.py` 通过

## Phase 7: RAG 知识库系统 (LangChain + Milvus)

- [ ] **7.1 文档处理**
  - [ ] 使用 LangChain DocumentLoaders (PyPDFLoader, TextLoader, etc.)
  - [ ] 使用 LangChain TextSplitters (RecursiveCharacter, MarkdownHeader)
  - [ ] `tests/knowledge_base/test_parsers.py` + `test_chunkers.py` 通过

- [ ] **7.2 向量存储和检索**
  - [ ] 使用 LangChain **Milvus** 封装 (非 FAISS)
  - [ ] BM25 + RRF 融合
  - [ ] `tests/knowledge_base/test_vec_store.py` + `test_retrieval.py` 通过

- [ ] **7.3 知识库管理**
  - [ ] upload → 解析 → 分块 → Embedding → Milvus
  - [ ] query() + get_retrieval_context()
  - [ ] `tests/knowledge_base/test_manager.py` 通过

## Phase 8: Agent 引擎 (LangGraph)

- [ ] **8.1 LangGraph 状态图**
  - [ ] AgentState TypedDict 定义
  - [ ] StateGraph: inject_knowledge → inject_skills → invoke_llm → call_tools → END
  - [ ] 条件路由: should_continue (tool_calls → call_tools, 否则 → END)
  - [ ] 编译图 (含 MemorySaver 检查点)
  - [ ] `tests/agent/test_graph.py` 通过

- [ ] **8.2 节点函数**
  - [ ] inject_knowledge_node — RAG 注入
  - [ ] invoke_llm_node — ChatModel.bind_tools() + ainvoke()
  - [ ] call_tools_node — 执行工具 + 追加 ToolMessage
  - [ ] should_continue — 条件路由
  - [ ] `tests/agent/test_nodes.py` 通过

- [ ] **8.3 Agent Runner**
  - [ ] 包装 CompiledGraph，使用 astream_events()
  - [ ] run() — 流式 AsyncGenerator
  - [ ] run_sync() — 非流式
  - [ ] interrupt() — 中断
  - [ ] `tests/agent/test_runner.py` 通过

- [ ] **8.4 检查点持久化**
  - [ ] SQLAlchemyStore 持久化 LangGraph 检查点到 PostgreSQL
  - [ ] `tests/agent/test_checkpoint.py` 通过

- [ ] **8.5 端到端**
  - [ ] `tests/agent/test_e2e.py` — Mock LLM + Tool 验证完整 ReAct

## Phase 9: Pipeline 架构

- [ ] **9.1 Pipeline 基础框架**
  - [ ] Stage ABC + PipelineContext + PipelineScheduler
  - [ ] `tests/pipeline/test_scheduler.py` 通过

- [ ] **9.2 Pipeline 阶段**
  - [ ] RateLimitStage / PreProcessStage / ProcessStage / RespondStage
  - [ ] `tests/pipeline/test_pipeline.py` 通过

## Phase 10: Web 聊天对话功能

- [ ] **10.1 后端 WebSocket API**
  - [ ] POST /agent/chat — 非流式
  - [ ] WS /agent/chat/ws/{conv_id} — 流式 (astream_events → ws.send_json)
  - [ ] 心跳保活 (ping/pong 每 30s)
  - [ ] `tests/api/test_agent_chat.py` 通过

- [ ] **10.2 前端聊天页面**
  - [ ] ChatWindow + ConversationsList + MessageBubble + ToolCallPanel
  - [ ] MessageBubble 使用 react-markdown 渲染
  - [ ] useAgentChat hook (WebSocket + 自动重连)
  - [ ] 组件测试 + Playwright E2E

- [ ] **10.3 前端管理页面**
  - [ ] Provider / KB / MCP / Skill / Persona / Tools / Conversations 管理页
  - [ ] 每个页面至少一个 E2E 测试

- [ ] **10.4 WS 通道上下文记忆**（建议在 10.3 之前实施）
  - [ ] agent_ws.py: 校验会话归属 + 持久化用户消息 / AI 回复
  - [ ] agent_ws.py: get_context_messages 加载历史传入 agent.stream
  - [ ] WS 下行 history 事件 + 前端 useAgentChat 恢复历史
  - [ ] `docs/protocols/chat-ws-protocol.md` 更新协议
  - [ ] 集成测试: 两轮对话记忆 + 重连恢复 + 越权拒绝

## Phase 11 起：见 istbot-implement-plan.md

> 原 Phase 11（集成测试与优化）已并入新计划。按 IM 机器人框架定位重排后的 Phase 11–16 验收清单，
> 以 [istbot-implement-plan.md](./istbot-implement-plan.md) 第八节为准。

---

## Success Criteria

- [x] **SC1**: 端到端对话 (LangGraph ReAct 循环完整)
- [x] **SC2**: 至少 2 种 LLM (LangChain ChatModel 切换)
- [ ] **SC2.1**: Provider 便捷切换 — REST API + 控制台（Task 10.5，代码完成待 UI 实测）
- [x] **SC3**: 至少 3 种内置工具 (LangChain @tool)
- [x] **SC4**: MCP Server 连接 + LangChain ToolBridge 调用
- [x] **SC5**: LangChain TextSplitter + Milvus + 检索返回（缺 Rerank，见 SC5.1）
- [ ] **SC5.1**: RAG 检索链路含 Rerank 段（新增）
- [x] **SC6**: Skill 安装 + Agent 读取 SKILL.md
- [ ] **SC7**: Web 控制台可完成「接平台 → 配模型 → 装插件 → 看会话」全流程（**重新定义**：Web 为配置台，聊天页仅调试）
- [ ] **SC8**: Pipeline 执行所有 9 个 Stage（含洋葱模型）
- [x] **SC9**: Alembic 迁移覆盖全部模型
- [x] **SC10**: WebSocket 断线自动重连
- [ ] **SC11**: 至少 1 个 IM 平台完成接入并端到端可用（新增，产品定义性）
- [ ] **SC12**: 插件可通过控制台安装、配置、触发生效、热重载（新增，生态核心）
- [ ] **SC13**: Agent 可通过 IM 主动推送消息（新增，对应 Cron）
- [ ] **SC14**: IM 图文消息可正常接收与回复（新增，多模态）
