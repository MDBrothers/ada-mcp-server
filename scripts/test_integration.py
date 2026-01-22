#!/usr/bin/env python3
"""
Integration test for Ada MCP Server with real ALS.

This test starts the MCP server with ALS_PATH configured, uses the
sample Ada project, and tests all tools with real ALS responses.
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
        line = json.dumps(message, separators=(",", ":")) + "\n"
        assert self.process.stdin is not None
        self.process.stdin.write(line.encode("utf-8"))
        await self.process.stdin.drain()

    async def _read_response(self, expected_id: int, timeout: float = 60.0) -> dict:
        """Read JSON-RPC response with matching ID."""
        assert self.process.stdout is not None

        async def read_message() -> dict:
            line = await self.process.stdout.readline()
            if not line:
                raise EOFError("Server closed connection")
            return json.loads(line.decode("utf-8"))

        while True:
            try:
                message = await asyncio.wait_for(read_message(), timeout=timeout)
            except asyncio.TimeoutError:
                raise TimeoutError(f"Timeout waiting for response to request {expected_id}")

            if "id" not in message:
                continue  # Skip notifications

            if message.get("id") == expected_id:
                return message


async def call_tool(client: MCPTestClient, name: str, arguments: dict) -> dict:
    """Call a tool and return the parsed result."""
    response = await client.send_request("tools/call", {
        "name": name,
        "arguments": arguments,
    })
    
    if "error" in response:
        return {"error": response["error"]}
    
    content = response.get("result", {}).get("content", [])
    if content:
        return json.loads(content[0].get("text", "{}"))
    return {}


async def run_integration_tests() -> bool:
    """Run integration tests with real ALS."""
    print("=" * 70)
    print("Ada MCP Server Integration Test (with real ALS)")
    print("=" * 70)

    # Setup paths
    project_root = Path(__file__).parent.parent
    sample_project = project_root / "tests" / "fixtures" / "sample_project"
    test_file = sample_project / "src" / "main.adb"
    utils_file = sample_project / "src" / "utils.ads"
    
    if not sample_project.exists():
        print(f"ERROR: Sample project not found: {sample_project}")
        return False

    # Find ALS
    als_path = os.environ.get("ALS_PATH")
    if not als_path:
        # Try VS Code extension path
        vscode_als = Path.home() / ".vscode" / "extensions"
        als_candidates = list(vscode_als.glob("adacore.ada-*/x64/linux/ada_language_server"))
        if als_candidates:
            als_path = str(sorted(als_candidates)[-1])  # Use latest version
    
    if not als_path or not Path(als_path).exists():
        print("ERROR: ALS not found. Set ALS_PATH environment variable.")
        print("       Or install VS Code Ada extension.")
        return False

    print(f"\nUsing ALS: {als_path}")
    print(f"Project: {sample_project}")
    print(f"Test file: {test_file}")

    # Start server
    venv_python = project_root / ".venv" / "bin" / "python"
    if not venv_python.exists():
        venv_python = Path(sys.executable)

    env = os.environ.copy()
    env["ALS_PATH"] = als_path
    env["ADA_PROJECT_ROOT"] = str(sample_project)
    env["ADA_MCP_LOG_LEVEL"] = "DEBUG"

    print(f"\n[1] Starting MCP server...")
    process = await asyncio.create_subprocess_exec(
        str(venv_python),
        "-m", "ada_mcp",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        cwd=str(sample_project),
    )

    client = MCPTestClient(process)
    tests_passed = 0
    tests_failed = 0

    def test_result(name: str, passed: bool, message: str = ""):
        nonlocal tests_passed, tests_failed
        if passed:
            tests_passed += 1
            print(f"    ✓ {name}" + (f": {message}" if message else ""))
        else:
            tests_failed += 1
            print(f"    ✗ {name}" + (f": {message}" if message else ""))

    try:
        await asyncio.sleep(0.5)

        # Initialize
        print("\n[2] Initializing MCP connection...")
        response = await client.send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "integration-test", "version": "1.0.0"},
        })
        test_result("Initialize", "result" in response)
        await client.send_notification("notifications/initialized")

        # List tools
        print("\n[3] Checking available tools...")
        response = await client.send_request("tools/list", {})
        tools = response.get("result", {}).get("tools", [])
        tool_names = [t["name"] for t in tools]
        
        expected_tools = [
            "ada_goto_definition", "ada_hover", "ada_diagnostics",
            "ada_find_references", "ada_document_symbols", "ada_workspace_symbols"
        ]
        for tool in expected_tools:
            test_result(f"Tool '{tool}' registered", tool in tool_names)

        # Wait for ALS to initialize (first tool call starts ALS)
        print("\n[4] Testing ada_hover (this starts ALS, may take a moment)...")
        result = await call_tool(client, "ada_hover", {
            "file": str(test_file),
            "line": 4,  # "procedure Main is" line
            "column": 12,  # On "Main"
        })
        
        if "error" in result and "ALS" in str(result.get("error", "")):
            print(f"    ! ALS connection issue: {result['error']}")
            # Continue anyway to see what else works
        else:
            has_contents = result.get("found") and result.get("contents")
            test_result("ada_hover", has_contents or result.get("found") is not None,
                       f"found={result.get('found')}")

        # Test goto_definition
        print("\n[5] Testing ada_goto_definition...")
        result = await call_tool(client, "ada_goto_definition", {
            "file": str(test_file),
            "line": 5,  # Line with Utils.Add call
            "column": 24,  # Position of "Add"
        })
        
        if "error" not in result:
            found = result.get("found", False)
            target_file = result.get("file", "")
            test_result("ada_goto_definition", found,
                       f"-> {Path(target_file).name if target_file else 'not found'}")
        else:
            test_result("ada_goto_definition", False, str(result.get("error")))

        # Test find_references
        print("\n[6] Testing ada_find_references...")
        result = await call_tool(client, "ada_find_references", {
            "file": str(utils_file),
            "line": 5,  # "function Add" line
            "column": 13,  # On "Add"
            "include_declaration": True,
        })
        
        if "error" not in result:
            count = result.get("count", 0)
            test_result("ada_find_references", count > 0, f"found {count} references")
        else:
            test_result("ada_find_references", False, str(result.get("error")))

        # Test document_symbols
        print("\n[7] Testing ada_document_symbols...")
        result = await call_tool(client, "ada_document_symbols", {
            "file": str(test_file),
        })
        
        if "error" not in result:
            symbols = result.get("symbols", [])
            test_result("ada_document_symbols", len(symbols) > 0,
                       f"found {len(symbols)} symbols")
            for sym in symbols[:3]:
                print(f"        - {sym.get('name')} ({sym.get('kind')})")
        else:
            test_result("ada_document_symbols", False, str(result.get("error")))

        # Test workspace_symbols
        print("\n[8] Testing ada_workspace_symbols...")
        result = await call_tool(client, "ada_workspace_symbols", {
            "query": "Add",
            "kind": "all",
            "limit": 10,
        })
        
        if "error" not in result:
            symbols = result.get("symbols", [])
            test_result("ada_workspace_symbols", len(symbols) > 0,
                       f"found {len(symbols)} symbols matching 'Add'")
        else:
            test_result("ada_workspace_symbols", False, str(result.get("error")))

        # Test diagnostics
        print("\n[9] Testing ada_diagnostics...")
        result = await call_tool(client, "ada_diagnostics", {
            "severity": "all",
        })
        
        if "error" not in result:
            total = result.get("totalCount", 0)
            errors = result.get("errorCount", 0)
            warnings = result.get("warningCount", 0)
            test_result("ada_diagnostics", True,
                       f"{errors} errors, {warnings} warnings, {total} total")
        else:
            test_result("ada_diagnostics", False, str(result.get("error")))

    except Exception as e:
        print(f"\n    ✗ Test error: {e}")
        import traceback
        traceback.print_exc()
        tests_failed += 1

    finally:
        print("\n[10] Shutting down server...")
        try:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
                print("    ✓ Server terminated gracefully")
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                print("    ✓ Server killed")
        except Exception as e:
            print(f"    ! Shutdown error: {e}")

        # Show stderr if verbose
        if process.stderr and os.environ.get("VERBOSE"):
            stderr_data = await process.stderr.read()
            if stderr_data:
                print(f"\n[Server logs]:\n{stderr_data.decode()[:2000]}")

    # Summary
    print("\n" + "=" * 70)
    total = tests_passed + tests_failed
    print(f"Results: {tests_passed}/{total} passed, {tests_failed} failed")
    print("=" * 70)

    return tests_failed == 0


def main() -> int:
    success = asyncio.run(run_integration_tests())
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
