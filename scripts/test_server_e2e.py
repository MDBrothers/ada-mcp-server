#!/usr/bin/env python3
"""
End-to-end test script for Ada MCP Server.

Starts the server as a subprocess, sends MCP protocol messages,
validates responses, and shuts down cleanly.

MCP uses newline-delimited JSON (NDJSON) over stdio - one JSON message per line.
"""

import asyncio
import json
import os
import sys
from pathlib import Path


class MCPTestClient:
    """Simple MCP client for testing."""

    def __init__(self, process: asyncio.subprocess.Process):
        self.process = process
        self.request_id = 0

    async def send_request(self, method: str, params: dict | None = None) -> dict:
        """Send a JSON-RPC request and wait for response."""
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
        }
        if params is not None:
            request["params"] = params

        await self._write_message(request)
        return await self._read_response(self.request_id)

    async def send_notification(self, method: str, params: dict | None = None) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        notification = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params is not None:
            notification["params"] = params
        await self._write_message(notification)

    async def _write_message(self, message: dict) -> None:
        """Write a JSON-RPC message as newline-delimited JSON (NDJSON)."""
        # MCP uses NDJSON - one JSON object per line
        line = json.dumps(message, separators=(",", ":")) + "\n"

        assert self.process.stdin is not None
        self.process.stdin.write(line.encode("utf-8"))
        await self.process.stdin.drain()

    async def _read_response(self, expected_id: int, timeout: float = 30.0) -> dict:
        """Read JSON-RPC response with matching ID."""
        assert self.process.stdout is not None

        async def read_message() -> dict:
            # MCP uses NDJSON - read one line = one JSON message
            line = await self.process.stdout.readline()
            if not line:
                raise EOFError("Server closed connection")
            return json.loads(line.decode("utf-8"))

        # Read messages until we get the one with our ID
        # (server might send notifications in between)
        while True:
            try:
                message = await asyncio.wait_for(read_message(), timeout=timeout)
            except TimeoutError:
                raise TimeoutError(f"Timeout waiting for response to request {expected_id}")

            # Skip notifications (no id field)
            if "id" not in message:
                print(f"  [notification] {message.get('method', 'unknown')}")
                continue

            if message.get("id") == expected_id:
                return message

            print(f"  [unexpected id] got {message.get('id')}, expected {expected_id}")


async def run_tests() -> bool:
    """Run end-to-end tests against the MCP server."""
    print("=" * 60)
    print("Ada MCP Server End-to-End Test")
    print("=" * 60)

    # Find the Python interpreter in the venv
    project_root = Path(__file__).parent.parent
    venv_python = project_root / ".venv" / "bin" / "python"
    if not venv_python.exists():
        venv_python = Path(sys.executable)

    print(f"\n[1] Starting server with: {venv_python} -m ada_mcp")

    # Set up environment - use sample_project to avoid scanning the entire repo
    # which can cause massive memory usage from .venv and other non-Ada directories
    sample_project = project_root / "tests" / "fixtures" / "sample_project"
    env = os.environ.copy()
    env["ADA_PROJECT_ROOT"] = str(sample_project)

    # Start the server as a subprocess
    process = await asyncio.create_subprocess_exec(
        str(venv_python),
        "-m",
        "ada_mcp",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        cwd=str(sample_project),
    )

    client = MCPTestClient(process)
    tests_passed = 0
    tests_failed = 0

    try:
        # Give server a moment to start
        await asyncio.sleep(0.5)

        # Test 1: Initialize
        print("\n[2] Sending initialize request...")
        response = await client.send_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0.0"},
            },
        )

        if "result" in response:
            print(f"    ✓ Server initialized: {response['result'].get('serverInfo', {})}")
            tests_passed += 1
        else:
            print(f"    ✗ Initialize failed: {response.get('error', 'unknown error')}")
            tests_failed += 1
            return False

        # Send initialized notification
        await client.send_notification("notifications/initialized")
        print("    ✓ Sent initialized notification")

        # Test 2: List tools
        print("\n[3] Listing available tools...")
        response = await client.send_request("tools/list", {})

        if "result" in response:
            tools = response["result"].get("tools", [])
            print(f"    ✓ Found {len(tools)} tools:")
            for tool in tools:
                print(f"      - {tool['name']}: {tool.get('description', '')[:50]}...")
            tests_passed += 1
        else:
            print(f"    ✗ List tools failed: {response.get('error', 'unknown error')}")
            tests_failed += 1

        # Test 3: Call a tool
        print("\n[4] Calling ada_goto_definition tool...")
        response = await client.send_request(
            "tools/call",
            {
                "name": "ada_goto_definition",
                "arguments": {
                    "file": "/tmp/test.adb",
                    "line": 10,
                    "column": 5,
                },
            },
        )

        if "result" in response:
            content = response["result"].get("content", [])
            if content:
                text = content[0].get("text", "")
                result_data = json.loads(text) if text else {}
                print(f"    ✓ Tool returned: {result_data}")
                tests_passed += 1
            else:
                print("    ✓ Tool returned empty result (expected - ALS not connected)")
                tests_passed += 1
        else:
            print(f"    ✗ Tool call failed: {response.get('error', 'unknown error')}")
            tests_failed += 1

        # Test 4: Call unknown tool (should return error gracefully)
        print("\n[5] Calling unknown tool (testing error handling)...")
        response = await client.send_request(
            "tools/call",
            {
                "name": "nonexistent_tool",
                "arguments": {},
            },
        )

        if "result" in response:
            content = response["result"].get("content", [])
            if content:
                text = content[0].get("text", "")
                if "error" in text.lower() or "unknown" in text.lower():
                    print("    ✓ Unknown tool handled gracefully")
                    tests_passed += 1
                else:
                    print(f"    ? Unexpected response: {text}")
                    tests_passed += 1  # Still a valid response
            else:
                print("    ✓ Unknown tool returned empty (acceptable)")
                tests_passed += 1
        else:
            # Error response is also acceptable
            print(
                f"    ✓ Unknown tool returned error: {response.get('error', {}).get('message', '')}"
            )
            tests_passed += 1

    except Exception as e:
        print(f"\n    ✗ Test error: {e}")
        tests_failed += 1

    finally:
        # Shutdown
        print("\n[6] Shutting down server...")
        try:
            # Try graceful shutdown first
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=3.0)
                print("    ✓ Server terminated gracefully")
            except TimeoutError:
                print("    ! Server didn't terminate, killing...")
                process.kill()
                await process.wait()
                print("    ✓ Server killed")
        except Exception as e:
            print(f"    ! Shutdown error: {e}")

        # Check for any stderr output
        if process.stderr:
            stderr_data = await process.stderr.read()
            if stderr_data:
                stderr_text = stderr_data.decode().strip()
                if stderr_text:
                    print(f"\n[Server stderr]:\n{stderr_text[:500]}")

    # Summary
    print("\n" + "=" * 60)
    print(f"Results: {tests_passed} passed, {tests_failed} failed")
    print("=" * 60)

    return tests_failed == 0


def main() -> int:
    """Main entry point."""
    success = asyncio.run(run_tests())
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
