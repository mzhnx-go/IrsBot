"""Built-in tools for the Agent platform.

安全说明：
- `shell_execute` / `file_read` / `file_write` 具备破坏力，**注册进表但默认
  不对模型暴露**：是否可用由运行时配置（`settings_runtime.shell_enabled /
  file_write_enabled`，回落 .env 的 ENABLE_SHELL / ENABLE_FILE_WRITE，默认
  False）在每次 Agent 构建时过滤（Phase 15.2f，保存即生效、无需重启）。
- `web_search` / `knowledge_base_query` 为只读，始终可用。
- 注册是导入本模块时的副作用；Agent 入口会导入本模块以确保工具生效。
"""

from app.core.agent.builtins.file_ops import file_read, file_write
from app.core.agent.builtins.kb_query import knowledge_base_query
from app.core.agent.builtins.shell import shell_execute
from app.core.agent.builtins.web_search import web_search

__all__ = [
    "web_search",
    "knowledge_base_query",
    "shell_execute",
    "file_read",
    "file_write",
]
