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
    ToolPermissionsPublic,
    ToolPermissionsUpdate,
)
from app.core.settings_runtime import (
    count_users,
    deployment_mode,
    file_write_enabled,
    set_open_registration,
    set_tool_permissions,
    shell_enabled,
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


def _tool_permissions_response(session: Session) -> ToolPermissionsPublic:
    """组装工具权限响应（GET / PATCH 共用）。"""
    return ToolPermissionsPublic(
        shell_enabled=shell_enabled(session),
        file_write_enabled=file_write_enabled(session),
        env_shell_enabled=settings.ENABLE_SHELL,
        env_file_write_enabled=settings.ENABLE_FILE_WRITE,
    )


@router.get(
    "/tools",
    dependencies=[Depends(get_current_active_superuser)],
    response_model=ToolPermissionsPublic,
)
def read_tool_permissions(session: SessionDep) -> ToolPermissionsPublic:
    """读取工具权限开关（**超管专属**，Phase 15.2f）。"""
    return _tool_permissions_response(session)


@router.patch(
    "/tools",
    dependencies=[Depends(get_current_active_superuser)],
    response_model=ToolPermissionsPublic,
)
def update_tool_permissions(
    *, session: SessionDep, body: ToolPermissionsUpdate
) -> ToolPermissionsPublic:
    """更新工具权限开关（**超管专属**），保存即生效、无需重启。

    开启后 shell_execute / file_read / file_write 会出现在 Agent 可用工具
    列表里；file_write 仍受 FILE_WRITE_ROOTS 路径白名单约束。
    """
    current_shell = shell_enabled(session)
    current_file = file_write_enabled(session)
    set_tool_permissions(
        session,
        shell=body.shell_enabled if body.shell_enabled is not None else current_shell,
        file_write=(
            body.file_write_enabled
            if body.file_write_enabled is not None
            else current_file
        ),
    )
    return _tool_permissions_response(session)
