"""Provider 管理 REST API —— ProviderManager CRUD 的接口层。

多租户规则：所有操作按 user_id 过滤，只能看/改自己的 provider 配置。
设默认互斥：同一用户只有一条 is_default=True。
"""


import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from app.api.deps import SessionDep, get_current_user
from app.core.agent.provider import ProviderManager
from app.core.agent.provider_balance import ProviderBalanceOut, query_balance
from app.core.db.models import ProviderConfig
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

    result = await query_balance(
        base_url=pc.base_url, api_key=decrypt_api_key(pc.api_key)
    )
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
    fields = body.model_dump(exclude_none=True)
    # supports_vision 是唯一「None 本身有意义」的字段（None=自动），
    # exclude_none 会把「改回自动」的请求吃掉，故显式按是否传过来判断。
    if "supports_vision" in body.model_fields_set:
        fields["supports_vision"] = body.supports_vision
    return mgr.update_provider(provider_id, **fields)


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




