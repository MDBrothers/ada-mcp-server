"""MCP Server setup and tool registration for Ada Language Server."""

import asyncio
import json
import logging
import os
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from ada_mcp.als.client import ALSClient
from ada_mcp.als.process import shutdown_als, start_als
from ada_mcp.tools import (
    handle_diagnostics,
    handle_document_symbols,
    handle_find_references,
    handle_goto_definition,
    handle_hover,
    handle_implementation,
    handle_type_definition,
    handle_workspace_symbols,
)

logger = logging.getLogger(__name__)

# Create the MCP server instance
server = Server("ada-mcp-server")

# Global ALS client (initialized on first use)
_als_client: ALSClient | None = None
_als_lock = asyncio.Lock()


async def get_als_client() -> ALSClient:
    """Get or create the ALS client instance."""
    global _als_client

    async with _als_lock:
        if _als_client is not None and _als_client.is_running:
            return _als_client

        # Determine project root
        project_root_env = os.environ.get("ADA_PROJECT_ROOT")
        if project_root_env:
            project_root = Path(project_root_env)
        else:
            # Default to current directory
            project_root = Path.cwd()

        logger.info(f"Initializing ALS for project: {project_root}")

        try:
            _als_client = await start_als(project_root)
            # Give ALS time to index
            await asyncio.sleep(1.0)
            return _als_client
        except Exception as e:
            logger.exception(f"Failed to start ALS: {e}")
            raise


async def shutdown_als_client() -> None:
    """Shutdown the ALS client if running."""
    global _als_client

    async with _als_lock:
        if _als_client is not None:
            try:
                await shutdown_als(_als_client)
            except Exception as e:
                logger.warning(f"Error shutting down ALS: {e}")
            finally:
                _als_client = None


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Return list of available Ada tools."""
    return [
        # Phase 1: Core Navigation
        Tool(
            name="ada_goto_definition",
            description="Navigate to the definition of an Ada symbol at a given location",
            inputSchema={
                "type": "object",
                "properties": {
                    "file": {
                        "type": "string",
                        "description": "Absolute path to the Ada file",
                    },
                    "line": {
                        "type": "integer",
                        "description": "1-based line number",
                    },
                    "column": {
                        "type": "integer",
                        "description": "1-based column number",
                    },
                },
                "required": ["file", "line", "column"],
            },
        ),
        Tool(
            name="ada_hover",
            description="Get type information and documentation for an Ada symbol",
            inputSchema={
                "type": "object",
                "properties": {
                    "file": {
                        "type": "string",
                        "description": "Absolute path to the Ada file",
                    },
                    "line": {
                        "type": "integer",
                        "description": "1-based line number",
                    },
                    "column": {
                        "type": "integer",
                        "description": "1-based column number",
                    },
                },
                "required": ["file", "line", "column"],
            },
        ),
        Tool(
            name="ada_diagnostics",
            description="Get compiler errors and warnings for Ada files",
            inputSchema={
                "type": "object",
                "properties": {
                    "file": {
                        "type": "string",
                        "description": "Absolute path to Ada file, or omit for all files",
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["error", "warning", "hint", "all"],
                        "description": "Filter by severity level",
                        "default": "all",
                    },
                },
                "required": [],
            },
        ),
        # Phase 2: Enhanced Navigation
        Tool(
            name="ada_find_references",
            description="Find all references to an Ada symbol across the project",
            inputSchema={
                "type": "object",
                "properties": {
                    "file": {
                        "type": "string",
                        "description": "Absolute path to the Ada file",
                    },
                    "line": {
                        "type": "integer",
                        "description": "1-based line number",
                    },
                    "column": {
                        "type": "integer",
                        "description": "1-based column number",
                    },
                    "include_declaration": {
                        "type": "boolean",
                        "description": "Include the declaration in results",
                        "default": True,
                    },
                },
                "required": ["file", "line", "column"],
            },
        ),
        Tool(
            name="ada_document_symbols",
            description="Get all symbols defined in an Ada file (outline)",
            inputSchema={
                "type": "object",
                "properties": {
                    "file": {
                        "type": "string",
                        "description": "Absolute path to the Ada file",
                    },
                },
                "required": ["file"],
            },
        ),
        Tool(
            name="ada_workspace_symbols",
            description="Search for symbols by name across the entire Ada workspace",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Symbol name or pattern to search for",
                    },
                    "kind": {
                        "type": "string",
                        "enum": ["package", "procedure", "function", "type", "variable", "all"],
                        "description": "Filter by symbol kind",
                        "default": "all",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results",
                        "default": 50,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="ada_type_definition",
            description="Navigate to the type definition of a symbol (find where the type is defined, not just the variable)",
            inputSchema={
                "type": "object",
                "properties": {
                    "file": {
                        "type": "string",
                        "description": "Absolute path to the Ada file",
                    },
                    "line": {
                        "type": "integer",
                        "description": "1-based line number",
                    },
                    "column": {
                        "type": "integer",
                        "description": "1-based column number",
                    },
                },
                "required": ["file", "line", "column"],
            },
        ),
        Tool(
            name="ada_implementation",
            description="Navigate from a declaration to its implementation/body (e.g., from spec to body)",
            inputSchema={
                "type": "object",
                "properties": {
                    "file": {
                        "type": "string",
                        "description": "Absolute path to the Ada file",
                    },
                    "line": {
                        "type": "integer",
                        "description": "1-based line number",
                    },
                    "column": {
                        "type": "integer",
                        "description": "1-based column number",
                    },
                },
                "required": ["file", "line", "column"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool invocations."""
    logger.debug(f"Tool called: {name} with args: {arguments}")

    try:
        client = await get_als_client()
    except Exception as e:
        error_result = {"error": f"Failed to connect to ALS: {e}"}
        return [TextContent(type="text", text=json.dumps(error_result, indent=2))]

    try:
        match name:
            case "ada_goto_definition":
                result = await handle_goto_definition(
                    client,
                    file=arguments["file"],
                    line=arguments["line"],
                    column=arguments["column"],
                )

            case "ada_hover":
                result = await handle_hover(
                    client,
                    file=arguments["file"],
                    line=arguments["line"],
                    column=arguments["column"],
                )

            case "ada_diagnostics":
                result = await handle_diagnostics(
                    client,
                    file=arguments.get("file"),
                    severity=arguments.get("severity", "all"),
                )

            case "ada_find_references":
                result = await handle_find_references(
                    client,
                    file=arguments["file"],
                    line=arguments["line"],
                    column=arguments["column"],
                    include_declaration=arguments.get("include_declaration", True),
                )

            case "ada_document_symbols":
                result = await handle_document_symbols(
                    client,
                    file=arguments["file"],
                )

            case "ada_workspace_symbols":
                result = await handle_workspace_symbols(
                    client,
                    query=arguments["query"],
                    kind=arguments.get("kind", "all"),
                    limit=arguments.get("limit", 50),
                )

            case "ada_type_definition":
                result = await handle_type_definition(
                    client,
                    file=arguments["file"],
                    line=arguments["line"],
                    column=arguments["column"],
                )

            case "ada_implementation":
                result = await handle_implementation(
                    client,
                    file=arguments["file"],
                    line=arguments["line"],
                    column=arguments["column"],
                )

            case _:
                result = {"error": f"Unknown tool: {name}"}

    except Exception as e:
        logger.exception(f"Error executing tool {name}: {e}")
        result = {"error": str(e)}

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def run_server() -> None:
    """Run the MCP server using stdio transport."""
    logger.info("Ada MCP Server starting...")

    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )
    finally:
        # Clean up ALS on shutdown
        await shutdown_als_client()
        logger.info("Ada MCP Server stopped")
