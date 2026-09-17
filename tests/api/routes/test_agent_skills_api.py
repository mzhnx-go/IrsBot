"""Skill API 端点测试

测试 /agent/skills 下的 5 个端点。
注意：install/delete 测试会操作真实的 backend/skills 目录，
测试后统一清理安装的测试 Skill。
"""

import io
import zipfile
import shutil
from pathlib import Path

import pytest

from app.api.routes.agent import SKILLS_DIR
from fastapi.testclient import TestClient

from app.core.config import settings

# 测试用的 SKILL.md 内容
TEST_SKILL_MD = """---
name: api-test-skill
description: API 测试技能
---

# API 测试指令
"""

@pytest.fixture(autouse=True)
def cleanup_test_skill():
    """每个测试结束后，清理安装的测试 Skill 目录

    yield 之前：准备（无操作）
    yield 之后：清理（删除测试安装的 api-test-skill）
    即使测试断言失败，清理逻辑也会执行。
    """
    yield
    test_dir = SKILLS_DIR / "api-test-skill"
    if test_dir.exists():
        shutil.rmtree(test_dir)

def make_skill_zip(skill_md: str = TEST_SKILL_MD) -> bytes:
    """在内存中构建一个合法的 Skill ZIP"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("SKILL.md", skill_md)
    return buf.getvalue()

# ── 列表 / 详情 / 扫描 ──────────────────────────────────────

def test_list_skills(client: TestClient, superuser_token_headers: dict) -> None:
    """列出 Skill：至少包含示例的 code-review"""
    res = client.get(
        f"{settings.API_V1_STR}/agent/skills", headers=superuser_token_headers
    )
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    names = [s["name"] for s in data]
    assert "code-review" in names  # Task 6.6 创建的示例 Skill

def test_get_skill_detail(client: TestClient, superuser_token_headers: dict) -> None:
    """获取详情：包含 instructions"""
    res = client.get(
        f"{settings.API_V1_STR}/agent/skills/code-review",
        headers=superuser_token_headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "code-review"
    assert "审查步骤" in data["instructions"]  # 完整指令

def test_get_skill_not_found(client: TestClient, superuser_token_headers: dict) -> None:
    """不存在的 Skill → 404"""
    res = client.get(
        f"{settings.API_V1_STR}/agent/skills/no-such-skill",
        headers=superuser_token_headers,
    )
    assert res.status_code == 404

def test_scan_skills(client: TestClient, superuser_token_headers: dict) -> None:
    """重新扫描：返回技能数量和名称列表"""
    res = client.post(
        f"{settings.API_V1_STR}/agent/skills/scan", headers=superuser_token_headers
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "code-review" in data["skills"]

# ── 安装 / 删除 ─────────────────────────────────────────────

def test_install_skill_success(client: TestClient, superuser_token_headers: dict) -> None:
    """上传合法 ZIP → 安装成功"""
    res = client.post(
        f"{settings.API_V1_STR}/agent/skills/install",
        headers=superuser_token_headers,
        files={"skill_zip": ("skill.zip", make_skill_zip(), "application/zip")},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["name"] == "api-test-skill"

    # 安装后能查到详情
    res = client.get(
        f"{settings.API_V1_STR}/agent/skills/api-test-skill",
        headers=superuser_token_headers,
    )
    assert res.status_code == 200

def test_install_skill_not_a_zip(client: TestClient, superuser_token_headers: dict) -> None:
    """上传非 ZIP 内容 → 400"""
    res = client.post(
        f"{settings.API_V1_STR}/agent/skills/install",
        headers=superuser_token_headers,
        files={"skill_zip": ("fake.zip", b"this is not a zip", "application/zip")},
    )
    assert res.status_code == 400

def test_install_skill_missing_skill_md(client: TestClient, superuser_token_headers: dict) -> None:
    """ZIP 里没有 SKILL.md → 400"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", "没有 SKILL.md")
    res = client.post(
        f"{settings.API_V1_STR}/agent/skills/install",
        headers=superuser_token_headers,
        files={"skill_zip": ("noskill.zip", buf.getvalue(), "application/zip")},
    )
    assert res.status_code == 400

def test_install_skill_invalid_md(client: TestClient, superuser_token_headers: dict) -> None:
    """SKILL.md 缺少 name 字段 → 400"""
    bad_md = "---\ndescription: 没有名字\n---\n正文"
    res = client.post(
        f"{settings.API_V1_STR}/agent/skills/install",
        headers=superuser_token_headers,
        files={"skill_zip": ("bad.zip", make_skill_zip(bad_md), "application/zip")},
    )
    assert res.status_code == 400

def test_delete_skill(client: TestClient, superuser_token_headers: dict) -> None:
    """安装 → 删除 → 再查 404"""
    # 先安装
    res = client.post(
        f"{settings.API_V1_STR}/agent/skills/install",
        headers=superuser_token_headers,
        files={"skill_zip": ("skill.zip", make_skill_zip(), "application/zip")},
    )
    assert res.status_code == 200

    # 删除
    res = client.delete(
        f"{settings.API_V1_STR}/agent/skills/api-test-skill",
        headers=superuser_token_headers,
    )
    assert res.status_code == 200
    assert res.json()["success"] is True

    # 删除后查询 → 404
    res = client.get(
        f"{settings.API_V1_STR}/agent/skills/api-test-skill",
        headers=superuser_token_headers,
    )
    assert res.status_code == 404

def test_delete_skill_not_found(client: TestClient, superuser_token_headers: dict) -> None:
    """删除不存在的 Skill → 404"""
    res = client.delete(
        f"{settings.API_V1_STR}/agent/skills/no-such-skill",
        headers=superuser_token_headers,
    )
    assert res.status_code == 404