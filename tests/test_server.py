"""Tests for the MCP server module."""

import pytest


@pytest.mark.asyncio
async def test_list_tools():
    """Test that list_tools returns expected tools."""
    from ada_mcp.server import list_tools

    tools = await list_tools()

    assert len(tools) >= 3
    tool_names = [t.name for t in tools]
    assert "ada_goto_definition" in tool_names
    assert "ada_hover" in tool_names
    assert "ada_diagnostics" in tool_names


@pytest.mark.asyncio
async def test_call_tool_unknown():
    """Test that calling unknown tool returns error."""
    import json

    from ada_mcp.server import call_tool

    result = await call_tool("unknown_tool", {})

    assert len(result) == 1
    data = json.loads(result[0].text)
    assert "error" in data


@pytest.mark.asyncio
async def test_call_tool_goto_definition():
    """Test ada_goto_definition tool call."""
    import json

    from ada_mcp.server import call_tool

    result = await call_tool(
        "ada_goto_definition",
        {
            "file": "/some/path/test.adb",
            "line": 10,
            "column": 5,
        },
    )

    assert len(result) == 1
    data = json.loads(result[0].text)
    # Currently returns "not implemented" - update when ALS is integrated
    assert "found" in data or "error" in data
