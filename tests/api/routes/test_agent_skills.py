"""Skill 系统测试 — 解析器、安全模块、管理器"""

import zipfile
from pathlib import Path

import pytest
from app.core.skills.manager import SkillManager
from app.core.skills.parser import SkillInfo, SkillParser
from app.core.skills.security import (
    check_path_traversal,
    check_skill_md_size,
    check_zip_safety,
    validate_skill_name,
)

# ── SkillParser 测试 ──────────────────────────────────────
VALID_SKILL_MD = """---
name: test-skill
description: 测试技能
trigger: 测试
---

# 测试技能指令

这是测试内容。
"""

@pytest.fixture
def skill_dir(tmp_path):
    """创建一个临时Skill 目录"""
    d = tmp_path / "test-skill"
    d.mkdir()
    (d / "SKILL.md").write_text(VALID_SKILL_MD, encoding="utf-8")
    return d

class TestSkillParser:
    def test_parse_valid_skill(self, skill_dir):
        """正常解析：提取 name/description/trigger/instructions"""
        parser = SkillParser()
        info = parser.parse(str(skill_dir))

        assert info.name == "test-skill"
        assert info.description == "测试技能"
        assert info.trigger == "测试"
        assert "# 测试技能指令" in info.instructions

    def test_parse_missing_skill_md(self, tmp_path):
        """SKILL.md不存在 -> FileNotFoundError"""
        parser = SkillParser()
        with pytest.raises(FileNotFoundError):
            parser.parse(str(tmp_path / "not-such-dir" ) )
    
    def test_parse_missing_name(self, tmp_path):
        """缺少 name 字段 -> ValueError"""
        d = tmp_path / "bad-skill"
        d.mkdir()
        (d / "SKILL.md").write_text(
             "---\ndescription: 没有名字\n---\n正文", encoding="utf-8"
        )
        parser = SkillParser()
        with pytest.raises(ValueError):
            parser.parse(str(d))
    def test_parse_no_front_matter(self, tmp_path):
        """没有 front-matter → 缺 name → ValueError"""
        d = tmp_path / "no-fm"
        d.mkdir()
        (d / "SKILL.md").write_text("# 只有正文", encoding="utf-8")
        parser = SkillParser()
        with pytest.raises(ValueError):
            parser.parse(str(d))
    
# -- 安全检验测试 -----------------------
class TestSecurity:
    def test_validate_skill_name(self):
        """合法名称"""
        assert validate_skill_name("code-review") is True
        assert validate_skill_name("my_skill_2") is True

    def test_validate_skill_name_invalid(self):
        """非法名称：路径穿越、特殊字符、太短"""
        assert validate_skill_name("../evil") is False
        assert validate_skill_name("rm -rf") is False
        assert validate_skill_name("ab") is False  # 少于3位
        assert validate_skill_name("") is False

    def test_check_path_traversal_safe(self, tmp_path):
        """安全路径：在基准目录内"""
        safe = tmp_path / "sub" / "file.md"
        assert check_path_traversal(str(safe), str(tmp_path)) is True

    def test_check_path_traversal_attack(self, tmp_path):
        """路径穿越攻击：../ 逃出基准目录"""
        evil = tmp_path / ".." / "etc" / "passwd"
        assert check_path_traversal(str(evil), str(tmp_path)) is False

    def test_check_zip_safety_valid(self, tmp_path):
        """合法 ZIP：无穿越、含 SKILL.md、文件数正常"""
        # 先造一个合法的 Skill ZIP
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(VALID_SKILL_MD, encoding="utf-8")

        zip_path = tmp_path / "good.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.write(skill_dir / "SKILL.md", "SKILL.md")

        errors = check_zip_safety(str(zip_path), str(tmp_path / "extract"))
        assert errors == []

    def test_check_zip_safety_not_a_zip(self, tmp_path):
        """不是 ZIP 文件"""
        fake = tmp_path / "fake.zip"
        fake.write_text("这不是zip", encoding="utf-8")
        errors = check_zip_safety(str(fake), str(tmp_path))
        assert len(errors) == 1
        assert "ZIP" in errors[0]

    def test_check_zip_safety_missing_skill_md(self, tmp_path):
        """ZIP 中没有 SKILL.md"""
        zip_path = tmp_path / "noskill.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("readme.txt", "没有SKILL.md")

        errors = check_zip_safety(str(zip_path), str(tmp_path / "extract"))
        assert any("SKILL.md" in e for e in errors)

    def test_check_skill_md_size(self, tmp_path):
        """大小检查：1KB 通过（远小于1MB）"""
        f = tmp_path / "SKILL.md"
        f.write_text("# " + "x" * 1024, encoding="utf-8")
        assert check_skill_md_size(str(f)) is True

# ── SkillManager 测试 ─────────────────────────────────────
class TestSkillManager:
    def test_scan_and_get(self, tmp_path):
        """扫描目录后能获取 Skill"""
        d = tmp_path / "test-skill"
        d.mkdir()
        (d / "SKILL.md").write_text(VALID_SKILL_MD, encoding="utf-8")
        mgr = SkillManager(str(tmp_path))
        skills = mgr.scan()
        assert "test-skill" in skills
        assert mgr.get_skill("test-skill") is not None
        assert mgr.get_skill("no-exist") is None

    def test_build_skills_prompt(self, tmp_path):
        """清单提示词包含 name 和 description"""
        d = tmp_path / "test-skill"
        d.mkdir()
        (d / "SKILL.md").write_text(VALID_SKILL_MD, encoding="utf-8")

        mgr = SkillManager(skills_dir=str(tmp_path))
        prompt = mgr.build_skills_prompt()

        assert "test-skill" in prompt
        assert "测试技能" in prompt
        assert "# 测试技能指令" not in prompt  # 清单不包含完整指令（渐进式披露）

    def test_scan_empty_dir(self, tmp_path):
        """空目录：扫描结果为空，提示词为空字符串"""
        mgr = SkillManager(skills_dir=str(tmp_path))
        skills = mgr.scan()
        assert skills == {}
        assert mgr.build_skills_prompt() == ""
        