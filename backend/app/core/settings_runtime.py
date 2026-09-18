"""运行时配置读写层 —— 让部分系统开关不必改 `.env`、不必重启即可生效。

与 `app.core.config.settings` 的分工：

| | 载体 | 生效时机 | 角色 |
|---|---|---|---|
| 部署级配置 | `.env` → `Settings` | 进程启动时读取，改了要重启 | 同时充当运行时配置的**兜底初值** |
| 运行时配置 | `app_settings` 表 | 保存即生效 | 有记录时**覆盖** `.env` |

**优先级：`app_settings` 表 > `.env` > 代码默认值。**

兜底链的意义：升级后表是空的 → 系统行为与升级前**完全一致**；现有依赖
`settings.USERS_OPEN_REGISTRATION` 的测试也不必改写。

⚠️ 键名一律用本模块的常量，不要在各处手写字符串。KV 表没有 schema，
拼错的键不会报错，只会**静默新增一行**，表现为「配置改了不生效」。
"""

from typing import Final, Literal

from sqlmodel import Session, func, select

from app.core.config import settings
from app.core.db.models import AppSetting
from app.core.db.sqlmodel_models import User

# ── 键名常量 ───────────────────────────────────────────────────

#: 匿名自助注册是否开放。唯一对外的运行时开关。
KEY_OPEN_REGISTRATION: Final = "users.open_registration"

_TRUTHY: Final = frozenset({"1", "true", "yes", "on"})
_FALSY: Final = frozenset({"0", "false", "no", "off"})


def _parse_bool(raw: str | None) -> bool | None:
    """把 KV 里的字符串解析成布尔。

    Args:
        raw: 原始值；None 表示该键没有记录。

    Returns:
        True / False；值无法识别时返回 None（按「没有记录」处理，即回落 .env）。
        这样即使有人手工往表里写了个乱值，也不会得到意外行为。
    """
    if raw is None:
        return None
    value = raw.strip().lower()
    if value in _TRUTHY:
        return True
    if value in _FALSY:
        return False
    return None


# ── 通用 KV 读写（后续增加运行开关时直接复用，零迁移）──────────


def get_setting(session: Session, key: str) -> str | None:
    """读取一条运行时配置的原始字符串值。

    Args:
        session: 数据库会话。
        key: 配置键，建议用本模块的 `KEY_*` 常量。

    Returns:
        原始值；该键没有记录时返回 None（调用方据此回落 `.env`）。
    """
    obj = session.get(AppSetting, key)
    return obj.value if obj is not None else None


def set_setting(session: Session, key: str, value: str) -> None:
    """写入（或覆盖）一条运行时配置，立即提交。

    Args:
        session: 数据库会话。
        key: 配置键。
        value: 原始字符串值。
    """
    obj = session.get(AppSetting, key)
    if obj is None:
        obj = AppSetting(key=key, value=value)
    else:
        obj.value = value
    session.add(obj)
    session.commit()


# ── 自助注册开关 ───────────────────────────────────────────────


def signup_allowed(session: Session) -> bool:
    """匿名自助注册是否放行 —— **全项目唯一判断点**。

    判断依据只在这里计算。别在别处重复拼条件：依据一旦分散，早晚会分歧
    （例如新加一处只读 `.env` 的检查，运行时开关就形同虚设）。

    Args:
        session: 数据库会话。

    Returns:
        True 表示 `POST /users/signup` 放行；False 表示返回 403。
    """
    parsed = _parse_bool(get_setting(session, KEY_OPEN_REGISTRATION))
    if parsed is None:
        # 表里没有记录（或值不可识别）→ 回落部署级配置
        return settings.USERS_OPEN_REGISTRATION
    return parsed


def set_open_registration(session: Session, enabled: bool) -> None:
    """写入自助注册开关（超管操作，保存即生效）。

    Args:
        session: 数据库会话。
        enabled: True 开放自助注册，False 关闭。
    """
    set_setting(session, KEY_OPEN_REGISTRATION, "true" if enabled else "false")


def deployment_mode(session: Session) -> Literal["single_user", "multi_tenant"]:
    """部署模式的**展示标签**，由 `signup_allowed` 换算得到。

    ⚠️ 这不是独立配置项。之所以单独放在这里，是为了让「UI 词汇 ↔ 配置」
    的映射只有一处；将来若真的引入独立的模式键，也只改这一个函数。

    Args:
        session: 数据库会话。

    Returns:
        "multi_tenant"（开放自助注册）或 "single_user"（关闭）。
    """
    return "multi_tenant" if signup_allowed(session) else "single_user"


def count_users(session: Session) -> int:
    """统计系统内账号数（供前端提示「已有 N 个账号」）。

    Args:
        session: 数据库会话。

    Returns:
        用户表行数。
    """
    return session.exec(select(func.count()).select_from(User)).one()
