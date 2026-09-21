"""P5 供应商能力维度：默认源的互斥范围是 (user_id, capability)。

核心不变量：
- 「设为默认」只在**同一能力**内互斥，给 embedding 源设默认不许清掉对话默认源；
- 取默认源必须带 capability 过滤，否则对话链路会拿到嵌入源；
- 删默认源的接替者只从同能力里挑。

用合成的 user_id（不建 User 行），因此在本模块级别关掉外键校验。
"""

import uuid

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.core.agent.provider import ProviderManager
from app.core.db.engine import engine as db_engine
from app.core.db.models import ProviderConfig


# 合成 user_id 需要绕过外键（与 tests/provider/test_manager.py 同款）
@event.listens_for(db_engine, "begin")
def _disable_fk(conn):
    conn.execute(text("SET session_replication_role = 'replica';"))


def _uid() -> uuid.UUID:
    return uuid.uuid4()


def _mk(
    mgr: ProviderManager,
    user_id: uuid.UUID,
    *,
    name: str,
    capability: str = "chat",
    is_default: bool = False,
) -> ProviderConfig:
    return mgr.create_provider(
        user_id=user_id,
        name=name,
        provider_type="openai",
        api_key=f"sk-{name}",
        model_name="test-model",
        capability=capability,
        is_default=is_default,
    )


class TestCapabilityDefaults:
    def test_create_defaults_to_chat(self, db: Session):
        """不传 capability 时落 'chat'（存量调用方的兼容行为）。"""
        mgr = ProviderManager(db)
        obj = _mk(mgr, _uid(), name="legacy")
        assert obj.capability == "chat"

    def test_default_is_per_capability(self, db: Session):
        """同一用户可同时拥有对话默认源与嵌入默认源（互不挤占）。"""
        mgr = ProviderManager(db)
        uid = _uid()
        chat = _mk(mgr, uid, name="c", capability="chat", is_default=True)
        emb = _mk(mgr, uid, name="e", capability="embedding", is_default=True)

        rows = db.exec(
            select(ProviderConfig).where(ProviderConfig.user_id == uid)
        ).all()
        assert {r.capability for r in rows if r.is_default} == {"chat", "embedding"}
        assert chat.is_default is True and emb.is_default is True

    def test_clear_other_defaults_scoped_to_capability(self, db: Session):
        """按能力清默认：给对话源设默认不能动到嵌入默认源。

        clear_other_defaults 只负责「清掉别人的默认」，置真由随后的 update 完成
        （路由层就是这么两步走的），所以这里手动补上置真以还原完整语义。
        """
        mgr = ProviderManager(db)
        uid = _uid()
        chat_a = _mk(mgr, uid, name="c-a", capability="chat", is_default=True)
        chat_b = _mk(mgr, uid, name="c-b", capability="chat", is_default=False)
        emb_a = _mk(mgr, uid, name="e-a", capability="embedding", is_default=True)

        mgr.clear_other_defaults(user_id=uid, keep_id=chat_b.id, capability="chat")
        chat_b.is_default = True
        db.commit()

        db.refresh(chat_a)
        db.refresh(emb_a)
        assert chat_a.is_default is False
        assert emb_a.is_default is True, "跨能力清默认 = 把嵌入默认源误清掉（回归点）"

    def test_get_active_config_filters_capability(self, db: Session):
        """取默认源带能力过滤：只有对话源时取 embedding 必须为空。"""
        mgr = ProviderManager(db)
        uid = _uid()
        _mk(mgr, uid, name="c", capability="chat", is_default=True)
        emb = _mk(mgr, uid, name="e", capability="embedding", is_default=True)

        assert mgr.get_active_config(uid, capability="embedding").id == emb.id
        chat_cfg = mgr.get_active_config(uid, capability="chat")
        assert chat_cfg is not None and chat_cfg.capability == "chat"

        only_chat = _uid()
        _mk(mgr, only_chat, name="c2", capability="chat", is_default=True)
        assert mgr.get_active_config(only_chat, capability="embedding") is None

    def test_list_providers_filters_capability(self, db: Session):
        """列表按能力过滤；不传则返回全部（兼容旧调用方）。"""
        mgr = ProviderManager(db)
        uid = _uid()
        _mk(mgr, uid, name="c", capability="chat")
        _mk(mgr, uid, name="e", capability="embedding")
        _mk(mgr, uid, name="r", capability="rerank")

        assert len(mgr.list_providers(uid)) == 3
        assert [p.name for p in mgr.list_providers(uid, capability="embedding")] == ["e"]
        assert [p.name for p in mgr.list_providers(uid, capability="rerank")] == ["r"]

    def test_delete_default_promotes_same_capability_only(self, db: Session):
        """删对话默认源：接替者只在对话源里挑，绝不把嵌入源顶成对话默认。"""
        mgr = ProviderManager(db)
        uid = _uid()
        chat_a = _mk(mgr, uid, name="c-a", capability="chat", is_default=True)
        chat_b = _mk(mgr, uid, name="c-b", capability="chat")
        emb = _mk(mgr, uid, name="e", capability="embedding", is_default=True)

        assert mgr.delete_provider(chat_a.id) is True

        db.refresh(chat_b)
        db.refresh(emb)
        assert chat_b.is_default is True, "同能力的下一条应接替"
        assert emb.is_default is True, "嵌入默认源不该被牵连"

    def test_delete_default_without_same_capability_successor(self, db: Session):
        """对话源只剩一条且是默认：删掉后对话维度无默认，嵌入默认不受影响。"""
        mgr = ProviderManager(db)
        uid = _uid()
        chat = _mk(mgr, uid, name="c", capability="chat", is_default=True)
        emb = _mk(mgr, uid, name="e", capability="embedding", is_default=True)

        assert mgr.delete_provider(chat.id) is True

        db.refresh(emb)
        assert emb.is_default is True
        assert mgr.get_active_config(uid, capability="chat") is None
        assert mgr.get_active_config(uid, capability="embedding").id == emb.id


class TestCapabilityIndexAtDbLevel:
    def test_same_capability_second_default_rejected(self, db: Session):
        """同一 (user_id, capability) 第二条默认源必须被部分唯一索引拒绝。"""
        mgr = ProviderManager(db)
        uid = _uid()
        _mk(mgr, uid, name="c1", capability="chat", is_default=True)

        dup = ProviderConfig(
            user_id=uid,
            name="c2-dup",
            provider_type="openai",
            capability="chat",
            api_key="enc:v1:test",
            model_name="m",
            is_active=True,
            is_default=True,
        )
        db.add(dup)
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()

    def test_different_capability_defaults_coexist(self, db: Session):
        """不同能力各一条默认是合法状态（索引不能误伤）。"""
        mgr = ProviderManager(db)
        uid = _uid()
        _mk(mgr, uid, name="c", capability="chat", is_default=True)
        stt = _mk(mgr, uid, name="s", capability="stt", is_default=True)
        tts = _mk(mgr, uid, name="t", capability="tts", is_default=True)
        rerank = _mk(mgr, uid, name="r", capability="rerank", is_default=True)

        assert all(p.is_default for p in (stt, tts, rerank))
