"""Tests for ToolExecutor."""

import asyncio
import pytest
from langchain_core.tools import tool

from app.core.agent.tools import ToolExecutor


def _aiter(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestToolExecutor:
    def test_execute_success(self):
        @tool
        def add(a: int, b: int) -> int:
            """Add two numbers."""
            return a + b

        executor = ToolExecutor(default_timeout=30.0)
        result = _aiter(executor.execute(add, {"a": 3, "b": 4}))
        assert "7" in result

    def test_execute_timeout(self):
        @tool
        def slow_op(x: str) -> str:
            """A slow operation."""
            import time
            time.sleep(10)
            return "done"

        executor = ToolExecutor(default_timeout=0.1)
        result = _aiter(executor.execute(slow_op, {"x": "test"}, timeout=0.1))
        assert "timed out" in result.lower()

    def test_execute_error(self):
        @tool
        def failing_op(x: str) -> str:
            """Always fails."""
            raise ValueError("intentional error")

        executor = ToolExecutor()
        result = _aiter(executor.execute(failing_op, {"x": "test"}))
        assert "Error" in result
        assert "intentional error" in result

    def test_execute_many_success(self):
        @tool
        def upper(x: str) -> str:
            """Uppercase a string."""
            return x.upper()

        @tool
        def lower(x: str) -> str:
            """Lowercase a string."""
            return x.lower()

        executor = ToolExecutor()
        tools = {"upper": upper, "lower": lower}
        tool_calls = [
            {"name": "upper", "args": {"x": "hello"}, "tool_call_id": "1"},
            {"name": "lower", "args": {"x": "WORLD"}, "tool_call_id": "2"},
        ]
        results = _aiter(executor.execute_many(tool_calls, tools))
        assert len(results) == 2
        assert results[0]["content"].strip() == "HELLO"
        assert results[1]["content"].strip() == "world"

    def test_execute_many_missing_tool(self):
        executor = ToolExecutor()
        tool_calls = [{"name": "nonexistent", "args": {}, "tool_call_id": "1"}]
        results = _aiter(executor.execute_many(tool_calls, {}))
        assert len(results) == 1
        assert "not found" in results[0]["content"].lower()
