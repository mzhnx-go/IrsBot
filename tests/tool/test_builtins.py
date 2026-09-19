"""Tests for built-in tools (web_search, file_ops, shell, kb_query)."""

import asyncio
import tempfile
import os

import pytest


def _aiter(coro):
    """Helper to run a coroutine synchronously in tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


class TestWebSearch:
    def test_web_search_placeholder(self):
        from app.core.agent.builtins.web_search import web_search
        result = _aiter(web_search.ainvoke({"query": "test query", "engine": "tavily", "top_k": 3}))
        # Without API key, returns placeholder string
        assert isinstance(result, str)
        assert len(result) > 0

    def test_web_search_brave_fallback(self):
        from app.core.agent.builtins.web_search import web_search
        result = _aiter(web_search.ainvoke({"query": "test", "engine": "brave", "top_k": 5}))
        assert "test" in result


class TestFileOps:
    def test_file_write_and_read(self):
        from app.core.agent.builtins.file_ops import file_write, file_read

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            tmp_path = f.name

        try:
            result = _aiter(file_write.ainvoke({"path": tmp_path, "content": "hello world"}))
            assert "Successfully wrote" in result
            content = _aiter(file_read.ainvoke({"path": tmp_path}))
            assert content == "hello world"
        finally:
            os.unlink(tmp_path)

    def test_file_read_not_found(self):
        from app.core.agent.builtins.file_ops import file_read
        result = _aiter(file_read.ainvoke({"path": "/nonexistent/path/file.txt"}))
        assert "Error" in result

    def test_file_write_creates_parent_dirs(self):
        from app.core.agent.builtins.file_ops import file_write

        with tempfile.TemporaryDirectory() as tmpdir:
            nested = os.path.join(tmpdir, "a", "b", "c.txt")
            result = _aiter(file_write.ainvoke({"path": nested, "content": "nested content"}))
            assert "Successfully wrote" in result
            assert os.path.exists(nested)


class TestShellExecute:
    def test_echo_command(self):
        from app.core.agent.builtins.shell import shell_execute
        result = _aiter(shell_execute.ainvoke({"command": "echo hello"}))
        assert "hello" in result

    def test_blocked_rm_command(self):
        from app.core.agent.builtins.shell import shell_execute
        result = _aiter(shell_execute.ainvoke({"command": "rm -rf /tmp/test"}))
        assert "blocked" in result.lower() or "Error" in result

    def test_blocked_dangerous_chars(self):
        from app.core.agent.builtins.shell import shell_execute
        result = _aiter(shell_execute.ainvoke({"command": "echo hello && rm -rf /"}))
        assert "metacharacter" in result.lower() or "Error" in result

    def test_allowed_ls(self):
        from app.core.agent.builtins.shell import shell_execute
        result = _aiter(shell_execute.ainvoke({"command": "ls"}))
        assert result  # Should produce output (no error)


class TestKBQuery:
    def test_kb_query_fail_closed_without_user(self):
        """未挂用户身份时必须拒绝查询（fail closed），绝不回落成"查全部" """
        from app.core.agent.builtins.kb_query import knowledge_base_query, set_kb_user
        set_kb_user(None)
        result = _aiter(knowledge_base_query.ainvoke({"query": "test query", "top_k": 3}))
        assert "无法确定当前用户身份" in result

    def test_kb_query_rejects_invalid_kb_id(self):
        """身份有效时，LLM 传来的非法 kb_id 应返回友好错误而非异常"""
        import uuid

        from app.core.agent.builtins.kb_query import knowledge_base_query, set_kb_user
        set_kb_user(uuid.uuid4())
        try:
            result = _aiter(
                knowledge_base_query.ainvoke({"query": "query", "kb_id": "kb-123", "top_k": 5})
            )
            assert "不是合法的 UUID" in result
        finally:
            set_kb_user(None)  # 清理，防止身份残留影响其他测试
