"""MCP Server setup and tool registration for Ada Language Server."""

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from ada_mcp.als.client import ALSClient
from ada_mcp.als.process import (
    ALSHealthMonitor,
    find_project_root,
    shutdown_als,
    start_als_with_monitoring,
)
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
from ada_mcp.tools.build import (
    handle_alire_info,
    handle_build,
)
from ada_mcp.tools.project import (
    handle_call_hierarchy,
    handle_dependency_graph,
    handle_project_info,
)
from ada_mcp.tools.refactoring import (
    handle_code_actions,
    handle_completions,
    handle_format_file,
    handle_get_spec,
    handle_rename_symbol,
    handle_signature_help,
)

logger = logging.getLogger(__name__)

# Create the MCP server instance
server = Server("ada-mcp-server")

# =============================================================================
# Multi-Project ALS Pool
# =============================================================================
# Instead of a single global ALS, we maintain a pool of ALS instances,
# one per project. This allows multiple users/projects to work simultaneously
# without restarting ALS constantly.


@dataclass
class ALSInstance:
    """Represents an ALS instance for a specific project."""

    client: ALSClient
    monitor: ALSHealthMonitor | None
    project_root: Path
    last_used: float  # timestamp
    lock: asyncio.Lock  # per-instance lock for operations


class ALSPool:
    """
    Pool of ALS instances, one per project.

    Supports multiple concurrent projects with LRU eviction to limit
    memory usage. Each project gets its own ALS with proper Alire
    environment.
    """

    def __init__(self, max_instances: int = 3, idle_timeout: float = 300.0):
        """
        Initialize the ALS pool.

        Args:
            max_instances: Maximum number of concurrent ALS instances
            idle_timeout: Seconds after which idle instances can be evicted
        """
        self.max_instances = max_instances
        self.idle_timeout = idle_timeout
        self._instances: dict[Path, ALSInstance] = {}
        self._pool_lock = asyncio.Lock()
        self._cleanup_task: asyncio.Task | None = None

    def _create_restart_callback(self, project_root: Path):
        """Create a restart callback for a specific project."""

        def callback(new_client: ALSClient) -> None:
            if project_root in self._instances:
                self._instances[project_root].client = new_client
                logger.info(f"ALS client updated after restart for {project_root}")

        return callback

    async def get_client(self, file_path: str | None = None) -> ALSClient:
        """
        Get an ALS client for the project containing the given file.

        Args:
            file_path: File path to determine project from

        Returns:
            ALSClient for the appropriate project
        """
        import time

        # Determine project root
        project_root_env = os.environ.get("ADA_PROJECT_ROOT")
        if project_root_env:
            project_root = Path(project_root_env)
        elif file_path:
            project_root = find_project_root(Path(file_path))
        else:
            project_root = Path.cwd()

        async with self._pool_lock:
            # Check if we already have an instance for this project
            if project_root in self._instances:
                instance = self._instances[project_root]
                if instance.client.is_running:
                    instance.last_used = time.time()
                    logger.debug(f"Reusing ALS for project: {project_root}")
                    return instance.client
                else:
                    # Instance died, remove it
                    logger.warning(f"ALS instance for {project_root} died, removing")
                    del self._instances[project_root]

            # Need to create a new instance
            # First, check if we need to evict old instances
            await self._evict_if_needed()

            logger.info(f"Creating new ALS instance for project: {project_root}")

            try:
                client, monitor = await start_als_with_monitoring(
                    project_root, on_restart=self._create_restart_callback(project_root)
                )

                instance = ALSInstance(
                    client=client,
                    monitor=monitor,
                    project_root=project_root,
                    last_used=time.time(),
                    lock=asyncio.Lock(),
                )
                self._instances[project_root] = instance

                # Give ALS time to index
                await asyncio.sleep(1.0)

                # Start cleanup task if not running
                if self._cleanup_task is None or self._cleanup_task.done():
                    self._cleanup_task = asyncio.create_task(self._cleanup_loop())

                return client

            except Exception as e:
                logger.exception(f"Failed to start ALS for {project_root}: {e}")
                raise

    async def _evict_if_needed(self) -> None:
        """Evict oldest instance if at capacity."""

        if len(self._instances) < self.max_instances:
            return

        # Find the oldest (least recently used) instance
        oldest_root = None
        oldest_time = float("inf")

        for root, instance in self._instances.items():
            if instance.last_used < oldest_time:
                oldest_time = instance.last_used
                oldest_root = root

        if oldest_root:
            logger.info(f"Evicting ALS instance for {oldest_root} (LRU)")
            await self._shutdown_instance(oldest_root)

    async def _shutdown_instance(self, project_root: Path) -> None:
        """Shutdown a specific ALS instance."""
        if project_root not in self._instances:
            return

        instance = self._instances.pop(project_root)
        try:
            await shutdown_als(instance.client, instance.monitor)
        except Exception as e:
            logger.warning(f"Error shutting down ALS for {project_root}: {e}")

    async def _cleanup_loop(self) -> None:
        """Periodically clean up idle instances."""
        import time

        while True:
            try:
                await asyncio.sleep(60.0)  # Check every minute

                async with self._pool_lock:
                    now = time.time()
                    to_remove = []

                    for root, instance in self._instances.items():
                        idle_time = now - instance.last_used
                        if idle_time > self.idle_timeout:
                            logger.info(f"ALS for {root} idle for {idle_time:.0f}s, shutting down")
                            to_remove.append(root)

                    for root in to_remove:
                        await self._shutdown_instance(root)

                    # Stop cleanup loop if no instances left
                    if not self._instances:
                        logger.debug("No ALS instances, stopping cleanup loop")
                        return

            except asyncio.CancelledError:
                logger.debug("Cleanup loop cancelled")
                return
            except Exception as e:
                logger.exception(f"Error in cleanup loop: {e}")

    async def shutdown_all(self) -> None:
        """Shutdown all ALS instances."""
        async with self._pool_lock:
            if self._cleanup_task:
                self._cleanup_task.cancel()

            for root in list(self._instances.keys()):
                await self._shutdown_instance(root)

    def get_stats(self) -> dict:
        """Get pool statistics."""
        import time

        now = time.time()
        return {
            "active_instances": len(self._instances),
            "max_instances": self.max_instances,
            "projects": [
                {
                    "project": str(root),
                    "idle_seconds": now - inst.last_used,
                    "is_running": inst.client.is_running,
                }
                for root, inst in self._instances.items()
            ],
        }


# Global ALS pool (replaces single client)
_als_pool = ALSPool(max_instances=3, idle_timeout=300.0)


async def get_als_client(file_path: str | None = None) -> ALSClient:
    """
    Get an ALS client for the project containing the given file.

    This is a convenience wrapper around the ALS pool.
    """
    return await _als_pool.get_client(file_path)


async def shutdown_als_client() -> None:
    """Shutdown all ALS clients."""
    await _als_pool.shutdown_all()


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
            description="Navigate to a symbol's type definition (where the type is declared)",
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
            description="Navigate from declaration to implementation (spec to body)",
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
            name="ada_project_info",
            description="Get information about an Ada project from its GPR file",
            inputSchema={
                "type": "object",
                "properties": {
                    "gpr_file": {
                        "type": "string",
                        "description": "Absolute path to the .gpr project file",
                    },
                },
                "required": ["gpr_file"],
            },
        ),
        Tool(
            name="ada_call_hierarchy",
            description="Get call hierarchy (incoming/outgoing calls) for an Ada symbol",
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
                    "direction": {
                        "type": "string",
                        "description": "Call direction: 'outgoing', 'incoming', or 'both'",
                        "enum": ["outgoing", "incoming", "both"],
                        "default": "outgoing",
                    },
                },
                "required": ["file", "line", "column"],
            },
        ),
        Tool(
            name="ada_dependency_graph",
            description="Analyze package dependencies from 'with' clauses",
            inputSchema={
                "type": "object",
                "properties": {
                    "file": {
                        "type": "string",
                        "description": "Absolute path to Ada file or directory to analyze",
                    },
                },
                "required": ["file"],
            },
        ),
        Tool(
            name="ada_completions",
            description="Get code completion suggestions at a position in an Ada file",
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
                    "trigger_character": {
                        "type": "string",
                        "description": "Trigger character (e.g., '.', ':')",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of completions to return",
                        "default": 50,
                    },
                },
                "required": ["file", "line", "column"],
            },
        ),
        Tool(
            name="ada_signature_help",
            description="Get function/procedure signature help at a position",
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
            name="ada_code_actions",
            description="Get available code actions (quick fixes, refactorings) for a range",
            inputSchema={
                "type": "object",
                "properties": {
                    "file": {
                        "type": "string",
                        "description": "Absolute path to the Ada file",
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "Start line number (1-based)",
                    },
                    "start_column": {
                        "type": "integer",
                        "description": "Start column number (1-based)",
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "End line number (1-based), defaults to start_line",
                    },
                    "end_column": {
                        "type": "integer",
                        "description": "End column number (1-based), defaults to start_column",
                    },
                },
                "required": ["file", "start_line", "start_column"],
            },
        ),
        # Phase 5: Refactoring
        Tool(
            name="ada_rename_symbol",
            description="Rename an Ada symbol across the entire project",
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
                    "new_name": {
                        "type": "string",
                        "description": "New name for the symbol",
                    },
                    "preview": {
                        "type": "boolean",
                        "description": "If true, only return changes without applying",
                        "default": True,
                    },
                },
                "required": ["file", "line", "column", "new_name"],
            },
        ),
        Tool(
            name="ada_format_file",
            description="Format an Ada source file using GNATformat",
            inputSchema={
                "type": "object",
                "properties": {
                    "file": {
                        "type": "string",
                        "description": "Absolute path to the Ada file",
                    },
                    "tab_size": {
                        "type": "integer",
                        "description": "Tab width (default 3 for Ada)",
                        "default": 3,
                    },
                    "insert_spaces": {
                        "type": "boolean",
                        "description": "Use spaces instead of tabs",
                        "default": True,
                    },
                },
                "required": ["file"],
            },
        ),
        Tool(
            name="ada_get_spec",
            description="Navigate from body to spec file, or find corresponding spec",
            inputSchema={
                "type": "object",
                "properties": {
                    "file": {
                        "type": "string",
                        "description": "Absolute path to the Ada file (usually .adb)",
                    },
                    "line": {
                        "type": "integer",
                        "description": "Optional 1-based line number for precise lookup",
                    },
                    "column": {
                        "type": "integer",
                        "description": "Optional 1-based column number for precise lookup",
                    },
                },
                "required": ["file"],
            },
        ),
        # Phase 6: Build & Project Management
        Tool(
            name="ada_build",
            description="Build an Ada project using GPRbuild and return compilation results",
            inputSchema={
                "type": "object",
                "properties": {
                    "gpr_file": {
                        "type": "string",
                        "description": "Path to GPR project file (auto-detects if not provided)",
                    },
                    "target": {
                        "type": "string",
                        "description": "Specific build target (main unit name)",
                    },
                    "clean": {
                        "type": "boolean",
                        "description": "Clean before building",
                        "default": False,
                    },
                    "extra_args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Additional arguments to pass to gprbuild",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="ada_alire_info",
            description="Get Alire project information from alire.toml",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_dir": {
                        "type": "string",
                        "description": "Directory containing alire.toml (defaults to cwd)",
                    },
                },
                "required": [],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool invocations."""
    logger.debug(f"Tool called: {name} with args: {arguments}")

    # Extract file path from arguments for project detection
    file_path = arguments.get("file") or arguments.get("gpr_file")

    try:
        client = await get_als_client(file_path=file_path)
    except Exception as e:
        error_result = {
            "error": f"Failed to connect to ALS: {e}",
            "context": {"tool": name, "file": file_path},
            "hint": "Check that the Ada Language Server is installed and ALS_PATH is set correctly",
        }
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

            case "ada_project_info":
                result = await handle_project_info(
                    gpr_file=arguments["gpr_file"],
                )

            case "ada_call_hierarchy":
                result = await handle_call_hierarchy(
                    client,
                    file=arguments["file"],
                    line=arguments["line"],
                    column=arguments["column"],
                    direction=arguments.get("direction", "outgoing"),
                )

            case "ada_dependency_graph":
                result = await handle_dependency_graph(
                    file=arguments["file"],
                )

            case "ada_completions":
                result = await handle_completions(
                    client,
                    file=arguments["file"],
                    line=arguments["line"],
                    column=arguments["column"],
                    trigger_character=arguments.get("trigger_character"),
                    limit=arguments.get("limit", 50),
                )

            case "ada_signature_help":
                result = await handle_signature_help(
                    client,
                    file=arguments["file"],
                    line=arguments["line"],
                    column=arguments["column"],
                )

            case "ada_code_actions":
                result = await handle_code_actions(
                    client,
                    file=arguments["file"],
                    start_line=arguments["start_line"],
                    start_column=arguments["start_column"],
                    end_line=arguments.get("end_line"),
                    end_column=arguments.get("end_column"),
                )

            case "ada_rename_symbol":
                result = await handle_rename_symbol(
                    client,
                    file=arguments["file"],
                    line=arguments["line"],
                    column=arguments["column"],
                    new_name=arguments["new_name"],
                    preview=arguments.get("preview", True),
                )

            case "ada_format_file":
                result = await handle_format_file(
                    client,
                    file=arguments["file"],
                    tab_size=arguments.get("tab_size", 3),
                    insert_spaces=arguments.get("insert_spaces", True),
                )

            case "ada_get_spec":
                result = await handle_get_spec(
                    client,
                    file=arguments["file"],
                    line=arguments.get("line"),
                    column=arguments.get("column"),
                )

            case "ada_build":
                result = await handle_build(
                    gpr_file=arguments.get("gpr_file"),
                    target=arguments.get("target"),
                    clean=arguments.get("clean", False),
                    extra_args=arguments.get("extra_args"),
                )

            case "ada_alire_info":
                result = await handle_alire_info(
                    project_dir=arguments.get("project_dir"),
                )

            case _:
                result = {"error": f"Unknown tool: {name}", "available_tools": "Use list_tools to see available tools"}

    except Exception as e:
        logger.exception(f"Error executing tool {name}: {e}")
        result = {
            "error": str(e),
            "context": {"tool": name, "arguments": arguments},
        }

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
