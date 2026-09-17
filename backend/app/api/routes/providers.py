"""Provider 管理 REST API —— ProviderManager CRUD 的接口层。

多租户规则：所有操作按 user_id 过滤，只能看/改自己的 provider 配置。
设默认互斥：同一用户只有一条 is_default=True。
""" 


from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from app.api.deps import SessionDep, get_current_user
from app.core.agent.provider import ProviderManager
from app.core.db.models import ProviderConfig
from app.core.db.sqlmodel_models import User

router = APIRouter(tags=["providers"])

class ProviderCreate(BaseModel):
    """创建请求体"""
    name: str
    provider_type: str
    api_key: str
    model_name: str
    base_url: str | None = None
    is_default: bool = False


class ProviderUpdate(BaseModel):
    """更新请求体：所有字段可选"""
    name: str | None = None
    api_key: str | None = None
    model_name: str | None = None
    base_url: str | None = None
    is_default: bool | None = None

class ProviderOut(BaseModel):
    """响应体: 绝不返回明文 api_key"""
    id: UUID
    name: str
    provider_type: str
    model_name: str
    base_url: str | None
    is_default: bool
    is_active: bool



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
    )
    return obj



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
    return mgr.update_provider(provider_id, **body.model_dump(exclude_none=True))


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




