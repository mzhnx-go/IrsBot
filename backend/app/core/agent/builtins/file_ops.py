"""File operation tools — read and write files."""

import os
import tempfile
from pathlib import Path

from app.core.agent.tools import register_tool
from app.core.config import settings


def _allowed_roots() -> list[Path]:
    """Return list of allowed base directories for file operations.

    可通过 .env 的 FILE_WRITE_ROOTS（逗号分隔的绝对路径）自定义白名单；
    未配置时回退到 [项目根目录, /tmp, 系统临时目录]（原默认行为）。
    """
    roots = [Path(p).resolve() for p in settings.FILE_WRITE_ROOTS if p and p.strip()]
    if roots:
        return roots
    return [Path.cwd(), Path("/tmp"), Path(tempfile.gettempdir()).resolve()]


@register_tool("file_read", "Read the contents of a file", category="file")
async def file_read(path: str) -> str:
    """Read and return the contents of a file.

    Args:
        path: Absolute or relative path to the file.
    """
    try:
        full_path = Path(path).resolve()
        # Security: prevent path traversal outside allowed dirs
        if not any(str(full_path).startswith(str(root)) for root in _allowed_roots()):
            return f"Error: Access denied — path outside allowed directories: {path}"
        if not full_path.exists():
            return f"Error: File not found: {path}"
        if not full_path.is_file():
            return f"Error: Not a file: {path}"
        content = full_path.read_text(encoding="utf-8", errors="replace")
        if len(content) > 10000:
            content = content[:10000] + "\n\n... (truncated, too large)"
        return content
    except PermissionError:
        return f"Error: Permission denied reading file: {path}"
    except Exception as e:
        return f"Error reading file: {e}"


@register_tool("file_write", "Write content to a file", category="file")
async def file_write(path: str, content: str) -> str:
    """Write content to a file, creating it if necessary.

    Args:
        path: Absolute or relative path to the file.
        content: The text content to write.
    """
    try:
        full_path = Path(path).resolve()
        if not any(str(full_path).startswith(str(root)) for root in _allowed_roots()):
            return f"Error: Access denied — path outside allowed directories: {path}"
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        return f"Successfully wrote {len(content)} characters to {path}"
    except PermissionError:
        return f"Error: Permission denied writing to: {path}"
    except Exception as e:
        return f"Error writing file: {e}"
