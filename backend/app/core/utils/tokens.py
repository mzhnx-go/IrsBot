# 密码重置 token 的签发与校验（纯 JWT，无邮件依赖）。
#
# ⚠️ 从模板的 core/utils/email.py 中拆出（2026-09-17，D1.4 邮件依赖删除）：
#    原文件里的 send_email / generate_*_email 依赖 `emails` + `aiosmtplib`（已删），
#    但这两个 token 函数只是 jwt 签发/校验，与邮件无关 —— 被 /reset-password 端点使用。
import jwt
from datetime import datetime, timedelta, timezone

from jwt.exceptions import InvalidTokenError

from app.core.auth.security import ALGORITHM
from app.core.config import settings


def generate_password_reset_token(email: str) -> str:
    delta = timedelta(hours=settings.EMAIL_RESET_TOKEN_EXPIRE_HOURS)
    now = datetime.now(timezone.utc)
    expires = now + delta
    exp = expires.timestamp()
    encoded_jwt = jwt.encode(
        {"exp": exp, "nbf": now, "sub": email},
        settings.SECRET_KEY,
        algorithm=ALGORITHM,
    )
    return encoded_jwt


def verify_password_reset_token(token: str) -> str | None:
    try:
        decoded_token = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[ALGORITHM]
        )
        return str(decoded_token["sub"])
    except InvalidTokenError:
        return None
