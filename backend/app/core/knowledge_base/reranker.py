"""Reranker 重排段 — SiliconFlow rerank API（Jina 协议兼容）

RRF 融合只看「排名倒数」，不知道 query 与内容的真实相关度；
重排段把融合后的候选送 cross-encoder（bge-reranker-v2-m3）
按语义相关度精排，是把「召回不错」变成「排序正确」的最后一道工序。

设计约束：
- 降级安全：任何异常（网络/超时/4xx/空结果）都返回截断后的原序输入，
  检索链路绝不因重排失败而中断；
- 凭据来源：调用方传 `endpoint` 则用它（P9a：用户配的 `capability=rerank`
  默认源）；不传则回落 `.env` 的 `EMBEDDING_API_KEY / EMBEDDING_BASE_URL`
  （rerank 与 embedding 同属 SiliconFlow，历史约定不新增密钥配置）。
"""

import logging

import httpx
from langchain_core.documents import Document

from app.core.knowledge_base.endpoints import RerankEndpoint, env_rerank_endpoint

logger = logging.getLogger(__name__)

_RERANK_TIMEOUT_SECONDS = 5.0


def rerank(
    query: str,
    docs: list[Document],
    top_n: int,
    endpoint: RerankEndpoint | None = None,
) -> list[Document]:
    """用 rerank 模型对候选文档按 query 相关度精排。

    Args:
        query: 检索查询文本。
        docs: 候选文档（通常为 RRF 融合后的前 RERANK_CANDIDATES 条）。
        top_n: 返回的最相关条数。
        endpoint: 上游端点（由 `endpoints.resolve_rerank_endpoint` 解析）。
            None = 回落 `.env`，此时受 `ENABLE_RERANK` 开关与
            `EMBEDDING_API_KEY` 约束；**显式传入则开关不再参与判断**——
            用户既然配了重排序模型源，就是明确要用它。

    Returns:
        按相关度降序的前 top_n 条；开关关闭 / 无 Key / 调用失败时
        返回原序的前 top_n 条（降级）。
    """
    fallback = docs[:top_n]
    if not docs:
        return []
    if endpoint is None:
        endpoint = env_rerank_endpoint()
        if endpoint is None:
            logger.warning("Rerank 跳过：未开启 ENABLE_RERANK 或未配置 EMBEDDING_API_KEY")
            return fallback

    try:
        resp = httpx.post(
            f"{endpoint.base_url.rstrip('/')}/rerank",
            headers={"Authorization": f"Bearer {endpoint.api_key}"},
            json={
                "model": endpoint.model,
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
        ranked = []
        for item in results:
            doc = docs[item["index"]]
            # cross-encoder 相关度（0~1）写回 metadata，供前端来源展示
            if isinstance(item.get("relevance_score"), (int, float)):
                doc.metadata["relevance_score"] = item["relevance_score"]
            ranked.append(doc)
        return ranked
    except Exception as e:  # noqa: BLE001 —— 降级是特性，不是疏漏
        logger.warning(f"Rerank 调用失败，降级为 RRF 原序: {e}")
        return fallback
