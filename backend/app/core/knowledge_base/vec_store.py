"""向量存储 — Milvus 封装

每个知识库对应一个 Milvus collection：
- collection 命名: {MILVUS_COLLECTION_PREFIX}_{kb_id}
- 写入: 分块后的 Document → embedding → Milvus
- 检索: 查询文本 → embedding → 相似度搜索 → top-k Document
"""

from langchain_core.documents import Document
from langchain_milvus import Milvus as MilvusVectorStore
from langchain_openai import OpenAIEmbeddings
from pymilvus import MilvusClient

from app.core.config import settings


def get_embedding_model() -> OpenAIEmbeddings:
    """创建 Embedding 模型实例（SiliconFlow，OpenAI 兼容格式）"""
    return OpenAIEmbeddings(
        model=settings.EMBEDDING_MODEL,
        api_key=settings.EMBEDDING_API_KEY,
        base_url=settings.EMBEDDING_BASE_URL or None,
    )


def _collection_name(kb_id: str) -> str:
    """知识库 ID → collection 名称

    Milvus collection 名只允许字母/数字/下划线，
    因此把 UUID 中的连字符替换为下划线。
    """
    return f"{settings.MILVUS_COLLECTION_PREFIX}_{kb_id.replace('-', '_')}"


class VectorStore:
    """向量存储管理器（每个知识库实例化一个）"""

    def __init__(self, kb_id: str):
        self.kb_id = kb_id
        self.collection_name = _collection_name(kb_id)
        self.client = MilvusClient(uri=settings.MILVUS_URI)

    def _get_store(self) -> MilvusVectorStore:
        """获取 LangChain VectorStore 实例

        注意：每次都新建连接，不缓存。
        MilvusVectorStore 内部维护连接池，短生命周期实例更省心。
        """
        return MilvusVectorStore(
            connection_args={"uri": settings.MILVUS_URI},
            collection_name=self.collection_name,
            embedding_function=get_embedding_model(),
        )

    def add_documents(self, documents: list[Document]) -> list[str]:
        """写入文档块（自动调用 embedding 向量化）

        Returns:
            写入的 ID 列表
        """
        store = self._get_store()
        return store.add_documents(documents)

    def search(self, query: str, top_k: int | None = None) -> list[Document]:
        """相似度搜索

        Args:
            query: 查询文本
            top_k: 返回最相似的 k 条，默认用 settings.KB_TOP_K

        Returns:
            Document 列表（page_content=块内容, metadata 含 source 等）
        """
        if top_k is None:
            top_k = settings.KB_TOP_K
        store = self._get_store()
        return store.similarity_search(query, k=top_k)

    def delete_collection(self) -> None:
        """删除整个 collection（删除知识库时调用）"""
        if self.client.has_collection(self.collection_name):
            self.client.drop_collection(self.collection_name)

    def get_all_documents(self) -> list[Document]:
        """取回 collection 内全部分块

        用途：重建 BM25 关键词索引等需要"整份语料"的场景。
        返回的 metadata 用防御式处理——不假设 metadata 以何种字段存储，
        只保留除主键/正文/向量外的字段作为 metadata。
        """
        if not self.client.has_collection(self.collection_name):
            return []
        self.client.flush(self.collection_name)
        rows = self.client.query(
            collection_name=self.collection_name,
            filter="",  # 空过滤 = 全量
            limit=16384,
        )
        docs = []
        for row in rows:
            text = row.get("text", "")
            meta = {
                k: v
                for k, v in row.items()
                if k not in {"pk", "text", "vector"}
            }
            # 若 metadata 存在且是完整 dict，直接用（避免展开成独立字段的散乱形式）
            if isinstance(meta.get("metadata"), dict):
                meta = meta["metadata"]
            docs.append(Document(page_content=text, metadata=meta))
        return docs

    def count(self) -> int:
        """当前 collection 中的向量数量

        先 flush 确保数据落盘，否则新写入的行可能还没封段，
        get_collection_stats 的 row_count 会暂时是 0。
        """
        if not self.client.has_collection(self.collection_name):
            return 0
        self.client.flush(self.collection_name)
        return self.client.get_collection_stats(self.collection_name)["row_count"]

    def close(self) -> None:
        """关闭连接"""
        self.client.close()

    def delete_by_doc_id ( self, doc_id: str ) -> int :
        """按 doc_id 精准删除某个文档的全部向量块

        Args:
            doc_id: 文档记录的 UUID（字符串形式）

        Returns:
            删除的行数（仅作日志参考，Milvus 对某些版本可能返回 -1）

        注意：只有打了 doc_id 标记的块才能被删到——旧数据（标记机制上线前
        写入的块）没有该字段，匹配不到，只能靠整库删除兜底。
        """
        if not self.client.has_collection(self.collection_name):
            return 0
        res = self.client.delete(
            collection_name = self.collection_name,
            filter=f'doc_id == "{doc_id}"',
        )
        self.client.flush(self.collection_name)
        return res.get("delete_count", 0) if isinstance(res, dict) else 0