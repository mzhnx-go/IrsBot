import secrets
import warnings
from typing import Annotated, Any, Literal, Self

from pydantic import (
    AnyUrl,
    BeforeValidator,
    EmailStr,
    HttpUrl,
    PostgresDsn,
    computed_field,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


def parse_cors(v: Any) -> list[str] | str:
    if isinstance(v, str) and not v.startswith("["):
        return [i.strip() for i in v.split(",") if i.strip()]
    elif isinstance(v, list | str):
        return v
    raise ValueError(v)


def parse_path_list(v: Any) -> list[str] | str:
    """解析逗号分隔的路径白名单（FILE_WRITE_ROOTS 用）。

    环境变量里写成 `C:/a,D:/b` 会被拆成列表；已是列表则原样返回。
    """
    if isinstance(v, str) and not v.startswith("["):
        return [i.strip() for i in v.split(",") if i.strip()]
    elif isinstance(v, list):
        return v
    raise ValueError(v)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Use top level .env file (one level above ./backend/)
        env_file="../.env",
        env_ignore_empty=True,
        extra="ignore",
    )
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = secrets.token_urlsafe(32)
    # 60 minutes * 24 hours * 8 days = 8 days
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8
    FRONTEND_HOST: str = "http://localhost:5173"
    ENVIRONMENT: Literal["local", "staging", "production"] = "local"

    BACKEND_CORS_ORIGINS: Annotated[
        list[AnyUrl] | str, BeforeValidator(parse_cors)
    ] = []

    @computed_field  # type: ignore[prop-decorator]
    @property
    def all_cors_origins(self) -> list[str]:
        """获取所有CORS来源地址列表。

        将配置的BACKEND_CORS_ORIGINS与FRONTEND_HOST合并，
        去除末尾的斜杠，返回完整的跨域来源列表。

        Returns:
            所有CORS来源地址字符串列表
        """
        return [str(origin).rstrip("/") for origin in self.BACKEND_CORS_ORIGINS] + [
            self.FRONTEND_HOST
        ]

    PROJECT_NAME: str
    SENTRY_DSN: HttpUrl | None = None
    # 日志级别（root logger）。环形缓冲全量收集，前端控制台再按级别过滤；
    # 此项只影响控制台/终端输出量（见 core/logging.py）
    LOG_LEVEL: str = "INFO"
    POSTGRES_SERVER: str
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> PostgresDsn:
        return PostgresDsn.build(
            scheme="postgresql+psycopg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_SERVER,
            port=self.POSTGRES_PORT,
            path=self.POSTGRES_DB,
        )

    SMTP_TLS: bool = True
    SMTP_SSL: bool = False
    SMTP_PORT: int = 587
    SMTP_HOST: str | None = None
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    EMAILS_FROM_EMAIL: EmailStr | None = None
    EMAILS_FROM_NAME: str | None = None

    @model_validator(mode="after")
    def _set_default_emails_from(self) -> Self:
        if not self.EMAILS_FROM_NAME:
            self.EMAILS_FROM_NAME = self.PROJECT_NAME
        return self

    EMAIL_RESET_TOKEN_EXPIRE_HOURS: int = 48

    @computed_field  # type: ignore[prop-decorator]
    @property
    def emails_enabled(self) -> bool:
        return bool(self.SMTP_HOST and self.EMAILS_FROM_EMAIL)

    EMAIL_TEST_USER: EmailStr = "test@example.com"
    FIRST_SUPERUSER: EmailStr
    FIRST_SUPERUSER_PASSWORD: str

    # ── LLM Provider 配置 ──────────────────────────────────────
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = ""
    ANTHROPIC_API_KEY: str = ""
    GEMINI_API_KEY: str = ""

    DEFAULT_LLM_PROVIDER: str = "openai"  # "openai" | "anthropic" | "gemini"
    DEFAULT_LLM_MODEL: str = "gpt-4o"
    EMBEDDING_API_KEY: str = ""  # SiliconFlow API Key
    EMBEDDING_BASE_URL: str = ""  # 默认空 = OpenAI 官方
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    FALLBACK_PROVIDERS: str = "[]"  # JSON 数组字符串

    # ── Agent 配置 ─────────────────────────────────────────────
    MAX_AGENT_STEPS: int = 30  # 最大工具调用轮数（与 AstrBot 对齐，15 → 30）
    CONTEXT_MAX_TURNS: int = 20  # 最大对话轮次
    CONTEXT_MAX_TOKENS: int = 120000  # 最大 token 数
    AGENT_TIMEOUT: float = 120.0  # Agent 超时 (秒)

    # ── RAG 配置 ───────────────────────────────────────────────
    ENABLE_RAG: bool = True
    KB_CHUNK_SIZE: int = 500
    KB_CHUNK_OVERLAP: int = 50
    KB_TOP_K: int = 3
    # 重排段：RRF 融合后的候选用 rerank 模型按 query 相关度精排。
    # 复用 EMBEDDING_API_KEY / EMBEDDING_BASE_URL（SiliconFlow 同一账号）；
    # 调用失败自动降级为不重排（纯 RRF 排序），不影响检索可用性。
    ENABLE_RERANK: bool = True
    RERANK_MODEL: str = "BAAI/bge-reranker-v2-m3"
    RERANK_CANDIDATES: int = 10  # 送入重排的候选数（融合结果先截到此数再精排）
    MILVUS_URI: str = "http://localhost:19530"  # Docker 网络中使用 milvus:19530
    # 每个环境用不同前缀，避免测试/开发/生产的向量集合互相污染
    MILVUS_COLLECTION_PREFIX: str = "irsbot_kb"
    # 知识库上传文件的落盘根目录，按环境隔离
    KB_FILE_STORAGE_DIR: str = "./uploads/kb"
    # 回收站保留天数：文档软删除后，磁盘文件在此期间保留以便恢复；
    # 超过该天数的记录由惰性清理真正删除（见 routes/knowledge_base.py）。
    KB_TRASH_RETENTION_DAYS: int = 30

    # ── 聊天附件配置 ───────────────────────────────────────────
    # 附件落盘根目录，按 {user_id}/{conversation_id}/ 两级组织，
    # 删会话时整目录清理（见 core/agent/attachments.py）。
    CHAT_ATTACHMENT_DIR: str = "./uploads/chat_attachments"
    # 文档附件解析后注入上下文的最大字符数：超出即截断并回报 truncated。
    # 与 CONTEXT_MAX_TOKENS 是两套预算，前者管单个附件、后者管整轮上下文，
    # 这里留出足够余量，避免一个超大 PDF 直接吃掉整轮配额。
    ATTACHMENT_MAX_CHARS: int = 60000
    # 单文件字节上限（图片/文档分开设：图片要 base64 后进上下文，膨胀约 1/3）
    ATTACHMENT_MAX_DOC_BYTES: int = 20 * 1024 * 1024
    ATTACHMENT_MAX_IMAGE_BYTES: int = 10 * 1024 * 1024

    # ── 本地 OCR（视觉回退）────────────────────────────────────
    # 模型不支持视觉时，用离线 OCR 把图中文字提出来送上下文。
    # 关掉后行为退回「提示无法查看图片内容」（引擎依赖缺失时同样自动退回）。
    OCR_ENABLED: bool = True
    # 单张图片识别文字注入上下文的上限，超出截断（OCR 结果可能很长且噪声多）
    OCR_MAX_CHARS: int = 4000

    # ── MCP 配置 ───────────────────────────────────────────────
    ENABLE_MCP: bool = True
    MCP_TIMEOUT: float = 30.0
    MCP_MAX_RETRIES: int = 2

    # ── Skill 配置 ─────────────────────────────────────────────
    ENABLE_SKILLS: bool = True
    SKILL_DIRS: list[str] = ["./skills"]

    # ── 工具权限开关（安全默认：危险工具默认关闭）─────────────
    # shell_execute / file_write 具备破坏力，默认不注册到 Agent；
    # 如需启用，在 .env 设 true 并（file_write）配置 FILE_WRITE_ROOTS 白名单。
    ENABLE_SHELL: bool = False
    ENABLE_FILE_WRITE: bool = False
    FILE_WRITE_ROOTS: Annotated[list[str], BeforeValidator(parse_path_list)] = []

    # ── 注册开关（安全默认：不开放自助注册）───────────────────
    # ⚠️ 这是**兜底初值**，不是最终生效值。部署后在 /admin 页切换
    # 「单用户 / 多租户」保存即生效（值存 app_settings 表），运行时值
    # **优先级高于本变量**。判断统一走 settings_runtime.signup_allowed()，
    # 不要在别处直接读本字段。
    # 关时 POST /users/signup 直接 403，账号只由管理员创建。
    USERS_OPEN_REGISTRATION: bool = False

    # ── 内容安全 ───────────────────────────────────────────────
    ENABLE_CONTENT_SAFETY: bool = False
    SAFETY_KEYWORDS_FILE: str = "./config/safety_keywords.txt"

    # ── 频率限制 ──────────────────────────────────────────────
    RATE_LIMIT_REQUESTS: int = 20  # 每分钟最大请求数
    RATE_LIMIT_WINDOW: int = 60  # 窗口 (秒)
    MAX_USER_MESSAGE_LENGTH: int = 4096  # 用户发送消息的最大长度
    TOOL_CALL_TIMEOUT: int = 120  # 单次工具调用超时（秒），Phase 12.5 统一切点

    def _check_default_secret(self, var_name: str, value: str | None) -> None:
        if value == "changethis":
            message = (
                f'The value of {var_name} is "changethis", '
                "for security, please change it, at least for deployments."
            )
            if self.ENVIRONMENT == "local":
                warnings.warn(message, stacklevel=1)
            else:
                raise ValueError(message)

    @model_validator(mode="after")
    def _enforce_non_default_secrets(self) -> Self:
        self._check_default_secret("SECRET_KEY", self.SECRET_KEY)
        self._check_default_secret("POSTGRES_PASSWORD", self.POSTGRES_PASSWORD)
        self._check_default_secret(
            "FIRST_SUPERUSER_PASSWORD", self.FIRST_SUPERUSER_PASSWORD
        )

        return self


settings = Settings()
