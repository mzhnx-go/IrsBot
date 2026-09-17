from collections.abc import Generator
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Query, WebSocket, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError
from sqlmodel import Session

from app.core.auth import security
from app.core.config import settings
from app.core.db.engine import engine
from app.core.db.sqlmodel_models import TokenPayload, User

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token"
)


def get_db() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_db)]
TokenDep = Annotated[str, Depends(reusable_oauth2)]


def _get_user_by_token(session: Session, token: str) -> User:
    """公共逻辑：校验 JWT 并返回用户（HTTP 与 WebSocket 鉴权共用）"""
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except (InvalidTokenError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
    user = session.get(User, token_data.sub)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user


def get_current_user(session: SessionDep, token: TokenDep) -> User:
    return _get_user_by_token(session, token)


def get_current_user_ws(
    ws: WebSocket, session: SessionDep, token: str = Query(...)
) -> User:
    """WebSocket 鉴权：token 走 URL 查询参数（浏览器 WS API 不支持自定义请求头）"""
    return _get_user_by_token(session, token)


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_current_active_superuser(current_user: CurrentUser) -> User:
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403, detail="The user doesn't have enough privileges"
        )
    return current_user
