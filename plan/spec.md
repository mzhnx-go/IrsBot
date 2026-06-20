# AstrBot Core Features Replication Spec

## Why

基于 full-stack-template 项目复刻 AstrBot 的核心功能，构建一个完整的 AI Agent 平台。AstrBot 是一个成熟的多平台 LLM 聊天机器人和开发框架，其架构设计优秀，涵盖了对话管理、工具调用、RAG 检索、MCP 集成、技能系统等核心能力。通过复刻这些功能，可以深入理解 Agent 开发的最佳实践。

## What Changes

### 核心功能模块

#### 1. 对话管理系统 (Conversation Manager)
- **会话 (Session) 与对话 (Conversation) 分离**：一个会话可包含多个对话实例
- **消息持久化**：PostgreSQL 存储完整对话历史（JSON 列存多态消息）
- **上下文管理**：
  - 轮次截断 (Truncation)：按最大轮次限制截断旧消息
  - Token 压缩 (Compression)：支持直接截断和 LLM 摘要两种策略
  - Checkpoint 机制：内部断点标记用于持久化对齐
- **多模态消息支持**：文本、图片、音频、思考过程 (Think)、工具调用结果

#### 2. Agent 引擎 (Agent Engine)
- **工具调用循环 (Tool Loop)**：ReAct 模式的完整实现
  - LLM 推理 → 工具选择 → 工具执行 → 结果反馈 → 继续推理
  - 支持流式响应 (Streaming)
  - Fallback Provider 自动切换
  - 空输出重试机制 (指数退避)
  - 中断支持 (Graceful Stop)
- **请求装饰器模式**：
  - Persona/人格注入
  - Skills 提示词注入
  - 知识库上下文注入
  - 系统提醒 (时间/群名/用户ID)
  - Web 搜索工具按需注入

#### 3. Provider 系统 (LLM API 抽象层)
- **统一抽象接口**：
  - Chat Completion: `text_chat()` / `text_chat_stream()`
  - STT: `get_text()` (语音转文字)
  - TTS: `get_audio()` / `get_audio_stream()` (文字转语音)
  - Embedding: `get_embedding()` / `get_embeddings_batch()` (向量嵌入)
  - Rerank: `rerank()` (重排序)
- **支持的 Provider 类型**：
  - OpenAI 兼容 API (包括各种中转服务)
  - Anthropic Claude
  - Google Gemini
  - 国产大模型 (通义千问、智谱、MiniMax 等)
- **动态加载**：按需 import，避免全量加载
- **热重载**：运行时更新 Provider 配置
- **环境变量 Key 支持**：`$ENV_VAR` 格式解析

#### 4. Tool 系统 (函数调用框架)
- **工具定义 Schema**：
  - OpenAI Function Calling 格式
  - Anthropic Tool Use 格式
  - Google GenAI Function Declarations 格式
  - Light Schema (仅 name+description，用于 Skills-like 模式)
- **工具注册机制**：
  - 装饰器声明式注册 (`@builtin_tool`)
  - 运行时动态注册
  - 工具集合 (ToolSet) 管理
- **内置工具类别**：
  - 计算机工具：Shell 执行、Python 执行、文件操作、浏览器操作
  - 消息工具：发送消息给用户
  - 定时任务工具：Cron 管理
  - 知识库工具：RAG 查询
  - Web 搜索工具：Tavily/Brave/Baidu 等
- **执行引擎**：
  - 本地工具执行 (同步/异步/生成器)
  - MCP 工具委托执行
  - 子代理 (Handoff) 调度
  - 后台任务执行
  - 超时控制
  - 参数签名校验

#### 5. MCP 集成 (Model Context Protocol)
- **Transport 支持**：
  - SSE (Server-Sent Events)：HTTP 长连接
  - Streamable HTTP：HTTP 连接 + terminate_on_close
  - stdio：标准输入输出子进程
- **安全机制 (stdio)**：
  - 命令白名单 (python/node/npm/pnpm 等)
  - 命令黑名单 (bash/sh/curl/wget/rm 等)
  - Shell 元字符检测
  - 内联代码禁止 (`python -c`, `node -e`)
  - Docker 参数限制
- **客户端特性**：
  - 自动重连 (指数退避，最多 2 次)
  - 日志回调收集
  - Schema 正规化修复
  - 连接预检测试
- **工具桥接**：MCP Tool 作为 FunctionTool 子类无缝集成到 ToolSet

#### 6. Skill 系统 (技能指令包管理)
- **Skill 定义**：基于 Markdown 的指令包 (SKILL.md)
- **来源类型**：
  - local_only: 仅本地
  - both: 本地+沙箱同步
  - plugin: 来自插件
  - sandbox_only: 仅沙箱
- **渐进式披露 (Progressive Disclosure)**：
  - LLM 先看到 Skill 清单和摘要
  - 按需读取 SKILL.md 完整内容
  - 避免深度引用追踪
- **生命周期管理** (Sandbox 环境)：
  - Create/Promote/Rollback/Sync
  - Candidate 评估流程
- **安全措施**：
  - 名称正则校验
  - 路径穿越防护
  - ZIP 安装安全检查
  - Prompt 注入防护

#### 7. RAG/知识库系统 (检索增强生成)
- **文档处理流水线**：
  ```
  导入源 → Parser (PDF/EPUB/Text/URL/MarkItDown)
        → Chunker (RecursiveCharacter/FixedSize/Markdown)
        → Embedding (批量并发)
        → VecDB (Milvus + PostgreSQL)
        → Retrieval (BM25 + Vector + RankFusion)
  ```
- **分块策略**：
  - RecursiveCharacterChunker (默认): 递归字符分块
  - FixedSizeChunker: 固定大小分块
  - MarkdownChunker: Markdown 感知分块
- **混合检索**：
  - 稀疏检索 (BM25): 关键词匹配
  - 稠密检索 (Vector): Embedding 余弦相似度
  - Rank Fusion: 结果融合排序
- **使用模式**：
  - 非聚合模式: 直接注入 system_prompt
  - 聚合模式: 注入查询工具，LLM 自主决定何时查询

#### 8. Pipeline 架构 (消息处理流水线)
- **洋葱模型 (Onion Model)** 设计：
  - 9 个处理阶段有序执行
  - AsyncGenerator 实现前置/后置处理嵌套
  - 支持随时终止传播 (event.is_stopped())
- **阶段定义**：
  1. WakingCheckStage: 唤醒词检查
  2. WhitelistCheckStage: 白名单检查
  3. SessionStatusCheckStage: 会话状态检查
  4. RateLimitStage: 频率限制
  5. ContentSafetyCheckStage: 内容安全审核
  6. PreProcessStage: 预处理
  7. ProcessStage: 核心 (Star 插件 / LLM 调用)
  8. ResultDecorateStage: 结果装饰
  9. RespondStage: 发送消息

#### 9. WebUI/Dashboard (可视化管理界面)
- **前端技术栈**：React 19 + TypeScript + TanStack Router + shadcn/ui + Tailwind CSS v3
- **后端 API**：FastAPI RESTful API + WebSocket
- **核心页面**：
  - ChatPage: Web 聊天主界面 (WebSocket 流式响应)
  - ProviderPage: LLM/STT/TTS/Embedding 配置管理
  - KnowledgeBasePage: KB 列表/详情/文档/检索设置
  - ConversationPage: 对话列表/切换/搜索
  - MCPPage: MCP Server 管理
  - SkillPage: Skill 管理
  - PersonaPage: 人格 CRUD
  - TracePage: 请求追踪/调试
  - StatsPage: 使用统计
- **国际化**：准备 i18n 扩展点（暂不实现）

### 数据模型设计

#### 消息模型层次
```
ContentPart (基类, 多态)
├── TextPart      (type="text")
├── ThinkPart     (type="think")
├── ImageURLPart  (type="image_url")
└── AudioURLPart  (type="audio_url")

Message (Pydantic BaseModel)
├── role: system/user/assistant/tool/_checkpoint
├── content: str | list[ContentPart] | CheckpointData
├── tool_calls: list[ToolCall]
├── tool_call_id: str | None
└── _no_save: bool (私有属性)
```

#### 核心实体
- **Conversation**: id, session_id, name, created_at, updated_at, content (messages)
- **Persona**: id, name, prompt, tools, config
- **KnowledgeBase**: id, name, chunk_size, embedding_provider, rerank_provider
- **Provider**: id, type, api_key, base_url, model, config
- **MCPServer**: id, name, transport_type, command/url, args, env
- **Skill**: id, name, description, path, active, source_type

## Impact

### Affected Specs
- 无已有 spec，这是全新项目

### Affected Code (目标结构)
```
backend/app/
├── main.py                          # FastAPI 应用入口 (现有)
├── models.py                        # 现有: User/Item (SQLModel)
├── crud.py                          # 现有: CRUD 操作
├── core/
│   ├── config.py                    # 现有: Settings 配置
│   ├── db.py                        # 现有: SQLAlchemy engine
│   ├── security.py                  # 现有: JWT / 密码哈希
│   ├── db_agents.py                 # ★ 新增: Agent 平台 SQLAlchemy 2.0 模型
│   └── log.py                       # ★ 新增: 日志基础设施
├── api/
│   ├── main.py                      # 现有: 路由聚合
│   ├── deps.py                      # 现有: 依赖注入
│   └── routes/
│       ├── users.py                 # 现有
│       ├── items.py                 # 现有
│       ├── login.py                 # 现有
│       ├── private.py               # 现有
│       ├── utils.py                 # 现有
│       └── agent/                   # ★ 新增: Agent 平台 API
│           ├── __init__.py
│           ├── chat.py              # 聊天 REST + WebSocket
│           ├── conversation.py      # 对话管理
│           ├── provider_config.py   # Provider 配置管理
│           ├── knowledge.py         # 知识库 CRUD
│           ├── mcp_servers.py       # MCP Server 管理
│           ├── skills.py            # Skill 管理
│           ├── personas.py          # 人格管理
│           ├── tools.py             # 工具状态管理
│           └── stats.py             # 使用统计
├── core/                            # ★ 核心引擎
│   ├── pipeline/                    # 消息处理流水线 (9 Stage)
│   ├── provider/                    # LLM 提供商管理 (LangChain adapter)
│   ├── agent/                       # Agent 运行器 + LangGraph 图
│   ├── tool/                        # 工具系统
│   ├── mcp_client/                  # MCP 客户端
│   ├── skills/                      # 技能系统
│   ├── knowledge_base/              # RAG 知识库
│   ├── conversation/                # 对话管理
│   └── cron/                        # 定时任务管理
├── utils/                           # ★ 共享工具集
│   ├── crypto.py                    # 加密工具 (API Key AES-256)
│   └── helpers.py                   # 通用辅助函数
└── alembic/                         # 现有: 迁移 (新增 agent 相关)
```

## ADDED Requirements

### Requirement: 对话管理系统
系统 SHALL 提供完整的对话生命周期管理能力。

#### Scenario: 创建新对话
- **WHEN** 用户在新会话中发送第一条消息
- **THEN** 系统自动创建新的 Conversation 实例并分配唯一 ID
- **AND** 对话历史存储到 PostgreSQL 数据库（JSON 列存储多态消息）

#### Scenario: 上下文压缩
- **WHEN** 对话轮次超过 max_turns 阈值或 token 数超过 max_context_tokens
- **THEN** 系统根据配置选择截断或 LLM 摘要策略进行压缩
- **AND** 压缩后的上下文保留最近 15%-100% 的精确内容

#### Scenario: 多模态消息处理
- **WHEN** 用户发送包含文本、图片、音频的复合消息
- **THEN** 系统正确解析为 ContentPart 列表并序列化存储
- **AND** ThinkPart 内容可选择性不保存 (_no_save)

### Requirement: Agent 工具调用循环
系统 SHALL 实现 ReAct 模式的工具调用循环。

#### Scenario: 单步工具调用
- **WHEN** LLM 返回包含 tool_calls 的响应
- **THEN** 系统解析工具名称和参数，调用对应工具执行器
- **AND** 将工具结果追加到消息上下文，继续下一轮推理

#### Scenario: 流式响应
- **WHEN** LLM 支持流式输出
- **THEN** 系统通过 WebSocket 实时推送 token 到前端
- **AND** 工具调用期间暂停流式输出，恢复后继续推送

#### Scenario: Fallback Provider
- **WHEN** 主 Provider 请求失败 (网络错误/限流/超时)
- **THEN** 系统自动切换到配置的备用 Provider 重试
- **AND** 最多尝试 N 个备选 Provider (可配置)

### Requirement: Provider 统一抽象
系统 SHALL 提供统一的 LLM API 抽象层。

#### Scenario: 动态加载 Provider
- **WHEN** 配置文件添加了新的 Provider 条目
- **THEN** 系统运行时动态导入对应的 Provider 适配器模块
- **AND** 无需重启服务即可使用新 Provider

#### Scenario: 多模态能力感知
- **WHEN** 当前 Provider 不支持图片输入
- **THEN** 系统自动将图片转换为文字描述 (Image Captioning)
- **OR** 切换到支持图片的 Fallback Provider

### Requirement: Tool 系统框架
系统 SHALL 提供声明式的工具注册和执行框架。

#### Scenario: 装饰器注册
- **WHEN** 开发者使用 @builtin_tool("name", "description") 装饰函数
- **THEN** 系统自动从函数签名提取参数 Schema 并注册到 ToolSet
- **AND** 工具可通过 OpenAI/Anthropic/Google 格式暴露给 LLM

#### Scenario: MCP 工具集成
- **WHEN** MCP Server 连接成功并暴露了工具列表
- **THEN** 每个 MCP Tool 自动包装为 FunctionTool 子类
- **AND** 执行时委托给 MCPClient.call_tool()

### Requirement: MCP 协议集成
系统 SHALL 支持连接外部 MCP Server 并使用其能力。

#### Scenario: SSE Transport 连接
- **WHEN** 配置 MCP Server 为 SSE 模式 (url: "http://...")
- **THEN** 系统建立 HTTP 长连接并获取工具/资源列表
- **AND** 连接断开时自动重连 (最多 2 次，指数退避)

#### Scenario: stdio 安全执行
- **WHEN** 配置 MCP Server 为 stdio 模式 (command: "python", args: ["server.py"])
- **THEN** 系统验证命令在白名单内且不在黑名单
- **AND** 检测 Shell 元字符和内联代码标志，拒绝不安全命令

### Requirement: Skill 渐进式披露系统
系统 SHALL 实现基于 Markdown 的技能指令包管理。

#### Scenario: Skill 发现与触发
- **WHEN** LLM 收到用户请求
- **THEN** 系统在 System Prompt 中注入完整的 Skill 清单 (name + description)
- **AND** 当任务匹配某个 Skill 时，LLM 先读取 SKILL.md 获取完整指令再执行

#### Scenario: Skill 安装与安全管理
- **WHEN** 用户上传 Skill ZIP 包
- **THEN** 系统校验 ZIP 内无路径穿越攻击和危险文件
- **AND** 解压后注册到 SkillManager 并立即可用

### Requirement: RAG 知识库系统
系统 SHALL 提供完整的文档导入、向量化、检索链路。

#### Scenario: 文档导入与分块
- **WHEN** 用户上传 PDF/TXT/MD 文档到知识库
- **THEN** 系统自动解析文件内容并按配置的分块策略切分
- **AND** 分块结果批量向量化后存入 Milvus 向量数据库

#### Scenario: 混合检索
- **WHEN** Agent 需要查询知识库
- **THEN** 系统同时执行 BM25 稀疏检索和向量稠密检索
- **AND** 使用 Rank Fusion 算法融合排序返回 top_m_final 个结果

### Requirement: Pipeline 洋葱模型
系统 SHALL 采用洋葱模型实现消息处理流水线。

#### Scenario: 阶段嵌套执行
- **WHEN** 消息进入 Pipeline
- **THEN** 各 Stage 按 WakingCheck → Whitelist → ... → Respond 顺序执行
- **AND** 返回 AsyncGenerator 的 Stage 实现前置/后置处理嵌套

#### Scenario: 传播终止
- **WHEN** 某 Stage 调用 event.stop_propagation()
- **THEN** 后续所有 Stage 不再执行
- **AND** 已执行的 Stage 的后置逻辑正常完成

### Requirement: WebUI 可视化管理
系统 SHALL 提供完整的 Web 管理界面。

#### Scenario: 实时聊天
- **WHEN** 用户在 ChatPage 发送消息
- **THEN** 通过 WebSocket 建立双向通信
- **AND** LLM 的流式响应实时渲染到聊天界面
- **AND** 工具调用过程可视化展示 (折叠/展开)

#### Scenario: 配置管理
- **WHEN** 管理员访问配置页面
- **THEN** 可视化编辑 Provider/KB/MCP/Skill/Persona 配置
- **AND** 配置变更实时生效 (热重载)

## MODIFIED Requirements

无 (全新项目)

## REMOVED Requirements

无 (全新项目)

## Technical Constraints

1. **Python 版本**: >= 3.12 (使用 modern syntax: type statement, generics 等)
2. **异步优先**: 所有 I/O 操作使用 async/await
3. **Pydantic v2**: 数据模型使用 Pydantic BaseModel 进行校验和序列化
4. **数据库**: PostgreSQL 18 — 现有模型 (User/Item) 使用 SQLModel，Agent 平台模型使用纯 SQLAlchemy 2.0 (`Mapped` + `mapped_column`)
5. **向量检索**: Milvus 2.5+ (Docker 部署 etcd + MinIO + Milvus Standalone)
6. **Agent 编排**: LangChain + LangGraph — 统一 LLM 接口和工具抽象
7. **前端**: React 19 + TypeScript + TanStack Router + shadcn/ui + Tailwind CSS v3
8. **API 规范**: RESTful JSON + WebSocket (详见下方 API 规范章节)
9. **依赖最小化**: 核心功能不依赖重型框架，保持轻量
10. **配置驱动**: 所有能力通过环境变量启用或禁用

## API 规范

### RESTful 约定
- 基础路径: `/api/v1`
- 分页: `skip` (offset) + `limit` (page size)，响应包含 `data` 数组和 `count` 总数
- 状态码:
  - `200` — 成功
  - `201` — 创建成功
  - `400` — 请求参数错误
  - `401` — 未认证
  - `403` — 权限不足
  - `404` — 资源不存在
  - `409` — 资源冲突 (如邮箱重复)
  - `429` — 频率限制
  - `500` — 服务器内部错误
- 认证: Bearer JWT (OAuth2 Password Flow)

### WebSocket 协议
- 端点: `WS /api/v1/agent/chat/ws/{conversation_id}`
- 客户端 → 服务端消息格式:
  ```json
  {"type": "message", "content": "用户输入文本"}
  {"type": "stop"}
  ```
- 服务端 → 客户端事件类型:
  | type | 说明 |
  |------|------|
  | `text_chunk` | LLM 生成的文本片段 |
  | `tool_call` | 工具调用请求 (name, args) |
  | `tool_result` | 工具执行结果 |
  | `thinking` | Agent 思考过程 |
  | `done` | 对话结束 |
  | `error` | 错误信息 |
  | `pong` | 心跳响应 |
- 心跳: 服务端每 30s 发送 `{"type": "ping"}`，客户端回复 `{"type": "pong"}`
- 断线重连: 客户端自动指数退避重连，最多 5 次

## Non-Functional Requirements

### 性能要求
- 对话响应 P99 < 10s (简单查询无工具调用)
- 工具调用循环最多 15 步 (防止无限循环)
- 并发会话支持 >= 100
- API 响应 P95 < 200ms (不含 LLM 调用)

### 安全要求
- API Key 加密存储 (AES-256 via `cryptography` 库)
- MCP stdio 执行沙箱隔离 (命令白名单 + 黑名单)
- 输入长度限制 (防止 Prompt Injection)
- 速率限制 (Rate Limiting)
- JWT 过期自动刷新

### 可扩展性
- Provider 适配器插件化 (新增 LLM 只需实现基类)
- 工具注册开放 (第三方可注册自定义工具)
- Stage 可插拔 (Pipeline 阶段可增删改)
- 前端组件化 (React 组件复用)

### 可观测性
- Sentry 错误追踪 (生产环境)
- LangSmith / LangFuse Agent 调用追踪 (可选)
- Prometheus 指标暴露 (可选)

## Success Criteria

1. ✅ 能完成端到端对话: 用户输入 → Agent 推理 → 工具调用(可选) → 响应输出
2. ✅ 至少接入 2 种 LLM Provider (OpenAI + Anthropic)
3. ✅ 至少实现 3 种内置工具 (Web搜索 + 文件操作 + 消息发送)
4. ✅ 成功连接至少 1 个 MCP Server 并调用其工具
5. ✅ 导入文档到知识库并能正确检索返回相关内容
6. ✅ 安装 Skill 并在对话中被 LLM 正确触发和使用
7. ✅ WebUI 可视化管理所有配置和能力
8. ✅ Pipeline 正确执行所有阶段并可自定义拦截
