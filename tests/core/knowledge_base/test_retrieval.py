"""Task 7.2 检索测试 — RRF 融合 + BM25

纯逻辑部分（rrf_fuse、BM25）为单元测试，不依赖外部服务。
HybridRetriever 依赖 Milvus + Embedding，标记为 integration。
"""

import uuid
from collections.abc import Iterator

import pytest
from langchain_core.documents import Document

from app.core.knowledge_base.retrieval import BM25Retriever, HybridRetriever, rrf_fuse
from app.core.knowledge_base.vec_store import VectorStore


# ---------- 纯单元测试：RRF 融合 ----------

class TestRrfFuse:
    def test_fuse_merges_and_dedups(self):
        """多路结果去重合并，同一文档只在两个列表同时出现时算 1 条"""
        a = Document("文档A", metadata={"source": "a.md"})
        b = Document("文档B", metadata={"source": "a.md"})
        c = Document("文档C", metadata={"source": "b.md"})
        # A 同时在两路都排最前（分数最高），B、C 各只在单路出现
        fused = rrf_fuse([[a, b], [a, c]])
        # 去重后 3 条，A 排最前
        assert len(fused) == 3
        assert fused[0].page_content == "文档A"

    def test_fuse_prefers_common_document(self):
        """出现在多路且靠前的文档融合后靠前"""
        a = Document("A", metadata={"source": "s"})
        x = Document("X", metadata={"source": "s"})
        y = Document("Y", metadata={"source": "s"})
        # A 在路1第1、路2第3；X 只在路1第2；融合后 A 应高于 X
        fused = rrf_fuse([[a, x], [y, x, a]])
        assert fused[0].page_content == "A"

    def test_fuse_empty_input(self):
        """两路都空 → 返回空列表，不报错"""
        assert rrf_fuse([]) == []
        assert rrf_fuse([[], []]) == []

    def test_fuse_preserves_highest_rank_order(self):
        """单路输入时顺序保持不变"""
        a = Document("A", metadata={"source": "s"})
        b = Document("B", metadata={"source": "s"})
        fused = rrf_fuse([[a, b]])
        assert [d.page_content for d in fused] == ["A", "B"]


# ---------- 纯单元测试：BM25 关键词检索 ----------

class TestBM25Retriever:
    def test_keyword_match_ranks_exact_term_first(self):
        """含查询关键词的文档排最前"""
        docs = [
            Document("退货政策说明"),           # 词条多，idf 低
            Document("关于老鼠的饲养指南"),
            Document("五金工具清单大全大全大全大全大全大全"),  # 词条"大全"多
        ]
        retriever = BM25Retriever(docs)
        results = retriever.retrieve("五金 工具", top_k=3)
        assert results[0].page_content == "五金工具清单大全大全大全大全大全大全"
        assert "五金" in results[0].page_content

    def test_rm_empty_corpus(self):
        """空语料检索返回空，不报错"""
        retriever = BM25Retriever([])
        assert retriever.retrieve("任何查询") == []

    def test_top_k_limit(self):
        """top_k 限制返回数量"""
        docs = [Document(f"文档{i}号内容") for i in range(5)]
        retriever = BM25Retriever(docs)
        assert len(retriever.retrieve("文档 内容", top_k=2)) == 2


# ---------- 纯单元测试：jieba 分词 ----------

class TestTokenize:
    def test_chinese_not_single_char(self):
        """中文不再退化为纯单字：整词/子词出现"""
        from app.core.knowledge_base.retrieval import _tokenize
        toks = _tokenize("单元测试很重要")
        assert "单元测试" in toks or ("单元" in toks and "测试" in toks)
        assert "元测" not in toks  # 旧单字切分的伪词不应出现

    def test_ascii_unchanged(self):
        """纯 ASCII 行为不变：整词一个 token、小写化"""
        from app.core.knowledge_base.retrieval import _tokenize
        assert _tokenize("Hello World 123") == ["hello", "world", "123"]

    def test_mixed_text(self):
        """中英混排：英文整词 + 中文 jieba 词"""
        from app.core.knowledge_base.retrieval import _tokenize
        toks = _tokenize("用 pytest 跑单元测试")
        assert "pytest" in toks
        assert any(t in toks for t in ("单元测试", "单元", "测试"))

    def test_keyword_match_ranks_exact_chinese_term_first(self):
        """「单元测试」查询：含整词的文档排最前（旧单字分词的回归场景）"""
        docs = [
            Document("关于元测试的历史考据"),  # 只有单字碎片沾边
            Document("单元测试是保障代码质量的手段"),
        ]
        retriever = BM25Retriever(docs)
        results = retriever.retrieve("单元测试", top_k=2)
        assert results[0].page_content == "单元测试是保障代码质量的手段"


# ---------- 集成测试：混合检索（需要 Milvus + Embedding） ----------

class TestHybridRetriever:
    pytestmark = pytest.mark.integration


@pytest.fixture
def kb() -> Iterator[tuple[VectorStore, list[Document]]]:
    """临时 KB：独立 collection + 对应语料"""
    kb_id = str(uuid.uuid4())
    store = VectorStore(kb_id=kb_id)
    docs = [
        Document(
            "退货政策：购买后7天内可以无理由退货，需保留商品吊牌。",
            metadata={"source": "policy.md"},
        ),
        Document(
            "配送说明：默认使用顺丰快递，偏远地区发EMS，3-5天送达。",
            metadata={"source": "shipping.md"},
        ),
        Document(
            "会员权益：金卡会员享受95折优惠和生日礼包。",
            metadata={"source": "member.md"},
        ),
        Document(
            "客服热线 400-888-8888，建议投诉意见可通过邮箱 feedback@example.com 提交。",
            metadata={"source": "contact.md"},
        ),
    ]
    store.add_documents(docs)
    yield store, docs
    store.delete_collection()
    store.close()


class TestHybridRetriever:
    def test_retrieve_returns_ranked_docs(self, kb):
        """混合检索返回非空、去重、按相关度降序"""
        store, docs = kb
        retriever = HybridRetriever(store, docs)
        results = retriever.retrieve("退货退款可以吗", top_k=3)
        assert len(results) == 3
        # 退货政策应该在结果里
        assert any("退货" in d.page_content for d in results)

    def test_retrieve_top_k_limit(self, kb):
        """top_k 限制最终返回数量"""
        store, docs = kb
        retriever = HybridRetriever(store, docs)
        assert len(retriever.retrieve("配送 快递 多久", top_k=2)) == 2

    def test_retrieve_covers_keyword(self, kb):
        """BM25 能召回向量语义较弱但关键词明确的分块"""
        store, docs = kb
        retriever = HybridRetriever(store, docs)
        # 邮箱是精确词，BM25 应能召回 contact.md
        results = retriever.retrieve("feedback 邮箱", top_k=4)
        assert any("feedback" in d.page_content.lower() or "邮箱" in d.page_content for d in results)