"""ALS process management - spawning, initialization, and lifecycle."""

import asyncio
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ada_mcp.als.client import ALSClient

logger = logging.getLogger(__name__)


@dataclass
class ALSHealthMonitor:
    """
    Monitor ALS process health and handle automatic restarts.

    Implements exponential backoff for restart attempts to avoid
    overwhelming the system if ALS keeps crashing.
    """

    client: ALSClient
    project_root: Path
    als_path: str
    gpr_file: Path | None = None

    # Restart configuration
    max_restart_attempts: int = 5
    initial_backoff_seconds: float = 1.0
    max_backoff_seconds: float = 60.0
    backoff_multiplier: float = 2.0

    # State tracking
    restart_count: int = field(default=0, init=False)
    last_restart_time: float = field(default=0.0, init=False)
    _monitor_task: asyncio.Task | None = field(default=None, init=False)
    _shutdown_requested: bool = field(default=False, init=False)
    _on_restart_callback: Callable[["ALSClient"], None] | None = field(default=None, init=False)

    def start_monitoring(self, on_restart: Callable[["ALSClient"], None] | None = None) -> None:
        """Start the health monitoring background task."""
        self._on_restart_callback = on_restart
        self._shutdown_requested = False
        if self._monitor_task is None or self._monitor_task.done():
            self._monitor_task = asyncio.create_task(self._monitor_loop())
            logger.info("ALS health monitoring started")

    def stop_monitoring(self) -> None:
        """Stop the health monitoring task."""
        self._shutdown_requested = True
        if self._monitor_task is not None:
            self._monitor_task.cancel()
            logger.info("ALS health monitoring stopped")

    async def _monitor_loop(self) -> None:
        """Monitor ALS process and restart if crashed."""
        while not self._shutdown_requested:
            try:
                await asyncio.sleep(2.0)  # Check every 2 seconds

                if self._shutdown_requested:
                    break

                if not self.client.is_running:
                    logger.warning("ALS process has exited unexpectedly")
                    await self._handle_crash()

            except asyncio.CancelledError:
                logger.debug("Health monitor cancelled")
                break
            except Exception as e:
                logger.exception(f"Error in health monitor: {e}")
                await asyncio.sleep(5.0)

    async def _handle_crash(self) -> None:
        """Handle ALS crash by attempting restart with exponential backoff."""
        if self._shutdown_requested:
            return

        if self.restart_count >= self.max_restart_attempts:
            logger.error(
                f"ALS has crashed {self.restart_count} times. "
                "Max restart attempts reached. Manual intervention required."
            )
            return

        # Calculate backoff delay
        backoff = min(
            self.initial_backoff_seconds * (self.backoff_multiplier**self.restart_count),
            self.max_backoff_seconds,
        )

        logger.info(
            f"Attempting ALS restart in {backoff:.1f}s "
            f"(attempt {self.restart_count + 1}/{self.max_restart_attempts})"
        )

        await asyncio.sleep(backoff)

        if self._shutdown_requested:
            return

        try:
            # Attempt restart
            new_client = await start_als(
                self.project_root,
                als_path=self.als_path,
                gpr_file=self.gpr_file,
            )

            # Update reference
            self.client = new_client
            self.restart_count += 1

            logger.info(f"ALS restarted successfully (restart #{self.restart_count})")

            # Notify callback if set
            if self._on_restart_callback:
                self._on_restart_callback(new_client)

            # Reset restart count after successful period (30 seconds)
            await asyncio.sleep(30.0)
            if self.client.is_running:
                logger.info("ALS stable after restart, resetting restart counter")
                self.restart_count = 0

        except Exception as e:
            logger.exception(f"Failed to restart ALS: {e}")
            self.restart_count += 1

    def reset_restart_count(self) -> None:
        """Manually reset the restart counter."""
        self.restart_count = 0
        logger.debug("ALS restart counter reset")


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
    resolved_als_path: str
    if als_path is None:
        resolved_als_path = os.environ.get("ALS_PATH", "ada_language_server")
    else:
        resolved_als_path = als_path

    # Find GPR file
    if gpr_file is None:
        env_gpr = os.environ.get("ADA_PROJECT_FILE")
        if env_gpr:
            gpr_file = project_root / env_gpr
        else:
            gpr_file = await find_gpr_file(project_root)

    logger.info(f"Starting ALS: {resolved_als_path}")
    logger.info(f"Project root: {project_root}")
    if gpr_file:
        logger.info(f"GPR file: {gpr_file}")

    # Spawn ALS process
    process = await asyncio.create_subprocess_exec(
        resolved_als_path,
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

    # Add GPR file to initialization if found, otherwise disable indexing
    # to prevent ALS from scanning the entire workspace (which can cause
    # massive memory usage if the workspace contains non-Ada directories
    # like Python venvs or node_modules)
    if gpr_file and gpr_file.exists():
        init_params["initializationOptions"]["projectFile"] = str(gpr_file)
    else:
        logger.warning(
            "No GPR project file found. Disabling ALS indexing to prevent "
            "unbounded memory usage. Set ADA_PROJECT_FILE or ADA_PROJECT_ROOT "
            "to point to a valid Ada project."
        )
        init_params["initializationOptions"]["enableIndexing"] = False

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

    # Store configuration for potential restarts
    client._project_root = project_root
    client._als_path = resolved_als_path
    client._gpr_file = gpr_file

    return client


async def start_als_with_monitoring(
    project_root: Path,
    als_path: str | None = None,
    gpr_file: Path | None = None,
    on_restart: Callable[["ALSClient"], None] | None = None,
) -> tuple[ALSClient, ALSHealthMonitor]:
    """
    Start ALS with health monitoring and auto-restart capability.

    Args:
        project_root: Root directory of the Ada project
        als_path: Path to ALS executable
        gpr_file: Path to GPR file
        on_restart: Callback when ALS is restarted

    Returns:
        Tuple of (ALSClient, ALSHealthMonitor)
    """
    client = await start_als(project_root, als_path, gpr_file)

    resolved_als_path = als_path or os.environ.get("ALS_PATH", "ada_language_server")

    monitor = ALSHealthMonitor(
        client=client,
        project_root=project_root,
        als_path=resolved_als_path,
        gpr_file=gpr_file,
    )
    monitor.start_monitoring(on_restart=on_restart)

    return client, monitor


async def shutdown_als(client: ALSClient, monitor: ALSHealthMonitor | None = None) -> None:
    """Gracefully shutdown ALS client and process."""
    logger.info("Shutting down ALS")

    # Stop health monitoring first
    if monitor is not None:
        monitor.stop_monitoring()

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
