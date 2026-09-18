from fastapi import APIRouter

from app.api.deps import SessionDep
from app.core.db.sqlmodel_models import PublicSettings
from app.core.settings_runtime import signup_allowed

router = APIRouter(prefix="/utils", tags=["utils"])


@router.get("/health-check/")
async def health_check() -> bool:
    return True


@router.get("/public-settings", response_model=PublicSettings)
def read_public_settings(session: SessionDep) -> PublicSettings:
    """读取公开设置（**无需登录**）。

    存在的唯一原因：登录页要在**鉴权之前**决定是否渲染「注册」入口。

    ⚠️ 只放可以公开的信息。目前只有 `open_registration` 一位布尔——
    它本身就能由「试一次 POST /users/signup」的结果推得，因此不构成
    额外泄露；敏感配置（`.env` 兜底值等）只在超管专属的
    `GET /settings/deployment` 里返回。

    Args:
        session: 数据库会话。

    Returns:
        PublicSettings：`open_registration` 为当前生效值
        （`app_settings` 表 > `.env`）。
    """
    return PublicSettings(open_registration=signup_allowed(session))
