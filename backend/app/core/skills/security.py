"""Skill 安全模块 — 名称校验、路径穿越防护、ZIP 安全检查

Skill 允许用户上传安装，必须防止：
1. 路径穿越攻击（../../）
2. 名称注入攻击（特殊字符）
3. ZIP Slip 攻击（压缩包内路径逃逸）
4. 超大文件攻击
"""

import re
import zipfile
from pathlib import Path

SKILL_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{3,64}$")

MAX_SKILL_MD_SIZE = 1024 * 1024

MAX_SKILL_FILES = 100

def validate_skill_name(name: str) -> bool:
    """验证 Skill 名称是否合法

    规则：字母、数字、下划线、连字符，3-64 位
    防止路径穿越（../）和名称注入（特殊字符）

    Args:
        name: Skill 名称

    Returns:
        True 合法，False 非法
    """
    return bool(SKILL_NAME_PATTERN.match(name))

def check_path_traversal(path: str, base_dir: str) -> bool:
    """检查路径是否在基准目录内（防路径穿越）

    Args:
        path: 待检查的路径
        base_dir: 基准目录

    Returns:
        True 安全，False 包含穿越
    """
    resolved = Path(path).resolve()
    base = Path(base_dir).resolve()
    return str(resolved).startswith(str(base))


def check_zip_safety(zip_path: str, extract_dir: str) -> list[str]:
    """检查 ZIP 包是否安全（防 ZIP Slip 攻击）

    检查项：
    1. 是否为合法 ZIP 文件
    2. 解压后的每个文件路径是否都在目标目录内
    3. 文件数量是否超限
    4. 是否包含 SKILL.md（合法 Skill 的必要文件）

    Args:
        zip_path: ZIP 文件路径
        extract_dir: 解压目标目录

    Returns:
        错误列表（空列表表示安全）
    """
    errors: list[str] = []

    if not zipfile.is_zipfile(zip_path):
        errors.append("Not a valid ZIP file")
        return errors

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()

        if len(names) > MAX_SKILL_FILES:
            errors.append(f"文件数量超过限制（最多 {MAX_SKILL_FILES} 个）")
            return errors

        base = Path(extract_dir).resolve()
        for name in names:
            target = (base / name).resolve()
            if not str(target).startswith(str(base)):
                errors.append(f"检测到路径穿越: {name}")
                return errors
        has_skill_md = any(Path(n).name == "SKILL.md" for n in names)
        if not has_skill_md:
            errors.append("ZIP 中缺少 SKILL.md 文件")

        return errors

def check_skill_md_size(file_path: str) -> bool:
    """检查 SKILL.md 文件大小是否超限

    Args:
        file_path: SKILL.md 文件路径

    Returns:
        True 未超限，False 超限
    """
    size = Path(file_path).stat().st_size
    return size <= MAX_SKILL_MD_SIZE

