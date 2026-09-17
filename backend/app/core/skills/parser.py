"""Skill 解析器 -- 解析SKILL.md文件， 提取结构化信息
SKILL.md 文件格式:
    ---
    name: skill-name
    description: 技能描述
    trigger: 触发关键词
    ---
    # Markdown 正文(指令全文)
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class SkillInfo:
    """解析后的 Skill 信息

    Attributes:
        name: Skill 名称（唯一标识）
        description: 简短描述（用于渐进式披露的清单）
        path: SKILL.md 文件的绝对路径
        trigger: 触发关键词（可选），用于自动匹配用户意图
        instructions: SKILL.md 的正文内容（指令全文）
        metadata: front-matter 中的其他字段
    """

    name: str
    description: str
    path: str
    trigger: str | None = None
    instructions: str = ""
    metadata: dict = field(default_factory=dict)

class SkillParser:
    """Skill 文件解析器
    负责读取和解析SKILL.md文件, 提取元数据和指令内容。
    """
    NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
    
    def parse(self, skill_dir: str) -> SkillInfo:
        """解析 Skill目录中的SKILL.md文件
        Args:
            skill_dir: Skill 目录路径
        Returns:
            SkillInfo对象
        Raises:
            FileNotFoundError: SKILL.md 文件不存在
            ValueError: 文件格式错误或缺少必填字段
        """ 
        skill_path = Path(skill_dir) / "SKILL.md"
        if not skill_path.exists():
            raise FileNotFoundError(f"SKILL.md 不存在: {skill_path}")
        content = skill_path.read_text(encoding="utf-8")   
        front_matter, body = self._split_front_matter(content)
        metadata = yaml.safe_load(front_matter) or {}
        name = metadata.pop("name", None)
        if not name:
            raise ValueError(f"SKILL.md 缺少必填字段 'name': {skill_path}")
        description = metadata.pop("description", None)
        trigger = metadata.pop("trigger", None)
        if not self.validate_name(name):
            raise ValueError(f"Skill 名称无效 '{name}'：只允许字母、数字、下划线、连字符")
        return SkillInfo(
            name = name,
            description = description,
            path = str(skill_path.resolve()),
            trigger = trigger,
            instructions = body.strip(),
            metadata = metadata,
        )

    def _split_front_matter(self, content: str) -> tuple[str, str]:
        """分离 YAML front-matter 和 Markdown 正文
        Args:
            content: SKILL.md 文件内容
        Returns:
            (front_matter, body) 元组
        """
        pattern = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)", re.DOTALL)
        match = pattern.match(content)

        if match:
            front_matter = match.group(1)
            body = match.group(2)
            return front_matter, body

        # 没有 front-matter，全部作为 body
        return "", content

    def validate_name(self, name: str) -> bool:
        """验证 Skill 名称是否合法

        规则：只允许字母、数字、下划线、连字符
        防止名称注入攻击（如 ../ 或特殊字符）
        """
        return bool(self.NAME_PATTERN.match(name))

    def validate_path(self, path: str, base_dir: str) -> bool:
        """验证路径是否在 base_dir 内（防止路径穿越攻击）"""
        resolved = Path(path).resolve()
        base = Path(base_dir).resolve()
        return str(resolved).startswith(str(base))