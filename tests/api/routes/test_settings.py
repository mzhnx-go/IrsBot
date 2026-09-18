"""部署设置端点测试。

覆盖三个端点：
- `GET  /settings/deployment`      超管读部署设置
- `PATCH /settings/deployment`     超管改自助注册开关（保存即生效）
- `GET  /utils/public-settings`    匿名读公开设置（登录页渲染注册入口用）

同时锁住**决策 2**：单用户模式只关**匿名自助注册**，超管仍可建号，
且切换模式**不会**删除或停用任何已有账号。
"""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, delete, select

from app.core.config import settings
from app.core.db.models import AppSetting
from app.core.db.sqlmodel_models import User
from tests.utils.utils import random_email, random_lower_string

DEPLOYMENT_URL = f"{settings.API_V1_STR}/settings/deployment"
PUBLIC_SETTINGS_URL = f"{settings.API_V1_STR}/utils/public-settings"
SIGNUP_URL = f"{settings.API_V1_STR}/users/signup"
USERS_URL = f"{settings.API_V1_STR}/users/"


def _signup_payload() -> dict[str, str]:
    """构造一份可用的匿名注册请求体（邮箱每次随机，避免撞已存在）。"""
    return {
        "email": random_email(),
        "password": random_lower_string(),
        "full_name": random_lower_string(),
    }


def _drop_user(db: Session, email: str) -> None:
    """删除测试新建的账号。

    `db` 是 session 级 fixture，中途新建的账号会一直留到整轮结束，
    会影响后续用例的账号计数断言，所以谁建谁清。
    """
    user = db.exec(select(User).where(User.email == email)).first()
    if user is not None:
        db.delete(user)
        db.commit()


@pytest.fixture(autouse=True)
def _runtime_settings_isolated(db: Session) -> Generator[None, None, None]:
    """每条用例前后清空运行时配置，防止开关状态跨用例泄漏。"""
    db.execute(delete(AppSetting))
    db.commit()
    yield
    db.execute(delete(AppSetting))
    db.commit()


# ── GET /settings/deployment ───────────────────────────────────


def test_read_deployment_settings_as_superuser(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """超管可读，且各字段自洽。"""
    r = client.get(DEPLOYMENT_URL, headers=superuser_token_headers)
    assert r.status_code == 200

    body = r.json()
    assert body["open_registration"] is False
    assert body["mode"] == "single_user"
    assert body["user_count"] >= 1
    # `.env` 兜底值原样回传，便于管理员排查「为什么我改 .env 不生效」
    assert body["env_open_registration"] is settings.USERS_OPEN_REGISTRATION


def test_read_deployment_settings_forbidden_for_normal_user(
    client: TestClient, normal_user_token_headers: dict[str, str]
) -> None:
    """普通用户 403 —— 部署设置是超管专属。"""
    r = client.get(DEPLOYMENT_URL, headers=normal_user_token_headers)
    assert r.status_code == 403


def test_read_deployment_settings_requires_auth(client: TestClient) -> None:
    """匿名 401。"""
    r = client.get(DEPLOYMENT_URL)
    assert r.status_code == 401


# ── PATCH /settings/deployment ─────────────────────────────────


def test_patch_opens_registration_immediately(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """打开后**无需重启**，下一次匿名注册即放行 —— 这是运行时开关的全部意义。"""
    r = client.patch(
        DEPLOYMENT_URL,
        headers=superuser_token_headers,
        json={"open_registration": True},
    )
    assert r.status_code == 200
    assert r.json()["open_registration"] is True
    assert r.json()["mode"] == "multi_tenant"

    payload = _signup_payload()
    signup = client.post(SIGNUP_URL, json=payload)
    assert signup.status_code == 200
    assert signup.json()["email"] == payload["email"]

    _drop_user(db, payload["email"])


def test_patch_closes_registration_immediately(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """关闭后立刻 403（先打开、再关闭，证明是开关在起作用而非默认值）。"""
    opened = client.patch(
        DEPLOYMENT_URL,
        headers=superuser_token_headers,
        json={"open_registration": True},
    )
    assert opened.status_code == 200

    closed = client.patch(
        DEPLOYMENT_URL,
        headers=superuser_token_headers,
        json={"open_registration": False},
    )
    assert closed.status_code == 200
    assert closed.json()["open_registration"] is False
    assert closed.json()["mode"] == "single_user"

    assert client.post(SIGNUP_URL, json=_signup_payload()).status_code == 403


def test_patch_forbidden_for_normal_user(
    client: TestClient, normal_user_token_headers: dict[str, str]
) -> None:
    """普通用户改不动，且**确实没有生效**（不能只看状态码）。"""
    r = client.patch(
        DEPLOYMENT_URL,
        headers=normal_user_token_headers,
        json={"open_registration": True},
    )
    assert r.status_code == 403

    assert client.post(SIGNUP_URL, json=_signup_payload()).status_code == 403


def test_patch_requires_auth(client: TestClient) -> None:
    """匿名 401，且没生效。"""
    r = client.patch(DEPLOYMENT_URL, json={"open_registration": True})
    assert r.status_code == 401

    assert client.post(SIGNUP_URL, json=_signup_payload()).status_code == 403


def test_patch_rejects_non_bool(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """无法解析成布尔的取值 → 422。

    注意：pydantic 宽松模式会把 "true"/"yes"/"1" 这类**合法**字符串转成布尔，
    所以这里用真正无法解析的 "maybe"——否则测的是「有没有报错」而不是
    「非法值会不会被静默当成 False」。
    """
    r = client.patch(
        DEPLOYMENT_URL,
        headers=superuser_token_headers,
        json={"open_registration": "maybe"},
    )
    assert r.status_code == 422


def test_patch_rejects_missing_field(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """字段缺失 → 422（不提供「什么都不改」的隐式语义，避免误判成功）。"""
    r = client.patch(DEPLOYMENT_URL, headers=superuser_token_headers, json={})
    assert r.status_code == 422


# ── 决策 2 的回归：单用户模式仍是「关注册」，不是「只许一个账号」 ──


def test_admin_can_still_create_user_while_registration_closed(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """单用户模式下超管仍可建号 —— 注册闸门只管**匿名自助注册**。"""
    closed = client.patch(
        DEPLOYMENT_URL,
        headers=superuser_token_headers,
        json={"open_registration": False},
    )
    assert closed.status_code == 200

    payload = _signup_payload()
    r = client.post(USERS_URL, headers=superuser_token_headers, json=payload)
    assert r.status_code == 200
    assert r.json()["email"] == payload["email"]

    _drop_user(db, payload["email"])


def test_switching_mode_never_touches_existing_accounts(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """来回切换模式，账号数不变（不删、不冻结）。

    这条防的是「切回单用户顺手清掉多余账号」这种想当然的实现。
    """
    before = client.get(DEPLOYMENT_URL, headers=superuser_token_headers).json()

    client.patch(
        DEPLOYMENT_URL,
        headers=superuser_token_headers,
        json={"open_registration": True},
    )
    middle = client.get(DEPLOYMENT_URL, headers=superuser_token_headers).json()

    client.patch(
        DEPLOYMENT_URL,
        headers=superuser_token_headers,
        json={"open_registration": False},
    )
    after = client.get(DEPLOYMENT_URL, headers=superuser_token_headers).json()

    assert before["user_count"] == middle["user_count"] == after["user_count"]


# ── GET /utils/public-settings ─────────────────────────────────


def test_public_settings_is_readable_anonymously(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """匿名可读，且只暴露 open_registration 一位布尔。

    登录页必须在**鉴权之前**判断要不要渲染「注册」入口，所以这个端点
    不能要求登录；也正因为匿名，它**不许**夹带任何其它字段。
    """
    monkeypatch.setattr(settings, "USERS_OPEN_REGISTRATION", False)

    r = client.get(PUBLIC_SETTINGS_URL)
    assert r.status_code == 200
    assert r.json() == {"open_registration": False}


def test_public_settings_tracks_runtime_value(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """运行时改了开关，公开端点同步跟随（登录页据此显示/隐藏注册入口）。"""
    client.patch(
        DEPLOYMENT_URL,
        headers=superuser_token_headers,
        json={"open_registration": True},
    )

    r = client.get(PUBLIC_SETTINGS_URL)
    assert r.status_code == 200
    assert r.json() == {"open_registration": True}
