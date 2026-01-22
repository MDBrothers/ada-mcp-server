"""MCP tools for Ada Language Server."""

from ada_mcp.tools.diagnostics import handle_diagnostics
from ada_mcp.tools.navigation import (
    clear_open_files_cache,
    handle_find_references,
    handle_goto_definition,
    handle_hover,
    handle_implementation,
    handle_type_definition,
)
from ada_mcp.tools.symbols import (
    handle_document_symbols,
    handle_workspace_symbols,
)

__all__ = [
    "handle_goto_definition",
    "handle_find_references",
    "handle_hover",
    "handle_type_definition",
    "handle_implementation",
    "handle_diagnostics",
    "handle_document_symbols",
    "handle_workspace_symbols",
    "clear_open_files_cache",
]
