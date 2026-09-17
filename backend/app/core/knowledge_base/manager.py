"""Task 7.3 知识库管理器 — 把解析/分块/向量化/检索串成流水线"""

import uuid
from pathlib import Path

from langchain_core.documents import Document  # 这是"分块"
from sqlalchemy.orm import Session

from app.core.db.models import Document as DocumentRecord  # 这是"数据库记录"
from app.core.knowledge_base.chunkers import Chunkers
from app.core.knowledge_base.parsers import DocumentParser
from app.core.knowledge_base.retrieval import HybridRetriever
from app.core.knowledge_base.vec_store import VectorStore

# BM25 检索器缓存：kb_id → 建好索引的混合检索器
# 语料未变化时复用，避免每次查询都拉全量语料 + 重建索引
_retriever_cache: dict[str, HybridRetriever] = {}

def invalidate_kb_cache(kb_id: str) -> None:
    """知识库内容变更后清除其检索器缓存（上传/删除文档时调用）"""
    _retriever_cache.pop(kb_id, None)

class KBManager:

    def __init__(self, session: Session) -> None:
        """注入数据库会话——测试时方便换 mock"""
        self._session = session

    async def upload_document(
        self, kb_id: uuid.UUID, file_path: str, filename: str, user_id: uuid.UUID
    ) -> DocumentRecord:
        """处理文档：解析 → 分块 → 向量化 → 落库"""
        # 1. 建一条 pending 记录（先入库，处理失败也有留痕）
        record = DocumentRecord(
            kb_id=kb_id,
            file_path=file_path,
            filename=filename,
            file_size=Path(file_path).stat().st_size,
            user_id = user_id,
        )
        self._session.add(record)
        self._session.commit()

        try:
            # 2. 解析成原始文档
            record.status = "processing"
            self._session.commit()
            docs = await DocumentParser.parse(file_path)

            # 3. 分块：.md 用结构感知分块，其他用递归分块
            chunks = (
                Chunkers.markdown(docs)
                if Path(file_path).suffix.lower() in {".md", ".markdown"}
                else Chunkers.recursive_character(docs)
            )

            # 4. 向量化写入 Milvus
            VectorStore(kb_id=str(kb_id)).add_documents(chunks)

            # 5. 更新记录
            record.status = "done"
            record.chunks_count = len(chunks)
            invalidate_kb_cache(str(kb_id))  # 内容变了，旧索引作废
        except Exception:
            record.status = "error"
            raise
        finally:
            self._session.commit()

        return record

    def _get_retriever(self, kb_id: str, candidate_top_k: int) -> HybridRetriever | None:
        """获取缓存的检索器；没有则构建并缓存

        Returns:
            HybridRetriever，语料为空（知识库无数据）时返回 None
        """
        cached = _retriever_cache.get(kb_id)
        if cached is not None:
            return cached
        store = VectorStore(kb_id=kb_id)
        corpus = store.get_all_documents()
        if not corpus:
            store.close()
            return None

        retriever = HybridRetriever(
            vector_store=store,
            documents=corpus,
            candidate_top_k=candidate_top_k,
        )
        _retriever_cache[kb_id] = retriever
        return retriever

    def query(
        self,
        kb_id: uuid.UUID,
        query: str,
        top_k: int = 4,
        candidate_top_k: int = 10,
    ) -> list[Document]:
        """对知识库发起混合检索：向量语义 + BM25 关键词 → RRF 融合

        Args:
            kb_id: 知识库 ID
            query: 用户的检索问题
            top_k: 最终返回的命中小块数
            candidate_top_k: 每路检索先取的候选数（融合后再收敛到 top_k）

        Returns:
            相关度降序的 Document 列表（metadata 含来源）
        """
        retriever = self._get_retriever(str(kb_id), candidate_top_k)
        if retriever is None:
            return []
        return retriever.retrieve(query, top_k=top_k)

    def get_retrieval_context(self, results: list[Document]) -> str:
        # 把每条分块拼成 "[序号] 来源: xxx\n内容"
        """将 Milvus返回的原始文档列表（results），转换成一段排版整洁、带有来源出处的文本。
        这段文本通常会作为“背景知识”或“上下文”喂给大语言模型（LLM），让 AI 能够基于事实回答问题，
        并知道答案的出处。
        """
        parts = []
        for i, doc in enumerate(results, start=1):
            src = doc.metadata.get("source", "未知")
            parts.append(f"[{i}] 来源: {src}\n{doc.page_content}")
        return "\n\n".join(parts) if parts else "（知识库中无相关匹配）"