"""Tests for MCPClient (unit tests without actual MCP server)."""

import pytest

from app.core.mcp.client import MCPClient


class TestMCPClientInit:
    def test_default_init(self):
        client = MCPClient()
        assert client.transport_type == "sse"
        assert client.url is None
        assert client.command is None
        assert client.args == []
        assert client.max_retries == 2
        assert client.timeout == 30.0
        assert not client.is_connected

    def test_sse_config(self):
        client = MCPClient(transport_type="sse", url="http://localhost:8080")
        assert client.url == "http://localhost:8080"

    def test_stdio_config(self):
        client = MCPClient(
            transport_type="stdio",
            command="python",
            args=["server.py"],
            env={"KEY": "val"},
        )
        assert client.command == "python"
        assert client.args == ["server.py"]
        assert client.env == {"KEY": "val"}


class TestMCPClientValidation:
    @pytest.mark.asyncio
    async def test_connect_sse_requires_url(self):
        client = MCPClient(transport_type="sse")
        with pytest.raises(ValueError, match="requires a URL"):
            await client.connect_sse()

    @pytest.mark.asyncio
    async def test_connect_stdio_requires_command(self):
        client = MCPClient(transport_type="stdio")
        with pytest.raises(ValueError, match="requires a command"):
            await client.connect_stdio()

    @pytest.mark.asyncio
    async def test_connect_streamable_http_requires_url(self):
        client = MCPClient(transport_type="streamable_http")
        with pytest.raises(ValueError, match="requires a URL"):
            await client.connect_streamable_http()

    @pytest.mark.asyncio
    async def test_call_tool_not_connected(self):
        client = MCPClient()
        with pytest.raises(RuntimeError, match="Not connected"):
            await client.call_tool("test")

    @pytest.mark.asyncio
    async def test_list_tools_not_connected(self):
        client = MCPClient()
        with pytest.raises(RuntimeError, match="Not connected"):
            await client.list_tools()

    def test_blocked_command_rejected(self):
        """MCPClient should reject blocked commands via security check."""
        from app.core.mcp.security import MCPSecurity
        sec = MCPSecurity()
        # Security layer rejects blocked commands
        assert sec.validate_command("bash", ["-c", "ls"]) is False
        assert sec.validate_command("sh", ["script"]) is False
        assert sec.validate_command("python", ["-c", "import os"]) is False
