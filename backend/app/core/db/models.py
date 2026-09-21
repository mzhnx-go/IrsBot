"""Agent 平台数据模型 —— SQLModel 风格。

所有模型（含模板的 User/Item）统一注册在 SQLModel.metadata 下，
由 Alembic 统一管理迁移（见 app/alembic/env.py）。

每个模型对应一张表：
1. ProviderConfig  —— LLM 供应商配置
2. Conversation    —— 对话会话
3. Message         —— 会话中的消息
4. KnowledgeBase   —— RAG 知识库
5. Document        —— 知识库文档
6. MCPServer       —— MCP 服务器配置
7. Skill           —— 已安装技能
8. Persona         —— 智能体人设
9. AgentRun        —— Agent 执行记录
10. AppSetting     —— 运行时配置（通用 KV，与 .env 的部署级配置区分）
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlmodel import Field, Relationship, SQLModel

from app.core.db.sqlmodel_models import get_datetime_utc

# ── 1. ProviderConfig ──────────────────────────────────────────


class ProviderModel(SQLModel, table=True):
    """供应商可用模型清单。

    「获取模型列表」从上游 /models 拉取后 upsert；「自定义模型」手填。
    (provider_id, model_id) 唯一，重复拉取幂等。

    Attributes:
        id: 主键，UUID 自动生成。
        provider_id: 所属供应商，级联删除。
        model_id: 上游模型标识（如 gpt-4o）。
        display_name: 展示名（可选，默认用 model_id）。
        created_at: 创建时间（UTC）。
    """

    __tablename__ = "provider_models"
    __table_args__ = (
        UniqueConstraint("provider_id", "model_id", name="uq_provider_models_pair"),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=UUID(as_uuid=True),
    )
    provider_id: uuid.UUID = Field(
        foreign_key="provider_configs.id", ondelete="CASCADE", index=True
    )
    model_id: str = Field(sa_type=String(200), max_length=200)
    display_name: str | None = Field(default=None, sa_type=String(200), max_length=200)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(
            DateTime(timezone=True), default=get_datetime_utc, nullable=False
        ),
    )


class ProviderKey(SQLModel, table=True):
    """供应商的多把 API Key（P8「添加更多」）。

    轮换策略：每次取 Key 选 `last_used_at` 最旧的可用行（顺序轮换）；
    连败 3 次（401/403/429）进入 5 分钟冷却。迁移时把
    provider_configs.api_key 回填为首行，无行时 resolve 回落到该列。

    Attributes:
        id: 主键，UUID 自动生成。
        provider_id: 所属供应商，级联删除。
        encrypted_key: 加密密文（enc:v1:）。
        is_active: 手动启停。
        last_used_at: 最近一次被轮换选中的时间。
        fail_count: 连续失败计数（成功不重置时由调用方自行清零）。
        cooldown_until: 冷却截止时间（非空 = 冷却中）。
        created_at: 创建时间（UTC）。
    """

    __tablename__ = "provider_keys"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=UUID(as_uuid=True),
    )
    provider_id: uuid.UUID = Field(
        foreign_key="provider_configs.id", ondelete="CASCADE", index=True
    )
    encrypted_key: str = Field(sa_type=Text)
    is_active: bool = True
    last_used_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    fail_count: int = 0
    cooldown_until: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(
            DateTime(timezone=True), default=get_datetime_utc, nullable=False
        ),
    )


class ProviderConfig(SQLModel, table=True):
    """LLM 供应商配置表。

    存储用户接入的模型服务商信息（密钥、模型名、自定义地址等），
    供 ProviderManager 动态构建 LangChain 模型实例。

    Attributes:
        id: 主键，UUID 自动生成。
        user_id: 所属用户，级联删除。
        name: 配置显示名称。
        provider_type: 供应商类型，"openai" | "anthropic" | "gemini"。
        api_key: API 密钥。
        base_url: 自定义 API 地址（兼容 OpenAI 协议的中转站等）。
        model_name: 默认使用的模型名。
        supports_vision: 视觉能力三态（None=自动/True/False）。
        config: 额外扩展配置（JSON）。
        is_active: 是否启用。
        is_default: 是否为该用户的默认配置。
        fallback_order: 回退优先级，数值越小越优先。
        created_at / updated_at: 创建与更新时间（UTC）。
    """

    __tablename__ = "provider_configs"

    # DB 级约束：同一用户最多一条 is_default=True 的配置。
    # 应用层的互斥清零（clear_default）只是「尽力而为」，并发写入仍可能产生
    # 两条默认源；部分唯一索引在数据库层面兜底（只约束 is_default=true 的行）。
    __table_args__ = (
        Index(
            "uq_provider_configs_default_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("is_default"),
        ),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=UUID(as_uuid=True),
    )
    user_id: uuid.UUID = Field(foreign_key="user.id", ondelete="CASCADE", index=True)
    name: str = Field(sa_type=String(100), max_length=100)
    provider_type: str = Field(
        sa_type=String(50), max_length=50
    )  # "openai" | "anthropic" | "gemini"
    api_key: str = Field(sa_type=Text)  # 加密存储
    base_url: str | None = Field(default=None, sa_type=String(500), max_length=500)
    model_name: str = Field(sa_type=String(100), max_length=100)
    # 视觉能力三态：None=自动（按模型名启发式判断），True/False=用户显式声明。
    # 用户自带 base_url + 自填模型名是常态，固定能力表覆盖不到，故留可纠正的开关。
    supports_vision: bool | None = Field(default=None)
    config: dict = Field(default_factory=dict, sa_type=JSON)

    # ── 高级配置（存于 config JSON，免建列；前端「高级配置…」区读写）──
    # 用 property 而非列：FastAPI 的 ProviderOut 序列化时经 getattr 取值，
    # 语义上仍是 ProviderConfig 的一等字段。
    @property
    def timeout_seconds(self) -> int:
        """对上游 API 的请求超时（秒）。"""
        return int(self.config.get("timeout_seconds") or 120)

    @property
    def proxy_url(self) -> str | None:
        """HTTP/HTTPS 代理地址，仅对该提供商的出站请求生效。"""
        return self.config.get("proxy_url") or None

    @property
    def extra_headers(self) -> dict[str, str]:
        """合并进该提供商 HTTP 请求头的自定义键值对。"""
        headers = self.config.get("extra_headers")
        return headers if isinstance(headers, dict) else {}

    def apply_advanced_config(
        self,
        *,
        timeout_seconds: int | None = None,
        proxy_url: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """把高级配置合并进 config JSON（None 表示不修改该项）。"""
        new_config = dict(self.config or {})
        if timeout_seconds is not None:
            new_config["timeout_seconds"] = timeout_seconds
        if proxy_url is not None:
            new_config["proxy_url"] = proxy_url or ""  # 空串 = 清除
        if extra_headers is not None:
            new_config["extra_headers"] = extra_headers
        self.config = new_config
    is_active: bool = True
    is_default: bool = False
    fallback_order: int = 999
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(
            DateTime(timezone=True), default=get_datetime_utc, nullable=False
        ),
    )
    updated_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(
            DateTime(timezone=True),
            default=get_datetime_utc,
            onupdate=get_datetime_utc,
            nullable=False,
        ),
    )


# ── 2. Conversation ────────────────────────────────────────────


class Conversation(SQLModel, table=True):
    """对话会话表。

    一次会话包含多条消息和多次 Agent 执行记录；删除会话时
    级联删除其下所有消息与执行记录。

    Attributes:
        id: 主键，UUID 自动生成。
        session_id: 前端会话标识，建索引用于查询。
        user_id: 所属用户，级联删除。
        title: 会话标题，默认"新对话"。
        persona_id: 关联的智能体人设 id（可为空）。
        created_at / updated_at: 创建与更新时间（UTC）。
        messages: 该会话下的消息列表（一对多）。
        runs: 该会话下的 Agent 执行记录列表（一对多）。
    """

    __tablename__ = "conversations"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=UUID(as_uuid=True),
    )
    session_id: str = Field(sa_type=String(255), max_length=255, index=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", ondelete="CASCADE", index=True)
    title: str = Field(default="新对话", sa_type=String(255), max_length=255)
    # 会话级开关：False 时管线 SessionStatus 阶段直接拦截消息（Phase 12.1）
    is_enabled: bool = Field(
        default=True, sa_type=Boolean, sa_column_kwargs={"server_default": text("true")}
    )
    persona_id: uuid.UUID | None = Field(default=None, sa_type=UUID(as_uuid=True))
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(
            DateTime(timezone=True), default=get_datetime_utc, nullable=False
        ),
    )
    updated_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(
            DateTime(timezone=True),
            default=get_datetime_utc,
            onupdate=get_datetime_utc,
            nullable=False,
        ),
    )

    messages: list["Message"] = Relationship(
        back_populates="conversation", cascade_delete=True
    )
    runs: list["AgentRun"] = Relationship(
        back_populates="conversation", cascade_delete=True
    )


# ── 3. Message ─────────────────────────────────────────────────


class Message(SQLModel, table=True):
    """会话消息表。

    存储对话中的一条消息，role 区分消息来源；content 统一序列化为
    JSON 以支持多态的内容分片（文本/图片等）。

    Attributes:
        id: 主键，UUID 自动生成。
        conversation_id: 所属会话，级联删除。
        role: 消息角色，"system" | "user" | "assistant" | "tool"。
        content: 消息内容（多态 ContentPart 序列化为 JSON）。
        tool_calls: 助手发起的工具调用列表（仅 assistant 消息）。
        tool_call_id: 工具结果的调用 id（仅 tool 消息，与请求侧配对）。
        created_at: 创建时间（UTC）。
        conversation: 反向关联的会话对象。
    """

    __tablename__ = "messages"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=UUID(as_uuid=True),
    )
    conversation_id: uuid.UUID = Field(
        foreign_key="conversations.id", ondelete="CASCADE", index=True
    )
    role: str = Field(sa_type=String(20), max_length=20)  # system/user/assistant/tool
    content: dict = Field(sa_type=JSON)  # 多态 ContentPart，序列化为 JSON
    tool_calls: list[dict] | None = Field(default=None, sa_type=JSON)
    tool_call_id: str | None = Field(default=None, sa_type=String(255), max_length=255)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(
            DateTime(timezone=True), default=get_datetime_utc, nullable=False
        ),
    )

    conversation: Conversation | None = Relationship(back_populates="messages")


# ── 4. KnowledgeBase ───────────────────────────────────────────


class KnowledgeBase(SQLModel, table=True):
    """RAG 知识库表。

    一个知识库包含若干文档，并定义分块与检索策略。

    Attributes:
        id: 主键，UUID 自动生成。
        user_id: 所属用户，级联删除。
        name: 知识库名称。
        description: 描述（可为空）。
        embedding_provider_id: 指定的向量模型 Provider id（为空时用默认）。
        chunk_size: 分块大小（字符数），默认 500。
        chunk_overlap: 分块重叠长度，默认 50。
        retrieval_mode: 检索注入方式，"inject"（注入提示词）| "tool"（作为工具调用）。
        created_at: 创建时间（UTC）。
        documents: 该知识库下的文档列表（一对多）。
    """

    __tablename__ = "knowledge_bases"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=UUID(as_uuid=True),
    )
    user_id: uuid.UUID = Field(foreign_key="user.id", ondelete="CASCADE", index=True)
    name: str = Field(sa_type=String(255), max_length=255)
    description: str | None = Field(default=None, sa_type=Text)
    embedding_provider_id: uuid.UUID | None = Field(
        default=None, sa_type=UUID(as_uuid=True)
    )
    chunk_size: int = 500
    chunk_overlap: int = 50
    retrieval_mode: str = Field(
        default="inject", sa_type=String(20), max_length=20
    )  # "inject" | "tool"
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(
            DateTime(timezone=True), default=get_datetime_utc, nullable=False
        ),
    )

    documents: list["Document"] = Relationship(back_populates="kb", cascade_delete=True)


# ── 5. Document ────────────────────────────────────────────────


class Document(SQLModel, table=True):
    """知识库文档表。

    记录上传到知识库的文件及其解析/向量化状态。

    Attributes:
        id: 主键，UUID 自动生成。
        kb_id: 所属知识库，级联删除。
        user_id: 上传用户，级联删除。
        filename: 原始文件名。
        file_path: 落盘存储路径。
        status: 处理状态，pending / processing / done / error。
        chunks_count: 切分出的文本块数量。
        file_size: 文件大小（字节）。
        file_type: 文件类型（如 md、pdf，可为空）。
        created_at: 创建时间（UTC）。
        deleted_at: 软删除时间（UTC）。为 None 表示正常文档；有值表示已移入
              回收站——磁盘文件仍保留，可恢复；超过保留期由惰性清理真正删除。
        kb: 反向关联的知识库对象。
    """

    __tablename__ = "documents"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=UUID(as_uuid=True),
    )
    kb_id: uuid.UUID = Field(
        foreign_key="knowledge_bases.id", ondelete="CASCADE", index=True
    )
    user_id: uuid.UUID = Field(foreign_key="user.id", ondelete="CASCADE", index=True)
    filename: str = Field(sa_type=String(500), max_length=500)
    file_path: str = Field(sa_type=String(1000), max_length=1000)
    status: str = Field(
        default="pending", sa_type=String(20), max_length=20
    )  # pending / processing / done / error
    chunks_count: int = 0
    file_size: int = 0
    file_type: str | None = Field(default=None, sa_type=String(20), max_length=20)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(
            DateTime(timezone=True), default=get_datetime_utc, nullable=False
        ),
    )
    # 软删除标记：建索引是因为列表/回收站/清理三条路径都按它过滤
    deleted_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True, index=True),
    )

    kb: KnowledgeBase | None = Relationship(back_populates="documents")


# ── 6. MCPServer ───────────────────────────────────────────────


class MCPServer(SQLModel, table=True):
    """MCP 服务器配置表。

    存储外部 MCP (Model Context Protocol) 服务器的连接方式与可用工具列表。

    Attributes:
        id: 主键，UUID 自动生成。
        user_id: 所属用户，级联删除。
        name: 服务器显示名称。
        transport_type: 传输方式，"sse" | "streamable_http" | "stdio"。
        url: 远程服务器地址（sse / streamable_http 时必填）。
        command: 启动命令（stdio 时使用）。
        args: 启动命令参数列表。
        env_vars: 环境变量字典。
        is_active: 是否启用。
        tools: 该服务器提供的工具列表（JSON）。
        created_at: 创建时间（UTC）。
    """

    __tablename__ = "mcp_servers"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=UUID(as_uuid=True),
    )
    user_id: uuid.UUID = Field(foreign_key="user.id", ondelete="CASCADE", index=True)
    name: str = Field(sa_type=String(100), max_length=100)
    transport_type: str = Field(
        sa_type=String(20), max_length=20
    )  # "sse" | "streamable_http" | "stdio"
    url: str | None = Field(default=None, sa_type=String(1000), max_length=1000)
    command: str | None = Field(default=None, sa_type=String(500), max_length=500)
    args: list[str] = Field(default_factory=list, sa_type=JSON)
    env_vars: dict = Field(default_factory=dict, sa_type=JSON)
    is_active: bool = True
    tools: list[dict] = Field(default_factory=list, sa_type=JSON)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(
            DateTime(timezone=True), default=get_datetime_utc, nullable=False
        ),
    )


# ── 7. Skill ───────────────────────────────────────────────────


class Skill(SQLModel, table=True):
    """已安装技能表。

    每条记录对应一个已安装到本地的技能目录（含 SKILL.md）。

    Attributes:
        id: 主键，UUID 自动生成。
        name: 技能名，全局唯一。
        description: 技能描述。
        path: 技能目录的磁盘路径。
        source_type: 安装来源，local / plugin / sandbox。
        is_active: 是否启用（停用后不注入提示词）。
        config: 额外配置（JSON）。
        created_at: 创建时间（UTC）。
    """

    __tablename__ = "skills"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=UUID(as_uuid=True),
    )
    name: str = Field(sa_type=String(100), max_length=100, unique=True)
    description: str = Field(sa_type=Text)
    path: str = Field(sa_type=String(1000), max_length=1000)
    source_type: str = Field(
        default="local", sa_type=String(20), max_length=20
    )  # local / plugin / sandbox
    is_active: bool = True
    config: dict = Field(default_factory=dict, sa_type=JSON)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(
            DateTime(timezone=True), default=get_datetime_utc, nullable=False
        ),
    )


# ── 8. Persona ─────────────────────────────────────────────────


class Persona(SQLModel, table=True):
    """智能体人设表。

    定义一个 Agent 人设：系统提示词、头像、默认模型与绑定的工具集。

    Attributes:
        id: 主键，UUID 自动生成。
        user_id: 所属用户，级联删除。
        name: 人设名称。
        prompt: 系统提示词。
        avatar: 头像 URL 或路径（可为空）。
        default_provider_id: 默认使用的 Provider id（为空时用用户默认）。
        tools: 绑定的工具名列表（JSON）。
        is_active: 是否启用。
        created_at: 创建时间（UTC）。
    """

    __tablename__ = "personas"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=UUID(as_uuid=True),
    )
    user_id: uuid.UUID = Field(foreign_key="user.id", ondelete="CASCADE", index=True)
    name: str = Field(sa_type=String(100), max_length=100)
    prompt: str = Field(sa_type=Text)  # 系统提示词
    avatar: str | None = Field(default=None, sa_type=String(500), max_length=500)
    default_provider_id: uuid.UUID | None = Field(
        default=None, sa_type=UUID(as_uuid=True)
    )
    tools: list[str] = Field(default_factory=list, sa_type=JSON)
    is_active: bool = True
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(
            DateTime(timezone=True), default=get_datetime_utc, nullable=False
        ),
    )


# ── 9. AgentRun（执行记录）────────────────────────────────────


class AgentRun(SQLModel, table=True):
    """Agent 执行记录表。

    每次用户触发 Agent 执行都会写入一条记录，用于追踪状态、
    token 消耗、耗时与错误信息。

    Attributes:
        id: 主键，UUID 自动生成。
        conversation_id: 所属会话；会话删除时置 NULL（SET NULL）。
        user_id: 所属用户，级联删除。
        provider_id: 本次使用的 Provider id（可为空）。
        persona_id: 本次使用的人设 id（可为空）。
        status: 执行状态，running / completed / failed / interrupted。
        input_text: 用户输入文本。
        output_text: Agent 最终输出（可为空）。
        tool_calls_made: 本次执行的工具调用次数。
        tokens_used: 消耗的 token 数。
        duration_ms: 执行耗时（毫秒，可为空）。
        error_message: 失败时的错误信息（可为空）。
        created_at: 创建时间（UTC）。
        conversation: 反向关联的会话对象。
    """

    __tablename__ = "agent_runs"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=UUID(as_uuid=True),
    )
    conversation_id: uuid.UUID | None = Field(
        default=None, foreign_key="conversations.id", ondelete="SET NULL", index=True
    )
    user_id: uuid.UUID = Field(foreign_key="user.id", ondelete="CASCADE", index=True)
    provider_id: uuid.UUID | None = Field(default=None, sa_type=UUID(as_uuid=True))
    persona_id: uuid.UUID | None = Field(default=None, sa_type=UUID(as_uuid=True))
    status: str = Field(sa_type=String(20), max_length=20)  # running/completed/...
    input_text: str = Field(sa_type=Text)
    output_text: str | None = Field(default=None, sa_type=Text)
    tool_calls_made: int = 0
    tokens_used: int = 0
    duration_ms: int | None = None
    error_message: str | None = Field(default=None, sa_type=Text)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(
            DateTime(timezone=True), default=get_datetime_utc, nullable=False
        ),
    )

    conversation: Conversation | None = Relationship(back_populates="runs")


# ── 10. AppSetting（运行时配置）────────────────────────────────


class AppSetting(SQLModel, table=True):
    """运行时配置表（通用 KV）。

    存放**可在运行时变更**的系统配置，与 `Settings`（`.env`，进程启动时
    读取、需重启生效）区分开：

    - `.env`：部署级配置，改了要重启；也是运行时配置的**兜底初值**
    - 本表：超管在网页上即可变更，立即生效，无需重启

    通用 KV 而非类型化单行表，是为了后续增加运行开关时**不必再写迁移**
    （加一个键即可）；类型校验由 `app/core/settings_runtime.py` 的读取
    助手承担。

    ⚠️ 键名必须走 `settings_runtime` 里的常量，不要在各处手写字符串——
    KV 表没有 schema，拼错键不会报错，只会**静默新增一行**、配置看起来
    「改了不生效」。

    Attributes:
        key: 主键，如 "users.open_registration"。
        value: 值，统一按字符串存（"true"/"false"/...），读取时类型化。
        updated_at: 最后更新时间（UTC），便于审计。
    """

    __tablename__ = "app_settings"

    key: str = Field(sa_type=String(100), max_length=100, primary_key=True)
    value: str = Field(sa_type=Text)
    updated_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(
            DateTime(timezone=True),
            default=get_datetime_utc,
            onupdate=get_datetime_utc,
            nullable=False,
        ),
    )
