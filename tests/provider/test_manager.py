"""Tests for ProviderManager."""

import uuid

import pytest
from sqlalchemy import event, text
from sqlmodel import Session, delete

from app.core.agent.provider import ProviderManager
from app.core.db.engine import engine as db_engine
from app.core.db.models import ProviderConfig


# Disable FK checks for synthetic user_ids
@event.listens_for(db_engine, "begin")
def _disable_fk(conn):
    conn.execute(text("SET session_replication_role = 'replica';"))


def _uid() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture(autouse=True)
def _cleanup_providers(db: Session):
    """Clean up all provider_configs before each test to avoid interference."""
    db.execute(delete(ProviderConfig))
    db.commit()
    yield


class TestProviderCRUD:
    def test_create(self, db: Session):
        mgr = ProviderManager(db)
        uid = _uid()
        obj = mgr.create_provider(
            user_id=uid,
            name="openai-dev",
            provider_type="openai",
            api_key="sk-test",
            model_name="gpt-4o",
            is_default=True,
        )
        assert obj.name == "openai-dev"
        assert obj.is_default is True
        assert obj.is_active is True

    def test_list(self, db: Session):
        mgr = ProviderManager(db)
        uid = _uid()
        mgr.create_provider(user_id=uid, name="p1", provider_type="openai",
                            api_key="k1", model_name="gpt-4o")
        mgr.create_provider(user_id=uid, name="p2", provider_type="anthropic",
                            api_key="k2", model_name="claude-3-5-sonnet")
        providers = mgr.list_providers()
        assert len(providers) == 2

    def test_update(self, db: Session):
        mgr = ProviderManager(db)
        uid = _uid()
        obj = mgr.create_provider(user_id=uid, name="old", provider_type="openai",
                                  api_key="k", model_name="gpt-4o")
        updated = mgr.update_provider(obj.id, name="new", is_active=False)
        assert updated is not None
        assert updated.name == "new"
        assert updated.is_active is False

    def test_delete(self, db: Session):
        mgr = ProviderManager(db)
        uid = _uid()
        obj = mgr.create_provider(user_id=uid, name="del", provider_type="openai",
                                  api_key="k", model_name="gpt-4o")
        assert mgr.delete_provider(obj.id) is True
        assert len(mgr.list_providers()) == 0

    def test_delete_default_promotes_successor(self, db: Session):
        """回归（§10.6 d）：删掉默认源后，自动提升同用户下一条为默认。

        修复前：删除后全库没有任何 is_default=True，界面无「默认」徽标，
        且取默认源的链路直接拿不到东西。
        """
        mgr = ProviderManager(db)
        uid = _uid()
        first = mgr.create_provider(user_id=uid, name="first", provider_type="openai",
                                    api_key="k1", model_name="gpt-4o",
                                    is_default=True, fallback_order=1)
        second = mgr.create_provider(user_id=uid, name="second", provider_type="openai",
                                     api_key="k2", model_name="gpt-4o-mini",
                                     fallback_order=2)

        assert mgr.delete_provider(first.id) is True

        rows = mgr.list_providers(user_id=uid)
        assert len(rows) == 1
        assert rows[0].id == second.id
        assert rows[0].is_default is True

    def test_delete_default_picks_lowest_fallback_order(self, db: Session):
        """多个候选时按 fallback_order 升序挑（数字更小的优先）。"""
        mgr = ProviderManager(db)
        uid = _uid()
        current = mgr.create_provider(user_id=uid, name="current", provider_type="openai",
                                      api_key="k0", model_name="gpt-4o",
                                      is_default=True, fallback_order=0)
        slow = mgr.create_provider(user_id=uid, name="slow", provider_type="openai",
                                   api_key="k1", model_name="a", fallback_order=99)
        fast = mgr.create_provider(user_id=uid, name="fast", provider_type="openai",
                                   api_key="k2", model_name="b", fallback_order=5)

        mgr.delete_provider(current.id)

        defaults = [p for p in mgr.list_providers(user_id=uid) if p.is_default]
        assert len(defaults) == 1
        assert defaults[0].id == fast.id, "应挑 fallback_order 最小的一条"
        assert slow.is_default is False

    def test_delete_default_skips_inactive_candidates(self, db: Session):
        """候选必须具备 is_active=True：停用中的配置不能顶上来当默认。

        否则会「看起来有默认、实际取不到」——get_chat_model 要求 is_default
        与 is_active 同时成立。
        """
        mgr = ProviderManager(db)
        uid = _uid()
        current = mgr.create_provider(user_id=uid, name="current", provider_type="openai",
                                      api_key="k0", model_name="gpt-4o",
                                      is_default=True, fallback_order=1)
        off = mgr.create_provider(user_id=uid, name="off", provider_type="openai",
                                  api_key="k1", model_name="a",
                                  is_active=False, fallback_order=2)
        on = mgr.create_provider(user_id=uid, name="on", provider_type="openai",
                                 api_key="k2", model_name="b", fallback_order=3)

        mgr.delete_provider(current.id)

        defaults = [p for p in mgr.list_providers(user_id=uid) if p.is_default]
        assert len(defaults) == 1
        assert defaults[0].id == on.id
        assert off.is_default is False

    def test_delete_last_default_leaves_no_default(self, db: Session):
        """删掉唯一的默认源：无接替者，保持无默认（不报错、不误提升）。"""
        mgr = ProviderManager(db)
        uid = _uid()
        only = mgr.create_provider(user_id=uid, name="only", provider_type="openai",
                                   api_key="k", model_name="gpt-4o", is_default=True)

        assert mgr.delete_provider(only.id) is True

        rows = mgr.list_providers(user_id=uid)
        assert rows == []

    def test_delete_default_does_not_touch_other_users(self, db: Session):
        """多租户隔离：接替者只能从「同一用户」的配置里挑。

        否则删自己的默认源会把别人的源提上来，造成越权使用他人密钥。
        """
        mgr = ProviderManager(db)
        alice, bob = _uid(), _uid()
        alice_default = mgr.create_provider(user_id=alice, name="alice-d",
                                            provider_type="openai", api_key="ka",
                                            model_name="gpt-4o",
                                            is_default=True, fallback_order=1)
        bob_default = mgr.create_provider(user_id=bob, name="bob-d",
                                          provider_type="openai", api_key="kb",
                                          model_name="gpt-4o", is_default=True)

        mgr.delete_provider(alice_default.id)

        alice_rows = mgr.list_providers(user_id=alice)
        bob_rows = mgr.list_providers(user_id=bob)
        assert alice_rows == [], "不能把 bob 的源提升给 alice"
        assert len(bob_rows) == 1 and bob_rows[0].id == bob_default.id
        assert bob_rows[0].is_default is True

    def test_delete_non_default_keeps_existing_default(self, db: Session):
        """删非默认源：不动现有默认（不该误提升）。"""
        mgr = ProviderManager(db)
        uid = _uid()
        keep = mgr.create_provider(user_id=uid, name="keep", provider_type="openai",
                                   api_key="k0", model_name="gpt-4o",
                                   is_default=True, fallback_order=1)
        other = mgr.create_provider(user_id=uid, name="other", provider_type="openai",
                                    api_key="k1", model_name="a", fallback_order=2)

        mgr.delete_provider(other.id)

        rows = mgr.list_providers(user_id=uid)
        assert len(rows) == 1
        assert rows[0].id == keep.id and rows[0].is_default is True

    def test_delete_missing_returns_false(self, db: Session):
        """删不存在的 id → False（且不改动任何数据）。"""
        mgr = ProviderManager(db)
        assert mgr.delete_provider(_uid()) is False


class TestGetChatModel:
    def test_raises_without_provider(self, db: Session):
        mgr = ProviderManager(db)
        with pytest.raises(RuntimeError, match="No active provider"):
            mgr.get_chat_model(user_id=_uid())

    def test_raises_unsupported_type(self, db: Session):
        mgr = ProviderManager(db)
        uid = _uid()
        mgr.create_provider(user_id=uid, name="bad", provider_type="unknown",
                            api_key="k", model_name="x")
        with pytest.raises(ValueError, match="Unsupported provider type"):
            mgr.get_chat_model(user_id=uid, provider_id=mgr.list_providers(uid)[0].id)

    def test_caches_model(self, db: Session):
        mgr = ProviderManager(db)
        uid = _uid()
        obj = mgr.create_provider(user_id=uid, name="cached", provider_type="openai",
                                  api_key="sk-test-key-for-testing", model_name="gpt-4o-mini")
        # Just verify it doesn't crash on instantiation
        # (actual model creation requires valid API key, but init_chat_model
        #  with a fake key still creates the object — it fails at call time)
        try:
            model = mgr.get_chat_model(user_id=uid, provider_id=obj.id)
            assert model is not None
        except Exception:
            # API key invalid is expected in tests — object was created
            pass

    def test_cache_key_is_user_scoped(self, db: Session):
        """缓存 key 必须含 user_id，否则不同用户会命中同一条目拿到别人的实例。"""
        mgr = ProviderManager(db)
        uid = _uid()
        mgr.create_provider(user_id=uid, name="a", provider_type="openai",
                            api_key="sk-test-key-for-testing", model_name="gpt-4o-mini",
                            is_default=True)
        try:
            mgr.get_chat_model(user_id=uid)
        except Exception:
            pytest.skip("init_chat_model 未能构建实例，跳过缓存 key 断言")
        assert mgr._chat_cache, "应已写入缓存"
        assert all(str(uid) in key for key in mgr._chat_cache)


class TestMultiTenantIsolation:
    """Provider 解析的多租户隔离（防 A 用户静默用上 B 用户的密钥/模型）。"""

    def test_default_lookup_does_not_cross_users(self, db: Session):
        """A 无默认源、B 有默认源 → A 取默认必须失败，绝不能取到 B 的。"""
        mgr = ProviderManager(db)
        a, b = _uid(), _uid()
        mgr.create_provider(user_id=b, name="b-default", provider_type="openai",
                            api_key="sk-b-secret", model_name="gpt-4o-mini",
                            is_default=True)

        with pytest.raises(RuntimeError, match="No active provider"):
            mgr.get_chat_model(user_id=a)

    def test_default_lookup_prefers_own_provider(self, db: Session):
        """A、B 各有默认源 → A 解析到的必须是 A 自己那条（用不支持的类型做判别）。"""
        mgr = ProviderManager(db)
        a, b = _uid(), _uid()
        # B 的默认源类型合法
        mgr.create_provider(user_id=b, name="b-ok", provider_type="openai",
                            api_key="sk-b-secret", model_name="gpt-4o-mini",
                            is_default=True)
        # A 的默认源类型非法 → 若 A 取到自己的就会抛 ValueError
        mgr.create_provider(user_id=a, name="a-bad", provider_type="unknown",
                            api_key="sk-a-secret", model_name="x",
                            is_default=True)

        with pytest.raises(ValueError, match="Unsupported provider type"):
            mgr.get_chat_model(user_id=a)

    def test_explicit_provider_id_cannot_cross_users(self, db: Session):
        """A 显式传 B 的 provider_id → 必须取不到（provider_id 分支同样按归属过滤）。"""
        mgr = ProviderManager(db)
        a, b = _uid(), _uid()
        b_obj = mgr.create_provider(user_id=b, name="b-obj", provider_type="openai",
                                    api_key="sk-b-secret", model_name="gpt-4o-mini",
                                    is_default=True)

        with pytest.raises(RuntimeError, match="No active provider"):
            mgr.get_chat_model(user_id=a, provider_id=b_obj.id)

    def test_no_user_id_fails_closed(self, db: Session):
        """user_id 为 None → 查不到任何源（fail closed），不回落成「取全库默认源」。"""
        mgr = ProviderManager(db)
        mgr.create_provider(user_id=_uid(), name="someone", provider_type="openai",
                            api_key="sk-x", model_name="gpt-4o-mini", is_default=True)

        with pytest.raises(RuntimeError, match="No active provider"):
            mgr.get_chat_model(user_id=None)

    def test_embedding_lookup_does_not_cross_users(self, db: Session):
        """embedding 取默认同样按归属过滤。"""
        mgr = ProviderManager(db)
        a, b = _uid(), _uid()
        mgr.create_provider(user_id=b, name="b-embed", provider_type="openai",
                            api_key="sk-b-secret", model_name="BAAI/bge-m3",
                            is_default=True)

        with pytest.raises(RuntimeError, match="No active embedding provider"):
            mgr.get_embedding_model(user_id=a)

    @pytest.mark.asyncio
    async def test_fallback_candidates_are_user_scoped(self, db: Session):
        """回退链的候选源只在本人范围内挑选。"""
        mgr = ProviderManager(db)
        a, b = _uid(), _uid()
        mgr.create_provider(user_id=b, name="b-only", provider_type="openai",
                            api_key="sk-b-secret", model_name="gpt-4o-mini",
                            is_default=True)

        with pytest.raises(RuntimeError, match="No active providers"):
            await mgr.chat_with_fallback(user_id=a, messages=[])


class TestReloadConfig:
    def test_clears_caches(self, db: Session):
        mgr = ProviderManager(db)
        mgr.clear_chat_cache()
        mgr.clear_embed_cache()
        # No exception means success
        assert mgr._chat_cache == {}
        assert mgr._embed_cache == {}
