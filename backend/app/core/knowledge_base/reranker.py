"""Reranker 重排段 — SiliconFlow rerank API（Jina 协议兼容）

RRF 融合只看「排名倒数」，不知道 query 与内容的真实相关度；
重排段把融合后的候选送 cross-encoder（bge-reranker-v2-m3）
按语义相关度精排，是把「召回不错」变成「排序正确」的最后一道工序。

设计约束：
- 降级安全：任何异常（网络/超时/4xx/空结果）都返回截断后的原序输入，
  检索链路绝不因重排失败而中断；
- 复用凭据：rerank 与 embedding 同属 SiliconFlow，直接用
  EMBEDDING_API_KEY / EMBEDDING_BASE_URL，不新增密钥配置。
"""

import logging

import httpx
from langchain_core.documents import Document

from app.core.config import settings

logger = logging.getLogger(__name__)

_RERANK_TIMEOUT_SECONDS = 5.0


def rerank(query: str, docs: list[Document], top_n: int) -> list[Document]:
    """用 rerank 模型对候选文档按 query 相关度精排。

    Args:
        query: 检索查询文本。
        docs: 候选文档（通常为 RRF 融合后的前 RERANK_CANDIDATES 条）。
        top_n: 返回的最相关条数。

    Returns:
        按相关度降序的前 top_n 条；开关关闭 / 无 Key / 调用失败时
        返回原序的前 top_n 条（降级）。
    """
    fallback = docs[:top_n]
    if not settings.ENABLE_RERANK:
        return fallback
    if not docs:
        return []
    if not settings.EMBEDDING_API_KEY:
        logger.warning("Rerank 跳过：未配置 EMBEDDING_API_KEY")
        return fallback

    base_url = settings.EMBEDDING_BASE_URL.rstrip("/") or "https://api.siliconflow.cn/v1"
    try:
        resp = httpx.post(
            f"{base_url}/rerank",
            headers={"Authorization": f"Bearer {settings.EMBEDDING_API_KEY}"},
            json={
                "model": settings.RERANK_MODEL,
                "query": query,
                "documents": [d.page_content for d in docs],
                "top_n": top_n,
            },
            timeout=_RERANK_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            logger.warning("Rerank 返回空结果，降级为 RRF 原序")
            return fallback
        return [docs[item["index"]] for item in results]
    except Exception as e:  # noqa: BLE001 —— 降级是特性，不是疏漏
        logger.warning(f"Rerank 调用失败，降级为 RRF 原序: {e}")
        return fallback
