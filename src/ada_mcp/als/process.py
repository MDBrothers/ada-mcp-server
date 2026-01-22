"""ALS process management - spawning, initialization, and lifecycle."""

import asyncio
import logging
import os
from pathlib import Path

from ada_mcp.als.client import ALSClient

logger = logging.getLogger(__name__)


async def find_gpr_file(project_root: Path) -> Path | None:
    """Find GPR file in project root, preferring alire-generated ones."""
    gpr_files = list(project_root.glob("*.gpr"))

    if not gpr_files:
        return None

    # Prefer non-alire GPR if both exist (alire generates wrapper)
    for gpr in gpr_files:
        if not gpr.name.startswith("alire"):
            return gpr

    return gpr_files[0]


async def start_als(
    project_root: Path,
    als_path: str | None = None,
    gpr_file: Path | None = None,
) -> ALSClient:
    """
    Spawn ALS process and initialize LSP session.

    Args:
        project_root: Root directory of the Ada project
        als_path: Path to ALS executable (defaults to 'ada_language_server')
        gpr_file: Path to GPR file (auto-detected if None)

    Returns:
        Initialized ALSClient ready for requests
    """
    # Determine ALS path
    if als_path is None:
        als_path = os.environ.get("ALS_PATH", "ada_language_server")

    # Find GPR file
    if gpr_file is None:
        env_gpr = os.environ.get("ADA_PROJECT_FILE")
        if env_gpr:
            gpr_file = project_root / env_gpr
        else:
            gpr_file = await find_gpr_file(project_root)

    logger.info(f"Starting ALS: {als_path}")
    logger.info(f"Project root: {project_root}")
    if gpr_file:
        logger.info(f"GPR file: {gpr_file}")

    # Spawn ALS process
    process = await asyncio.create_subprocess_exec(
        als_path,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(project_root),
    )

    client = ALSClient(process=process)

    # Start reading responses in background
    client.start_reading()

    # Send initialize request
    root_uri = project_root.as_uri()

    init_params = {
        "processId": os.getpid(),
        "capabilities": {
            "textDocument": {
                "definition": {
                    "dynamicRegistration": True,
                    "linkSupport": True,
                },
                "references": {
                    "dynamicRegistration": True,
                },
                "hover": {
                    "dynamicRegistration": True,
                    "contentFormat": ["plaintext", "markdown"],
                },
                "documentSymbol": {
                    "dynamicRegistration": True,
                    "hierarchicalDocumentSymbolSupport": True,
                },
                "completion": {
                    "dynamicRegistration": True,
                    "completionItem": {
                        "snippetSupport": False,
                        "documentationFormat": ["plaintext", "markdown"],
                    },
                },
                "publishDiagnostics": {
                    "relatedInformation": True,
                },
                "callHierarchy": {
                    "dynamicRegistration": True,
                },
                "rename": {
                    "dynamicRegistration": True,
                    "prepareSupport": True,
                },
            },
            "workspace": {
                "workspaceFolders": True,
                "symbol": {
                    "dynamicRegistration": True,
                },
            },
        },
        "rootUri": root_uri,
        "rootPath": str(project_root),
        "workspaceFolders": [{"uri": root_uri, "name": project_root.name}],
        "initializationOptions": {},
    }

    # Add GPR file to initialization if found
    if gpr_file and gpr_file.exists():
        init_params["initializationOptions"]["projectFile"] = str(gpr_file)

    logger.debug("Sending initialize request")
    result = await client.send_request("initialize", init_params)

    # Store server capabilities
    client._server_capabilities = result.get("capabilities", {})
    client._initialized = True

    logger.info("ALS initialized successfully")
    logger.debug(f"Server capabilities: {list(client._server_capabilities.keys())}")

    # Send initialized notification
    await client.send_notification("initialized", {})

    # Open GPR file to trigger project loading and indexing
    if gpr_file and gpr_file.exists():
        logger.debug(f"Opening GPR file: {gpr_file}")
        await client.send_notification(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": gpr_file.as_uri(),
                    "languageId": "gpr",
                    "version": 1,
                    "text": gpr_file.read_text(),
                }
            },
        )

        # Give ALS time to index the project
        await asyncio.sleep(0.5)

    return client


async def shutdown_als(client: ALSClient) -> None:
    """Gracefully shutdown ALS client and process."""
    logger.info("Shutting down ALS")

    try:
        await client.shutdown()
    except Exception as e:
        logger.warning(f"Error during ALS shutdown: {e}")

    # Terminate process if still running
    if client.is_running:
        client.process.terminate()
        try:
            await asyncio.wait_for(client.process.wait(), timeout=5.0)
        except TimeoutError:
            logger.warning("ALS did not terminate gracefully, killing")
            client.process.kill()
            await client.process.wait()

    logger.info("ALS shutdown complete")
