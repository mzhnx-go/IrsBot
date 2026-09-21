"""RAG 凭据解析（P9a）单元测试 —— Provider 优先、.env 兜底。

用例全部用假凭据（`sk-test-*`）与合成 user_id，不碰真实上游。
"""

import logging
import uuid

import pytest
from sqlalchemy import event, text
from sqlmodel import Session, delete

from app.core.config import settings
from app.core.db.engine import engine as db_engine
from app.core.db.models import ProviderConfig, ProviderKey
from app.core.knowledge_base import endpoints
from app.core.knowledge_base.endpoints import (
    RerankEndpoint,
    env_rerank_endpoint,
    resolve_embedding_function,
    resolve_rerank_endpoint,
)


@event.listens_for(db_engine, "begin")
def _disable_fk(conn):
    conn.execute(text("SET session_replication_role = 'replica';"))


@pytest.fixture(autouse=True)
def _cleanup(db: Session):
    db.execute(delete(ProviderKey))
    db.execute(delete(ProviderConfig))
    db.commit()
    yield


@pytest.fixture(autouse=True)
def _env_creds(monkeypatch):
    """统一的 .env 兜底凭据（用例内可单独覆盖）"""
    monkeypatch.setattr(settings, "EMBEDDING_API_KEY", "sk-env-key", raising=False)
    monkeypatch.setattr(
        settings, "EMBEDDING_BASE_URL", "https://env.example.com/v1", raising=False
    )
    monkeypatch.setattr(settings, "EMBEDDING_MODEL", "env-embed-model", raising=False)
    monkeypatch.setattr(settings, "RERANK_MODEL", "env-rerank-model", raising=False)
    monkeypatch.setattr(settings, "ENABLE_RERANK", True)


def _mk(
    db: Session,
    user_id: uuid.UUID,
    *,
    name: str,
    capability: str,
    model_name: str,
    base_url: str | None = None,
    is_default: bool = True,
    is_active: bool = True,
) -> ProviderConfig:
    from app.core.agent.provider import ProviderManager

    return ProviderManager(db).create_provider(
        user_id=user_id,
        name=name,
        provider_type="openai",
        api_key=f"sk-{name}",
        model_name=model_name,
        base_url=base_url,
        capability=capability,
        is_default=is_default,
        is_active=is_active,
    )


class TestEnvFallback:
    def test_env_embedding_uses_settings(self):
        embed = endpoints.env_embedding_function()
        assert embed.model == "env-embed-model"
        assert "env.example.com" in str(embed.openai_api_base)

    def test_env_rerank_none_when_switch_off(self, monkeypatch):
        monkeypatch.setattr(settings, "ENABLE_RERANK", False)
        assert env_rerank_endpoint() is None

    def test_env_rerank_none_without_key(self, monkeypatch):
        monkeypatch.setattr(settings, "EMBEDDING_API_KEY", "", raising=False)
        assert env_rerank_endpoint() is None

    def test_env_rerank_uses_settings_and_default_base(self, monkeypatch):
        monkeypatch.setattr(settings, "EMBEDDING_BASE_URL", "", raising=False)
        ep = env_rerank_endpoint()
        assert ep is not None
        assert ep.api_key == "sk-env-key"
        assert ep.model == "env-rerank-model"
        assert ep.base_url == endpoints.DEFAULT_EMBEDDING_BASE_URL

    def test_env_rerank_strips_trailing_slash(self, monkeypatch):
        # 拼 URL 时会再拼 /rerank，留着尾斜杠会得到 //rerank
        monkeypatch.setattr(
            settings, "EMBEDDING_BASE_URL", "https://x.example.com/v1/", raising=False
        )
        assert env_rerank_endpoint().base_url == "https://x.example.com/v1"

    def test_no_user_never_touches_provider_table(self, db: Session):
        """user_id=None 时直接用 .env，不去查库挑「全库任意默认源」"""
        _mk(db, uuid.uuid4(), name="someone", capability="embedding",
            model_name="other-embed")
        embed = resolve_embedding_function(db, None)
        assert embed.model == "env-embed-model"
        assert resolve_rerank_endpoint(db, None).model == "env-rerank-model"


class TestEmbeddingResolution:
    def test_prefers_user_embedding_default(self, db: Session):
        uid = uuid.uuid4()
        _mk(db, uid, name="emb", capability="embedding",
            model_name="BAAI/bge-m3", base_url="https://embed.example.com/v1")
        embed = resolve_embedding_function(db, uid)
        assert embed.model == "BAAI/bge-m3"
        assert "embed.example.com" in str(embed.openai_api_base)

    def test_chat_default_is_not_used_as_embedding_source(self, db: Session):
        """回归：不带 capability 过滤时会把对话默认源当嵌入源（P5 之前的老 bug）"""
        uid = uuid.uuid4()
        _mk(db, uid, name="chat", capability="chat", model_name="agnes-3.0-flash")
        embed = resolve_embedding_function(db, uid)
        assert embed.model == "env-embed-model"

    def test_falls_back_when_source_deactivated(self, db: Session):
        uid = uuid.uuid4()
        _mk(db, uid, name="emb", capability="embedding", model_name="BAAI/bge-m3",
            is_active=False)
        assert resolve_embedding_function(db, uid).model == "env-embed-model"

    def test_falls_back_when_type_unsupported(self, db: Session):
        """嵌入源类型不支持（如 gemini）时降级，不把整条链路打挂"""
        from app.core.agent.provider import ProviderManager

        uid = uuid.uuid4()
        ProviderManager(db).create_provider(
            user_id=uid, name="gemini-emb", provider_type="gemini",
            api_key="sk-g", model_name="text-embedding-004",
            capability="embedding", is_default=True,
        )
        assert resolve_embedding_function(db, uid).model == "env-embed-model"

    def test_other_users_source_is_invisible(self, db: Session):
        mine, other = uuid.uuid4(), uuid.uuid4()
        _mk(db, other, name="emb", capability="embedding", model_name="BAAI/bge-m3")
        assert resolve_embedding_function(db, mine).model == "env-embed-model"


class TestRerankResolution:
    def test_prefers_provider_even_when_env_switch_off(self, db: Session, monkeypatch):
        """用户显式配了 rerank 源就用它 —— ENABLE_RERANK 只管 .env 那套"""
        monkeypatch.setattr(settings, "ENABLE_RERANK", False)
        uid = uuid.uuid4()
        _mk(db, uid, name="rr", capability="rerank",
            model_name="BAAI/bge-reranker-v2-m3", base_url="https://rr.example.com/v1")
        ep = resolve_rerank_endpoint(db, uid)
        assert ep == RerankEndpoint(
            api_key="sk-rr",
            base_url="https://rr.example.com/v1",
            model="BAAI/bge-reranker-v2-m3",
        )

    def test_provider_without_base_url_uses_default(self, db: Session):
        """多数重排序上游与对话同址：没填 API 地址时按 SiliconFlow 默认拼"""
        uid = uuid.uuid4()
        _mk(db, uid, name="rr", capability="rerank", model_name="reranker-x")
        ep = resolve_rerank_endpoint(db, uid)
        assert ep.base_url == endpoints.DEFAULT_EMBEDDING_BASE_URL

    def test_falls_back_to_env_when_no_provider(self, db: Session):
        uid = uuid.uuid4()
        _mk(db, uid, name="chat", capability="chat", model_name="agnes-3.0-flash")
        assert resolve_rerank_endpoint(db, uid) == env_rerank_endpoint()

    def test_all_keys_cooling_falls_back_to_env(self, db: Session):
        """源的 Key 全在冷却中时降级，不让检索直接报错"""
        from datetime import timedelta

        from sqlmodel import select

        from app.core.db.sqlmodel_models import get_datetime_utc

        uid = uuid.uuid4()
        pc = _mk(db, uid, name="rr", capability="rerank", model_name="reranker-x")
        key_row = db.exec(
            select(ProviderKey).where(ProviderKey.provider_id == pc.id)
        ).one()
        key_row.cooldown_until = get_datetime_utc() + timedelta(minutes=5)
        db.add(key_row)
        db.commit()

        assert resolve_rerank_endpoint(db, uid) == env_rerank_endpoint()


class TestMigrationHint:
    def _hint_logs(self, caplog, monkeypatch, key: str, base: str) -> list[str]:
        monkeypatch.setattr(settings, "EMBEDDING_API_KEY", key, raising=False)
        monkeypatch.setattr(settings, "EMBEDDING_BASE_URL", base, raising=False)
        with caplog.at_level(logging.INFO, logger=endpoints.__name__):
            endpoints.log_embedding_migration_hint()
        return [r.message for r in caplog.records]

    def test_logs_when_both_present(self, caplog, monkeypatch):
        logs = self._hint_logs(caplog, monkeypatch, "sk-x", "https://x/v1")
        assert any("EMBEDDING_API_KEY" in m for m in logs)

    def test_silent_when_key_missing(self, caplog, monkeypatch):
        assert self._hint_logs(caplog, monkeypatch, "", "https://x/v1") == []

    def test_silent_when_base_missing(self, caplog, monkeypatch):
        assert self._hint_logs(caplog, monkeypatch, "sk-x", "") == []
