"""Tests for MCPToolBridge."""

import pytest

from app.core.mcp.bridge import MCPToolBridge


class TestMCPToolBridge:
    async def mock_call_tool(self, name, args):
        return type("Result", (), {"content": [type("Block", (), {"text": f"result for {name}"})()]})()

    def test_to_langchain_tool_basic(self):
        mcp_tool = {
            "name": "test_tool",
            "description": "A test MCP tool",
            "inputSchema": {"type": "object", "properties": {"x": {"type": "string"}}},
        }
        tool = MCPToolBridge.to_langchain_tool(mcp_tool, self.mock_call_tool)
        assert tool.name == "test_tool"
        assert "test MCP tool" in tool.description

    def test_batch_conversion(self):
        mcp_tools = [
            {"name": "tool_a", "description": "A", "inputSchema": {}},
            {"name": "tool_b", "description": "B", "inputSchema": {}},
        ]
        tools = MCPToolBridge.batch_to_langchain_tools(mcp_tools, self.mock_call_tool)
        assert len(tools) == 2
        assert tools[0].name == "tool_a"
        assert tools[1].name == "tool_b"

    def test_empty_description(self):
        mcp_tool = {
            "name": "minimal",
            "description": "",
            "inputSchema": {},
        }
        tool = MCPToolBridge.to_langchain_tool(mcp_tool, self.mock_call_tool)
        assert tool.name == "minimal"
