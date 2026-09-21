"""Provider 管理 REST API —— ProviderManager CRUD 的接口层。

多租户规则：所有操作按 user_id 过滤，只能看/改自己的 provider 配置。
设默认互斥：同一用户只有一条 is_default=True。
"""


import logging
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.api.deps import SessionDep, get_current_user
from app.core.agent.provider import ProviderManager
from app.core.agent.provider_balance import ProviderBalanceOut, query_balance
from app.core.agent.provider_models import fetch_upstream_models
from app.core.db.models import ProviderConfig, ProviderKey, ProviderModel
from app.core.db.sqlmodel_models import User
from app.utils.crypto import decrypt_api_key

router = APIRouter(tags=["providers"])

logger = logging.getLogger(__name__)

class ProviderCreate(BaseModel):
    """创建请求体"""
    name: str
    provider_type: str
    api_key: str
    model_name: str
    base_url: str | None = None
    is_default: bool = False
    # 视觉能力三态：None=自动（按模型名猜），True/False=显式声明
    supports_vision: bool | None = None


class ProviderUpdate(BaseModel):
    """更新请求体：所有字段可选"""

    name: str | None = None
    api_key: str | None = None
    model_name: str | None = None
    base_url: str | None = None
    is_default: bool | None = None
    supports_vision: bool | None = None
    # ── 高级配置（存 config JSON）──
    # 超时：5–600 秒，越界由 pydantic 直接 422
    timeout_seconds: int | None = Field(default=None, ge=5, le=600)
    # 代理：路由层校验协议前缀；空串 = 清除
    proxy_url: str | None = None
    # 自定义请求头：pydantic dict[str, str] 保证值必须是字符串（非 str 直接 422）
    extra_headers: dict[str, str] | None = None

class ProviderOut(BaseModel):
    """响应体: 绝不返回明文 api_key"""
    id: UUID
    name: str
    provider_type: str
    model_name: str
    base_url: str | None
    is_default: bool
    is_active: bool
    supports_vision: bool | None = None
    # 高级配置：从 ProviderConfig 的同名 property 读取（存于 config JSON）
    timeout_seconds: int = 120
    proxy_url: str | None = None
    extra_headers: dict[str, str] = {}


class ProviderModelOut(BaseModel):
    id: UUID
    model_id: str
    display_name: str | None = None


class ProviderModelsOut(BaseModel):
    items: list[ProviderModelOut]
    count: int


class ProviderModelCreate(BaseModel):
    """「自定义模型」请求体"""
    model_id: str = Field(min_length=1, max_length=200)
    display_name: str | None = Field(default=None, max_length=200)


class ProviderKeyOut(BaseModel):
    """密钥行：只回打码形态，绝不含明文/密文"""
    id: UUID
    key_mask: str
    is_active: bool
    fail_count: int
    cooldown_until: str | None = None
    last_used_at: str | None = None


class ProviderKeysOut(BaseModel):
    items: list[ProviderKeyOut]
    count: int


class ProviderKeysAdd(BaseModel):
    """「添加更多」批量粘贴：一行一个 Key"""
    keys: list[str] = Field(min_length=1)



@router.get("/providers", response_model=list[ProviderOut])
def list_providers(session: SessionDep, current_user: User = Depends(get_current_user)):
    """列出当前用户的所有 Provider 配置（默认排最前）。"""
    return ProviderManager(session).list_providers(current_user.id)


@router.post("/providers", response_model=ProviderOut)
def create_provider(
    body: ProviderCreate,
    session: SessionDep,
    current_user: User = Depends(get_current_user),
):
    """新增一条 Provider 配置；若设为默认，先清掉该用户其他默认。"""
    mgr = ProviderManager(session)

    if body.is_default:
        # 互斥清理：新记录还没 id，不需要 keep_id
        mgr.clear_other_defaults(user_id=current_user.id)

    obj = mgr.create_provider(
        user_id=current_user.id,
        name=body.name,
        provider_type=body.provider_type,
        api_key=body.api_key,
        model_name=body.model_name,
        base_url=body.base_url,
        is_default=body.is_default,
        supports_vision=body.supports_vision,
    )
    return obj



@router.get("/providers/{provider_id}/balance", response_model=ProviderBalanceOut)
async def get_provider_balance(
    provider_id: UUID,
    session: SessionDep,
    current_user: User = Depends(get_current_user),
):
    """查询该模型源的账户余额（用其自身 API Key 调服务商余额接口）。

    越权与不存在同返 404，不泄露其他用户是否配过该 provider。
    上游不可用/服务商无接口时仍返回 200，由 `supported` / `error` 字段表达结果。
    """
    stmt = select(ProviderConfig).where(
        ProviderConfig.id == provider_id,
        ProviderConfig.user_id == current_user.id,
    )
    pc = session.exec(stmt).one_or_none()
    if pc is None:
        raise HTTPException(status_code=404, detail="Provider not found")

    mgr = ProviderManager(session)
    key_plain, key_row_id = mgr.resolve_api_key(pc)
    result = await query_balance(
        base_url=pc.base_url,
        api_key=key_plain,
        timeout_seconds=pc.timeout_seconds,
        proxy_url=pc.proxy_url,
        extra_headers=pc.extra_headers or None,
    )
    if result.error:
        mgr.mark_key_failure(key_row_id)
    else:
        mgr.mark_key_success(key_row_id)
    if result.supported:
        logger.info(
            "余额查询成功：provider=%s 剩余=%s%s",
            pc.name,
            result.remaining,
            f" {result.currency}" if result.currency else "",
        )
    elif result.error:
        logger.error("余额查询失败：provider=%s %s", pc.name, result.error)
    else:
        logger.info("余额查询：provider=%s %s", pc.name, result.detail)
    return result


@router.patch("/providers/{provider_id}", response_model=ProviderOut)
def update_provider(
    provider_id: UUID,
    body: ProviderUpdate,
    session: SessionDep,
    current_user: User = Depends(get_current_user),
):
    """更新 Provider 配置；设为默认时清理其他默认。"""
    mgr = ProviderManager(session)

    stmt = select(ProviderConfig).where(
        ProviderConfig.id == provider_id,
        ProviderConfig.user_id == current_user.id,
    )
    pc = session.exec(stmt).one_or_none()
    if pc is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    if body.is_default:
        mgr.clear_other_defaults(user_id=current_user.id, keep_id=provider_id)
    fields = body.model_dump(exclude_none=True, exclude={"timeout_seconds", "proxy_url", "extra_headers"})
    # supports_vision 是唯一「None 本身有意义」的字段（None=自动），
    # exclude_none 会把「改回自动」的请求吃掉，故显式按是否传过来判断。
    if "supports_vision" in body.model_fields_set:
        fields["supports_vision"] = body.supports_vision

    # ── 高级配置：校验后合并进 config JSON（与普通字段同事务落库）──
    if body.proxy_url is not None:
        proxy = body.proxy_url.strip()
        if proxy and not proxy.startswith(("http://", "https://")):
            raise HTTPException(
                status_code=400,
                detail="代理地址必须以 http:// 或 https:// 开头",
            )
        pc.apply_advanced_config(
            proxy_url=proxy,  # 空串 = 清除
            timeout_seconds=body.timeout_seconds,
            extra_headers=body.extra_headers,
        )
    elif body.timeout_seconds is not None or body.extra_headers is not None:
        pc.apply_advanced_config(
            timeout_seconds=body.timeout_seconds,
            extra_headers=body.extra_headers,
        )
    return mgr.update_provider(provider_id, **fields)


# ── 模型清单（「获取模型列表」/「自定义模型」）─────────────────


def _get_owned_provider(
    provider_id: UUID, session: Session, current_user: User
) -> ProviderConfig:
    """归属校验：不存在或不是自己的都 404（零副作用，与余额端点同款）。"""
    stmt = select(ProviderConfig).where(
        ProviderConfig.id == provider_id,
        ProviderConfig.user_id == current_user.id,
    )
    pc = session.exec(stmt).one_or_none()
    if pc is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    return pc


def _list_models(session: Session, provider_id: UUID) -> list[ProviderModelOut]:
    rows = session.exec(
        select(ProviderModel)
        .where(ProviderModel.provider_id == provider_id)
        .order_by(ProviderModel.model_id)
    ).all()
    return [
        ProviderModelOut(id=r.id, model_id=r.model_id, display_name=r.display_name)
        for r in rows
    ]


@router.get("/providers/{provider_id}/models", response_model=ProviderModelsOut)
def list_provider_models(
    provider_id: UUID,
    session: SessionDep,
    current_user: User = Depends(get_current_user),
):
    """列出该供应商的模型清单。"""
    pc = _get_owned_provider(provider_id, session, current_user)
    items = _list_models(session, pc.id)
    return ProviderModelsOut(items=items, count=len(items))


@router.post("/providers/{provider_id}/models/fetch", response_model=ProviderModelsOut)
async def fetch_provider_models(
    provider_id: UUID,
    session: SessionDep,
    current_user: User = Depends(get_current_user),
):
    """从上游拉取模型列表并 upsert 落库（**显式动作**，不自动触发）。

    上游失败翻译为中文 502/504：Key 无效 / 不可达 / 超时，便于用户排障。
    """
    pc = _get_owned_provider(provider_id, session, current_user)
    mgr = ProviderManager(session)
    key_plain, key_row_id = mgr.resolve_api_key(pc)
    try:
        models = await fetch_upstream_models(
            provider_type=pc.provider_type,
            base_url=pc.base_url,
            api_key=key_plain,
            timeout_seconds=pc.timeout_seconds,
            proxy_url=pc.proxy_url,
            extra_headers=pc.extra_headers or None,
        )
    except httpx.TimeoutException:
        mgr.mark_key_failure(key_row_id)
        raise HTTPException(status_code=504, detail="拉取超时，请稍后再试或调大超时时间")
    except httpx.HTTPStatusError as exc:
        mgr.mark_key_failure(key_row_id)
        status = exc.response.status_code
        if status in (401, 403):
            raise HTTPException(status_code=502, detail="API Key 无效或无权限获取模型列表")
        raise HTTPException(
            status_code=502, detail=f"服务商返回错误（HTTP {status}）"
        )
    except httpx.HTTPError:
        mgr.mark_key_failure(key_row_id)
        raise HTTPException(
            status_code=502, detail="无法连接到服务商，请检查网络与 API 地址"
        )
    mgr.mark_key_success(key_row_id)

    if not models:
        raise HTTPException(status_code=502, detail="服务商返回了空的模型列表")

    # upsert：幂等，重复拉取不产生重复行
    existing = {
        r.model_id
        for r in session.exec(
            select(ProviderModel).where(ProviderModel.provider_id == pc.id)
        ).all()
    }
    for model_id in models:
        if model_id not in existing:
            session.add(ProviderModel(provider_id=pc.id, model_id=model_id))
    session.commit()

    items = _list_models(session, pc.id)
    logger.info("模型列表已更新：provider=%s 新增 %d 个", pc.name, len(models) - len(existing))
    return ProviderModelsOut(items=items, count=len(items))


@router.post("/providers/{provider_id}/models", response_model=ProviderModelOut)
def add_provider_model(
    provider_id: UUID,
    body: ProviderModelCreate,
    session: SessionDep,
    current_user: User = Depends(get_current_user),
):
    """「自定义模型」：手填一个上游清单里没有的模型 ID。"""
    pc = _get_owned_provider(provider_id, session, current_user)
    dup = session.exec(
        select(ProviderModel).where(
            ProviderModel.provider_id == pc.id,
            ProviderModel.model_id == body.model_id.strip(),
        )
    ).one_or_none()
    if dup is not None:
        raise HTTPException(status_code=409, detail="该模型已在列表中")
    row = ProviderModel(
        provider_id=pc.id,
        model_id=body.model_id.strip(),
        display_name=body.display_name,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return ProviderModelOut(id=row.id, model_id=row.model_id, display_name=row.display_name)


@router.delete("/providers/{provider_id}/models/{model_id}")
def delete_provider_model(
    provider_id: UUID,
    model_id: UUID,
    session: SessionDep,
    current_user: User = Depends(get_current_user),
):
    """从清单移除一个模型（404 = 不存在或不是自己的）。"""
    pc = _get_owned_provider(provider_id, session, current_user)
    row = session.get(ProviderModel, model_id)
    if row is None or row.provider_id != pc.id:
        raise HTTPException(status_code=404, detail="模型不存在")
    session.delete(row)
    session.commit()
    return {"message": "模型已移除"}


# ── 多 API Key（「添加更多」）─────────────────────────────────


def _mask_key(plain: str) -> str:
    """明文 Key 打码：前 4 后 4，中间星号；过短则全遮。"""
    if len(plain) <= 12:
        return "****"
    return f"{plain[:4]}****{plain[-4:]}"


def _list_keys(session: Session, provider_id: UUID) -> list[ProviderKeyOut]:
    rows = session.exec(
        select(ProviderKey)
        .where(ProviderKey.provider_id == provider_id)
        .order_by(ProviderKey.created_at)
    ).all()
    items = []
    for r in rows:
        plain = decrypt_api_key(r.encrypted_key)
        items.append(
            ProviderKeyOut(
                id=r.id,
                key_mask=_mask_key(plain),
                is_active=r.is_active,
                fail_count=r.fail_count,
                cooldown_until=r.cooldown_until.isoformat() if r.cooldown_until else None,
                last_used_at=r.last_used_at.isoformat() if r.last_used_at else None,
            )
        )
    return items


@router.get("/providers/{provider_id}/keys", response_model=ProviderKeysOut)
def list_provider_keys(
    provider_id: UUID,
    session: SessionDep,
    current_user: User = Depends(get_current_user),
):
    """列出该供应商的密钥行（打码）。"""
    pc = _get_owned_provider(provider_id, session, current_user)
    items = _list_keys(session, pc.id)
    return ProviderKeysOut(items=items, count=len(items))


@router.post("/providers/{provider_id}/keys", response_model=ProviderKeysOut)
def add_provider_keys(
    provider_id: UUID,
    body: ProviderKeysAdd,
    session: SessionDep,
    current_user: User = Depends(get_current_user),
):
    """批量添加 Key（一行一个，去重、去空白）。"""
    from app.utils.crypto import encrypt_api_key

    pc = _get_owned_provider(provider_id, session, current_user)
    existing = {
        decrypt_api_key(r.encrypted_key)
        for r in session.exec(
            select(ProviderKey).where(ProviderKey.provider_id == pc.id)
        ).all()
    }
    added = 0
    for raw in body.keys:
        key = raw.strip()
        if not key or key in existing:
            continue
        session.add(ProviderKey(provider_id=pc.id, encrypted_key=encrypt_api_key(key)))
        existing.add(key)
        added += 1
    if added:
        session.commit()
    logger.info("密钥批量添加：provider=%s 新增 %d 把", pc.name, added)
    items = _list_keys(session, pc.id)
    return ProviderKeysOut(items=items, count=len(items))


@router.patch("/providers/{provider_id}/keys/{key_id}", response_model=ProviderKeyOut)
def toggle_provider_key(
    provider_id: UUID,
    key_id: UUID,
    body: dict,
    session: SessionDep,
    current_user: User = Depends(get_current_user),
):
    """启停一把 Key（停用后不参与轮换）。"""
    _get_owned_provider(provider_id, session, current_user)
    row = session.get(ProviderKey, key_id)
    if row is None or row.provider_id != provider_id:
        raise HTTPException(status_code=404, detail="密钥不存在")
    if "is_active" in body:
        row.is_active = bool(body["is_active"])
        if not row.is_active:
            row.fail_count = 0
            row.cooldown_until = None
        session.commit()
        session.refresh(row)
    items = _list_keys(session, provider_id)
    return next(i for i in items if i.id == key_id)


@router.delete("/providers/{provider_id}/keys/{key_id}")
def delete_provider_key(
    provider_id: UUID,
    key_id: UUID,
    session: SessionDep,
    current_user: User = Depends(get_current_user),
):
    """删除一把 Key（404 = 不存在或不是自己的）。"""
    _get_owned_provider(provider_id, session, current_user)
    row = session.get(ProviderKey, key_id)
    if row is None or row.provider_id != provider_id:
        raise HTTPException(status_code=404, detail="密钥不存在")
    session.delete(row)
    session.commit()
    remaining = _list_keys(session, provider_id)
    if not remaining:
        # 最后一行被删：留一个空提示由前端处理（api_key 列仍可回落）
        logger.warning("供应商 %s 的密钥行已清空，取 Key 将回落 api_key 列", provider_id)
    return {"message": "密钥已删除"}


@router.delete("/providers/{provider_id}")
def delete_provider(
    provider_id: UUID,
    session: SessionDep,
    current_user: User = Depends(get_current_user),
):
    """删除当前用户的一条 Provider 配置。"""
    mgr = ProviderManager(session)
    stmt = select(ProviderConfig).where(
        ProviderConfig.id == provider_id,
        ProviderConfig.user_id == current_user.id,
    )
    if session.exec(stmt).one_or_none() is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    mgr.delete_provider(provider_id)
    return {"ok": True}




