"""Skill 管理器 — 扫描、获取和构建 Skill 提示词

负责扫描 skills 目录，解析所有 SKILL.md 文件，
并提供渐进式披露的提示词构建功能。
"""

from pathlib import Path

from app.core.skills.parser import SkillInfo, SkillParser


class SkillManager:
    """Skill 管理器（单例）

    职责：
    1. 扫描 skills 目录，解析所有 SKILL.md
    2. 获取某个 Skill 的完整信息
    3. 构建 Skill 清单提示词（渐进式披露）
    4. 获取某个 Skill 的完整指令
    """

    _instance = None

    def __init__(self, skills_dir: str = "skills"):
        """初始化 Skill 管理器

        Args:
            skills_dir: skills 根目录路径
        """
        self.skills_dir = Path(skills_dir)
        self.parser = SkillParser()
        self._skills: dict[str, SkillInfo] = {}
        self._loaded = False

    @classmethod
    def instance(cls) -> "SkillManager":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def scan(self) -> dict[str, SkillInfo]:
        """扫描 skills 目录，解析所有 SKILL.md 文件

        Returns:
            name -> SkillInfo 的字典
        """
        self._skills.clear()

        if not self.skills_dir.exists():
            self._loaded = True
            return self._skills

        for skill_dir in self.skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue

            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue

            try:
                info = self.parser.parse(str(skill_dir))
                self._skills[info.name] = info
            except (ValueError, FileNotFoundError) as e:
                print(f"⚠️ 跳过 Skill '{skill_dir.name}': {e}")

        self._loaded = True
        return self._skills

    def get_skill(self, name: str) -> SkillInfo | None:
        """获取某个 Skill 的完整信息"""
        if not self._loaded:
            self.scan()
        return self._skills.get(name)

    def list_skills(self) -> list[SkillInfo]:
        """列出所有 Skill"""
        if not self._loaded:
            self.scan()
        return list(self._skills.values())

    def build_skills_prompt(self) -> str:
        """构建 Skill 清单提示词（渐进式披露第 1 步）

        只包含 name 和 description，不包含完整指令。
        """
        if not self._loaded:
            self.scan()

        if not self._skills:
            return ""

        lines = ["## 可用技能\n"]
        for skill in self._skills.values():
            lines.append(f"- **{skill.name}**: {skill.description}")

        lines.append("\n（如需使用某个技能，请告知用户你正在加载该技能）")
        return "\n".join(lines)

    def get_skill_instructions(self, name: str) -> str | None:
        """获取某个 Skill 的完整指令（渐进式披露第 2 步）"""
        info = self.get_skill(name)
        if info is None:
            return None
        return info.instructions