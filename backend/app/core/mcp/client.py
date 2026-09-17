"""MCP client — connects to external MCP Servers via SSE, stdio, or Streamable HTTP."""

import asyncio
from typing import Any

from app.core.mcp.security import MCPSecurity


class MCPClient:
    """MCP client supporting multiple transport types with auto-reconnect."""

    def __init__(
        self,
        transport_type: str = "sse",
        url: str | None = None,
        command: str | None = None,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        max_retries: int = 2,
        timeout: float = 30.0,
    ):
        self.transport_type = transport_type
        self.url = url
        self.command = command
        self.args = args or []
        self.env = env or {}
        self.max_retries = max_retries
        self.timeout = timeout
        self._session = None
        self._connected = False
        self._security = MCPSecurity()

    async def connect_sse(self, url: str | None = None) -> bool:
        """Connect via SSE transport."""
        target_url = url or self.url
        if not target_url:
            raise ValueError("SSE transport requires a URL")

        retries = 0
        while retries <= self.max_retries:
            try:
                from mcp import ClientSession
                from mcp.client.sse import sse_client

                self._sse_context = sse_client(target_url)
                self._sse_transport = await self._sse_context.__aenter__()
                self._session = ClientSession(*self._sse_transport)
                await self._session.initialize()
                self._connected = True
                return True
            except Exception:
                retries += 1
                if retries > self.max_retries:
                    raise RuntimeError("Connection failed after retries")
                await asyncio.sleep(2 ** retries)  # exponential backoff

    async def connect_stdio(
        self,
        command: str | None = None,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
    ) -> bool:
        """Connect via stdio transport."""
        cmd = command or self.command
        cmd_args = args or self.args
        cmd_env = env or self.env

        if not cmd:
            raise ValueError("stdio transport requires a command")

        # Security check
        if not self._security.validate_command(cmd, cmd_args):
            raise ValueError(f"Command '{cmd}' is not allowed by security policy")

        retries = 0
        while retries <= self.max_retries:
            try:
                from mcp import ClientSession
                from mcp.client.stdio import stdio_client

                env_dict = cmd_env.copy() if cmd_env else None
                self._stdio_context = stdio_client(cmd, cmd_args, env=env_dict)
                self._stdio_transport = await self._stdio_context.__aenter__()
                self._session = ClientSession(*self._stdio_transport)
                await self._session.initialize()
                self._connected = True
                return True
            except Exception:
                retries += 1
                if retries > self.max_retries:
                    raise RuntimeError("Connection failed after retries")
                await asyncio.sleep(2 ** retries)

    async def connect_streamable_http(self, url: str | None = None) -> bool:
        """Connect via Streamable HTTP transport."""
        target_url = url or self.url
        if not target_url:
            raise ValueError("Streamable HTTP transport requires a URL")

        retries = 0
        while retries <= self.max_retries:
            try:
                from mcp import ClientSession
                from mcp.client.streamable_http import streamable_http_client

                self._http_context = streamable_http_client(target_url)
                self._http_transport = await self._http_context.__aenter__()
                self._session = ClientSession(*self._http_transport)
                await self._session.initialize()
                self._connected = True
                return True
            except Exception:
                retries += 1
                if retries > self.max_retries:
                    raise RuntimeError("Connection failed after retries")
                await asyncio.sleep(2 ** retries)

    async def list_tools(self) -> list[dict]:
        """List available tools from the connected MCP server."""
        if not self._connected or self._session is None:
            raise RuntimeError("Not connected to MCP server")
        result = await self._session.list_tools()
        return [
            {
                "name": t.name,
                "description": t.description or "",
                "inputSchema": t.inputSchema,
            }
            for t in result.tools
        ]

    async def call_tool(self, name: str, arguments: dict | None = None) -> Any:
        """Call a tool on the connected MCP server."""
        if not self._connected or self._session is None:
            raise RuntimeError("Not connected to MCP server")

        if arguments and not self._security.validate_arguments(arguments):
            raise ValueError(f"Arguments contain potentially dangerous characters in tool '{name}'")

        result = await self._session.call_tool(name, arguments or {})
        return result

    async def call_tool_with_reconnect(
        self, name: str, arguments: dict | None = None
    ) -> Any:
        """Call a tool with automatic reconnect on network failure only."""
        try:
            return await self.call_tool(name, arguments)
        except (ConnectionError, TimeoutError, OSError):
            # Only reconnect on network errors, not tool errors
            await self.close()
            if self.transport_type == "sse":
                await self.connect_sse()
            elif self.transport_type == "stdio":
                await self.connect_stdio()
            else:
                await self.connect_streamable_http()
            return await self.call_tool(name, arguments)

    async def close(self) -> None:
        """Close the MCP connection."""
        if self._session is not None:
            try:
                await self._session.close()
            except Exception:
                pass
            self._session = None
        self._connected = False

        # Close transport contexts
        for attr in ("_sse_context", "_stdio_context", "_http_context"):
            ctx = getattr(self, attr, None)
            if ctx is not None:
                try:
                    await ctx.__aexit__(None, None, None)
                except Exception:
                    pass

    @property
    def is_connected(self) -> bool:
        return self._connected
