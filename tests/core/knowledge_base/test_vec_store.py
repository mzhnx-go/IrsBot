"""Task 7.2 集成测试 — 向量存储 (Milvus + SiliconFlow Embedding)

真实依赖：Milvus Docker + SiliconFlow API，用 @pytest.mark.integration 标记。
测试用随机 kb_id 建独立 collection，结束时删除，不留垃圾。
"""

import uuid
from collections.abc import Iterator

import pytest
from langchain_core.documents import Document

from app.core.knowledge_base.vec_store import VectorStore, get_embedding_model

pytestmark = pytest.mark.integration

@pytest.fixture
def store() -> Iterator[VectorStore]:
    """每个测试一个独立的 VectorStore（随机 kb_id → 独立 collection）"""
    s = VectorStore(kb_id=str(uuid.uuid4()))
    yield s
    # teardown：清理测试 collection + 关闭连接
    s.delete_collection()
    s.close()

class TestEmbedding:
    def test_embed_query_dim(self):
        """Embedding 返回 1024 维向量（bge-m3 的固定维度）"""
        model = get_embedding_model()
        vec = model.embed_query("测试文本")
        assert len(vec) == 1024
        assert any(abs(x) > 0 for x in vec)  # 不是全零

    def test_embed_batch(self):
        """批量 embedding：顺序和输入一致"""
        model = get_embedding_model()
        vecs = model.embed_documents(["第一句", "第二句", "第三句"])
        assert len(vecs) == 3
        assert all(len(v) == 1024 for v in vecs)

class TestVectorStore:
    def test_add_and_search(self, store):
        """核心流程：写入 → 相似度搜索 → 命中最相关的块"""
        docs = [
            Document(
                page_content="退货政策：购买后7天内可以无理由退货，需保留商品吊牌。",
                metadata={"source": "policy.md"},
            ),
            Document(
                page_content="配送说明：默认使用顺丰快递，偏远地区发EMS，3-5天送达。",
                metadata={"source": "shipping.md"},
            ),
            Document(
                page_content="会员权益：金卡会员享受95折优惠和生日礼包。",
                metadata={"source": "member.md"},
            ),
        ]
        store.add_documents(docs)

        # 等待 Milvus 数据可见（写入有轻微延迟）
        import time
        for _ in range(10):
            if store.count() >= 3:
                break
            time.sleep(0.5)
        assert store.count() == 3

        # 检索：问退货，应该命中文档1
        results = store.search("退货退款可以吗", top_k=1)
        assert len(results) == 1
        assert "退货" in results[0].page_content
        assert results[0].metadata["source"] == "policy.md"

    def test_search_relevance_order(self, store):
        """检索排序：最相关的排最前"""
        docs = [
            Document(page_content="Python 是一种解释型编程语言。"),
            Document(page_content="Java 是一种面向对象的编程语言。"),
            Document(page_content="红烧肉的做法：五花肉焯水后加冰糖炒糖色。"),
        ]
        store.add_documents(docs)

        import time
        for _ in range(10):
            if store.count() >= 3:
                break
            time.sleep(0.5)

        results = store.search("怎么做好吃的红烧肉", top_k=3)
        # 菜谱应该排第一（最相关）
        assert "红烧肉" in results[0].page_content

    def test_search_top_k_limit(self, store):
        """top_k 限制返回数量"""
        docs = [
            Document(page_content=f"测试文档第 {i} 号，内容各不相同。")
            for i in range(5)
        ]
        store.add_documents(docs)

        import time
        for _ in range(10):
            if store.count() >= 5:
                break
            time.sleep(0.5)

        assert len(store.search("测试文档", top_k=2)) == 2

    def test_count_empty_collection(self, store):
        """空 collection（未写入过）count 为 0，不报错"""
        assert store.count() == 0

    def test_delete_collection(self, store):
        """删除 collection 后 count 归零"""
        store.add_documents([Document(page_content="待删除的内容")])
        store.delete_collection()
        assert store.count() == 0

    def test_metadata_preserved(self, store):
        """metadata 写入后被保留（检索结果带来源）"""
        store.add_documents(
            [Document(page_content="带元数据的内容", metadata={"source": "test.md", "page": 2})]
        )

        import time
        for _ in range(10):
            if store.count() >= 1:
                break
            time.sleep(0.5)

        results = store.search("带元数据", top_k=1)
        assert results[0].metadata["source"] == "test.md"
        assert results[0].metadata["page"] == 2

    def test_get_all_documents(self, store):
        """取回全部分块，作为 BM25 重建语料的数据源"""
        store.add_documents(
            [
                Document(
                    page_content="退货政策：7天内无理由退货。",
                    metadata={"source": "policy.md"},
                ),
                Document(
                    page_content="配送说明：顺丰快递3-5天送达。",
                    metadata={"source": "shipping.md"},
                ),
            ]
        )

        import time
        for _ in range(10):
            if store.count() >= 2:
                break
            time.sleep(0.5)

        docs = store.get_all_documents()
        contents = " ".join(d.page_content for d in docs)
        assert len(docs) == 2
        assert "退货政策" in contents
        assert "配送说明" in contents