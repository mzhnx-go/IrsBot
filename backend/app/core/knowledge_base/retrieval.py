"""混合检索 — 向量 (Milvus) + BM25 关键词，RRF 融合

RAG 检索分两条腿，各有擅长：
1. 向量检索 (VectorStore.search)：语义相似，能召回"换说法"的请求
2. BM25 关键词检索：精确词匹配，擅长术语 / 专有名词 / 编号

单路都覆盖不了另一路的场景，因此用 RRF (Reciprocal Rank Fusion)
按排名倒数和把两路结果融合成一份最终的 top-k。
"""

import re

from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

_DEFAULT_RRF_K = 60

# 匹配连续的 ASCII 字母数字（作为一个词）+ 单个 CJK 字符（一个 token）
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]")


def _doc_key(doc: Document) -> str:
    """文档稳定标识 — 用正文内容作为融合去重的 key

    向量检索返回的 Document 与 BM25 语料里的 Document 是同一分块，
    正文相同，因此可用正文合并两路结果。
    """
    return doc.page_content


def _tokenize(text: str) -> list[str]:
    """中文友好的简单分词

    rank_bm25 需要 token 列表。ASCII 单词整体作为一个 token，
    中文没有空格分词，就按单字切分（够用于相似度排序）。
    """
    return [tok.lower() for tok in _TOKEN_RE.findall(text)]


def rrf_fuse(result_lists: list[list[Document]], k: int = _DEFAULT_RRF_K) -> list[Document]:
    """Reciprocal Rank Fusion：多路检索结果按倒数排名融合

    Args:
        result_lists: 多路检索结果（每路一个按相关度降序的 Document 列表）
        k: RRF 平滑常数，默认 60

    Returns:
        融合后按分数降序、已去重的 Document 列表
    """
    scores: dict[str, float] = {}
    docs_by_key: dict[str, Document] = {}

    for result_list in result_lists:
        for rank, doc in enumerate(result_list, start=1):
            key = _doc_key(doc)
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            docs_by_key[key] = doc

    ordered = sorted(docs_by_key, key=lambda key: scores[key], reverse=True)
    return [docs_by_key[key] for key in ordered]


class BM25Retriever:
    """BM25 关键词检索器（rank_bm25）

    构造时用分块后的语料建索引，查询时按关键词相关度返回 top-k Document。
    """

    def __init__(self, documents: list[Document]):
        """初始化 BM25 索引

        Args:
            documents: 分块后的语料（与写入向量库的分块一致）
        """
        self._documents = documents
        corpus: list[list[str]] = [_tokenize(d.page_content) for d in documents]
        # BM25Okapi 需可迭代对象；空语料时防止空 token 崩溃
        self._bm25 = BM25Okapi(corpus) if documents else None



    def retrieve(self, query: str, top_k: int = 5) -> list[Document]:
        """按关键词相关度检索

            Args:
                query: 查询文本
                top_k: 返回最相关的 k 条

            Returns:
                相关度降序的 Document 列表（不含分数）
            """
        if not self._documents or self._bm25 is None:
            return []
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []
        scored = self._bm25.get_top_n(
            query_tokens,
            self._documents,
            n=min(top_k, len(self._documents)),
        )
        return scored


class HybridRetriever:
    """混合检索器 — 向量 + BM25 → RRF 融合

    向量检索走 Milvus（语义），BM25 走本地语料（关键词），
    两路候选用 RRF 融合后取最终的 top-k。
    """

    def __init__(
        self,
        vector_store,
        documents: list[Document],
        candidate_top_k: int = 10,
    ):
        """初始化混合检索器

        Args:
            vector_store: 已写入同一批分块的 VectorStore 实例
            documents: 与向量库对应的分块语料（供 BM25 建索引）
            candidate_top_k: 每路检索取的候选数（融合后收敛到最终 top-k）
        """
        self._vector_store = vector_store
        self._bm25 = BM25Retriever(documents)
        self._candidate_top_k = candidate_top_k

    def retrieve(self, query: str, top_k: int = 4) -> list[Document]:
        """混合检索

        Args:
            query: 查询文本
            top_k: 最终返回的条数

        Returns:
            融合后相关度降序、去掉重复的 Document（metadata 带 source 等）
        """
        vec_results = self._vector_store.search(query, top_k=self._candidate_top_k)
        kw_results = self._bm25.retrieve(query, self._candidate_top_k)
        fused = rrf_fuse([vec_results, kw_results])
        return fused[:top_k]