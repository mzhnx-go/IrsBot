# IrsBot Agent Platform — 详细实施计划 (v2)

> 基于现有 FastAPI + React 全栈脚手架，引入 **LangChain + LangGraph** 作为 Agent 编排框架，使用 **uv** 管理依赖，**SQLAlchemy** 做数据库层，构建一个集 RAG、MCP、Tool、Skill、多模型适配于一体的 Agent 平台，并提供 Web 聊天对话界面。
>
> 架构设计参考 [AstrBot](https://github.com/StarskyLabs/AstrBot) 的模块化分层思想。

---

## 0. 技术栈总览

| 层级 | 技术选型 | 说明 |
|------|----------|------|
| **包管理** | `uv` | 极速 Python 包管理器 + 虚拟环境管理 |
| **Web 框架** | FastAPI 0.115+ | 现有，保持不变 |
| **ORM (现有)** | SQLModel 0.0.21 (via SQLAlchemy 2.0) | 现有 User/Item 模型继续使用 |
| **ORM (Agent)** | SQLAlchemy 2.0 (Mapped + mapped_column) | Agent 平台新模型使用纯 SQLAlchemy 2.0 风格 |
| **迁移** | Alembic | 现有，同时管理 SQLModel 和 SQLAlchemy 模型的迁移 |
| **Agent 编排** | **LangChain + LangGraph** | 核心 Agent 框架，状态机驱动的 ReAct 循环 |
| **LLM 适配** | **LangChain Chat Models** | 统一 OpenAI / Anthropic / Gemini / 国产模型 |
| **向量检索** | **LangChain Text Splitters + Milvus** | RAG 分块 + 向量存储 (Docker 部署 Milvus Standalone) |
| **MCP** | `mcp` SDK + LangChain ToolBridge | MCP Server 工具桥接为 LangChain Tool |
| **消息推送** | FastAPI WebSocket | 流式输出推送到前端 |
| **前端** | React 19 + TS + TanStack Router + shadcn/ui + Tailwind CSS v3 | 现有，新增聊天页面 |
| **前端 WebSocket** | `ws` 库 + 自定义 hook | 原生 WebSocket API + 自动重连封装 |
| **前端 Markdown** | `react-markdown` + `remark-gfm` | 聊天消息 Markdown 渲染 |

### 为什么选 LangChain + LangGraph？

- **LangChain**: 统一 LLM 接口 (ChatModel)、Tool 抽象、RAG 组件 (TextSplitter, VectorStore, Retriever)，免去手写 Provider 适配层
- **LangGraph**: 状态机驱动的 Agent 编排，天然支持 ReAct 循环、工具调用、分支/条件路由、检查点持久化，比手写 `step_until_done()` 更可靠
- 两者都是 LangChain 官方出品，类型安全，社区活跃

### 双 ORM 策略说明

本项目同时存在两套 ORM 范式，通过 Alembic 统一管理：

| | SQLModel | SQLAlchemy 2.0 |
|---|---|---|
| **适用范围** | 现有 User/Item 模型 | 新增 Agent 平台模型 |
| **风格** | `Field()` + `table=True` | `Mapped` + `mapped_column` |
| **查询** | `session.exec(select(...))` | `session.execute(select(...))` |
| **Alembic** | `SQLModel.metadata` | `Base.metadata` (在 `db_agents.py` 中定义) |
| **迁移** | Alembic 一次生成，同时扫描两个 metadata | |

Alembic `env.py` 配置方式：
```python
from app.models import SQLModel
from app.core.db_agents import Base as AgentBase

target_metadata = [SQLModel.metadata, AgentBase.metadata]
```

### 版本锁定策略

LangChain 生态 API 变动频繁，所有依赖锁定小版本范围：

```toml
langchain = ["langchain>=0.3.0,<0.4.0"]
langgraph = ["langgraph>=0.2.0,<0.3.0"]
langchain-openai = ["langchain-openai>=0.2.0,<0.3.0"]
```

实际开发中使用 `uv lock` 生成精确锁定文件，生产部署时安装 `uv.lock` 保证一致性。

---

## 1. 目录结构 (参考 AstrBot 分层)

### 1.1 后端完整结构

```
backend/app/
├── main.py                          # FastAPI 应用入口 (现有)
├── models.py                        # 现有: User/Item (SQLModel)
├── crud.py                          # 现有: CRUD 操作
├── core/
│   ├── config.py                    # 现有: Settings 配置 (新增 Agent 字段)
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
├── core/                            # ★ 核心引擎 — AstrBot 的心脏
│   ├── __init__.py
│   ├── pipeline/                    # 消息处理流水线 (9 Stage)
│   │   ├── __init__.py
│   │   ├── base.py                  # Stage ABC + PipelineContext
│   │   ├── scheduler.py             # PipelineScheduler
│   │   └── stages/                  # 各处理阶段
│   │       ├── __init__.py
│   │       ├── waking_check.py      # 唤醒词检查
│   │       ├── whitelist.py         # 白名单
│   │       ├── rate_limit.py        # 频率限制
│   │       ├── content_safety.py    # 内容安全
│   │       ├── pre_process.py       # 预处理
│   │       ├── process.py           # 核心 Agent 调用 (LangGraph)
│   │       ├── result_decorate.py   # 结果装饰
│   │       └── respond.py           # 发送消息
│   ├── provider/                    # LLM 提供商管理
│   │   ├── __init__.py
│   │   ├── manager.py               # ProviderManager (LangChain adapter registry)
│   │   ├── sources.py               # 模型来源配置
│   │   └── adapters/                # 各模型适配 (LangChain ChatModel)
│   │       ├── __init__.py
│   │       └── registry.py          # 适配注册表
│   ├── agent/                       # Agent 运行器 + LangGraph 图
│   │   ├── __init__.py
│   │   ├── graph.py                 # ★ LangGraph StateGraph 定义 (ReAct 图)
│   │   ├── nodes.py                 # 图的节点函数 (invoke_llm, call_tool, etc.)
│   │   ├── state.py                 # Agent 状态定义 (RunnableConfig)
│   │   ├── builder.py               # build_main_agent() 组装器
│   │   ├── hooks.py                 # Agent 生命周期钩子
│   │   ├── runner.py                # AgentRunner (LangGraph executor wrapper)
│   │   └── checkpoint.py            # 检查点存储 (SQLAlchemyStore)
│   ├── tool/                        # 工具系统
│   │   ├── __init__.py
│   │   ├── registry.py              # 工具注册中心 (@register_tool)
│   │   ├── executor.py              # 工具执行器
│   │   └── builtins/                # 内置工具集
│   │       ├── __init__.py
│   │       ├── web_search.py        # Web 搜索
│   │       ├── file_ops.py          # 文件读写
│   │       ├── shell.py             # Shell 执行
│   │       └── kb_query.py          # 知识库查询
│   ├── mcp_client/                  # MCP 客户端
│   │   ├── __init__.py
│   │   ├── client.py                # MCPClient (SSE/stdio/streamable_http)
│   │   ├── security.py              # 安全校验
│   │   └── bridge.py                # MCP → LangChain Tool 桥接
│   ├── skills/                      # 技能系统
│   │   ├── __init__.py
│   │   └── manager.py               # SkillManager (扫描/SKILL.md/渐进披露)
│   ├── knowledge_base/              # RAG 知识库
│   │   ├── __init__.py
│   │   ├── mgr.py                   # KnowledgeBaseManager
│   │   ├── parsers.py               # 文档解析器 (PDF/MD/HTML)
│   │   ├── chunkers.py              # 分块器 (LangChain TextSplitter)
│   │   ├── vec_store.py             # 向量存储 (Milvus via LangChain)
│   │   └── retrieval/               # 检索模块
│   │       ├── __init__.py
│   │       ├── sparse.py            # BM25 (LangChain BM25Transformer)
│   │       ├── dense.py             # 向量检索
│   │       └── rank_fusion.py       # RRF 融合
│   ├── conversation/                # 对话管理
│   │   ├── __init__.py
│   │   ├── manager.py               # ConversationManager
│   │   └── context.py               # 上下文管理 (LangChain ConversationBuffer)
│   └── cron/                        # 定时任务管理
│       ├── __init__.py
│       └── scheduler.py             # APScheduler 集成
├── utils/                           # ★ 共享工具集
│   ├── __init__.py
│   ├── crypto.py                    # 加密工具 (API Key AES-256)
│   └── helpers.py                   # 通用辅助函数
└── alembic/                         # 现有: 迁移 (新增 agent 相关)
```

### 1.2 前端结构

```
frontend/src/
├── routes/
│   ├── __root.tsx                   # 现有
│   ├── login.tsx                    # 现有
│   └── _layout/
│       ├── index.tsx                # 现有: Dashboard
│       ├── agent-chat.tsx           # ★ Web 聊天页
│       ├── agent-conversations.tsx  # ★ 对话列表
│       ├── agent-providers.tsx      # ★ Provider 配置
│       ├── agent-knowledge.tsx      # ★ 知识库管理
│       ├── agent-mcp.tsx            # ★ MCP Server 管理
│       ├── agent-skills.tsx         # ★ Skill 管理
│       ├── agent-personas.tsx       # ★ 人格管理
│       └── agent-tools.tsx          # ★ 工具管理
├── components/
│   ├── Agent/
│   │   ├── ChatWindow.tsx           # 聊天窗口
│   │   ├── MessageBubble.tsx        # 消息气泡 (Markdown)
│   │   ├── ToolCallPanel.tsx        # 工具调用折叠面板
│   │   ├── StreamingIndicator.tsx   # 流式指示器
│   │   └── ConversationsList.tsx    # 对话列表侧栏
│   └── AgentForm/
│       ├── provider-form.tsx
│       ├── knowledge-upload.tsx
│       └── mcp-server-form.tsx
├── hooks/
│   ├── useAgentChat.ts              # WebSocket 聊天 hook (自动重连)
│   ├── useConversations.ts          # 对话管理 hook
│   └── useProviders.ts              # Provider 管理 hook
└── lib/
    └── agent-api.ts                 # Agent API SDK
```

### 1.3 项目根目录

```
IrsBot/
├── .env                             # 环境变量 (现有，新增 Agent 变量)
├── .env.example                     # ★ 新增: 配置模板
├── pyproject.toml                   # 现有: 前端包管理
├── backend/                         # 现有 + 新增
│   ├── pyproject.toml               # ★ 更新: uv 依赖管理
│   ├── uv.lock                      # ★ 新增: uv 锁定文件
│   ├── app/                         # 如上
│   ├── alembic/                     # 现有: 迁移 (新增 agent 相关)
│   ├── Dockerfile                   # 现有
│   └── tests/                       # ★ 新增: Agent 测试
├── frontend/                        # 现有 + 新增页面
├── compose.yml                      # 现有
├── compose.override.yml             # 现有 (含 Milvus 基础设施)
├── plan/                            # 规划文档
│   ├── spec.md                      # 需求规格
│   ├── tasks.md                     # 任务分解
│   └── checklist.md                 # 验收清单
└── k8s/                             # ★ 预留: K8s 部署清单
```

---

## 2. 分阶段实施计划

> **总则**: 每个 Phase 完成后必须通过该阶段的单元测试 + 集成测试，方可进入下一阶段。
> 使用 `uv` 管理依赖和运行命令。

---

### Phase 1: 项目基础架构搭建

**目标**: 搭建 Agent 平台的底层基础设施——依赖、数据模型、数据库表。

#### Task 1.0: 环境准备 (新增)

**工作内容**:
1. 确认 `uv` 已安装: `curl -LsSf https://astral.sh/uv/install.sh | sh`
2. `cd backend && uv sync --extra all` 安装所有依赖
3. 验证 `docker compose -f compose.yml -f compose.override.yml up -d` 中 Milvus 健康检查通过
4. 验证 `alembic upgrade head` 对现有 SQLModel 模型无报错

#### Task 1.1: 依赖与 uv 配置

**工作内容**:

1. 更新 `backend/pyproject.toml`，使用 `uv` 管理:

```toml
[project.optional-dependencies]
langchain = [
    "langchain>=0.3.0,<0.4.0",
    "langchain-openai>=0.2.0,<0.3.0",
    "langchain-anthropic>=0.2.0,<0.3.0",
    "langchain-google-genai>=2.0.0,<3.0.0",
    "langchain-community>=0.3.0,<0.4.0",
    "langgraph>=0.2.0,<0.3.0",
    "langchain-text-splitters>=0.3.0,<0.4.0",
    "langchain-core>=0.3.0,<0.4.0",
    "langchain-milvus>=0.1.0,<0.2.0",
]
rag = [
    "pymilvus>=2.5.0,<3.0.0",
    "pypdf>=5.0.0",
    "beautifulsoup4>=4.12.0",
    "python-magic>=0.4.0",
    "tiktoken>=0.7.0",
    "rank-bm25>=0.2.2",
]
mcp = [
    "mcp>=1.0.0,<2.0.0",
    "aiohttp>=3.9.0,<4.0.0",
]
all = [langchain + rag + mcp 的所有依赖]
```

2. 使用 uv 初始化:
```bash
cd backend
uv sync          # 安装所有依赖 (生成 uv.lock)
uv sync --extra langchain   # 仅安装 langchain 组
uv sync --extra all          # 安装全部
```

3. 在 `core/config.py` 的 Settings 中新增:

```python
# LLM Provider 配置
OPENAI_API_KEY: str = ""
ANTHROPIC_API_KEY: str = ""
GEMINI_API_KEY: str = ""
DEFAULT_LLM_PROVIDER: str = "openai"       # "openai" | "anthropic" | "gemini"
DEFAULT_LLM_MODEL: str = "gpt-4o"
EMBEDDING_MODEL: str = "text-embedding-3-small"
FALLBACK_PROVIDERS: str = "[]"              # JSON 数组

# Agent 配置
MAX_AGENT_STEPS: int = 15                  # 最大工具调用步数
CONTEXT_MAX_TURNS: int = 20                # 最大对话轮次
CONTEXT_MAX_TOKENS: int = 120000           # 最大 token 数
AGENT_TIMEOUT: float = 120.0               # Agent 超时 (秒)

# RAG 配置
ENABLE_RAG: bool = True
KB_CHUNK_SIZE: int = 500
KB_CHUNK_OVERLAP: int = 50
KB_TOP_K: int = 3
MILVUS_URI: str = "http://milvus:19530"      # Docker 网络中的 Milvus 地址
MILVUS_COLLECTION_PREFIX: str = "irsbot_kb"  # Milvus collection 名前缀

# MCP 配置
ENABLE_MCP: bool = True
MCP_TIMEOUT: float = 30.0
MCP_MAX_RETRIES: int = 2

# Skill 配置
ENABLE_SKILLS: bool = True
SKILL_DIRS: list[str] = ["./skills"]

# 内容安全
ENABLE_CONTENT_SAFETY: bool = False
SAFETY_KEYWORDS_FILE: str = "./config/safety_keywords.txt"

# 频率限制
RATE_LIMIT_REQUESTS: int = 20              # 每分钟最大请求数
RATE_LIMIT_WINDOW: int = 60                # 窗口 (秒)
```

4. 更新 `.env.example`:
```env
# LLM Providers
OPENAI_API_KEY=sk-xxx
ANTHROPIC_API_KEY=sk-ant-xxx
GEMINI_API_KEY=aiza-xxx

# Agent
DEFAULT_LLM_PROVIDER=openai
DEFAULT_LLM_MODEL=gpt-4o
MAX_AGENT_STEPS=15
CONTEXT_MAX_TURNS=20

# RAG
ENABLE_RAG=true
KB_CHUNK_SIZE=500
KB_TOP_K=3
MILVUS_URI=http://milvus:19530

# MCP
ENABLE_MCP=true

# Skills
ENABLE_SKILLS=true
```

**测试要求**:
- [ ] `uv run pytest tests/core/test_config.py` — 验证 Settings 加载
- [ ] `uv run python -c "from app.core.config import settings; print(settings.DEFAULT_LLM_MODEL)"` 输出 `gpt-4o`
- [ ] `uv lock` 无冲突

#### Task 1.2: Agent 数据模型 (SQLAlchemy 2.0)

**工作内容**:
在 `backend/app/core/db_agents.py` 新建所有 Agent 平台相关的 SQLAlchemy 2.0 模型 (使用 `Mapped` + `mapped_column` 风格):

```python
from datetime import datetime, timezone
from typing import Optional
import uuid

from sqlalchemy import String, Text, Integer, Boolean, ForeignKey, JSON, DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, DeclarativeBase


class Base(DeclarativeBase):
    pass


# ===== 1. Provider 配置 =====
class ProviderConfig(Base):
    """LLM Provider 配置表"""
    __tablename__ = "provider_configs"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True,
                                           default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    provider_type: Mapped[str] = mapped_column(String(50))  # "openai" | "anthropic" | "gemini"
    api_key: Mapped[str] = mapped_column(Text)  # 加密存储
    base_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    model_name: Mapped[str] = mapped_column(String(100))
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    fallback_order: Mapped[int] = mapped_column(Integer, default=999)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=get_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=get_utc_now,
                                                  onupdate=get_utc_now)


# ===== 2. Conversation =====
class Conversation(Base):
    """对话表"""
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(PGPSUUID(as_uuid=True), primary_key=True,
                                           default=uuid.uuid4)
    session_id: Mapped[str] = mapped_column(String(255), index=True)  # 用户会话标识
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(255), default="新对话")
    persona_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGPSUUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=get_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=get_utc_now,
                                                  onupdate=get_utc_now)

    # Relationships
    messages: Mapped[list["Message"]] = relationship("Message", back_populates="conversation",
                                                       cascade="all, delete-orphan")
    runs: Mapped[list["AgentRun"]] = relationship("AgentRun", back_populates="conversation",
                                                   cascade="all, delete-orphan")


# ===== 3. Message =====
class Message(Base):
    """消息表"""
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(PGPSUUID(as_uuid=True), primary_key=True,
                                           default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(20))  # "system" | "user" | "assistant" | "tool"
    content: Mapped[dict] = mapped_column(JSON)  # 多态 ContentPart 序列化为 JSON
    tool_calls: Mapped[Optional[list[dict]]] = mapped_column(JSON, nullable=True)
    tool_call_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=get_utc_now)

    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")


# ===== 4. KnowledgeBase =====
class KnowledgeBase(Base):
    """知识库表"""
    __tablename__ = "knowledge_bases"

    id: Mapped[uuid.UUID] = mapped_column(PGPSUUID(as_uuid=True), primary_key=True,
                                           default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    embedding_provider_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGPSUUID(as_uuid=True), nullable=True)
    chunk_size: Mapped[int] = mapped_column(Integer, default=500)
    chunk_overlap: Mapped[int] = mapped_column(Integer, default=50)
    retrieval_mode: Mapped[str] = mapped_column(String(20), default="inject")  # "inject" | "tool"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=get_utc_now)

    documents: Mapped[list["Document"]] = relationship("Document", back_populates="kb",
                                                        cascade="all, delete-orphan")


# ===== 5. Document =====
class Document(Base):
    """知识库文档表"""
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(PGPSUUID(as_uuid=True), primary_key=True,
                                           default=uuid.uuid4)
    kb_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    filename: Mapped[str] = mapped_column(String(500))
    file_path: Mapped[str] = mapped_column(String(1000))  # 存储路径
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/processing/done/error
    chunks_count: Mapped[int] = mapped_column(Integer, default=0)
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    file_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # pdf/md/txt/html
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=get_utc_now)

    kb: Mapped["KnowledgeBase"] = relationship("KnowledgeBase", back_populates="documents")


# ===== 6. MCPServer =====
class MCPServer(Base):
    """MCP Server 配置表"""
    __tablename__ = "mcp_servers"

    id: Mapped[uuid.UUID] = mapped_column(PGPSUUID(as_uuid=True), primary_key=True,
                                           default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    transport_type: Mapped[str] = mapped_column(String(20))  # "sse" | "streamable_http" | "stdio"
    url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    command: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    args: Mapped[list[str]] = mapped_column(JSON, default=list)
    env_vars: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    tools: Mapped[list[dict]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=get_utc_now)


# ===== 7. Skill =====
class Skill(Base):
    """Skill 表"""
    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = mapped_column(PGPSUUID(as_uuid=True), primary_key=True,
                                           default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str] = mapped_column(Text)
    path: Mapped[str] = mapped_column(String(1000))
    source_type: Mapped[str] = mapped_column(String(20), default="local")  # local/plugin/sandbox
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=get_utc_now)


# ===== 8. Persona =====
class Persona(Base):
    """人格表"""
    __tablename__ = "personas"

    id: Mapped[uuid.UUID] = mapped_column(PGPSUUID(as_uuid=True), primary_key=True,
                                           default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    prompt: Mapped[str] = mapped_column(Text)  # 系统提示词
    avatar: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    default_provider_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGPSUUID(as_uuid=True), nullable=True)
    tools: Mapped[list[str]] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=get_utc_now)


# ===== 9. AgentRun (追踪) =====
class AgentRun(Base):
    """Agent 运行记录表"""
    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(PGPSUUID(as_uuid=True), primary_key=True,
                                           default=uuid.uuid4)
    conversation_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGPSUUID(as_uuid=True), nullable=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    provider_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGPSUUID(as_uuid=True), nullable=True)
    persona_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGPSUUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20))  # running/completed/failed/interrupted
    input_text: Mapped[str] = mapped_column(Text)
    output_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tool_calls_made: Mapped[int] = mapped_column(Integer, default=0)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=get_utc_now)

    conversation: Mapped[Optional[Conversation]] = relationship("Conversation", back_populates="runs")
```

**测试要求**:
- [ ] 单元测试 `tests/core/db/test_models.py` — 验证所有模型可实例化
- [ ] `alembic revision --autogenerate -m "add_agent_platform_tables"` 生成迁移
- [ ] `alembic upgrade head` 在测试库上执行成功
- [ ] 验证所有表在 PostgreSQL 中正确创建

**关键注意事项**:
- Alembic `env.py` 必须导入 `from app.core.db_agents import Base as AgentBase`
- `target_metadata` 设为 `[SQLModel.metadata, AgentBase.metadata]`
- 迁移脚本会自动检测新增表和字段

#### Task 1.3: Agent CRUD 层

**工作内容**:
在 `backend/app/crud_agent.py` (新建) 中为 Agent 模型创建 CRUD 函数，复用现有 `crud.py` 的模式:

```python
# 模式: 与现有 crud.py 一致，但使用 session.execute(select(...)) 而非 session.exec()
def create_conversation(session: Session, title: str, user_id: uuid.UUID) -> Conversation
def get_conversation(session: Session, conv_id: uuid.UUID) -> Conversation | None
def list_conversations(session: Session, user_id: uuid.UUID, skip: int, limit: int) -> tuple[list[Conversation], int]
def add_message(session: Session, conversation_id: uuid.UUID, role: str, content: dict, ...) -> Message
# ... 每个模型都有 create/get/get_multi/update/delete
```

**测试要求**:
- [ ] `tests/core/db/test_crud_agent.py` — 每个模型 4 个 CRUD 测试用例
- [ ] 验证 user_id 隔离

---

### Phase 2: 对话管理系统

**目标**: 实现会话和对话的生命周期管理，利用 LangChain 的 Conversation Buffer 能力。

#### Task 2.1: 对话管理器

**工作内容**:
`backend/app/core/conversation/manager.py`:

```python
class ConversationManager:
    """管理 Conversation 和 Message 的 CRUD + LangChain 集成"""

    def __init__(self, db: Session, provider_manager: "ProviderManager"):
        self.db = db
        self.provider_manager = provider_manager

    async def create_conversation(self, session_id: str, user_id: uuid.UUID, title: str = "新对话") -> Conversation
    async def get_conversation(self, conv_id: uuid.UUID) -> Conversation | None
    async def list_conversations(self, user_id: uuid.UUID, skip: int = 0, limit: int = 20) -> tuple[list[Conversation], int]
    async def delete_conversation(self, conv_id: uuid.UUID, user_id: uuid.UUID) -> bool
    async def add_message(self, conv_id: uuid.UUID, role: str, content: Any,
                          tool_calls: list[dict] | None = None, tool_call_id: str | None = None) -> Message
    async def get_messages(self, conv_id: uuid.UUID, limit: int = 50, offset: int = 0) -> list[Message]
    async def get_langchain_messages(self, conv_id: uuid.UUID) -> list[Any]:
        """将数据库消息转换为 LangChain Message 格式 (AIMessage, HumanMessage, ToolMessage)"""
    async def get_context_messages(self, conv_id: uuid.UUID, max_tokens: int = 120000) -> list[Any]:
        """获取符合 token 限制的最近消息 (LangChain 格式)"""
```

关键: `get_langchain_messages()` 将 DB 中的 JSON 消息转换为 LangChain 的 `HumanMessage` / `AIMessage` / `ToolMessage` 对象，供 LangGraph 直接使用。

**测试要求**:
- [ ] `tests/conversation/test_manager.py`
  - 创建/获取/列出/删除对话
  - 添加消息并验证持久化
  - `get_langchain_messages()` 正确转换角色
  - `get_context_messages()` token 截断逻辑

#### Task 2.2: 上下文管理

**工作内容**:
`backend/app/core/conversation/context.py`:

```python
class ContextConfig(BaseModel):
    max_turns: int = 20
    max_context_tokens: int = 120000
    compression_threshold: float = 0.75  # 达到此 token 比例时触发压缩

class ContextManager:
    """上下文管理: 截断 + LangChain ConversationSummaryBuffer"""

    async def prepare_context(self, conv_id: uuid.UUID, config: ContextConfig) -> list[Any]:
        """准备 LangGraph 可用的消息列表"""
```

利用 LangChain 的 `ConversationSummaryBuffer` 做摘要压缩，而不是手写 LLM 摘要。

**测试要求**:
- [ ] `tests/conversation/test_context.py`
  - 验证截断策略
  - 验证 LangChain SummaryBuffer 摘要生成

---

### Phase 3: Provider 系统 (LangChain 适配层)

**目标**: 利用 LangChain 的统一 ChatModel 接口管理多模型，而非手写 Provider 适配。

#### Task 3.1: Provider 管理器

**工作内容**:
`backend/app/core/provider/manager.py`:

```python
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.embeddings import Embeddings

class ProviderManager:
    """管理 LangChain ChatModel 实例"""

    def __init__(self, db: Session):
        self.db = db
        self._cache: dict[str, BaseChatModel] = {}
        self._embed_cache: dict[str, Embeddings] = {}

    async def get_chat_model(self, provider_id: uuid.UUID | None = None) -> BaseChatModel:
        """获取 LangChain ChatModel 实例 (openai/anthropic/gemini)"""
        # 从 ProviderConfig 表读取配置
        # 使用 langchain.chat_models.init_chat_model() 创建实例
        # 缓存避免重复创建

    async def get_embedding_model(self, provider_id: uuid.UUID | None = None) -> Embeddings:
        """获取 LangChain Embeddings 实例"""

    async def get_default_provider_id(self) -> uuid.UUID | None
    async def chat_with_fallback(self, messages: list, **kwargs) -> Any:
        """主 Provider 失败时按 fallback_order 切换"""

    async def reload_config(self) -> None:
        """热重载: 清空缓存，下次获取时重建"""

    def list_providers(self) -> list[ProviderConfig]
    def create_provider(self, **fields) -> ProviderConfig
    def update_provider(self, provider_id: uuid.UUID, **fields) -> ProviderConfig
    def delete_provider(self, provider_id: uuid.UUID) -> bool
```

核心: 不再手写 OpenAIProvider/AnthropicProvider，而是通过 LangChain 的 `init_chat_model(name="gpt-4o", api_key=..., base_url=...)` 动态创建。

**测试要求**:
- [ ] `tests/provider/test_manager.py`
  - 验证 Provider CRUD
  - 验证 `get_chat_model()` 返回正确的 LangChain 实例
  - 验证 Fallback 逻辑
  - 验证热重载

#### Task 3.2: 模型来源配置

**工作内容**:
`backend/app/core/provider/sources.py`:

```python
# 预定义常用模型来源
MODEL_SOURCES = {
    "openai": {
        "default_model": "gpt-4o",
        "supported_models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
        "supports_tools": True,
        "supports_image": True,
        "supports_stream": True,
    },
    "anthropic": {
        "default_model": "claude-3-5-sonnet-20241022",
        "supported_models": ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229"],
        "supports_tools": True,
        "supports_image": True,
        "supports_stream": True,
    },
    "gemini": {
        "default_model": "gemini-2.0-flash",
        "supported_models": ["gemini-2.0-flash", "gemini-1.5-pro"],
        "supports_tools": True,
        "supports_image": True,
        "supports_stream": True,
    },
}
```

---

### Phase 4: Tool 系统 (LangChain Tool 集成)

**目标**: 利用 LangChain 的 Tool 抽象，让内置工具和 MCP 工具都能被 LangGraph 识别。

#### Task 4.1: 工具注册中心

**工作内容**:
`backend/app/core/tool/registry.py`:

```python
from langchain_core.tools import BaseTool, tool
from typing import Callable

class ToolRegistry:
    """全局工具注册中心 (单例)"""

    def register(self, tool_instance: BaseTool) -> None
    def get_tool(self, name: str) -> BaseTool | None
    def get_all_tools(self) -> list[BaseTool]
    def get_tools_by_category(self, category: str) -> list[BaseTool]
    def clear(self) -> None

    @classmethod
    def instance(cls) -> "ToolRegistry":
        if not hasattr(cls, "_instance"):
            cls._instance = cls()
        return cls._instance

# 装饰器: 从函数签名自动创建 LangChain @tool
def register_tool(name: str, description: str, category: str = "builtin"):
    """装饰器: 等价于 @tool(description=description) 并自动注册"""
    def decorator(func: Callable) -> BaseTool:
        langchain_tool = tool(description=description)(func)
        langchain_tool.name = name
        langchain_tool.category = category
        ToolRegistry.instance().register(langchain_tool)
        return langchain_tool
    return decorator
```

**测试要求**:
- [ ] `tests/tool/test_registry.py`
  - 验证装饰器注册
  - 验证 `get_all_tools()` 返回
  - 验证按分类查询

#### Task 4.2: 内置工具集

**工作内容**:
在 `backend/app/core/tool/builtins/` 下:

```python
# web_search.py
@register_tool("web_search", "Search the web for information", category="web")
async def web_search(query: str, engine: str = "tavily", top_k: int = 5) -> str:
    """使用 Tavily/Brave 搜索引擎获取网页摘要"""
    ...

# file_ops.py
@register_tool("file_read", "Read the contents of a file", category="file")
async def file_read(path: str) -> str:
    """读取文件内容"""
    ...

@register_tool("file_write", "Write content to a file", category="file")
async def file_write(path: str, content: str) -> str:
    """写入文件"""
    ...

# shell.py
@register_tool("shell_execute", "Execute a shell command", category="system")
async def shell_execute(command: str, timeout: float = 30.0) -> str:
    """在受限环境中执行 shell 命令"""
    ...

# kb_query.py
@register_tool("knowledge_base_query", "Query the knowledge base for relevant information", category="rag")
async def knowledge_base_query(query: str, kb_id: str | None = None, top_k: int = 3) -> str:
    """查询知识库获取相关信息"""
    ...
```

每个工具使用 LangChain 的 `@tool` 装饰器，自动获得 JSON Schema 提取和类型安全。

**测试要求**:
- [ ] `tests/tool/test_builtins.py`
  - 每个工具至少 2 个测试用例
  - Mock 外部依赖 (HTTP/文件/子进程)

#### Task 4.3: 工具执行器

**工作内容**:
`backend/app/core/tool/executor.py`:

```python
class ToolExecutor:
    """LangChain Tool 执行器"""

    async def execute(self, tool: BaseTool, input_data: dict | str) -> Any:
        """执行 LangChain Tool，支持异步和超时"""
        ...
```

利用 LangChain 内置的执行逻辑，我们只需要加超时控制和错误处理。

---

### Phase 5: MCP 协议集成

**目标**: 连接外部 MCP Server，将其工具桥接为 LangChain Tool。

#### Task 5.1: MCP 客户端

**工作内容**:
`backend/app/core/mcp_client/client.py`:

```python
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client

class MCPClient:
    """MCP 客户端，支持多种 Transport"""

    async def connect_sse(self, url: str) -> ClientSession
    async def connect_stdio(self, command: str, args: list[str], env: dict | None = None) -> ClientSession
    async def connect_streamable_http(self, url: str) -> ClientSession

    async def list_tools(self) -> list[dict]
    async def call_tool(self, name: str, arguments: dict) -> Any
    async def close(self) -> None

    # 自动重连
    async def call_tool_with_reconnect(self, name: str, arguments: dict) -> Any
```

使用 `mcp` SDK 的原生客户端，而非自己实现协议。

#### Task 5.2: MCP 安全机制

**工作内容**:
`backend/app/core/mcp_client/security.py`:

```python
class MCPSecurity:
    ALLOWED_COMMANDS = {"python", "node", "npm", "pnpm", "yarn", "bun", "deno", "uv", "uvx"}
    BLOCKED_COMMANDS = {"bash", "sh", "zsh", "curl", "wget", "rm", "sudo", "chmod"}
    # ... 同之前设计
```

#### Task 5.3: MCP → LangChain Tool 桥接

**工作内容**:
`backend/app/core/mcp_client/bridge.py`:

```python
from langchain_core.tools import BaseTool, tool

class MCPToolBridge:
    """将 MCP Server 的工具转换为 LangChain BaseTool"""

    @staticmethod
    def to_langchain_tool(mcp_tool_info: dict, session: ClientSession) -> BaseTool:
        """将 MCP tool 信息包装为 LangChain Tool"""
        wrapped = tool(description=mcp_tool_info["description"])(
            lambda **kwargs: session.call_tool(mcp_tool_info["name"], kwargs)
        )
        wrapped.name = mcp_tool_info["name"]
        return wrapped
```

**测试要求**:
- [ ] `tests/mcp/` — 客户端连接 + 安全校验 + 桥接转换

---

### Phase 6: Skill 系统

**目标**: 实现基于 Markdown 的技能指令包管理和渐进式披露。

#### Task 6.1: Skill 管理器

**工作内容**:
`backend/app/core/skills/manager.py`:

```python
class SkillManager:
    async def scan_skills(self, paths: list[str]) -> list[SkillInfo]
    async def get_skill(self, name: str) -> SkillInfo | None
    async def build_skills_prompt(self, active_skills: list[SkillInfo]) -> str
    async def install_skill(self, zip_path: str, dest_dir: str) -> Skill
    async def uninstall_skill(self, name: str) -> bool
```

渐进式披露:
1. System Prompt 中只注入 Skill 清单 (name + description)
2. Agent 决定使用某 Skill 时，读取 `SKILL.md` 全文注入上下文

#### Task 6.2: Skill 安全

同之前的设计 (名称正则、路径穿越、ZIP 安全)。

**测试要求**:
- [ ] `tests/skills/test_manager.py` + `test_security.py`

---

### Phase 7: RAG 知识库系统 (LangChain 集成)

**目标**: 利用 LangChain 的 TextSplitter、VectorStore、Retriever 实现 RAG。

#### Task 7.1: 文档处理

**工作内容**:
`backend/app/core/knowledge_base/parsers.py`:

```python
from langchain_community.document_loaders import (
    PyPDFLoader,
    TextLoader,
    BeautifulSoupWebLoader,
    UnstructuredMarkdownLoader,
)

class DocumentParser:
    @staticmethod
    async def parse_pdf(file_path: str) -> list[Document]:
        return PyPDFLoader(file_path).load()

    @staticmethod
    async def parse_text(file_path: str) -> list[Document]:
        return TextLoader(file_path).load()

    @staticmethod
    async def parse_markdown(file_path: str) -> list[Document]:
        return UnstructuredMarkdownLoader(file_path).load()

    @staticmethod
    async def parse_html(url: str) -> list[Document]:
        return BeautifulSoupWebLoader(url).load()
```

Chunkers 使用 LangChain 的 `RecursiveCharacterTextSplitter` / `MarkdownHeaderTextSplitter`:

```python
from langchain_text_splitters import RecursiveCharacterTextSplitter, MarkdownHeaderTextSplitter

class Chunkers:
    @staticmethod
    def recursive_character(text: str, chunk_size: int = 500, overlap: int = 50):
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=overlap,
            length_function=len,
        )
        return splitter.split_text(text)

    @staticmethod
    def markdown(text: str):
        splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[("#", "Header 1"), ("##", "Header 2"), ("###", "Header 3")]
        )
        return splitter.split_text(text)
```

#### Task 7.2: 向量存储和检索

**工作内容**:
`backend/app/core/knowledge_base/vec_store.py`:

```python
from pymilvus import Collection, CollectionSchema, FieldSchema, DataType, connections
from langchain_milvus import Milvus
from langchain_core.embeddings import Embeddings
from langchain_core.documents import Document

class MilvusVectorStore:
    """LangChain Milvus 封装 (替代 FAISS)"""

    def __init__(self, uri: str = "http://localhost:19530", collection_prefix: str = "irsbot_kb"):
        self.uri = uri
        self.collection_prefix = collection_prefix
        self._collections: dict[str, Milvus] = {}

    async def get_or_create_collection(self, kb_id: uuid.UUID, embeddings: Embeddings) -> Milvus:
        """为每个知识库创建独立的 Milvus collection"""
        if kb_id not in self._collections:
            collection_name = f"{self.collection_prefix}_{kb_id.hex[:12]}"
            self._collections[kb_id] = Milvus(
                embedding_function=embeddings,
                collection_name=collection_name,
                connection_args={"uri": self.uri},
                metadata_fields=["doc_id", "source", "kb_id"],
            )
        return self._collections[kb_id]

    async def add_documents(self, kb_id: uuid.UUID, documents: list[Document], embeddings: Embeddings) -> None
    async def search(self, kb_id: uuid.UUID, query: str, embeddings: Embeddings, top_k: int = 3) -> list[Document]
    async def delete(self, kb_id: uuid.UUID, doc_ids: list[str]) -> None
    async def drop_collection(self, kb_id: uuid.UUID) -> None
    async def close(self) -> None
```

Milvus 的优势:
- 支持分布式、水平扩展 (FAISS 单机)
- 原生支持 metadata filtering (按 kb_id/doc_id 过滤)
- 多种索引类型 (IVF_FLAT, HNSW, DISKANN, GPU)
- 持久化到本地/MinIO，容器重启不丢失

检索模块:
```python
# sparse.py — BM25 (同前，使用 LangChain BM25Transformer)
from langchain_community.retrievers import BM25Retriever

# rank_fusion.py — RRF (同前)
class RankFusion:
    @staticmethod
    def reciprocal_rank_fusion(sparse_docs: list[Doc], dense_docs: list[Doc], alpha: float = 0.5) -> list[Doc]:
        ...
```

#### Task 7.3: 知识库管理

`backend/app/core/knowledge_base/mgr.py`:

```python
class KnowledgeBaseManager:
    async def create_kb(self, user_id, name, config) -> KnowledgeBase
    async def upload_document(self, kb_id, user_id, file) -> Document
    async def process_document(self, doc: Document) -> None:
        """解析 → 分块 → Embedding → 存入 Milvus"""
    async def query(self, kb_id, query_text, top_k=3) -> list[RetrievedChunk]
    async def get_retrieval_context(self, kb_id, query_text) -> str:
        """非聚合模式: 返回拼接上下文"""
```

**测试要求**:
- [ ] `tests/knowledge_base/` — 解析 + 分块 + 向量存储 + 检索 + 端到端

---

### Phase 8: Agent 引擎 (LangGraph 核心)

**目标**: 使用 LangGraph 构建状态机驱动的 ReAct Agent，这是整个平台的核心。

#### Task 8.1: LangGraph 状态图定义

**工作内容**:
`backend/app/core/agent/graph.py`:

```python
from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver
from .state import AgentState
from .nodes import (
    invoke_llm_node,
    call_tools_node,
    should_continue,
    inject_knowledge_node,
    inject_skills_node,
)

def build_agent_graph() -> "CompiledGraph":
    """构建 LangGraph ReAct 状态图"""

    # 定义图节点
    graph = StateGraph(AgentState)

    # 核心节点
    graph.add_node("inject_knowledge", inject_knowledge_node)  # RAG 注入
    graph.add_node("inject_skills", inject_skills_node)        # Skill 注入
    graph.add_node("invoke_llm", invoke_llm_node)              # LLM 推理
    graph.add_node("call_tools", call_tools_node)              # 工具执行

    # 条件路由
    graph.add_conditional_edges(
        "invoke_llm",
        should_continue,  # 有 tool_calls → call_tools, 否则 → END
        {"tools": "call_tools", "end": END},
    )
    graph.add_edge("call_tools", "invoke_llm")  # 工具执行完回到 LLM
    graph.add_edge(START, "inject_knowledge")
    graph.add_edge("inject_knowledge", "inject_skills")
    graph.add_edge("inject_skills", "invoke_llm")

    # 编译 (含检查点)
    # 开发环境: MemorySaver (内存)
    # 生产环境: SQLAlchemyStore (持久化)
    memory = MemorySaver()
    compiled = graph.compile(checkpointer=memory)

    return compiled
```

#### Task 8.2: 节点函数实现

**工作内容**:
`backend/app/core/agent/nodes.py`:

```python
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, SystemMessage
from .state import AgentState

async def inject_knowledge_node(state: AgentState) -> AgentState:
    """注入知识库检索结果到 messages"""
    if state.knowledge_base:
        retriever = state.knowledge_base.get_retriever()
        docs = await retriever.ainvoke(state.messages[-1].content)  # 最后一条用户消息
        context = "\n\n".join([d.page_content for d in docs])
        state.messages.append(SystemMessage(content=f"[Knowledge Base Context]\n{context}"))
    return state

async def inject_skills_node(state: AgentState) -> AgentState:
    """注入 Skill 提示词"""
    if state.skills_prompt:
        state.messages.insert(0, SystemMessage(content=state.skills_prompt))
    return state

async def invoke_llm_node(state: AgentState) -> AgentState:
    """调用 LLM (LangChain ChatModel)"""
    llm_with_tools = state.llm.bind_tools(state.tools)
    response = await llm_with_tools.ainvoke(state.messages)
    state.messages.append(response)
    state.last_llm_response = response
    return state

async def call_tools_node(state: AgentState) -> AgentState:
    """执行工具调用"""
    final_messages = state.messages[:]
    for tool_call in state.messages[-1].tool_calls:
        tool = next((t for t in state.tools if t.name == tool_call["name"]), None)
        if tool:
            result = await tool.ainvoke(tool_call["args"])
            final_messages.append(ToolMessage(content=result, tool_call_id=tool_call["id"]))
    state.messages = final_messages
    return state

def should_continue(state: AgentState) -> str:
    """条件路由: 检查最后一条消息是否有 tool_calls"""
    last_msg = state.messages[-1]
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        return "tools"
    return "end"
```

#### Task 8.3: Agent 状态定义

**工作内容**:
`backend/app/core/agent/state.py`:

```python
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from typing import TypedDict, Annotated

class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]  # LangGraph 自动合并
    tools: list  # LangChain BaseTool 列表
    llm: Any  # LangChain ChatModel
    knowledge_base: Any  # KBManager
    skills_prompt: str
    max_steps: int
    step_count: int
    conversation_id: str
    user_id: str
```

#### Task 8.4: Agent Runner

**工作内容**:
`backend/app/core/agent/runner.py`:

```python
from langgraph.graph.state import CompiledGraph

class AgentRunner:
    """LangGraph CompiledGraph 的包装器"""

    def __init__(self, compiled_graph: CompiledGraph):
        self.graph = compiled_graph

    async def run(self, user_input: str, conversation_id: str, user_id: str,
                  tools: list, llm: Any, kb_mgr: Any, skills: list) -> AsyncGenerator[str, None]:
        """
        流式运行 Agent:
        1. 构建初始 state
        2. 调用 graph.astream() 获取事件流
        3. 将事件转换为 StreamEvent 转发给前端
        """
        config = {
            "configurable": {"thread_id": conversation_id},
            "recursion_limit": 15,  # MAX_AGENT_STEPS
        }
        async for event in self.graph.astream_events(
            {"messages": [("user", user_input)], "tools": tools, ...},
            config=config,
            version="v2",
        ):
            yield self._convert_event(event)

    async def run_sync(self, user_input: str, ...) -> str:
        """非流式运行"""
        ...
```

使用 LangGraph 的 `astream_events()` API 获取细粒度的流式事件 (LLM 调用、工具执行、节点完成)，而非自己实现 yield 协议。

#### Task 8.5: 检查点持久化

**工作内容**:
`backend/app/core/agent/checkpoint.py`:

```python
from langgraph.checkpoint.sqlstore import SQLAlchemyStore

class CheckpointStore:
    """使用 SQLAlchemyStore 持久化 LangGraph 检查点到 PostgreSQL"""

    def __init__(self, engine):
        self.store = SQLAlchemyStore(engine)
```

这样对话状态可以跨请求恢复，支持中断/恢复。

**测试要求**:
- [ ] `tests/agent/test_graph.py` — 验证 LangGraph 图构建
- [ ] `tests/agent/test_nodes.py` — 验证每个节点函数
- [ ] `tests/agent/test_runner.py` — 验证流式输出
- [ ] `tests/agent/test_e2e.py` — Mock LLM + Tool 验证完整 ReAct 循环

---

### Phase 9: Pipeline 架构

**目标**: 实现洋葱模型的消息处理流水线，在 LangGraph 外层包裹业务逻辑 Stage。

#### Task 9.1: Pipeline 基础框架

**工作内容**:
`backend/app/core/pipeline/base.py`:

```python
class PipelineContext(BaseModel):
    user_id: uuid.UUID
    session_id: str
    event_data: dict
    conversation_id: uuid.UUID | None = None
    _stopped: bool = False

    def stop_propagation(self):
        self._stopped = True

class Stage(ABC):
    @abstractmethod
    async def process(self, context: PipelineContext) -> PipelineContext | None:
        ...

class PipelineScheduler:
    def __init__(self, stages: list[Stage]):
        self.stages = stages

    async def execute(self, context: PipelineContext) -> PipelineContext:
        for stage in self.stages:
            if context._stopped:
                break
            result = await stage.process(context)
            if result is None:
                context.stop_propagation()
                break
        return context
```

#### Task 9.2: Pipeline 阶段

**工作内容**:
`backend/app/core/pipeline/stages/`:

```python
# rate_limit.py
class RateLimitStage(Stage):
    """频率限制"""
    async def process(self, ctx):
        if not await self._check_limit(ctx.user_id):
            ctx.stop_propagation()
            return None  # 返回 None 终止

# pre_process.py
class PreProcessStage(Stage):
    """消息预处理: 清洗、截断过长输入"""

# process.py
class ProcessStage(Stage):
    """核心: 调用 AgentRunner (LangGraph)"""
    async def process(self, ctx):
        runner = AgentRunner.get_instance()
        async for event in runner.run(ctx.event_data["content"], ...):
            await ctx.emit_event(event)  # 推送给前端
```

**测试要求**:
- [ ] `tests/pipeline/test_scheduler.py` + `test_pipeline.py`

---

### Phase 10: Web 聊天对话功能

#### Task 10.1: 后端 WebSocket API

**工作内容**:
`backend/app/api/routes/agent/chat.py`:

```python
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from app.api.deps import get_current_user
from app.core.agent.runner import AgentRunner

router = APIRouter(prefix="/agent", tags=["agent"])

@router.websocket("/chat/ws/{conversation_id}")
async def chat_ws(ws: WebSocket, conversation_id: str, current_user = Depends(get_current_user)):
    await ws.accept()
    runner = AgentRunner()

    try:
        while True:
            data = await ws.receive_json()
            if data["type"] == "message":
                # 流式推送
                async for event in runner.run(
                    user_input=data["content"],
                    conversation_id=conversation_id,
                    user_id=current_user.id,
                ):
                    await ws.send_json(event.to_dict())
            elif data["type"] == "stop":
                # 中断 Agent
                await runner.interrupt(conversation_id)
    except WebSocketDisconnect:
        pass
```

同时提供 REST 接口:
```python
@router.post("/chat")
async def chat_completion(request: ChatRequest, current_user = Depends(get_current_user)):
    """非流式聊天"""
```

**测试要求**:
- [ ] `tests/api/test_agent_chat.py` — WebSocket 连接 + 消息收发 + 流式转发

#### Task 10.2: 前端聊天页面

**工作内容**:
`frontend/src/routes/_layout/agent-chat.tsx`:

```tsx
// 页面结构:
// ┌────────────┬──────────────────────────┐
// │ 对话列表    │  聊天窗口                 │
// │            │  ┌────────────────────┐  │
// │ NewConv    │  │ MessageBubble x N  │  │
// │ Conv 1     │  │ [正在思考...]       │  │
// │ Conv 2     │  │                    │  │
// │            │  └────────────────────┘  │
// │            │  ┌────────────────────┐  │
// │            │  │ [输入框]    [发送]  │  │
// │            │  └────────────────────┘  │
// └────────────┴──────────────────────────┘
```

`useAgentChat.ts`:
```typescript
function useAgentChat(convId: string) {
  const [messages, setMessages] = useState<Message[]>([])
  const [isStreaming, setIsStreaming] = useState(false)

  useEffect(() => {
    const ws = new WebSocket(`/api/v1/agent/chat/ws/${convId}`)
    ws.onmessage = (e) => {
      const event = JSON.parse(e.data)
      switch (event.type) {
        case 'text_chunk': appendText(event.content)
        case 'tool_call': addToolCall(event)
        case 'tool_result': updateToolResult(event)
        case 'done': finalizeMessage()
      }
    }
    // 自动重连逻辑
    ws.onclose = () => setTimeout(() => reconnect(), 1000)
    return () => ws.close()
  }, [convId])

  return { messages, isStreaming, sendMessage: (text) => ws.send(...) }
}
```

**测试要求**:
- [ ] 组件测试 + Playwright E2E

#### Task 10.3: 前端管理页面

同之前设计 (Provider/KB/MCP/Skill/Persona 管理页)。

#### Task 10.4: WS 通道上下文记忆

> 高优先级，建议在 Task 10.3 之前实施。
> 背景：`agent_ws.py` 实际实现时为最小可用版（每条消息 `history=None`，未持久化），
> 导致网页对话每轮都是全新单轮对话、刷新即丢失。REST 版 chat 路由
> （`agent.py` 的 `POST /conversations/{id}/chat`）已有完整记忆链路，本任务补齐 WS 通道。

**后端改造** `backend/app/api/routes/agent_ws.py`:

```python
@router.websocket("/agent/chat/ws/{conversation_id}")
async def chat_ws(ws, conversation_id: str, session, current_user):
    await ws.accept()
    # 1. 校验会话归属（防越权：任何人可传任意 conversation_id）
    conv = crud.get_conversation(session, conv_id=uuid.UUID(conversation_id),
                                 user_id=current_user.id)
    if not conv:
        await ws.close(code=4404)
        return

    conv_manager = ConversationManager(session)

    while True:
        data = await ws.receive_json()
        if data["type"] == "message":
            # 2. 持久化用户消息
            conv_manager.add_message(conv.id, role="user", content=data["content"])
            # 3. 加载历史（20 轮 + token 截断），传入 Agent
            history = conv_manager.get_context_messages(conv.id)
            agent = Agent(session=session, conversation_id=str(conv.id),
                          user_id=str(current_user.id))
            async for event in agent.stream(data["content"], history=history):
                msg = to_frontend_event(event)
                if msg:
                    await ws.send_json(msg)
            # 4. 流结束后持久化 AI 回复（result.messages 最后一条 AIMessage）
```

**前端改造**:

- WS 协议新增下行事件（建连后推送一次）：
  `{"type": "history", "messages": [{"role": "user"|"assistant", "content": "..."}]}`
- `useAgentChat`: 收到 history 事件时初始化 messages，刷新页面后恢复对话

**测试要求**:
- [ ] 同一 WS 连接两轮对话，第二轮 AI 能记住第一轮内容（集成测试）
- [ ] 断开重连后收到 history 事件（集成测试）
- [ ] 传他人 conversation_id 时连接被拒绝（安全测试）
- [ ] 更新 `docs/protocols/chat-ws-protocol.md` 补充 history 事件定义

---

### Phase 11: 集成测试与优化

#### Task 11.1: 端到端集成测试

| 场景 | 测试方式 |
|------|----------|
| 简单对话 "你好" | `pytest` + Mock LLM |
| 工具调用 "搜索 xxx" | 集成测试 |
| Fallback Provider | 集成测试 (Mock 主 Provider 失败) |
| MCP 工具 | 集成测试 (Mock MCP Server) |
| RAG 检索 | 集成测试 (上传 → 查询) |
| Skill 触发 | 集成测试 |
| Pipeline 全流程 | 集成测试 |

#### Task 11.2: 性能与安全

- [ ] P99 < 10s 基准测试
- [ ] API Key AES-256 加密存储 (`utils/crypto.py`)
- [ ] Rate Limiting 生效
- [ ] 输入长度限制
- [ ] Prompt Injection 检测

---

## 3. 实施顺序与并行策略

### 关键路径 (串行)
```
Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 8 → Phase 10
```

### 可并行路径
```
Phase 5 (MCP)  ─┐
Phase 6 (Skill) ─┤  三者独立，可并行
Phase 7 (RAG)  ─┘
Phase 9 (Pipeline) ← 依赖 Phase 8
Phase 10 (前端) ← 依赖 Phase 8 + 10.1 API
```

### 推荐节奏

| 周次 | 阶段 | 产出 |
|------|------|------|
| 第 1 周 | Phase 1-2 | 数据模型 + 对话管理 |
| 第 2 周 | Phase 3 | LangChain Provider 管理 |
| 第 3 周 | Phase 4 | Tool 系统 + 内置工具 |
| 第 4 周 | Phase 5-7 | MCP + Skill + RAG (并行) |
| 第 5 周 | Phase 8 | LangGraph Agent 引擎 |
| 第 6 周 | Phase 9-10.1 | Pipeline + WebSocket API |
| 第 7 周 | Phase 10.2-10.3 + 11 | 前端 + 集成测试 |

---

## 4. 验收标准 (Success Criteria)

- [ ] **SC1**: 端到端对话 (输入 → LangGraph 推理 → 工具调用(可选) → 输出)
- [ ] **SC2**: 至少 2 种 LLM (OpenAI + Anthropic) 通过 LangChain 切换
- [ ] **SC3**: 至少 3 种内置工具 (Web搜索 + 文件操作 + Shell)
- [ ] **SC4**: 连接 MCP Server 并通过 LangChain ToolBridge 调用
- [ ] **SC5**: 上传文档 → LangChain TextSplitter → Milvus → 检索返回
- [ ] **SC6**: 安装 Skill → Agent 读取 SKILL.md
- [ ] **SC7**: WebUI 聊天 + 管理页面
- [ ] **SC8**: Pipeline 执行所有 Stage
- [ ] **SC9**: Alembic 迁移同时覆盖 SQLModel 和 SQLAlchemy 2.0 模型（autogenerate 后人工审查，确认无误再 apply）
- [ ] **SC10**: WebSocket 断线自动重连（指数退避，最多 5 次）

---

## 5. 测试策略

### 测试文件组织

> 测试目录位于 `backend/app/tests/`，与现有项目结构保持一致。

```
backend/app/tests/
├── conftest.py                    # db session, mock llm, mock tools
├── core/
│   ├── test_config.py
│   ├── db/
│   │   ├── test_models.py
│   │   └── test_crud_agent.py
│   ├── conversation/
│   │   ├── test_manager.py
│   │   └── test_context.py
│   ├── provider/
│   │   ├── test_manager.py
│   │   └── test_sources.py
│   ├── tool/
│   │   ├── test_registry.py
│   │   ├── test_executor.py
│   │   └── test_builtins.py
│   ├── mcp_client/
│   │   ├── test_client.py
│   │   ├── test_security.py
│   │   └── test_bridge.py
│   ├── skills/
│   │   ├── test_manager.py
│   │   └── test_security.py
│   ├── knowledge_base/
│   │   ├── test_parsers.py
│   │   ├── test_chunkers.py
│   │   ├── test_vec_store.py
│   │   └── test_manager.py
│   ├── agent/
│   │   ├── test_graph.py
│   │   ├── test_nodes.py
│   │   ├── test_runner.py
│   │   └── test_e2e.py
│   └── pipeline/
│       ├── test_scheduler.py
│       └── test_pipeline.py
└── api/
    ├── test_agent_chat.py
    └── test_agent_providers.py
```

### 运行测试
```bash
uv run pytest                          # 全部
uv run pytest tests/agent/             # 仅 Agent
uv run pytest tests/core/db/ -v        # 数据库测试详细输出
uv run pytest --cov=app --cov-report=html  # 覆盖率报告
```

### E2E 测试
- **后端**: `pytest` + `httpx.AsyncClient` (模拟 API 请求) + `pytest-asyncio`
- **前端**: [Playwright](https://playwright.dev/) — 聊天页面 + 各管理页面各至少 1 个 E2E 用例
- **CI 集成**: GitHub Actions 中运行 `pytest` + `playwright test`，覆盖率阈值 ≥ 60%

### 数据库迁移策略
- `alembic revision --autogenerate` 自动生成迁移脚本后，**必须人工审查** diff，确认无误再 `alembic upgrade head`
- 每次迁移需支持 `alembic downgrade -1` 回滚
- 双 ORM 迁移: Alembic `env.py` 中 `target_metadata = [SQLModel.metadata, AgentBase.metadata]`，一次扫描两个 metadata

---

## 6. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| LangChain API 变动 | 代码不兼容 | 锁定小版本 + `uv lock` 精确锁定 |
| LangGraph 学习曲线 | 开发效率低 | 先跑通最小 ReAct 图再扩展 |
| MCP SDK 不稳定 | 连接失败 | 自动重连 + 优雅降级 |
| RAG 检索质量差 | 回答不准确 | 可调参 chunk_size/top_k + RRF |
| 前端 WebSocket 断连 | 聊天中断 | 自动重连 + 消息队列 |
| 依赖包体积 | 镜像大 | 可选依赖分组 + Docker 多阶段构建 |
| Milvus 资源占用高 | 开发环境卡顿 | 提供降级方案 (ChromaDB 单机) |
| 双 ORM 维护成本 | 代码风格不一致 | 严格限定范围: SQLModel 仅 User/Item，Agent 模型全用 SQLAlchemy 2.0 |
