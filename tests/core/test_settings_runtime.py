"""运行时配置层（`app_settings`）单元测试。

重点锁住**优先级**：`app_settings` 表 > `.env`。这条一旦走偏，就会出现
「管理员在网页改了开关却不生效」或「`.env` 改了却被旧记录悄悄覆盖」——
两者都是**无报错的失效**，本项目最忌讳的一类故障。
"""

from collections.abc import Generator

import pytest
from sqlmodel import Session, delete

from app.core.config import settings
from app.core.db.models import AppSetting
from app.core.settings_runtime import (
    KEY_ENABLE_FILE_WRITE,
    KEY_ENABLE_SHELL,
    KEY_OPEN_REGISTRATION,
    _parse_bool,
    count_users,
    deployment_mode,
    file_write_enabled,
    get_setting,
    set_open_registration,
    set_setting,
    set_tool_permissions,
    shell_enabled,
)

# 便于测试直接校验其它键的通用读写
OTHER_KEY = "test.some_key"


def _clear(session: Session) -> None:
    session.execute(delete(AppSetting))
    session.commit()


def _raw_write(session: Session, value: str) -> None:
    """绕过类型化助手，直接往 KV 表写原始值。

    模拟「手工改库」或「旧版本 / 其它进程写入」的情况：读取路径必须能容忍。
    """
    session.add(AppSetting(key=KEY_OPEN_REGISTRATION, value=value))
    session.commit()


@pytest.fixture(autouse=True)
def _runtime_settings_isolated(db: Session) -> Generator[None, None, None]:
    """每条用例前后清空运行时配置。

    ⚠️ `db` 是 **session 级**的：不清的话，某条用例写下的 `true` 会**漏给
    后面所有用例**（包括 `test_users.py` 里依赖「默认关闭」的注册闸门断言）。
    """
    _clear(db)
    yield
    _clear(db)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("true", True),
        ("TRUE", True),
        ("  yes  ", True),
        ("1", True),
        ("on", True),
        ("false", False),
        ("0", False),
        ("no", False),
        ("off", False),
        # 以下无法识别 → None，调用方据此回落 .env（而不是猜一个值）
        (None, None),
        ("maybe", None),
        ("", None),
    ],
)
def test_parse_bool(raw: str | None, expected: bool | None) -> None:
    """布尔解析：可识别的取值 + 无法识别时明确返回 None。"""
    assert _parse_bool(raw) is expected


def test_signup_allowed_falls_back_to_env_when_no_record(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """表里没有记录时，一律以 `.env` 为准（升级后行为零变化）。"""
    assert get_setting(db, KEY_OPEN_REGISTRATION) is None

    monkeypatch.setattr(settings, "USERS_OPEN_REGISTRATION", False)
    assert _parse_bool(get_setting(db, KEY_OPEN_REGISTRATION)) is None
    assert deployment_mode(db) == "single_user"

    monkeypatch.setattr(settings, "USERS_OPEN_REGISTRATION", True)
    assert deployment_mode(db) == "multi_tenant"


def test_runtime_value_overrides_env_both_directions(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """运行时值覆盖 `.env` —— 两个方向都必须锁。

    只测一个方向会漏掉「改小了不生效」这种更隐蔽的情况：
    例如管理员在网页关了注册，`.env` 却还是 true。
    """
    # .env 关、运行时开 → 开
    monkeypatch.setattr(settings, "USERS_OPEN_REGISTRATION", False)
    _raw_write(db, "true")
    assert deployment_mode(db) == "multi_tenant"

    # .env 开、运行时关 → 关
    _clear(db)
    monkeypatch.setattr(settings, "USERS_OPEN_REGISTRATION", True)
    _raw_write(db, "false")
    assert deployment_mode(db) == "single_user"


def test_garbage_value_falls_back_to_env(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """表里被写进无法识别的值时，回落 `.env`，而不是擅自当成 True/False。"""
    monkeypatch.setattr(settings, "USERS_OPEN_REGISTRATION", False)
    _raw_write(db, "definitely-not-a-bool")
    assert deployment_mode(db) == "single_user"


def test_set_open_registration_round_trip(db: Session) -> None:
    """类型化写入器：布尔 → 字符串 → 布尔，且模式标签同步跟随。"""
    set_open_registration(db, True)
    assert get_setting(db, KEY_OPEN_REGISTRATION) == "true"
    assert deployment_mode(db) == "multi_tenant"

    set_open_registration(db, False)
    assert get_setting(db, KEY_OPEN_REGISTRATION) == "false"
    assert deployment_mode(db) == "single_user"


def test_generic_set_setting_overwrites(db: Session) -> None:
    """通用 KV 读写：同一键重复写入应覆盖，而不是插出第二行。

    这条保证「后续增加运行开关不必再写迁移」这个前提真的成立。
    """
    set_setting(db, OTHER_KEY, "a")
    assert get_setting(db, OTHER_KEY) == "a"

    set_setting(db, OTHER_KEY, "b")
    assert get_setting(db, OTHER_KEY) == "b"


def test_get_setting_missing_key_returns_none(db: Session) -> None:
    """从未写入过的键返回 None（键名拼错时表现为「回落 .env」而非报错）。"""
    assert get_setting(db, "test.never_written") is None


def test_count_users_is_positive(db: Session) -> None:
    """用户计数可用（init_db 至少播种了超管）。"""
    assert count_users(db) >= 1


def test_runtime_key_constant_matches_documented_name() -> None:
    """锁住键名：改名会让已部署实例上的旧记录**全部失效**（静默回落 .env）。"""
    assert KEY_OPEN_REGISTRATION == "users.open_registration"


# ── 工具权限开关（D6 / Phase 15.2f）─────────────────────────────


def test_tool_permission_key_constants_match_documented_names() -> None:
    """锁住工具权限键名（同上：改名 = 已部署实例上的开关静默失效）。"""
    assert KEY_ENABLE_SHELL == "tools.enable_shell"
    assert KEY_ENABLE_FILE_WRITE == "tools.enable_file_write"


def test_tool_flags_fall_back_to_env(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """表里没有记录时，工具开关以 `.env` 为准 —— 两个方向都测。"""
    monkeypatch.setattr(settings, "ENABLE_SHELL", False)
    monkeypatch.setattr(settings, "ENABLE_FILE_WRITE", False)
    assert shell_enabled(db) is False
    assert file_write_enabled(db) is False

    monkeypatch.setattr(settings, "ENABLE_SHELL", True)
    monkeypatch.setattr(settings, "ENABLE_FILE_WRITE", True)
    assert shell_enabled(db) is True
    assert file_write_enabled(db) is True


def test_tool_flags_runtime_override_wins_both_directions(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """运行时记录覆盖 `.env`：网页开了 `.env` 关 → 开；反之 → 关。"""
    monkeypatch.setattr(settings, "ENABLE_SHELL", False)
    set_tool_permissions(db, shell=True, file_write=False)
    assert shell_enabled(db) is True
    assert file_write_enabled(db) is False

    # 再关掉：网页的关闭决定同样要赢过 `.env`
    set_tool_permissions(db, shell=False, file_write=False)
    assert shell_enabled(db) is False


def test_tool_flags_garbage_falls_back_to_env(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """脏值不猜语义 —— 回落 `.env`，危险工具不会因为一行坏数据被放开。"""
    monkeypatch.setattr(settings, "ENABLE_SHELL", False)
    set_setting(db, KEY_ENABLE_SHELL, "maybe")
    assert shell_enabled(db) is False


def test_set_tool_permissions_round_trip(db: Session) -> None:
    """类型化写入器：两个键都落库，值可被读回。"""
    set_tool_permissions(db, shell=True, file_write=True)
    assert get_setting(db, KEY_ENABLE_SHELL) == "true"
    assert get_setting(db, KEY_ENABLE_FILE_WRITE) == "true"
    assert shell_enabled(db) is True
    assert file_write_enabled(db) is True
