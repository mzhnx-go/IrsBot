"""Provider 管理模块 —— 模型来源定义 + LangChain ChatModel/Embeddings 工厂。

本模块负责两件事：
1. 定义各模型提供方（openai / anthropic / gemini）支持的模型元信息；
2. 通过 ProviderManager 根据数据库中的 ProviderConfig 配置，动态创建
   LangChain 的 ChatModel（对话模型）与 Embeddings（向量模型）实例，
   并支持缓存、回退切换和热更新。
"""

import logging
import uuid
from collections import OrderedDict
from datetime import timedelta
from typing import Any

import httpx
from sqlmodel import Session, col, select

from app.core.db.models import ProviderConfig, ProviderKey
from app.core.db.sqlmodel_models import get_datetime_utc
from app.utils.crypto import decrypt_api_key, encrypt_api_key

logger = logging.getLogger(__name__)

# ── 模型来源定义（原 sources.py 内容）─────────────────────────

#: 各 Provider 类型 → 能力/模型说明，供前端下拉展示与能力判断使用。
#: 若需在出厂列表中增删模型，请改这里。
MODEL_SOURCES: dict[str, dict] = {
    "openai": {
        "default_model": "gpt-4o",
        "supported_models": [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "gpt-4",
            "gpt-3.5-turbo",
        ],
        "embedding_models": [
            "text-embedding-3-large",
            "text-embedding-3-small",
            "text-embedding-ada-002",
        ],
        "supports_tools": True,
        "supports_image": True,
        "supports_stream": True,
        "max_tokens": 128000,
    },
    "anthropic": {
        "default_model": "claude-3-5-sonnet-20241022",
        "supported_models": [
            "claude-3-5-sonnet-20241022",
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307",
        ],
        "supports_tools": True,
        "supports_image": True,
        "supports_stream": True,
        "max_tokens": 200000,
    },
    "gemini": {
        "default_model": "gemini-2.0-flash",
        "supported_models": [
            "gemini-2.0-flash",
            "gemini-1.5-pro",
            "gemini-1.5-flash",
        ],
        "supports_tools": True,
        "supports_image": True,
        "supports_stream": True,
        "max_tokens": 1000000,
    },
}


def get_supported_models(provider_type: str) -> list[str]:
    """查询指定 Provider 支持的全部模型名列表。

    Args:
        provider_type: Provider 类型，如 "openai"、"anthropic"、"gemini"。

    Returns:
        该 Provider 支持的模型名列表；若 Provider 类型未知则返回空列表。
    """
    source = MODEL_SOURCES.get(provider_type)
    if source is None:
        return []
    return source["supported_models"]


def get_default_model(provider_type: str) -> str | None:
    """查询指定 Provider 的默认模型名。

    Args:
        provider_type: Provider 类型，如 "openai"。

    Returns:
        默认模型名；若 Provider 类型未知则返回 None。
    """
    source = MODEL_SOURCES.get(provider_type)
    if source is None:
        return None
    return source["default_model"]


def get_model_capabilities(provider_type: str, model_name: str) -> dict | None:
    """查询指定 Provider + 模型的组合能力。

    Args:
        provider_type: Provider 类型，如 "openai"。
        model_name: 具体模型名，须在 supported_models 内。

    Returns:
        包含 supports_tools / supports_image / supports_stream / max_tokens
        的能力字典；若 Provider 未知或模型不在支持列表中则返回 None。
    """
    source = MODEL_SOURCES.get(provider_type)
    if source is None or model_name not in source["supported_models"]:
        return None
    return {
        "supports_tools": source["supports_tools"],
        "supports_image": source["supports_image"],
        "supports_stream": source["supports_stream"],
        "max_tokens": source["max_tokens"],
    }


#: 模型名里出现这些片段，通常就是视觉（多模态）模型。
#: 覆盖常见厂商命名：qwen-vl / gpt-4o / claude-3 / gemini / glm-4v / internvl…
#: 纯启发式，只为「没显式声明时」给个合理默认，猜错可由用户一键改。
VISION_NAME_HINTS: tuple[str, ...] = (
    "vision",
    "vl",
    "4o",
    "claude-3",
    "claude-4",
    "gemini",
    "gpt-4.1",
    "gpt-5",
    "glm-4v",
    "qvq",
    "internvl",
    "minicpm-v",
    "llava",
    "omni",
    "multimodal",
)


def looks_like_vision_model(model_name: str | None) -> bool:
    """按模型名启发式判断是否可能是视觉模型（纯函数，好测）。

    只做子串匹配、大小写无关；名字里带 "vl" 这类短片段是常见命名的
    真实产物（qwen-vl-max、qvq-72b 等），宁可多认几个也不漏掉视觉模型
    —— 误判成支持视觉时用户可显式改；漏判则要用户自己发现并去改。
    """
    if not model_name:
        return False
    lowered = model_name.lower()
    return any(hint in lowered for hint in VISION_NAME_HINTS)


def resolve_supports_vision(
    provider_config: Any, model_name: str | None = None
) -> bool:
    """判定该模型源当前使用的模型是否支持视觉输入。

    优先级：ProviderConfig.supports_vision 显式值 > 模型名启发式。
    模型名优先取调用方指定的（Agent 可能临时换模型），否则用配置里的。

    Args:
        provider_config: ProviderConfig 实例；None 时只能靠 model_name 猜。
        model_name: 本次实际使用的模型名；None 则回落到配置的 model_name。

    Returns:
        是否支持视觉输入。
    """
    explicit = getattr(provider_config, "supports_vision", None)
    if explicit is not None:
        return bool(explicit)
    name = model_name or getattr(provider_config, "model_name", None)
    return looks_like_vision_model(name)


# ── Provider 管理器（原 manager.py 内容）──────────────────────


class _LRUCache(OrderedDict):
    """容量受限的 LRU 缓存（单进程内使用，无锁）。

    超出 maxsize 时淘汰最久未使用的条目，防止用户/模型组合不断增长
    导致缓存无界膨胀（每个条目是一个完整的模型客户端对象）。
    """

    def __init__(self, maxsize: int = 32):
        super().__init__()
        self.maxsize = maxsize

    def __setitem__(self, key: str, value: Any) -> None:
        super().__setitem__(key, value)
        self.move_to_end(key)
        while len(self) > self.maxsize:
            self.popitem(last=False)

    def get_hit(self, key: str) -> Any | None:
        """命中则返回值并刷新为最近使用；未命中返回 None。"""
        if key not in self:
            return None
        self.move_to_end(key)
        return self[key]


class ProviderManager:
    """管理 LangChain ChatModel 与 Embeddings 实例。

    基于 ProviderConfig（数据库表）读取配置并按需创建/缓存模型实例，
    避免每次调用都重复构建模型对象带来的开销。

    Attributes:
        session: SQLAlchemy 会话，用于读取 ProviderConfig。
    """

    def __init__(self, session: Session):
        """初始化管理器。

        Args:
            session: SQLAlchemy 数据库会话。
        """
        self.session = session
        self._chat_cache: _LRUCache = _LRUCache()
        self._embed_cache: _LRUCache = _LRUCache()

    # -- 对话模型 ChatModel ----------------------------------------

    def get_active_config(
        self,
        user_id: uuid.UUID | None,
        provider_id: uuid.UUID | None = None,
    ) -> ProviderConfig | None:
        """解析本次实际生效的 ProviderConfig（不建模型实例）。

        get_chat_model 的选源逻辑抽到这里，供「需要读配置本身」的调用方
        复用（如视觉能力判定），避免同一套租户过滤条件写两遍。

        ⚠️ 两条分支都必须带 user_id 过滤（同 get_chat_model 的多租户硬约束）。

        Args:
            user_id: 归属用户 id。
            provider_id: 指定配置 id；None 时取该用户的默认启用配置。

        Returns:
            命中的 ProviderConfig；无可用配置时返回 None。
        """
        if provider_id:
            stmt = select(ProviderConfig).where(
                ProviderConfig.id == provider_id,
                ProviderConfig.user_id == user_id,
                ProviderConfig.is_active.is_(True),
            )
        else:
            stmt = select(ProviderConfig).where(
                ProviderConfig.user_id == user_id,
                ProviderConfig.is_default.is_(True),
                ProviderConfig.is_active.is_(True),
            )
        return self.session.exec(stmt).one_or_none()

    def get_chat_model(
        self,
        user_id: uuid.UUID | None,
        provider_id: uuid.UUID | None = None,
        model_name: str | None = None,
        temperature: float = 0.0,
    ) -> Any:
        """获取一个 LangChain ChatModel 实例（带缓存）。

        优先按 provider_id 查找启用中的配置；未指定时回退到默认且启用中的
        配置。实例按 key 缓存，命中缓存不重复创建。

        ⚠️ 多租户硬约束：两条查找分支都必须带 user_id 过滤。
        否则（provider_id 为 None 时）会取到**别人**的默认源，导致越权使用
        他人密钥与模型。user_id 为 None 时查不到任何源（fail closed），
        绝不回落成「取全库任意默认源」。

        Args:
            user_id: 归属用户 id，限定只能取该用户自己的 ProviderConfig。
            provider_id: ProviderConfig 的 id；为 None 时取该用户的默认配置。
            model_name: 覆盖配置中的模型名；为 None 时用配置默认模型。
            temperature: 采样温度，默认 0.0。

        Returns:
            一个 LangChain ChatModel 实例。

        Raises:
            RuntimeError: 该用户没有可用的（激活或默认）Provider 配置时。
            ValueError: Provider 类型不支持（非 openai/anthropic/gemini）时。
        """
        from langchain.chat_models import init_chat_model

        # pc 先读再算缓存键：高级配置与轮换选中的 Key 都参与签名，
        # 改配置或轮换到另一把 Key 都会得到新实例。
        pc = self.get_active_config(user_id=user_id, provider_id=provider_id)
        if pc is None:
            raise RuntimeError(
                "No active provider configured. Create a ProviderConfig first."
            )
        advanced_sig = (
            f"{pc.timeout_seconds}|{pc.proxy_url or ''}|"
            f"{sorted((pc.extra_headers or {}).items())}"
        )
        # ⚠️ cache key 必须含 user_id：否则不同用户用同一 provider_id=None 时
        #    会命中同一缓存条目，拿到别人的模型实例。
        pc_key_row: uuid.UUID | None
        api_key_plain, pc_key_row = self.resolve_api_key(pc)
        cache_key = (
            f"{user_id}:{provider_id}:{model_name}:{temperature}:"
            f"{advanced_sig}:{pc_key_row or 'legacy'}"
        )
        hit = self._chat_cache.get_hit(cache_key)
        if hit is not None:
            return hit

        kwargs: dict[str, Any] = {
            "model": model_name or pc.model_name,
            "temperature": temperature,
            "api_key": api_key_plain,
        }
        if pc.base_url:
            kwargs["base_url"] = pc.base_url

        # ── 高级配置（config JSON）：超时 / 代理 / 自定义请求头 ──
        # openai / anthropic 客户端原生支持；gemini 走 google_genai 的
        # 传输层，暂不接线（如实记录，不静默）。
        timeout_seconds = pc.timeout_seconds
        extra_headers = pc.extra_headers or None
        proxy_url = pc.proxy_url

        # 模型名作为位置参数传入，避免与 kwargs["model"] 冲突
        model_name_arg = kwargs.pop("model", pc.model_name)

        provider_type = pc.provider_type.lower()
        if provider_type in ("openai", "anthropic"):
            if extra_headers:
                kwargs["default_headers"] = extra_headers
            if provider_type == "openai":
                kwargs["timeout"] = timeout_seconds
            else:
                kwargs["default_request_timeout"] = timeout_seconds
            if proxy_url:
                kwargs["http_client"] = httpx.Client(
                    proxy=proxy_url, timeout=timeout_seconds
                )
        elif provider_type != "gemini":
            logger.info(
                "高级配置对类型 %s 暂未生效（仅 openai/anthropic 支持）",
                provider_type,
            )
        if provider_type == "openai":
            model = init_chat_model(model_name_arg, model_provider="openai", **kwargs)
        elif provider_type == "anthropic":
            model = init_chat_model(model_name_arg, model_provider="anthropic", **kwargs)
        elif provider_type == "gemini":
            model = init_chat_model(model_name_arg, model_provider="google_genai", **kwargs)
        else:
            raise ValueError(f"Unsupported provider type: {provider_type}")

        self._chat_cache[cache_key] = model
        return model

    def clear_chat_cache(self) -> None:
        """清空对话模型缓存，下次调用会重新构建。"""
        self._chat_cache.clear()

    # -- 向量模型 Embeddings --------------------------------------

    def get_embedding_model(
        self, user_id: uuid.UUID | None, provider_id: uuid.UUID | None = None
    ) -> Any:
        """获取一个 LangChain Embeddings 实例（带缓存）。

        ⚠️ 依赖惰性导入：langchain_anthropic 当前版本没有 AnthropicEmbeddings，
        若写成函数顶部导入会让**任何** provider 都在查库前就 ImportError（原缺陷）。

        ⚠️ 多租户硬约束：两条查找分支都必须带 user_id 过滤，理由同
        get_chat_model（否则会越权使用他人的密钥）；user_id 为 None 时
        fail closed（查不到任何源）。

        Args:
            user_id: 归属用户 id，限定只能取该用户自己的 ProviderConfig。
            provider_id: ProviderConfig 的 id；为 None 时取该用户的默认且启用中的配置。

        Returns:
            一个 LangChain Embeddings 实例。

        Raises:
            RuntimeError: 该用户没有可用的 embedding Provider 配置时。
            ValueError: Provider 类型不支持 embedding（仅 openai/anthropic）时。
        """
        if provider_id:
            stmt = select(ProviderConfig).where(
                ProviderConfig.id == provider_id,
                ProviderConfig.user_id == user_id,
                ProviderConfig.is_active.is_(True),
            )
            pc = self.session.exec(stmt).one_or_none()
        else:
            stmt = select(ProviderConfig).where(
                ProviderConfig.user_id == user_id,
                ProviderConfig.is_default.is_(True),
                ProviderConfig.is_active.is_(True),
            )
            pc = self.session.exec(stmt).one_or_none()

        if pc is None:
            raise RuntimeError("No active embedding provider configured.")

        cache_key = str(pc.id)
        hit = self._embed_cache.get_hit(cache_key)
        if hit is not None:
            return hit

        provider_type = pc.provider_type.lower()
        # api_key 在库中加密存储，构建 Embeddings 时必须先解密，
        # 否则会把密文当密钥发给服务商 → 鉴权失败（get_chat_model 已解密，这里漏了）。
        api_key = decrypt_api_key(pc.api_key)
        if provider_type == "openai":
            from langchain_openai import OpenAIEmbeddings

            embed = OpenAIEmbeddings(
                model=pc.model_name,
                api_key=api_key,
                base_url=pc.base_url or None,
            )
        elif provider_type == "anthropic":
            from langchain_anthropic import AnthropicEmbeddings

            embed = AnthropicEmbeddings(api_key=api_key)
        else:
            raise ValueError(f"Unsupported embedding provider: {provider_type}")

        self._embed_cache[cache_key] = embed
        return embed

    def clear_embed_cache(self) -> None:
        """清空向量模型缓存，下次调用会重新构建。"""
        self._embed_cache.clear()

    # -- 回退调用链 ------------------------------------------------

    async def chat_with_fallback(
        self,
        user_id: uuid.UUID | None,
        messages: list[Any],
        provider_id: uuid.UUID | None = None,
        max_retries: int = 2,
    ) -> Any:
        """调用 LLM，并在主 Provider 失败时自动回退到其他启用中的 Provider。

        按 fallback_order 升序依次尝试**该用户**所有启用中的 Provider，直到成功
        或超过最大重试次数。

        Args:
            user_id: 归属用户 id；候选源只在该用户的 ProviderConfig 中挑选。
            messages: 待发送给 LLM 的消息列表。
            provider_id: 可选，指定起始 Provider；为 None 时按回退顺序从头尝试。
            max_retries: 最多尝试的 Provider 个数（额外上限），默认 2。

        Returns:
            LLM 的响应对象。

        Raises:
            RuntimeError: 该用户没有启用中的 Provider，或所有 Provider 均失败时。
        """
        stmt = (
            select(ProviderConfig)
            .where(
                ProviderConfig.user_id == user_id,
                ProviderConfig.is_active.is_(True),
            )
            .order_by(ProviderConfig.fallback_order)
        )
        providers = list(self.session.exec(stmt).all())

        if not providers:
            raise RuntimeError("No active providers available.")

        last_error = None
        for i, pc in enumerate(providers):
            if i > max_retries:
                break
            try:
                model = self.get_chat_model(user_id=user_id, provider_id=pc.id)
                response = await model.ainvoke(messages)
                return response
            except Exception as exc:
                last_error = exc
                continue

        raise RuntimeError(
            f"All providers failed. Last error: {last_error}"
        ) from last_error

    # -- 热更新 ----------------------------------------------------

    async def reload_config(self) -> None:
        """清空全部缓存，使下次调用重新构建模型实例。"""
        self._chat_cache.clear()
        self._embed_cache.clear()

    # -- Provider CRUD ---------------------------------------------

    def list_providers(
        self, user_id: uuid.UUID | None = None
    ) -> list[ProviderConfig]:
        """列出 Provider 配置。

        Args:
            user_id: 可选，只列出该用户的 Provider；为 None 时列出全部。

        Returns:
            ProviderConfig 对象列表（is_default 优先，其余按 fallback_order）。
        """
        stmt = select(ProviderConfig)
        if user_id is not None:
            stmt = stmt.where(ProviderConfig.user_id == user_id)
        stmt = stmt.order_by(
            col(ProviderConfig.is_default).desc(),
            ProviderConfig.fallback_order,
        )
        return list(self.session.exec(stmt).all())

    def clear_other_defaults(
        self, user_id: uuid.UUID, keep_id: uuid.UUID | None = None
    ) -> None:
        """把该用户 is_default=True 的 Provider 全部置 False。

        用于设新默认前的互斥清理。keep_id 不为 None 时会跳过自己
        （PATCH 更新场景：不能把正在更新的那条也清了）。

        Args:
            user_id: 目标用户 id。
            keep_id: 需要保留为默认的那条 Provider id；None 表示全清。
        """
        stmt = select(ProviderConfig).where(
            ProviderConfig.user_id == user_id,
            ProviderConfig.is_default.is_(True),
        )
        if keep_id is not None:
            stmt = stmt.where(ProviderConfig.id != keep_id)
        for row in self.session.exec(stmt):
            row.is_default = False
        self.session.commit()

    def create_provider(
        self,
        user_id: uuid.UUID,
        name: str,
        provider_type: str,
        api_key: str,
        model_name: str,
        base_url: str | None = None,
        is_default: bool = False,
        is_active: bool = True,
        fallback_order: int = 999,
        config: dict | None = None,
        supports_vision: bool | None = None,
    ) -> ProviderConfig:
        """创建一个新的 Provider 配置并入库。

        Args:
            user_id: 所属用户 id。
            name: Provider 显示名称。
            provider_type: Provider 类型（openai/anthropic/gemini）。
            api_key: API 密钥。
            model_name: 默认模型名。
            base_url: 可选，自定义 API 地址。
            is_default: 是否为默认配置，默认 False。
            is_active: 是否启用，默认 True。
            fallback_order: 回退优先级（越小越优先），默认 999。
            config: 可选，额外扩展配置字典，默认空字典。
            supports_vision: 视觉能力三态，None=自动（按模型名启发式）。

        Returns:
            已入库并刷新的 ProviderConfig 对象。
        """
        obj = ProviderConfig(
            user_id=user_id,
            name=name,
            provider_type=provider_type,
            api_key=encrypt_api_key(api_key),
            model_name=model_name,
            base_url=base_url,
            is_default=is_default,
            is_active=is_active,
            fallback_order=fallback_order,
            config=config or {},
            supports_vision=supports_vision,
        )
        self.session.add(obj)
        self.session.commit()
        self.session.refresh(obj)
        # 多 Key 体系：创建时同步写入第一行（provider_keys 为权威来源，
        # api_key 列仅作无行时的回落）
        self.session.add(
            ProviderKey(provider_id=obj.id, encrypted_key=obj.api_key)
        )
        self.session.commit()
        return obj

    # ── 多 API Key（P8）：轮换 / 冷却 / CRUD ─────────────────────

    #: 连败达到该次数进入冷却
    KEY_FAIL_THRESHOLD = 3
    #: 冷却时长（分钟）
    KEY_COOLDOWN_MINUTES = 5

    def resolve_api_key(self, pc: ProviderConfig) -> tuple[str, uuid.UUID | None]:
        """轮换取一把可用 Key。

        顺序轮换：在「启用且未冷却」的行里选 `last_used_at` 最旧的，
        选中即刷新 last_used_at。全部冷却时如实报错；无行（异常态）
        回落到 api_key 列。

        Returns:
            (明文 Key, ProviderKey 行 id)。行 id 为 None 表示用了回落列。

        Raises:
            RuntimeError: 该供应商存在 Key 但全部处于冷却中。
        """
        rows = self.session.exec(
            select(ProviderKey)
            .where(ProviderKey.provider_id == pc.id, ProviderKey.is_active)
            .order_by(
                col(ProviderKey.last_used_at).asc().nulls_first(),
            )
        ).all()
        now = get_datetime_utc()
        available = [
            r
            for r in rows
            if r.cooldown_until is None or r.cooldown_until <= now
        ]
        if not available:
            if rows:
                raise RuntimeError(
                    "该模型源的所有 API Key 都处于失败冷却中，请稍后再试或更换 Key"
                )
            # 无行：回落 api_key 列（兼容异常态 / 手工改库）
            return decrypt_api_key(pc.api_key), None

        row = available[0]
        row.last_used_at = now
        self.session.commit()
        return decrypt_api_key(row.encrypted_key), row.id

    def mark_key_failure(self, key_row_id: uuid.UUID | None) -> None:
        """记录一次上游鉴权/限流失败；连败达阈值进入冷却。

        key_row_id 为 None（回落列）时不处理。成功重置由调用方
        `mark_key_success` 触发。
        """
        if key_row_id is None:
            return
        row = self.session.get(ProviderKey, key_row_id)
        if row is None:
            return
        row.fail_count += 1
        if row.fail_count >= self.KEY_FAIL_THRESHOLD:
            row.cooldown_until = get_datetime_utc() + timedelta(
                minutes=self.KEY_COOLDOWN_MINUTES
            )
            row.fail_count = 0
        self.session.commit()

    def mark_key_success(self, key_row_id: uuid.UUID | None) -> None:
        """成功后重置失败计数（不清冷却——冷却到期自动恢复）。"""
        if key_row_id is None:
            return
        row = self.session.get(ProviderKey, key_row_id)
        if row is not None and row.fail_count:
            row.fail_count = 0
            self.session.commit()

    def update_provider(
        self, provider_id: uuid.UUID, **fields
    ) -> ProviderConfig | None:
        """按字段更新一个 Provider 配置。

        Args:
            provider_id: 目标 ProviderConfig 的 id。
            **fields: 需要更新的字段，如 model_name、is_active 等。

        Returns:
            更新后的 ProviderConfig 对象；若该 id 不存在则返回 None。
        """
        stmt = select(ProviderConfig).where(ProviderConfig.id == provider_id)
        obj = self.session.exec(stmt).one_or_none()
        if obj:
            for k, v in fields.items():
                if k == "api_key":
                    # api_key 更新时同样加密落库
                    v = encrypt_api_key(v)
                if hasattr(obj, k):
                    setattr(obj, k, v)
            if "api_key" in fields:
                # 多 Key 体系同步：用户在设置区填新 Key = 重置凭据，
                # 清空全部轮换行、写入唯一新行（可预期，不产生漂移）
                for row in self.session.exec(
                    select(ProviderKey).where(ProviderKey.provider_id == obj.id)
                ).all():
                    self.session.delete(row)
                self.session.add(
                    ProviderKey(provider_id=obj.id, encrypted_key=obj.api_key)
                )
            self.session.commit()
            self.session.refresh(obj)
        return obj

    def delete_provider(self, provider_id: uuid.UUID) -> bool:
        """删除一个 Provider 配置；若删的是默认源，则自动提升同用户下一条为默认。

        不补位会留下「无默认源」空窗：列表里没有任何「默认」徽标，且
        get_chat_model() / get_embedding_model() 取默认的路径会直接失败
        （RuntimeError: No active provider configured）。

        接替者只在该用户的**其余启用中**（is_active=True）配置里按 fallback_order
        升序挑第一条；若没有可接替的，则保持无默认（此时也确实没有可用源）。

        Args:
            provider_id: 目标 ProviderConfig 的 id。

        Returns:
            True 表示删除成功；若该 id 不存在则返回 False。
        """
        stmt = select(ProviderConfig).where(ProviderConfig.id == provider_id)
        obj = self.session.exec(stmt).one_or_none()
        if obj is None:
            return False

        # 先删原默认并 flush，再晋升接替者：
        # 部分唯一索引要求任一时刻该用户只有一条默认，若先晋升再删，
        # 同一事务 flush 时会短暂出现两条默认而撞索引。
        # 删除与晋升在同一事务内完成，对读方不存在「无默认空窗」。
        was_default = obj.is_default
        self.session.delete(obj)
        self.session.flush()
        if was_default:
            successor_stmt = (
                select(ProviderConfig)
                .where(
                    ProviderConfig.user_id == obj.user_id,
                    ProviderConfig.id != obj.id,
                    ProviderConfig.is_active.is_(True),
                )
                .order_by(ProviderConfig.fallback_order)
                .limit(1)
            )
            successor = self.session.exec(successor_stmt).first()
            if successor is not None:
                successor.is_default = True

        self.session.commit()
        return True


