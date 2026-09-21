"""RAG 上游凭据解析 — Provider 优先，`.env` 兜底（P9a）

P5 之后「嵌入 / 重排序」已是真实的供应商能力维度，但 RAG 链路当时仍直接读
`settings.EMBEDDING_*`（SiliconFlow）。本模块补上**读时兼容**：

- 该用户配了 `capability=embedding` / `capability=rerank` 的默认源 → 用它的
  Key / base_url / model（Key 走多 Key 轮换表，选中即刷 `last_used_at`）；
- 没有（或该源类型不支持 embedding）→ 回落 `.env`，**存量部署行为零变化**。

`user_id` 为 None 时一律走 `.env`：这里的 fail closed 表现为「不碰任何用户数据」，
而不是「取全库任意默认源」。
"""

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from langchain_openai import OpenAIEmbeddings
from sqlmodel import Session

from app.core.config import settings

logger = logging.getLogger(__name__)

#: `.env` 兜底的 SiliconFlow 端点（历史默认值，与旧 vec_store/reranker 一致）
DEFAULT_EMBEDDING_BASE_URL = "https://api.siliconflow.cn/v1"


@dataclass(frozen=True)
class RerankEndpoint:
    """一次 rerank 调用所需的上游信息。"""

    api_key: str
    base_url: str
    model: str


def env_embedding_function() -> OpenAIEmbeddings:
    """`.env` 兜底的向量模型（SiliconFlow，OpenAI 兼容格式）"""
    return OpenAIEmbeddings(
        model=settings.EMBEDDING_MODEL,
        api_key=settings.EMBEDDING_API_KEY,
        base_url=settings.EMBEDDING_BASE_URL or None,
    )


def env_rerank_endpoint() -> RerankEndpoint | None:
    """`.env` 兜底的 rerank 端点；开关关闭或缺 Key 时返回 None。"""
    if not settings.ENABLE_RERANK or not settings.EMBEDDING_API_KEY:
        return None
    return RerankEndpoint(
        api_key=settings.EMBEDDING_API_KEY,
        base_url=settings.EMBEDDING_BASE_URL.rstrip("/") or DEFAULT_EMBEDDING_BASE_URL,
        model=settings.RERANK_MODEL,
    )


def resolve_embedding_function(session: Session, user_id: uuid.UUID | None) -> Any:
    """返回一个 LangChain Embeddings 实例：用户默认嵌入源优先，`.env` 兜底。

    源类型不支持 embedding（例如误把 gemini 源设成嵌入默认）时如实记日志并回落，
    不让整条上传/检索链路因一个配错的能力源而中断——与 rerank 的降级原则一致。
    """
    if user_id is not None:
        # 惰性导入：core/agent/provider 会连带拉起 agent 包，避免模块间循环
        from app.core.agent.provider import ProviderManager

        try:
            return ProviderManager(session).get_embedding_model(user_id=user_id)
        except (RuntimeError, ValueError) as exc:
            logger.info("无可用 embedding 模型源，回落 .env EMBEDDING_*：%s", exc)
    return env_embedding_function()


def resolve_rerank_endpoint(
    session: Session, user_id: uuid.UUID | None
) -> RerankEndpoint | None:
    """rerank 端点：用户默认重排序源优先，`.env` 兜底。

    语义差异要记清：**用户显式配了 rerank 源就用它，不再看 `ENABLE_RERANK`**
    （那个开关的历史含义是「.env 那套硅基流动的 rerank 开不开」）；只有回落
    `.env` 时才受它约束。
    """
    if user_id is not None:
        from app.core.agent.provider import ProviderManager

        mgr = ProviderManager(session)
        pc = mgr.get_active_config(user_id, capability="rerank")
        if pc is not None:
            try:
                api_key, _ = mgr.resolve_api_key(pc)
            except RuntimeError as exc:
                # 该源所有 Key 都在冷却中：如实记日志，降级而不是把检索打挂
                logger.warning("rerank 模型源取 Key 失败，回落 .env：%s", exc)
            else:
                return RerankEndpoint(
                    api_key=api_key,
                    base_url=pc.base_url.rstrip("/")
                    if pc.base_url
                    else DEFAULT_EMBEDDING_BASE_URL,
                    model=pc.model_name,
                )
    return env_rerank_endpoint()


def log_embedding_migration_hint() -> None:
    """启动时提示：`.env` 里的嵌入凭据可以迁到「模型源 → 嵌入」统一管理。

    只在**两个值都在**时提示（只配一半说明本来就没在用），且不改任何行为——
    没配默认源时照旧读 `.env`。
    """
    if settings.EMBEDDING_API_KEY and settings.EMBEDDING_BASE_URL:
        logger.info(
            "检测到 .env 的 EMBEDDING_API_KEY / EMBEDDING_BASE_URL。"
            "在「模型源 → 嵌入」配好默认源后即可删掉这两个环境变量；"
            "未配默认源时仍按 .env 工作，行为不变。"
        )
