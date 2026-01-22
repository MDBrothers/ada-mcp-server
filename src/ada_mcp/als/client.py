"""Async client for communicating with Ada Language Server via LSP."""

import asyncio
import json
import logging
from typing import Any

from ada_mcp.als.types import (
    Diagnostic,
    DiagnosticSeverity,
)

logger = logging.getLogger(__name__)


class LSPError(Exception):
    """Raised when LSP returns an error response."""

    def __init__(self, code: int, message: str, data: Any = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(f"LSP Error {code}: {message}")


class ALSClient:
    """Async client for communicating with Ada Language Server."""

    def __init__(self, process: asyncio.subprocess.Process):
        self.process = process
        self._request_id = 0
        self._pending_requests: dict[int, asyncio.Future[Any]] = {}
        self._read_task: asyncio.Task[None] | None = None
        self._initialized = False
        self._server_capabilities: dict[str, Any] = {}

        # Diagnostics are pushed via notifications, store them here
        self._diagnostics: dict[str, list[Diagnostic]] = {}
        self._diagnostics_lock = asyncio.Lock()

    @property
    def is_running(self) -> bool:
        """Check if ALS process is still running."""
        return self.process.returncode is None

    def start_reading(self) -> None:
        """Start the background read loop."""
        if self._read_task is None:
            self._read_task = asyncio.create_task(self._read_loop())

    async def send_request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        """Send LSP request and wait for response."""
        if not self.is_running:
            raise LSPError(-1, "ALS process is not running")

        self._request_id += 1
        request_id = self._request_id

        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params is not None:
            request["params"] = params

        future: asyncio.Future[Any] = asyncio.get_event_loop().create_future()
        self._pending_requests[request_id] = future

        logger.debug(f"Sending request {request_id}: {method}")
        await self._write_message(request)

        try:
            result = await asyncio.wait_for(future, timeout=30.0)
            return result
        except TimeoutError:
            self._pending_requests.pop(request_id, None)
            raise LSPError(-1, f"Request {method} timed out")

    async def send_notification(self, method: str, params: dict[str, Any] | None = None) -> None:
        """Send LSP notification (no response expected)."""
        if not self.is_running:
            raise LSPError(-1, "ALS process is not running")

        notification: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params is not None:
            notification["params"] = params

        logger.debug(f"Sending notification: {method}")
        await self._write_message(notification)

    async def _write_message(self, message: dict[str, Any]) -> None:
        """Write JSON-RPC message to ALS stdin."""
        if self.process.stdin is None:
            raise LSPError(-1, "ALS stdin is not available")

        content = json.dumps(message)
        content_bytes = content.encode("utf-8")
        header = f"Content-Length: {len(content_bytes)}\r\n\r\n"

        self.process.stdin.write(header.encode("utf-8") + content_bytes)
        await self.process.stdin.drain()

    async def _read_loop(self) -> None:
        """Read responses and notifications from ALS stdout."""
        if self.process.stdout is None:
            logger.error("ALS stdout is not available")
            return

        try:
            while self.is_running:
                # Read headers
                headers: dict[str, str] = {}
                while True:
                    line = await self.process.stdout.readline()
                    if not line:
                        logger.info("ALS stdout closed")
                        return

                    line_str = line.decode("utf-8").strip()
                    if not line_str:
                        break  # Empty line separates headers from content

                    if ": " in line_str:
                        key, value = line_str.split(": ", 1)
                        headers[key] = value

                # Get content length
                content_length_str = headers.get("Content-Length")
                if content_length_str is None:
                    logger.warning("Missing Content-Length header")
                    continue

                content_length = int(content_length_str)

                # Read content
                content = await self.process.stdout.read(content_length)
                if len(content) < content_length:
                    logger.warning(
                        f"Incomplete message: got {len(content)}, expected {content_length}"
                    )
                    continue

                message = json.loads(content.decode("utf-8"))
                await self._handle_message(message)

        except asyncio.CancelledError:
            logger.debug("Read loop cancelled")
        except Exception as e:
            logger.exception(f"Error in read loop: {e}")

    async def _handle_message(self, message: dict[str, Any]) -> None:
        """Handle incoming LSP message."""
        if "id" in message:
            # Response to a request
            request_id = message["id"]
            future = self._pending_requests.pop(request_id, None)

            if future is None:
                logger.warning(f"Received response for unknown request {request_id}")
                return

            if "error" in message:
                error = message["error"]
                future.set_exception(
                    LSPError(
                        code=error.get("code", -1),
                        message=error.get("message", "Unknown error"),
                        data=error.get("data"),
                    )
                )
            else:
                future.set_result(message.get("result"))

        elif "method" in message:
            # Server notification or request
            method = message["method"]
            params = message.get("params", {})

            if method == "textDocument/publishDiagnostics":
                await self._handle_diagnostics(params)
            elif method == "window/logMessage":
                self._handle_log_message(params)
            elif method == "window/showMessage":
                self._handle_show_message(params)
            else:
                logger.debug(f"Unhandled notification: {method}")

    async def _handle_diagnostics(self, params: dict[str, Any]) -> None:
        """Handle publishDiagnostics notification."""
        uri = params.get("uri", "")
        diagnostics_data = params.get("diagnostics", [])

        diagnostics = [Diagnostic.from_dict(d) for d in diagnostics_data]

        async with self._diagnostics_lock:
            self._diagnostics[uri] = diagnostics

        logger.debug(f"Received {len(diagnostics)} diagnostics for {uri}")

    def _handle_log_message(self, params: dict[str, Any]) -> None:
        """Handle window/logMessage notification."""
        message_type = params.get("type", 4)
        message = params.get("message", "")

        if message_type == 1:  # Error
            logger.error(f"ALS: {message}")
        elif message_type == 2:  # Warning
            logger.warning(f"ALS: {message}")
        elif message_type == 3:  # Info
            logger.info(f"ALS: {message}")
        else:  # Log
            logger.debug(f"ALS: {message}")

    def _handle_show_message(self, params: dict[str, Any]) -> None:
        """Handle window/showMessage notification."""
        message = params.get("message", "")
        logger.info(f"ALS message: {message}")

    async def get_diagnostics(
        self, uri: str | None = None, severity: DiagnosticSeverity | None = None
    ) -> dict[str, list[Diagnostic]]:
        """Get cached diagnostics, optionally filtered by URI and severity."""
        async with self._diagnostics_lock:
            if uri is not None:
                diagnostics = {uri: self._diagnostics.get(uri, [])}
            else:
                diagnostics = dict(self._diagnostics)

        if severity is not None:
            filtered: dict[str, list[Diagnostic]] = {}
            for file_uri, diags in diagnostics.items():
                filtered[file_uri] = [d for d in diags if d.severity == severity]
            return filtered

        return diagnostics

    async def shutdown(self) -> None:
        """Send shutdown request and exit notification."""
        try:
            if self.is_running:
                await self.send_request("shutdown")
                await self.send_notification("exit")
        except Exception as e:
            logger.warning(f"Error during shutdown: {e}")

        if self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
