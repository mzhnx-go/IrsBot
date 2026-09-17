"""Tool registry and executor — global singleton for LangChain tool management."""

from collections.abc import Callable
from typing import Any
import asyncio

from langchain_core.tools import BaseTool, tool


# ── Registry (原 registry.py) ────────────────────────────────────


class ToolRegistry:
    """Global tool registry (singleton pattern).

    Stores all registered tools by name and supports category-based queries.
    """

    _instance: "ToolRegistry | None" = None

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
        self._categories: dict[str, list[str]] = {}  # category -> [tool_names]

    @classmethod
    def instance(cls) -> "ToolRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, tool_instance: BaseTool, category: str = "builtin") -> None:
        """Register a LangChain BaseTool instance."""
        self._tools[tool_instance.name] = tool_instance
        self._categories.setdefault(category, []).append(tool_instance.name)

    def get_tool(self, name: str) -> BaseTool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def get_all_tools(self) -> list[BaseTool]:
        """Return all registered tools."""
        return list(self._tools.values())

    def get_tools_by_category(self, category: str) -> list[BaseTool]:
        """Return tools in a specific category."""
        names = self._categories.get(category, [])
        return [self._tools[n] for n in names if n in self._tools]

    def get_categories(self) -> list[str]:
        """Return all registered categories."""
        return list(self._categories.keys())

    def clear(self) -> None:
        """Remove all registered tools."""
        self._tools.clear()
        self._categories.clear()

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    def __repr__(self) -> str:
        return f"ToolRegistry(tools={len(self)}, categories={self.get_categories()})"


def register_tool(
    name: str,
    description: str,
    category: str = "builtin",
) -> Callable[[Callable[..., Any]], BaseTool]:
    """Decorator: wrap a function as a LangChain @tool and auto-register it.

    Usage:
        @register_tool("my_tool", "Description of my tool", category="custom")
        async def my_tool(param: str) -> str:
            return param.upper()
    """
    def decorator(func: Callable[..., Any]) -> BaseTool:
        langchain_tool = tool(description=description)(func)
        langchain_tool.name = name
        # Store category in tool's metadata (BaseTool doesn't have a 'category' field)
        existing_meta = langchain_tool.metadata or {}
        langchain_tool.metadata = existing_meta | {"category": category}
        ToolRegistry.instance().register(langchain_tool, category=category)
        return langchain_tool
    return decorator


# ── Executor (原 executor.py) ─────────────────────────────────────


class ToolExecutor:
    """Execute LangChain BaseTools with timeout and error handling."""

    def __init__(self, default_timeout: float = 30.0):
        self.default_timeout = default_timeout

    async def execute(
        self,
        tool: BaseTool,
        input_data: dict | str,
        timeout: float | None = None,
    ) -> str:
        """Execute a tool with timeout protection.

        Args:
            tool: The LangChain BaseTool to execute.
            input_data: Tool input (dict for named args, str for single arg).
            timeout: Override default timeout in seconds.

        Returns:
            Tool output as string.
        """
        try:
            result = await asyncio.wait_for(
                tool.ainvoke(input_data),
                timeout=timeout or self.default_timeout,
            )
            return str(result)
        except asyncio.TimeoutError:
            return f"Error: Tool '{tool.name}' timed out after {(timeout or self.default_timeout):.1f}s"
        except Exception as e:
            return f"Error executing tool '{tool.name}': {e}"

    async def execute_many(
        self,
        tool_calls: list[dict],
        tools_by_name: dict[str, BaseTool],
        timeout: float | None = None,
    ) -> list[dict]:
        """Execute multiple tool calls and return results.

        Args:
            tool_calls: List of dicts with 'name' and 'args'.
            tools_by_name: Mapping of tool name to BaseTool.
            timeout: Timeout per tool call.

        Returns:
            List of result dicts with 'tool_call_id', 'name', 'content'.
        """
        results = []
        for tc in tool_calls:
            tool_name = tc.get("name", "")
            tool_args = tc.get("args", {})
            tool_id = tc.get("tool_call_id", "")

            tool = tools_by_name.get(tool_name)
            if tool is None:
                results.append({
                    "tool_call_id": tool_id,
                    "name": tool_name,
                    "content": f"Error: Tool '{tool_name}' not found",
                })
                continue

            content = await self.execute(tool, tool_args, timeout=timeout)
            results.append({
                "tool_call_id": tool_id,
                "name": tool_name,
                "content": content,
            })
        return results
