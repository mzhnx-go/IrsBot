"""MCP → LangChain Tool Bridge — wraps MCP tools as LangChain BaseTool."""

from typing import Any

from langchain_core.tools import BaseTool, tool


class MCPToolBridge:
    """Convert MCP tool definitions to LangChain BaseTool instances."""

    @staticmethod
    def to_langchain_tool(
        mcp_tool_info: dict,
        call_tool_fn,
    ) -> BaseTool:
        """Wrap an MCP tool as a LangChain BaseTool.

        Args:
            mcp_tool_info: MCP tool definition with name, description, inputSchema.
            call_tool_fn: Async function that calls the MCP tool.

        Returns:
            A LangChain BaseTool instance.
        """
        tool_name = mcp_tool_info["name"]
        tool_desc = mcp_tool_info.get("description", "")
        input_schema = mcp_tool_info.get("inputSchema", {})

        # Build parameter schema from MCP inputSchema
        properties = input_schema.get("properties", {})
        required = input_schema.get("required", [])

        # Create a dynamic async function
        async def _execute(**kwargs) -> Any:
            result = await call_tool_fn(tool_name, kwargs)
            # MCP returns content blocks; extract text
            if hasattr(result, "content"):
                contents = result.content
                if isinstance(contents, list):
                    return "\n\n".join(
                        c.text if hasattr(c, "text") else str(c)
                        for c in contents
                    )
                return str(contents)
            return str(result)

        # Set function signature based on inputSchema
        _execute.__name__ = tool_name
        _execute.__doc__ = tool_desc

        # Use langchain's @tool decorator to create the BaseTool
        langchain_tool = tool(description=tool_desc)(_execute)
        langchain_tool.name = tool_name
        return langchain_tool

    @staticmethod
    def batch_to_langchain_tools(
        mcp_tools: list[dict],
        call_tool_fn,
    ) -> list[BaseTool]:
        """Convert a list of MCP tools to LangChain BaseTool instances."""
        return [
            MCPToolBridge.to_langchain_tool(tool_info, call_tool_fn)
            for tool_info in mcp_tools
        ]
