"""Task 7.3 测试 — KBManager 流水线 + 上下文拼装"""

import uuid
from unittest.mock import MagicMock

import pytest
from langchain_core.documents import Document

from app.core.knowledge_base.manager import KBManager

KB_ID = "00000000-0000-0000-0000-000000000001"  # 复用同一个测试 UUID


class FakeSession:
    """假数据库会话：只记录 add/commit 被调用了多少次"""

    def __init__(self):
        self.added = []
        self.commits = 0

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commits += 1


class TestGetRetrievalContext:
    def test_formats_source_and_content(self):
        """分块被拼成 [序号] 来源 + 内容"""
        docs = [Document("退货政策…", metadata={"source": "policy.md"})]
        mgr = KBManager(session=FakeSession())
        text = mgr.get_retrieval_context(docs)
        assert "policy.md" in text
        assert "退货政策…" in text

    def test_missing_source_falls_back(self):
        """缺 source 时给默认值，不抛 KeyError"""
        docs = [Document("内容", metadata={})]
        mgr = KBManager(session=FakeSession())
        assert "未知" in mgr.get_retrieval_context(docs)

    def test_empty_results(self):
        """空结果返回占位提示"""
        mgr = KBManager(session=FakeSession())
        assert mgr.get_retrieval_context([]) == "（知识库中无相关匹配）"


class TestUploadDocument:
    @pytest.mark.asyncio
    async def test_upload_sets_done(self, monkeypatch, tmp_path):
        """成功路径：status 变 done，chunks_count=2，并且向量化被调用"""
        from app.core.knowledge_base import manager

        # upload_document 会用 Path(file_path).stat() 读真实文件大小，
        # 所以必须是磁盘上真实存在的文件
        f = tmp_path / "x.txt"
        f.write_text("待解析内容", encoding="utf-8")

        # parse 是 async def，必须用真正的 async 函数替换才能 await
        async def fake_parse(file_path):
            return [Document("原文")]

        monkeypatch.setattr(manager.DocumentParser, "parse", fake_parse)

        # 凭据解析（P9a）要查库，而这里是 FakeSession → 桩掉；
        # 解析结果是否被传给向量库由下面的断言单独盯住
        monkeypatch.setattr(
            manager,
            "resolve_embedding_function",
            lambda session, user_id: "fake-embedding-function",
        )

        fake_store = MagicMock()
        monkeypatch.setattr(
            manager, "VectorStore", MagicMock(return_value=fake_store)
        )
        monkeypatch.setattr(
            manager.Chunkers,
            "recursive_character",
            lambda docs: [Document("块1"), Document("块2")],
        )

        fake = FakeSession()
        mgr = KBManager(session=fake)
        rec = await mgr.upload_document(
            kb_id=uuid.UUID(KB_ID),
            file_path=str(f),
            filename="x.txt",
             user_id=uuid.UUID("00000000-0000-0000-0000-000000000009")
        )

        assert rec.status == "done"
        assert rec.chunks_count == 2
        fake_store.add_documents.assert_called_once()
        # 解析出的向量化函数原样传给向量库（P9a 接线点）
        assert (
            manager.VectorStore.call_args.kwargs["embedding_function"]
            == "fake-embedding-function"
        )

    @pytest.mark.asyncio
    async def test_upload_sets_error_on_failure(self, monkeypatch, tmp_path):
        """失败路径：status 变 error，且异常会向上抛"""
        from app.core.knowledge_base import manager

        f = tmp_path / "x.txt"
        f.write_text("待解析内容", encoding="utf-8")

        async def fail_parse(file_path):
            raise OSError("解析失败")

        monkeypatch.setattr(manager.DocumentParser, "parse", fail_parse)

        fake = FakeSession()
        mgr = KBManager(session=fake)
        with pytest.raises(OSError):
            await mgr.upload_document(
                kb_id=uuid.UUID(KB_ID),
                file_path=str(f),
                filename="x.txt",
                user_id=uuid.UUID("00000000-0000-0000-0000-000000000009")
            )
        # 失败后，fake.added 里那条记录应处于 error 状态
        assert fake.added[0].status == "error"


class TestQuery:
    @pytest.fixture(autouse=True)
    def clear_cache(self):
        """每个测试前后清空模块级缓存，避免测试互相污染"""
        from app.core.knowledge_base import manager
        manager._retriever_cache.clear()
        yield
        manager._retriever_cache.clear()

    def test_query_returns_retriever_results(self, monkeypatch):
        """query：借助 HybridRetriever 做混合检索，返回命中小块"""
        from app.core.knowledge_base import manager

        fake_store = MagicMock()
        monkeypatch.setattr(
            manager, "VectorStore", MagicMock(return_value=fake_store)
        )

        # 语料非空 → 应走到 HybridRetriever
        fake_store.get_all_documents.return_value = [Document("语料")]
        fake_retriever = MagicMock()
        monkeypatch.setattr(
            manager,
            "HybridRetriever",
            MagicMock(return_value=fake_retriever),
        )
        fake_retriever.retrieve.return_value = [Document("命中块")]

        mgr = KBManager(session=FakeSession())
        results = mgr.query(uuid.UUID(KB_ID), "退货规则", top_k=2)

        assert len(results) == 1
        assert results[0].page_content == "命中块"
        fake_retriever.retrieve.assert_called_once_with("退货规则", top_k=2)
        # store 被缓存持有，不能关闭
        fake_store.close.assert_not_called()

    def test_query_empty_corpus_returns_empty(self, monkeypatch):
        """语料为空（知识库刚建好没数据）时返回空，不崩溃"""
        from app.core.knowledge_base import manager

        fake_store = MagicMock()
        monkeypatch.setattr(
            manager, "VectorStore", MagicMock(return_value=fake_store)
        )
        fake_store.get_all_documents.return_value = []

        mgr = KBManager(session=FakeSession())
        results = mgr.query(uuid.UUID(KB_ID), "任意问题")

        assert results == []
        fake_store.close.assert_called_once()

    def test_query_cache_hit_rebuilds_once(self, monkeypatch):
        """连续查两次：HybridRetriever 只构建 1 次（第二次走缓存）"""
        from app.core.knowledge_base import manager

        fake_store = MagicMock()
        fake_store.get_all_documents.return_value = [Document("语料")]
        monkeypatch.setattr(
            manager, "VectorStore", MagicMock(return_value=fake_store)
        )

        fake_retriever = MagicMock()
        fake_retriever.retrieve.return_value = [Document("命中")]
        retriever_cls = MagicMock(return_value=fake_retriever)
        monkeypatch.setattr(manager, "HybridRetriever", retriever_cls)

        mgr = KBManager(session=FakeSession())
        mgr.query(uuid.UUID(KB_ID), "问题一")
        mgr.query(uuid.UUID(KB_ID), "问题二")

        assert retriever_cls.call_count == 1  # 只建了一次索引
        assert fake_retriever.retrieve.call_count == 2  # 但查了两次

    def test_query_threads_user_id_into_credential_resolution(self, monkeypatch):
        """P9a：检索必须带 user_id 才会走用户配的嵌入/重排序模型源"""
        from app.core.knowledge_base import manager

        fake_store = MagicMock()
        fake_store.get_all_documents.return_value = [Document("语料")]
        monkeypatch.setattr(
            manager, "VectorStore", MagicMock(return_value=fake_store)
        )
        monkeypatch.setattr(manager, "HybridRetriever", MagicMock())

        seen = {}

        def fake_embed(session, user_id):
            seen["embed"] = user_id
            return "ef"

        def fake_rerank(session, user_id):
            seen["rerank"] = user_id
            return None

        monkeypatch.setattr(manager, "resolve_embedding_function", fake_embed)
        monkeypatch.setattr(manager, "resolve_rerank_endpoint", fake_rerank)

        uid = uuid.uuid4()
        KBManager(session=FakeSession()).query(
            uuid.UUID(KB_ID), "问题", user_id=uid
        )

        assert seen == {"embed": uid, "rerank": uid}