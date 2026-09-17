"""Built-in tools for the Agent platform.

安全说明：
- `shell_execute` / `file_read` / `file_write` 具备破坏力，**默认不注册**
  （见 config.py 的 ENABLE_SHELL / ENABLE_FILE_WRITE，默认 False）。
- `web_search` / `knowledge_base_query` 为只读，始终注册。
- 注册是导入本模块时的副作用；Agent 入口会导入本模块以确保工具生效。
"""

from app.core.config import settings

from app.core.agent.builtins.kb_query import knowledge_base_query
from app.core.agent.builtins.web_search import web_search

__all__ = ["web_search", "knowledge_base_query"]

if settings.ENABLE_SHELL:
    from app.core.agent.builtins.shell import shell_execute

    __all__.append("shell_execute")

if settings.ENABLE_FILE_WRITE:
    from app.core.agent.builtins.file_ops import file_read, file_write

    __all__.extend(["file_read", "file_write"])
