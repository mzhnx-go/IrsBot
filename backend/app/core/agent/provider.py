"""Provider 管理模块 —— 模型来源定义 + LangChain ChatModel/Embeddings 工厂。

本模块负责两件事：
1. 定义各模型提供方（openai / anthropic / gemini）支持的模型元信息；
2. 通过 ProviderManager 根据数据库中的 ProviderConfig 配置，动态创建
   LangChain 的 ChatModel（对话模型）与 Embeddings（向量模型）实例，
   并支持缓存、回退切换和热更新。
"""

import uuid
from typing import Any

from sqlmodel import Session, col, select

from app.core.db.models import ProviderConfig
from app.utils.crypto import decrypt_api_key, encrypt_api_key

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


# ── Provider 管理器（原 manager.py 内容）──────────────────────


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
        self._chat_cache: dict[str, Any] = {}
        self._embed_cache: dict[str, Any] = {}

    # -- 对话模型 ChatModel ----------------------------------------

    def get_chat_model(
        self,
        provider_id: uuid.UUID | None = None,
        model_name: str | None = None,
        temperature: float = 0.0,
    ) -> Any:
        """获取一个 LangChain ChatModel 实例（带缓存）。

        优先按 provider_id 查找启用中的配置；未指定时回退到默认且启用中的
        配置。实例按 key 缓存，命中缓存不重复创建。

        Args:
            provider_id: ProviderConfig 的 id；为 None 时取默认配置。
            model_name: 覆盖配置中的模型名；为 None 时用配置默认模型。
            temperature: 采样温度，默认 0.0。

        Returns:
            一个 LangChain ChatModel 实例。

        Raises:
            RuntimeError: 没有可用的（激活或默认）Provider 配置时。
            ValueError: Provider 类型不支持（非 openai/anthropic/gemini）时。
        """
        from langchain.chat_models import init_chat_model

        cache_key = f"{provider_id}:{model_name}:{temperature}"
        if cache_key in self._chat_cache:
            return self._chat_cache[cache_key]

        if provider_id:
            stmt = select(ProviderConfig).where(
                ProviderConfig.id == provider_id,
                ProviderConfig.is_active.is_(True),
            )
            pc = self.session.exec(stmt).one_or_none()
        else:
            stmt = select(ProviderConfig).where(
                ProviderConfig.is_default.is_(True),
                ProviderConfig.is_active.is_(True),
            )
            pc = self.session.exec(stmt).one_or_none()

        if pc is None:
            raise RuntimeError(
                "No active provider configured. Create a ProviderConfig first."
            )

        kwargs: dict[str, Any] = {
            "model": model_name or pc.model_name,
            "temperature": temperature,
            "api_key": decrypt_api_key(pc.api_key),
        }
        if pc.base_url:
            kwargs["base_url"] = pc.base_url

        # 模型名作为位置参数传入，避免与 kwargs["model"] 冲突
        model_name_arg = kwargs.pop("model", pc.model_name)

        provider_type = pc.provider_type.lower()
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

    def get_embedding_model(self, provider_id: uuid.UUID | None = None) -> Any:
        """获取一个 LangChain Embeddings 实例（带缓存）。

        Args:
            provider_id: ProviderConfig 的 id；为 None 时取默认且启用中的配置。

        Returns:
            一个 LangChain Embeddings 实例。

        Raises:
            RuntimeError: 没有可用的 embedding Provider 配置时。
            ValueError: Provider 类型不支持 embedding（仅 openai/anthropic）时。
        """
        from langchain_anthropic import AnthropicEmbeddings
        from langchain_openai import OpenAIEmbeddings

        if provider_id:
            stmt = select(ProviderConfig).where(
                ProviderConfig.id == provider_id,
                ProviderConfig.is_active.is_(True),
            )
            pc = self.session.exec(stmt).one_or_none()
        else:
            stmt = select(ProviderConfig).where(
                ProviderConfig.is_default.is_(True),
                ProviderConfig.is_active.is_(True),
            )
            pc = self.session.exec(stmt).one_or_none()

        if pc is None:
            raise RuntimeError("No active embedding provider configured.")

        cache_key = str(pc.id)
        if cache_key in self._embed_cache:
            return self._embed_cache[cache_key]

        provider_type = pc.provider_type.lower()
        # api_key 在库中加密存储，构建 Embeddings 时必须先解密，
        # 否则会把密文当密钥发给服务商 → 鉴权失败（get_chat_model 已解密，这里漏了）。
        api_key = decrypt_api_key(pc.api_key)
        if provider_type == "openai":
            embed = OpenAIEmbeddings(
                model=pc.model_name,
                api_key=api_key,
                base_url=pc.base_url or None,
            )
        elif provider_type == "anthropic":
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
        messages: list[Any],
        provider_id: uuid.UUID | None = None,
        max_retries: int = 2,
    ) -> Any:
        """调用 LLM，并在主 Provider 失败时自动回退到其他启用中的 Provider。

        按 fallback_order 升序依次尝试所有启用中的 Provider，直到成功或超过
        最大重试次数。

        Args:
            messages: 待发送给 LLM 的消息列表。
            provider_id: 可选，指定起始 Provider；为 None 时按回退顺序从头尝试。
            max_retries: 最多尝试的 Provider 个数（额外上限），默认 2。

        Returns:
            LLM 的响应对象。

        Raises:
            RuntimeError: 没有启用中的 Provider，或所有 Provider 均失败时。
        """
        stmt = (
            select(ProviderConfig)
            .where(ProviderConfig.is_active.is_(True))
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
                model = self.get_chat_model(provider_id=pc.id)
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
        )
        self.session.add(obj)
        self.session.commit()
        self.session.refresh(obj)
        return obj

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
            self.session.commit()
            self.session.refresh(obj)
        return obj

    def delete_provider(self, provider_id: uuid.UUID) -> bool:
        """删除一个 Provider 配置。

        Args:
            provider_id: 目标 ProviderConfig 的 id。

        Returns:
            True 表示删除成功；若该 id 不存在则返回 False。
        """
        stmt = select(ProviderConfig).where(ProviderConfig.id == provider_id)
        obj = self.session.exec(stmt).one_or_none()
        if obj:
            self.session.delete(obj)
            self.session.commit()
            return True
        return False


