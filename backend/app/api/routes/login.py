from datetime import timedelta
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import CurrentUser, SessionDep, get_current_active_superuser
from app.core import crud
from app.core.auth import security
from app.core.config import settings
from app.core.db.sqlmodel_models import (
    Message,
    NewPassword,
    Token,
    UserPublic,
    UserUpdate,
)
from app.core.utils.tokens import verify_password_reset_token

router = APIRouter(tags=["login"])

logger = logging.getLogger(__name__)


@router.post("/login/access-token")
def login_access_token(
    session: SessionDep, form_data: Annotated[OAuth2PasswordRequestForm, Depends()]
) -> Token:
    """
    OAuth2 compatible token login, get an access token for future requests
    """
    user = crud.authenticate(
        session=session, email=form_data.username, password=form_data.password
    )
    if not user:
        logger.warning("登录失败（凭据错误）：email=%s", form_data.username)
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    elif not user.is_active:
        logger.warning("登录拒绝（账号已停用）：email=%s", form_data.username)
        raise HTTPException(status_code=400, detail="Inactive user")
    logger.info("登录成功：%s", user.email)
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return Token(
        access_token=security.create_access_token(
            user.id, expires_delta=access_token_expires
        )
    )


@router.post("/login/test-token", response_model=UserPublic)
def test_token(current_user: CurrentUser) -> Any:
    """
    Test access token
    """
    return current_user


@router.post("/reset-password/")
def reset_password(session: SessionDep, body: NewPassword) -> Message:
    """
    Reset password
    """
    email = verify_password_reset_token(token=body.token)
    if not email:
        raise HTTPException(status_code=400, detail="Invalid token")
    user = crud.get_user_by_email(session=session, email=email)
    if not user:
        # Don't reveal that the user doesn't exist - use same error as invalid token
        raise HTTPException(status_code=400, detail="Invalid token")
    elif not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    user_in_update = UserUpdate(password=body.new_password)
    crud.update_user(
        session=session,
        db_user=user,
        user_in=user_in_update,
    )
    return Message(message="Password updated successfully")
