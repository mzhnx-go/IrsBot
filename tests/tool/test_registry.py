"""Tests for ToolRegistry and @register_tool decorator."""

import pytest

from app.core.agent.tools import ToolRegistry, register_tool


@pytest.fixture(autouse=True)
def _reset_registry():
    """Clear registry before each test."""
    ToolRegistry._instance = None
    yield
    ToolRegistry._instance = None


class TestToolRegistry:
    def test_singleton(self):
        r1 = ToolRegistry.instance()
        r2 = ToolRegistry.instance()
        assert r1 is r2

    def test_register_and_get(self):
        from langchain_core.tools import tool

        @tool
        def dummy_tool(x: str) -> str:
            """A dummy tool."""
            return x.upper()

        registry = ToolRegistry.instance()
        registry.register(dummy_tool, category="test")
        assert registry.get_tool("dummy_tool") is dummy_tool
        assert len(registry) == 1

    def test_get_all_tools(self):
        from langchain_core.tools import tool

        @tool
        def tool_a(x: str) -> str:
            """Tool A."""
            return x

        @tool
        def tool_b(x: str) -> str:
            """Tool B."""
            return x

        registry = ToolRegistry.instance()
        registry.register(tool_a, category="cat1")
        registry.register(tool_b, category="cat2")
        all_tools = registry.get_all_tools()
        assert len(all_tools) == 2
        names = {t.name for t in all_tools}
        assert "tool_a" in names
        assert "tool_b" in names

    def test_get_by_category(self):
        from langchain_core.tools import tool

        @tool
        def web_tool(x: str) -> str:
            """Web tool."""
            return x

        @tool
        def file_tool(x: str) -> str:
            """File tool."""
            return x

        registry = ToolRegistry.instance()
        registry.register(web_tool, category="web")
        registry.register(file_tool, category="file")
        web_tools = registry.get_tools_by_category("web")
        assert len(web_tools) == 1
        assert web_tools[0].name == "web_tool"

    def test_categories(self):
        from langchain_core.tools import tool

        @tool
        def t1(x: str) -> str:
            """T1."""
            return x

        registry = ToolRegistry.instance()
        registry.register(t1, category="alpha")
        assert "alpha" in registry.get_categories()

    def test_contains(self):
        from langchain_core.tools import tool

        @tool
        def t1(x: str) -> str:
            """T1."""
            return x

        registry = ToolRegistry.instance()
        registry.register(t1, category="test")
        assert "t1" in registry
        assert "nonexistent" not in registry

    def test_clear(self):
        from langchain_core.tools import tool

        @tool
        def t1(x: str) -> str:
            """T1."""
            return x

        registry = ToolRegistry.instance()
        registry.register(t1, category="test")
        registry.clear()
        assert len(registry) == 0
        assert registry.get_tool("t1") is None

    def test_repr(self):
        registry = ToolRegistry.instance()
        assert "ToolRegistry" in repr(registry)


class TestRegisterToolDecorator:
    def test_decorator_registers_tool(self):
        @register_tool("dec_tool", "A decorated tool", category="dec")
        async def dec_tool(x: str) -> str:
            return x.upper()

        registry = ToolRegistry.instance()
        tool_obj = registry.get_tool("dec_tool")
        assert tool_obj is not None
        assert tool_obj.name == "dec_tool"

    def test_decorator_returns_langchain_tool(self):
        @register_tool("dec2", "Another tool")
        async def dec2(x: int) -> int:
            return x + 1

        registry = ToolRegistry.instance()
        tool_obj = registry.get_tool("dec2")
        assert tool_obj is not None
        assert hasattr(tool_obj, "invoke")

    def test_decorator_category_stored_in_metadata(self):
        @register_tool("dec3", "Cat test", category="custom")
        async def dec3(x: str) -> str:
            return x

        registry = ToolRegistry.instance()
        tool_obj = registry.get_tool("dec3")
        assert tool_obj is not None
        meta = getattr(tool_obj, "metadata", {})
        assert meta.get("category") == "custom"
