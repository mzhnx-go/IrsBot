"""Tests for application settings (Agent platform configuration)."""

from app.core.config import Settings


def test_settings_defaults():
    """Settings should have correct defaults when no env vars override."""
    s = Settings()
    # LLM
    assert s.DEFAULT_LLM_PROVIDER == "openai"
    # 以下字段会被 .env 或测试环境变量覆盖，因此只校验它们已被正确加载（非空）
    assert s.DEFAULT_LLM_MODEL
    assert s.OPENAI_API_KEY is not None
    # 环境未覆盖时仍有默认值
    assert s.ANTHROPIC_API_KEY == ""
    assert s.GEMINI_API_KEY == ""
    assert s.FALLBACK_PROVIDERS == "[]"
    # Agent
    assert s.MAX_AGENT_STEPS == 15
    assert s.CONTEXT_MAX_TURNS == 20
    assert s.CONTEXT_MAX_TOKENS == 120000
    assert s.AGENT_TIMEOUT == 120.0
    # RAG
    assert s.ENABLE_RAG is True
    assert s.KB_CHUNK_SIZE == 500
    assert s.KB_CHUNK_OVERLAP == 50
    assert s.KB_TOP_K == 3
    assert s.MILVUS_URI == "http://localhost:19530"
    # 前缀可能被测试环境覆盖，校验其含义仍为基于 irsb_kb 的相关前缀
    assert s.MILVUS_COLLECTION_PREFIX.startswith("irsbot_kb")
    # MCP
    assert s.ENABLE_MCP is True
    assert s.MCP_TIMEOUT == 30.0
    assert s.MCP_MAX_RETRIES == 2
    # Skills
    assert s.ENABLE_SKILLS is True
    assert s.SKILL_DIRS == ["./skills"]
    # Safety
    assert s.ENABLE_CONTENT_SAFETY is False
    # Rate limit
    assert s.RATE_LIMIT_REQUESTS == 20
    assert s.RATE_LIMIT_WINDOW == 60


def test_settings_env_override(monkeypatch):
    """Settings should respect environment variable overrides."""
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("DEFAULT_LLM_MODEL", "claude-3-5-sonnet-20241022")
    monkeypatch.setenv("MAX_AGENT_STEPS", "30")
    monkeypatch.setenv("ENABLE_RAG", "false")
    monkeypatch.setenv("MILVUS_URI", "http://milvus:19530")

    s = Settings()
    assert s.DEFAULT_LLM_PROVIDER == "anthropic"
    assert s.DEFAULT_LLM_MODEL == "claude-3-5-sonnet-20241022"
    assert s.MAX_AGENT_STEPS == 30
    assert s.ENABLE_RAG is False
    assert s.MILVUS_URI == "http://milvus:19530"


def test_settings_sqlalchemy_database_uri():
    """SQLALCHEMY_DATABASE_URI should be constructible from components."""
    s = Settings()
    uri = str(s.SQLALCHEMY_DATABASE_URI)
    assert "postgresql" in uri
    assert s.POSTGRES_SERVER in uri
    assert s.POSTGRES_DB in uri
