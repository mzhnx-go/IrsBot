"""部署设置 REST API —— 运行时开关的读写入口（超管专属）。

目前只有一项：**匿名自助注册是否开放**。管理员在 `/admin` 页切换，
保存即生效，无需重启。

⚠️ 这里不复制任何判断逻辑：读走 `settings_runtime.signup_allowed()`，
写走 `settings_runtime.set_open_registration()`。判断依据只允许存在于
`settings_runtime` 一处——一旦分散，运行时开关早晚形同虚设。
"""

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.api.deps import SessionDep, get_current_active_superuser
from app.core.config import settings
from app.core.db.sqlmodel_models import (
    DeploymentSettingsPublic,
    DeploymentSettingsUpdate,
)
from app.core.settings_runtime import (
    count_users,
    deployment_mode,
    set_open_registration,
    signup_allowed,
)

router = APIRouter(prefix="/settings", tags=["settings"])


def _settings_response(session: Session) -> DeploymentSettingsPublic:
    """组装部署设置响应（GET / PATCH 共用，避免两处字段走偏）。

    Args:
        session: 数据库会话。

    Returns:
        含当前生效值、派生模式标签、账号数与 `.env` 兜底值的响应对象。
    """
    return DeploymentSettingsPublic(
        open_registration=signup_allowed(session),
        mode=deployment_mode(session),
        user_count=count_users(session),
        env_open_registration=settings.USERS_OPEN_REGISTRATION,
    )


@router.get(
    "/deployment",
    dependencies=[Depends(get_current_active_superuser)],
    response_model=DeploymentSettingsPublic,
)
def read_deployment_settings(session: SessionDep) -> DeploymentSettingsPublic:
    """读取部署设置（**超管专属**）。

    Args:
        session: 数据库会话。

    Returns:
        当前部署设置；`env_open_registration` 是 `.env` 里的兜底值，
        便于管理员判断「我改了网页开关，为什么 `.env` 不生效」。
    """
    return _settings_response(session)


@router.patch(
    "/deployment",
    dependencies=[Depends(get_current_active_superuser)],
    response_model=DeploymentSettingsPublic,
)
def update_deployment_settings(
    *, session: SessionDep, body: DeploymentSettingsUpdate
) -> DeploymentSettingsPublic:
    """更新部署设置（**超管专属**），保存即生效、无需重启。

    Args:
        session: 数据库会话。
        body: `open_registration` 目标值。

    Returns:
        更新后的部署设置。

    Note:
        关闭注册**不会**删除或停用任何已有账号；已存在的账号仍可正常登录。
    """
    set_open_registration(session, body.open_registration)
    return _settings_response(session)
