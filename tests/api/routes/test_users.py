import uuid

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import crud
from app.core.config import settings
from app.core.auth.security import verify_password
from app.models import User, UserCreate
from tests.utils.user import create_random_user
from tests.utils.utils import random_email, random_lower_string
from app.core.agent.prompts import DEFAULT_SYSTEM_PROMPT, resolve_system_prompt


def test_get_users_superuser_me(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    r = client.get(f"{settings.API_V1_STR}/users/me", headers=superuser_token_headers)
    current_user = r.json()
    assert current_user
    assert current_user["is_active"] is True
    assert current_user["is_superuser"]
    assert current_user["email"] == settings.FIRST_SUPERUSER


def test_get_users_normal_user_me(
    client: TestClient, normal_user_token_headers: dict[str, str]
) -> None:
    r = client.get(f"{settings.API_V1_STR}/users/me", headers=normal_user_token_headers)
    current_user = r.json()
    assert current_user
    assert current_user["is_active"] is True
    assert current_user["is_superuser"] is False
    assert current_user["email"] == settings.EMAIL_TEST_USER


def test_create_user_new_email(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    username = random_email()
    password = random_lower_string()
    data = {"email": username, "password": password}
    r = client.post(
        f"{settings.API_V1_STR}/users/",
        headers=superuser_token_headers,
        json=data,
    )
    assert 200 <= r.status_code < 300
    created_user = r.json()
    user = crud.get_user_by_email(session=db, email=username)
    assert user
    assert user.email == created_user["email"]


def test_get_existing_user_as_superuser(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    username = random_email()
    password = random_lower_string()
    user_in = UserCreate(email=username, password=password)
    user = crud.create_user(session=db, user_create=user_in)
    user_id = user.id
    r = client.get(
        f"{settings.API_V1_STR}/users/{user_id}",
        headers=superuser_token_headers,
    )
    assert 200 <= r.status_code < 300
    api_user = r.json()
    existing_user = crud.get_user_by_email(session=db, email=username)
    assert existing_user
    assert existing_user.email == api_user["email"]


def test_get_non_existing_user_as_superuser(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    r = client.get(
        f"{settings.API_V1_STR}/users/{uuid.uuid4()}",
        headers=superuser_token_headers,
    )
    assert r.status_code == 404
    assert r.json() == {"detail": "User not found"}


def test_get_existing_user_current_user(client: TestClient, db: Session) -> None:
    username = random_email()
    password = random_lower_string()
    user_in = UserCreate(email=username, password=password)
    user = crud.create_user(session=db, user_create=user_in)
    user_id = user.id

    login_data = {
        "username": username,
        "password": password,
    }
    r = client.post(f"{settings.API_V1_STR}/login/access-token", data=login_data)
    tokens = r.json()
    a_token = tokens["access_token"]
    headers = {"Authorization": f"Bearer {a_token}"}

    r = client.get(
        f"{settings.API_V1_STR}/users/{user_id}",
        headers=headers,
    )
    assert 200 <= r.status_code < 300
    api_user = r.json()
    existing_user = crud.get_user_by_email(session=db, email=username)
    assert existing_user
    assert existing_user.email == api_user["email"]


def test_get_existing_user_permissions_error(
    db: Session,
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    user = create_random_user(db)

    r = client.get(
        f"{settings.API_V1_STR}/users/{user.id}",
        headers=normal_user_token_headers,
    )
    assert r.status_code == 403
    assert r.json() == {"detail": "The user doesn't have enough privileges"}


def test_get_non_existing_user_permissions_error(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    user_id = uuid.uuid4()

    r = client.get(
        f"{settings.API_V1_STR}/users/{user_id}",
        headers=normal_user_token_headers,
    )
    assert r.status_code == 403
    assert r.json() == {"detail": "The user doesn't have enough privileges"}


def test_create_user_existing_username(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    username = random_email()
    # username = email
    password = random_lower_string()
    user_in = UserCreate(email=username, password=password)
    crud.create_user(session=db, user_create=user_in)
    data = {"email": username, "password": password}
    r = client.post(
        f"{settings.API_V1_STR}/users/",
        headers=superuser_token_headers,
        json=data,
    )
    created_user = r.json()
    assert r.status_code == 400
    assert "_id" not in created_user


def test_create_user_by_normal_user(
    client: TestClient, normal_user_token_headers: dict[str, str]
) -> None:
    username = random_email()
    password = random_lower_string()
    data = {"email": username, "password": password}
    r = client.post(
        f"{settings.API_V1_STR}/users/",
        headers=normal_user_token_headers,
        json=data,
    )
    assert r.status_code == 403


def test_retrieve_users(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    username = random_email()
    password = random_lower_string()
    user_in = UserCreate(email=username, password=password)
    crud.create_user(session=db, user_create=user_in)

    username2 = random_email()
    password2 = random_lower_string()
    user_in2 = UserCreate(email=username2, password=password2)
    crud.create_user(session=db, user_create=user_in2)

    r = client.get(f"{settings.API_V1_STR}/users/", headers=superuser_token_headers)
    all_users = r.json()

    assert len(all_users["data"]) > 1
    assert "count" in all_users
    for item in all_users["data"]:
        assert "email" in item


def test_update_user_me(
    client: TestClient, normal_user_token_headers: dict[str, str], db: Session
) -> None:
    full_name = "Updated Name"
    email = random_email()
    data = {"full_name": full_name, "email": email}
    r = client.patch(
        f"{settings.API_V1_STR}/users/me",
        headers=normal_user_token_headers,
        json=data,
    )
    assert r.status_code == 200
    updated_user = r.json()
    assert updated_user["email"] == email
    assert updated_user["full_name"] == full_name

    user_query = select(User).where(User.email == email)
    user_db = db.exec(user_query).first()
    assert user_db
    assert user_db.email == email
    assert user_db.full_name == full_name


def test_update_password_me(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    new_password = random_lower_string()
    data = {
        "current_password": settings.FIRST_SUPERUSER_PASSWORD,
        "new_password": new_password,
    }
    r = client.patch(
        f"{settings.API_V1_STR}/users/me/password",
        headers=superuser_token_headers,
        json=data,
    )
    assert r.status_code == 200
    updated_user = r.json()
    assert updated_user["message"] == "Password updated successfully"

    user_query = select(User).where(User.email == settings.FIRST_SUPERUSER)
    user_db = db.exec(user_query).first()
    assert user_db
    assert user_db.email == settings.FIRST_SUPERUSER
    verified, _ = verify_password(new_password, user_db.hashed_password)
    assert verified

    # Revert to the old password to keep consistency in test
    old_data = {
        "current_password": new_password,
        "new_password": settings.FIRST_SUPERUSER_PASSWORD,
    }
    r = client.patch(
        f"{settings.API_V1_STR}/users/me/password",
        headers=superuser_token_headers,
        json=old_data,
    )
    db.refresh(user_db)

    assert r.status_code == 200
    verified, _ = verify_password(
        settings.FIRST_SUPERUSER_PASSWORD, user_db.hashed_password
    )
    assert verified


def test_update_password_me_incorrect_password(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    new_password = random_lower_string()
    data = {"current_password": new_password, "new_password": new_password}
    r = client.patch(
        f"{settings.API_V1_STR}/users/me/password",
        headers=superuser_token_headers,
        json=data,
    )
    assert r.status_code == 400
    updated_user = r.json()
    assert updated_user["detail"] == "Incorrect password"


def test_update_user_me_email_exists(
    client: TestClient, normal_user_token_headers: dict[str, str], db: Session
) -> None:
    username = random_email()
    password = random_lower_string()
    user_in = UserCreate(email=username, password=password)
    user = crud.create_user(session=db, user_create=user_in)

    data = {"email": user.email}
    r = client.patch(
        f"{settings.API_V1_STR}/users/me",
        headers=normal_user_token_headers,
        json=data,
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "User with this email already exists"


def test_update_password_me_same_password_error(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    data = {
        "current_password": settings.FIRST_SUPERUSER_PASSWORD,
        "new_password": settings.FIRST_SUPERUSER_PASSWORD,
    }
    r = client.patch(
        f"{settings.API_V1_STR}/users/me/password",
        headers=superuser_token_headers,
        json=data,
    )
    assert r.status_code == 400
    updated_user = r.json()
    assert (
        updated_user["detail"] == "New password cannot be the same as the current one"
    )


def test_register_user(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """开关打开时注册端点正常工作（多用户场景 / 复用到另一个项目）。"""
    monkeypatch.setattr(settings, "USERS_OPEN_REGISTRATION", True)
    username = random_email()
    password = random_lower_string()
    full_name = random_lower_string()
    data = {"email": username, "password": password, "full_name": full_name}
    r = client.post(
        f"{settings.API_V1_STR}/users/signup",
        json=data,
    )
    assert r.status_code == 200
    created_user = r.json()
    assert created_user["email"] == username
    assert created_user["full_name"] == full_name

    user_query = select(User).where(User.email == username)
    user_db = db.exec(user_query).first()
    assert user_db
    assert user_db.email == username
    assert user_db.full_name == full_name
    verified, _ = verify_password(password, user_db.hashed_password)
    assert verified


def test_register_user_already_exists_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """开关打开时，注册已存在的邮箱返回 400。"""
    monkeypatch.setattr(settings, "USERS_OPEN_REGISTRATION", True)
    password = random_lower_string()
    full_name = random_lower_string()
    data = {
        "email": settings.FIRST_SUPERUSER,
        "password": password,
        "full_name": full_name,
    }
    r = client.post(
        f"{settings.API_V1_STR}/users/signup",
        json=data,
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "The user with this email already exists in the system"


def test_register_user_forbidden_when_disabled(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """安全默认：注册开关关闭时，匿名注册一律 403 且不落库。"""
    monkeypatch.setattr(settings, "USERS_OPEN_REGISTRATION", False)
    username = random_email()
    data = {
        "email": username,
        "password": random_lower_string(),
        "full_name": random_lower_string(),
    }
    r = client.post(
        f"{settings.API_V1_STR}/users/signup",
        json=data,
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "Open user registration is forbidden on this server"

    user_query = select(User).where(User.email == username)
    assert db.exec(user_query).first() is None


def test_signup_disabled_does_not_leak_email_existence(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """关闭时，已存在邮箱与全新邮箱的响应必须完全一致。

    这条锁住「守卫必须在查重之前」：若把守卫挪到查重之后，已存在邮箱会
    变成 400 而新邮箱是 403，差异即可被用来枚举系统内有哪些账号。
    """
    monkeypatch.setattr(settings, "USERS_OPEN_REGISTRATION", False)
    existing = client.post(
        f"{settings.API_V1_STR}/users/signup",
        json={
            "email": settings.FIRST_SUPERUSER,
            "password": random_lower_string(),
            "full_name": random_lower_string(),
        },
    )
    fresh = client.post(
        f"{settings.API_V1_STR}/users/signup",
        json={
            "email": random_email(),
            "password": random_lower_string(),
            "full_name": random_lower_string(),
        },
    )
    assert existing.status_code == fresh.status_code == 403
    assert existing.json() == fresh.json()


def test_users_open_registration_default_is_false() -> None:
    """锁住安全默认：字段默认值必须是 False（与 .env 是否写无关）。"""
    from app.core.config import Settings

    assert Settings.model_fields["USERS_OPEN_REGISTRATION"].default is False


def test_update_user(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    username = random_email()
    password = random_lower_string()
    user_in = UserCreate(email=username, password=password)
    user = crud.create_user(session=db, user_create=user_in)

    data = {"full_name": "Updated_full_name"}
    r = client.patch(
        f"{settings.API_V1_STR}/users/{user.id}",
        headers=superuser_token_headers,
        json=data,
    )
    assert r.status_code == 200
    updated_user = r.json()

    assert updated_user["full_name"] == "Updated_full_name"

    user_query = select(User).where(User.email == username)
    user_db = db.exec(user_query).first()
    db.refresh(user_db)
    assert user_db
    assert user_db.full_name == "Updated_full_name"


def test_update_user_not_exists(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    data = {"full_name": "Updated_full_name"}
    r = client.patch(
        f"{settings.API_V1_STR}/users/{uuid.uuid4()}",
        headers=superuser_token_headers,
        json=data,
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "The user with this id does not exist in the system"


def test_update_user_email_exists(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    username = random_email()
    password = random_lower_string()
    user_in = UserCreate(email=username, password=password)
    user = crud.create_user(session=db, user_create=user_in)

    username2 = random_email()
    password2 = random_lower_string()
    user_in2 = UserCreate(email=username2, password=password2)
    user2 = crud.create_user(session=db, user_create=user_in2)

    data = {"email": user2.email}
    r = client.patch(
        f"{settings.API_V1_STR}/users/{user.id}",
        headers=superuser_token_headers,
        json=data,
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "User with this email already exists"


def test_delete_user_me(client: TestClient, db: Session) -> None:
    username = random_email()
    password = random_lower_string()
    user_in = UserCreate(email=username, password=password)
    user = crud.create_user(session=db, user_create=user_in)
    user_id = user.id

    login_data = {
        "username": username,
        "password": password,
    }
    r = client.post(f"{settings.API_V1_STR}/login/access-token", data=login_data)
    tokens = r.json()
    a_token = tokens["access_token"]
    headers = {"Authorization": f"Bearer {a_token}"}

    r = client.delete(
        f"{settings.API_V1_STR}/users/me",
        headers=headers,
    )
    assert r.status_code == 200
    deleted_user = r.json()
    assert deleted_user["message"] == "User deleted successfully"
    result = db.exec(select(User).where(User.id == user_id)).first()
    assert result is None

    user_query = select(User).where(User.id == user_id)
    user_db = db.execute(user_query).first()
    assert user_db is None


def test_delete_user_me_as_superuser(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    r = client.delete(
        f"{settings.API_V1_STR}/users/me",
        headers=superuser_token_headers,
    )
    assert r.status_code == 403
    response = r.json()
    assert response["detail"] == "Super users are not allowed to delete themselves"


def test_delete_user_super_user(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    username = random_email()
    password = random_lower_string()
    user_in = UserCreate(email=username, password=password)
    user = crud.create_user(session=db, user_create=user_in)
    user_id = user.id
    r = client.delete(
        f"{settings.API_V1_STR}/users/{user_id}",
        headers=superuser_token_headers,
    )
    assert r.status_code == 200
    deleted_user = r.json()
    assert deleted_user["message"] == "User deleted successfully"
    result = db.exec(select(User).where(User.id == user_id)).first()
    assert result is None


def test_delete_user_not_found(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    r = client.delete(
        f"{settings.API_V1_STR}/users/{uuid.uuid4()}",
        headers=superuser_token_headers,
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "User not found"


def test_delete_user_current_super_user_error(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    super_user = crud.get_user_by_email(session=db, email=settings.FIRST_SUPERUSER)
    assert super_user
    user_id = super_user.id

    r = client.delete(
        f"{settings.API_V1_STR}/users/{user_id}",
        headers=superuser_token_headers,
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "Super users are not allowed to delete themselves"


def test_delete_user_without_privileges(
    client: TestClient, normal_user_token_headers: dict[str, str], db: Session
) -> None:
    username = random_email()
    password = random_lower_string()
    user_in = UserCreate(email=username, password=password)
    user = crud.create_user(session=db, user_create=user_in)

    r = client.delete(
        f"{settings.API_V1_STR}/users/{user.id}",
        headers=normal_user_token_headers,
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "The user doesn't have enough privileges"


# -- 系统提示词测试 ------
def test_get_my_system_prompt_default(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """未设置过 → is_custom=False，effective_prompt=默认提示词"""
    r = client.get(
        f"{settings.API_V1_STR}/users/me/system-prompt",
        headers=superuser_token_headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["system_prompt"] is None
    assert data["is_custom"] is False
    assert data["effective_prompt"] == DEFAULT_SYSTEM_PROMPT


def test_update_my_system_prompt_roundtrip(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    db: Session,
) -> None:
    """保存自定义 → 生效并落库；传空串 → 清空回落默认"""
    # ① 保存自定义
    r = client.patch(
        f"{settings.API_V1_STR}/users/me/system-prompt",
        headers=superuser_token_headers,
        json={"system_prompt": "你是测试提示词"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["system_prompt"] == "你是测试提示词"
    assert data["is_custom"] is True
    assert data["effective_prompt"] == "你是测试提示词"

    # ② GET 读回（验证响应组装层）
    r = client.get(
        f"{settings.API_V1_STR}/users/me/system-prompt",
        headers=superuser_token_headers,
    )
    assert r.status_code == 200
    assert r.json()["system_prompt"] == "你是测试提示词"

    # ③ 直接查库（验证存储层）
    user_query = select(User).where(User.email == settings.FIRST_SUPERUSER)
    user_db = db.exec(user_query).one()
    assert user_db.system_prompt == "你是测试提示词"

    # ④ 传空串 → 清空回落默认
    r = client.patch(
        f"{settings.API_V1_STR}/users/me/system-prompt",
        headers=superuser_token_headers,
        json={"system_prompt": ""},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["system_prompt"] is None
    assert data["is_custom"] is False
    assert data["effective_prompt"] == DEFAULT_SYSTEM_PROMPT


def test_update_my_system_prompt_too_long(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """超过10000字符 -> 400"""
    r = client.patch(
        f"{settings.API_V1_STR}/users/me/system-prompt",
        headers=superuser_token_headers,
        json={"system_prompt": "a" * 10001},
    )
    assert r.status_code == 400


def test_resolve_system_prompt_branches() -> None:
    """解析函数两分支：自定义优先，空值回落默认"""
    assert resolve_system_prompt("自定义内容") == "自定义内容"
    assert resolve_system_prompt(None) == DEFAULT_SYSTEM_PROMPT
    assert resolve_system_prompt("") == DEFAULT_SYSTEM_PROMPT
    assert resolve_system_prompt("     ") == DEFAULT_SYSTEM_PROMPT
