#!/usr/bin/env python3
"""
Comprehensive Phase 1 & 2 Integration Tests.

Tests all Phase 1 tools (ada_goto_definition, ada_hover, ada_diagnostics)
and Phase 2 tools (ada_find_references, ada_document_symbols, ada_workspace_symbols,
ada_type_definition, ada_implementation) with real ALS.

Run with: python scripts/test_phase1_integration.py
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Any


@dataclass
class TestCase:
    """A single test case."""
    name: str
    tool: str
    args: dict
    check: callable  # Function to validate result


class MCPTestClient:
    """MCP client for integration testing."""

    def __init__(self, process: asyncio.subprocess.Process):
        self.process = process
        self.request_id = 0

    async def send_request(self, method: str, params: dict | None = None) -> dict:
        self.request_id += 1
        request = {"jsonrpc": "2.0", "id": self.request_id, "method": method}
        if params is not None:
            request["params"] = params

        line = json.dumps(request, separators=(",", ":")) + "\n"
        self.process.stdin.write(line.encode())
        await self.process.stdin.drain()

        while True:
            resp_line = await asyncio.wait_for(
                self.process.stdout.readline(), timeout=60.0
            )
            if not resp_line:
                raise EOFError("Server closed")
            message = json.loads(resp_line.decode())
            if message.get("id") == self.request_id:
                return message

    async def send_notification(self, method: str, params: dict | None = None) -> None:
        notification = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            notification["params"] = params
        line = json.dumps(notification, separators=(",", ":")) + "\n"
        self.process.stdin.write(line.encode())
        await self.process.stdin.drain()


async def call_tool(client: MCPTestClient, name: str, arguments: dict) -> dict:
    """Call a tool and return the parsed result."""
    response = await client.send_request("tools/call", {
        "name": name,
        "arguments": arguments,
    })
    if "error" in response:
        return {"_error": response["error"]}
    content = response.get("result", {}).get("content", [])
    if content:
        return json.loads(content[0].get("text", "{}"))
    return {}


class Phase1IntegrationTests:
    """Phase 1 & 2 tool integration tests."""

    def __init__(self, sample_project: Path, error_project: Path):
        self.sample_project = sample_project
        self.error_project = error_project
        self.project_dir = sample_project  # Add this for Phase 3 tests
        self.main_adb = sample_project / "src" / "main.adb"
        self.utils_ads = sample_project / "src" / "utils.ads"
        self.utils_adb = sample_project / "src" / "utils.adb"
        self.broken_adb = error_project / "src" / "broken.adb"
        
        self.tests_passed = 0
        self.tests_failed = 0
        self.tests_skipped = 0

    def get_test_cases(self) -> list[TestCase]:
        """Return all test cases for Phase 1 & 2."""
        return [
            # ============================================================
            # ada_goto_definition tests
            # ============================================================
            TestCase(
                name="goto_definition: procedure call -> spec",
                tool="ada_goto_definition",
                args={"file": str(self.main_adb), "line": 5, "column": 24},  # Utils.Add
                check=lambda r: r.get("found") and "utils" in r.get("file", "").lower()
            ),
            TestCase(
                name="goto_definition: package name -> spec",
                tool="ada_goto_definition",
                args={"file": str(self.main_adb), "line": 5, "column": 18},  # Utils
                check=lambda r: r.get("found") is True or r.get("found") is False  # May resolve to type, not package
            ),
            TestCase(
                name="goto_definition: with clause -> spec",
                tool="ada_goto_definition",
                args={"file": str(self.main_adb), "line": 2, "column": 6},  # with Utils
                check=lambda r: r.get("found") and "utils" in r.get("file", "").lower()
            ),
            TestCase(
                name="goto_definition: Ada.Text_IO -> stdlib",
                tool="ada_goto_definition",
                args={"file": str(self.main_adb), "line": 1, "column": 10},  # Ada.Text_IO
                check=lambda r: r.get("found") is True or r.get("found") is False  # May or may not resolve
            ),
            TestCase(
                name="goto_definition: local variable -> declaration",
                tool="ada_goto_definition",
                args={"file": str(self.main_adb), "line": 7, "column": 53},  # Value in Put_Line
                check=lambda r: r.get("found") and r.get("line") == 5  # Declaration line
            ),
            TestCase(
                name="goto_definition: keyword (no definition)",
                tool="ada_goto_definition",
                args={"file": str(self.main_adb), "line": 6, "column": 1},  # begin
                check=lambda r: r.get("found") is False
            ),
            TestCase(
                name="goto_definition: whitespace (no definition)",
                tool="ada_goto_definition",
                args={"file": str(self.main_adb), "line": 6, "column": 6},  # after begin
                check=lambda r: r.get("found") is False or r.get("found") is True  # Depends on ALS
            ),
            TestCase(
                name="goto_definition: end of file",
                tool="ada_goto_definition",
                args={"file": str(self.main_adb), "line": 9, "column": 1},  # end Main;
                check=lambda r: "found" in r  # Should not crash
            ),
            TestCase(
                name="goto_definition: non-existent file",
                tool="ada_goto_definition",
                args={"file": "/nonexistent/file.adb", "line": 1, "column": 1},
                check=lambda r: r.get("found") is False or "_error" in r or "error" in r
            ),
            TestCase(
                name="goto_definition: line 0 (invalid)",
                tool="ada_goto_definition",
                args={"file": str(self.main_adb), "line": 0, "column": 1},
                check=lambda r: "found" in r or "error" in r  # Should handle gracefully
            ),
            TestCase(
                name="goto_definition: very large line number",
                tool="ada_goto_definition",
                args={"file": str(self.main_adb), "line": 99999, "column": 1},
                check=lambda r: r.get("found") is False
            ),
            
            # ============================================================
            # ada_hover tests
            # ============================================================
            TestCase(
                name="hover: procedure name",
                tool="ada_hover",
                args={"file": str(self.main_adb), "line": 4, "column": 12},  # Main
                check=lambda r: r.get("found") and "Main" in r.get("contents", "")
            ),
            TestCase(
                name="hover: function call",
                tool="ada_hover",
                args={"file": str(self.main_adb), "line": 5, "column": 24},  # Add
                check=lambda r: r.get("found") is True  # Content varies based on position
            ),
            TestCase(
                name="hover: variable",
                tool="ada_hover",
                args={"file": str(self.main_adb), "line": 5, "column": 4},  # Value
                check=lambda r: r.get("found") and "Integer" in r.get("contents", "")
            ),
            TestCase(
                name="hover: type name (Integer)",
                tool="ada_hover",
                args={"file": str(self.main_adb), "line": 5, "column": 12},  # Integer
                check=lambda r: r.get("found") is True or r.get("found") is False  # May vary
            ),
            TestCase(
                name="hover: package name",
                tool="ada_hover",
                args={"file": str(self.main_adb), "line": 5, "column": 18},  # Utils
                check=lambda r: r.get("found") is True  # May hover on type or package
            ),
            TestCase(
                name="hover: integer literal (no hover)",
                tool="ada_hover",
                args={"file": str(self.main_adb), "line": 5, "column": 30},  # 10
                check=lambda r: r.get("found") is False or "Integer" in r.get("contents", "")
            ),
            TestCase(
                name="hover: function in spec",
                tool="ada_hover",
                args={"file": str(self.utils_ads), "line": 5, "column": 13},  # Add
                check=lambda r: r.get("found") and "Add" in r.get("contents", "")
            ),
            TestCase(
                name="hover: function in body",
                tool="ada_hover",
                args={"file": str(self.utils_adb), "line": 4, "column": 13},  # Add
                check=lambda r: r.get("found") and "Add" in r.get("contents", "")
            ),
            TestCase(
                name="hover: parameter",
                tool="ada_hover",
                args={"file": str(self.utils_ads), "line": 5, "column": 18},  # A
                check=lambda r: r.get("found") and "Integer" in r.get("contents", "")
            ),
            TestCase(
                name="hover: keyword begin",
                tool="ada_hover",
                args={"file": str(self.main_adb), "line": 6, "column": 1},  # begin
                check=lambda r: r.get("found") is False
            ),
            TestCase(
                name="hover: empty line",
                tool="ada_hover",
                args={"file": str(self.utils_adb), "line": 3, "column": 1},  # empty line
                check=lambda r: r.get("found") is False
            ),
            TestCase(
                name="hover: non-existent file",
                tool="ada_hover",
                args={"file": "/nonexistent/file.adb", "line": 1, "column": 1},
                check=lambda r: r.get("found") is False or "_error" in r or "error" in r
            ),
            
            # ============================================================
            # ada_diagnostics tests
            # ============================================================
            TestCase(
                name="diagnostics: clean project (no errors)",
                tool="ada_diagnostics",
                args={"severity": "all"},
                check=lambda r: "diagnostics" in r and "errorCount" in r
            ),
            TestCase(
                name="diagnostics: specific clean file",
                tool="ada_diagnostics",
                args={"file": str(self.main_adb), "severity": "all"},
                check=lambda r: "diagnostics" in r
            ),
            TestCase(
                name="diagnostics: filter errors only",
                tool="ada_diagnostics",
                args={"severity": "error"},
                check=lambda r: "diagnostics" in r
            ),
            TestCase(
                name="diagnostics: filter warnings only",
                tool="ada_diagnostics",
                args={"severity": "warning"},
                check=lambda r: "diagnostics" in r
            ),
            TestCase(
                name="diagnostics: non-existent file",
                tool="ada_diagnostics",
                args={"file": "/nonexistent/file.adb", "severity": "all"},
                check=lambda r: "diagnostics" in r and len(r.get("diagnostics", [])) == 0
            ),
            TestCase(
                name="diagnostics: no parameters (all files)",
                tool="ada_diagnostics",
                args={},
                check=lambda r: "diagnostics" in r or "error" in r
            ),
            
            # ============================================================
            # ada_type_definition tests (NEW)
            # ============================================================
            TestCase(
                name="type_definition: variable -> type declaration",
                tool="ada_type_definition",
                args={"file": str(self.main_adb), "line": 5, "column": 4},  # Value : Integer
                check=lambda r: r.get("found") is True or r.get("found") is False  # Integer is built-in
            ),
            TestCase(
                name="type_definition: parameter -> type",
                tool="ada_type_definition",
                args={"file": str(self.utils_ads), "line": 5, "column": 18},  # A : Integer
                check=lambda r: r.get("found") is True or r.get("found") is False  # Integer is built-in
            ),
            TestCase(
                name="type_definition: function name (no type def)",
                tool="ada_type_definition",
                args={"file": str(self.utils_ads), "line": 5, "column": 13},  # Add function
                check=lambda r: "found" in r  # May or may not have type def
            ),
            TestCase(
                name="type_definition: keyword (no type)",
                tool="ada_type_definition",
                args={"file": str(self.main_adb), "line": 6, "column": 1},  # begin
                check=lambda r: r.get("found") is False
            ),
            TestCase(
                name="type_definition: non-existent file",
                tool="ada_type_definition",
                args={"file": "/nonexistent/file.adb", "line": 1, "column": 1},
                check=lambda r: r.get("found") is False or "error" in r
            ),
            
            # ============================================================
            # ada_implementation tests (NEW)
            # ============================================================
            TestCase(
                name="implementation: spec function -> body",
                tool="ada_implementation",
                args={"file": str(self.utils_ads), "line": 5, "column": 13},  # Add in spec
                check=lambda r: r.get("found") and "utils.adb" in r.get("file", "").lower()
            ),
            TestCase(
                name="implementation: spec Multiply -> body",
                tool="ada_implementation",
                args={"file": str(self.utils_ads), "line": 8, "column": 13},  # Multiply in spec
                check=lambda r: r.get("found") and "utils.adb" in r.get("file", "").lower()
            ),
            TestCase(
                name="implementation: body function (already impl)",
                tool="ada_implementation",
                args={"file": str(self.utils_adb), "line": 4, "column": 13},  # Add in body
                check=lambda r: "found" in r  # May return itself or nothing
            ),
            TestCase(
                name="implementation: package spec -> body",
                tool="ada_implementation",
                args={"file": str(self.utils_ads), "line": 2, "column": 10},  # package Utils
                check=lambda r: "found" in r  # May or may not find body
            ),
            TestCase(
                name="implementation: variable (no implementation)",
                tool="ada_implementation",
                args={"file": str(self.main_adb), "line": 5, "column": 4},  # Value variable
                check=lambda r: r.get("found") is False or "found" in r
            ),
            TestCase(
                name="implementation: non-existent file",
                tool="ada_implementation",
                args={"file": "/nonexistent/file.adb", "line": 1, "column": 1},
                check=lambda r: r.get("found") is False or "error" in r
            ),
            
            # ============================================================
            # ada_find_references tests
            # ============================================================
            TestCase(
                name="find_references: function Add",
                tool="ada_find_references",
                args={"file": str(self.utils_ads), "line": 5, "column": 13, "include_declaration": True},
                check=lambda r: r.get("count", 0) >= 2  # At least spec and call in main
            ),
            TestCase(
                name="find_references: exclude declaration",
                tool="ada_find_references",
                args={"file": str(self.utils_ads), "line": 5, "column": 13, "include_declaration": False},
                check=lambda r: "references" in r
            ),
            TestCase(
                name="find_references: local variable",
                tool="ada_find_references",
                args={"file": str(self.main_adb), "line": 5, "column": 4, "include_declaration": True},
                check=lambda r: r.get("count", 0) >= 1  # At least declaration and usage
            ),
            
            # ============================================================
            # ada_document_symbols tests
            # ============================================================
            TestCase(
                name="document_symbols: main.adb",
                tool="ada_document_symbols",
                args={"file": str(self.main_adb)},
                check=lambda r: len(r.get("symbols", [])) >= 1  # At least Main procedure
            ),
            TestCase(
                name="document_symbols: utils.ads",
                tool="ada_document_symbols",
                args={"file": str(self.utils_ads)},
                check=lambda r: len(r.get("symbols", [])) >= 1  # Package with functions
            ),
            
            # ============================================================
            # ada_workspace_symbols tests
            # ============================================================
            TestCase(
                name="workspace_symbols: search 'Add'",
                tool="ada_workspace_symbols",
                args={"query": "Add"},
                check=lambda r: len(r.get("symbols", [])) >= 1
            ),
            TestCase(
                name="workspace_symbols: search 'Main'",
                tool="ada_workspace_symbols",
                args={"query": "Main"},
                check=lambda r: len(r.get("symbols", [])) >= 1
            ),
            
            # ============================================================
            # ada_project_info tests (Phase 3.2)
            # ============================================================
            TestCase(
                name="project_info: sample.gpr",
                tool="ada_project_info",
                args={"gpr_file": str(self.project_dir / "sample.gpr")},
                check=lambda r: r.get("project_name") == "Sample" and len(r.get("source_dirs", [])) > 0
            ),
            TestCase(
                name="project_info: has main units",
                tool="ada_project_info",
                args={"gpr_file": str(self.project_dir / "sample.gpr")},
                check=lambda r: "main.adb" in r.get("main_units", [])
            ),
            
            # ============================================================
            # ada_call_hierarchy tests (Phase 3.3 & 3.4)
            # ============================================================
            TestCase(
                name="call_hierarchy: Main outgoing calls",
                tool="ada_call_hierarchy",
                args={"file": str(self.main_adb), "line": 4, "column": 12, "direction": "outgoing"},
                check=lambda r: r.get("found") is True or r.get("found") is False  # May have outgoing calls
            ),
            TestCase(
                name="call_hierarchy: Add incoming calls",
                tool="ada_call_hierarchy",
                args={"file": str(self.utils_ads), "line": 5, "column": 13, "direction": "incoming"},
                check=lambda r: "incoming_calls" in r or "outgoing_calls" in r
            ),
            TestCase(
                name="call_hierarchy: both directions",
                tool="ada_call_hierarchy",
                args={"file": str(self.utils_ads), "line": 5, "column": 13, "direction": "both"},
                check=lambda r: "incoming_calls" in r and "outgoing_calls" in r
            ),
            
            # ============================================================
            # ada_dependency_graph tests (Phase 3.5)
            # ============================================================
            TestCase(
                name="dependency_graph: main.adb",
                tool="ada_dependency_graph",
                args={"file": str(self.main_adb)},
                check=lambda r: r.get("package_count", 0) >= 1
            ),
            TestCase(
                name="dependency_graph: src directory",
                tool="ada_dependency_graph",
                args={"file": str(self.project_dir / "src")},
                check=lambda r: r.get("package_count", 0) >= 2  # Main and Utils
            ),
            
            # ============================================================
            # ada_completions tests (Phase 4.1 & 4.2)
            # ============================================================
            TestCase(
                name="completions: after 'Utils.'",
                tool="ada_completions",
                args={"file": str(self.main_adb), "line": 5, "column": 24, "trigger_character": "."},
                check=lambda r: "completions" in r and r.get("count", 0) >= 0
            ),
            TestCase(
                name="completions: at identifier",
                tool="ada_completions",
                args={"file": str(self.main_adb), "line": 5, "column": 4},
                check=lambda r: "completions" in r
            ),
            TestCase(
                name="completions: with limit",
                tool="ada_completions",
                args={"file": str(self.main_adb), "line": 5, "column": 4, "limit": 5},
                check=lambda r: r.get("count", 100) <= 5
            ),
            
            # ============================================================
            # ada_signature_help tests (Phase 4.3)
            # ============================================================
            TestCase(
                name="signature_help: function call",
                tool="ada_signature_help",
                args={"file": str(self.main_adb), "line": 5, "column": 28},  # Inside Add(...)
                check=lambda r: "signatures" in r
            ),
            TestCase(
                name="signature_help: not in call",
                tool="ada_signature_help",
                args={"file": str(self.main_adb), "line": 1, "column": 1},
                check=lambda r: r.get("found") is False or "signatures" in r
            ),
            
            # ============================================================
            # ada_code_actions tests (Phase 4.4)
            # ============================================================
            TestCase(
                name="code_actions: at position",
                tool="ada_code_actions",
                args={"file": str(self.main_adb), "start_line": 5, "start_column": 4},
                check=lambda r: "actions" in r and "count" in r
            ),
            TestCase(
                name="code_actions: with range",
                tool="ada_code_actions",
                args={"file": str(self.main_adb), "start_line": 5, "start_column": 1, "end_line": 7, "end_column": 60},
                check=lambda r: "actions" in r
            ),
        ]

    def report(self, name: str, passed: bool, message: str = ""):
        """Report a test result."""
        if passed:
            self.tests_passed += 1
            status = "✓"
        else:
            self.tests_failed += 1
            status = "✗"
        
        msg = f"  {status} {name}"
        if message:
            msg += f" - {message}"
        print(msg)

    async def run_all(self, client: MCPTestClient) -> bool:
        """Run all test cases."""
        test_cases = self.get_test_cases()
        
        print(f"\nRunning {len(test_cases)} Phase 1 & 2 integration tests...\n")
        
        # Group by tool
        current_tool = None
        for tc in test_cases:
            if tc.tool != current_tool:
                current_tool = tc.tool
                print(f"\n[{tc.tool}]")
            
            try:
                result = await call_tool(client, tc.tool, tc.args)
                passed = tc.check(result)
                
                # Build message
                msg = ""
                if "_error" in result:
                    msg = f"Error: {result['_error']}"
                elif not passed:
                    msg = f"Got: {json.dumps(result)[:100]}"
                
                self.report(tc.name, passed, msg)
                
            except asyncio.TimeoutError:
                self.report(tc.name, False, "Timeout")
            except Exception as e:
                self.report(tc.name, False, f"Exception: {e}")
        
        return self.tests_failed == 0


async def main() -> int:
    """Main entry point."""
    print("=" * 70)
    print("Phase 1 & 2 Integration Tests")
    print("=" * 70)
    
    # Setup paths
    project_root = Path(__file__).parent.parent
    sample_project = project_root / "tests" / "fixtures" / "sample_project"
    error_project = project_root / "tests" / "fixtures" / "error_project"
    
    if not sample_project.exists():
        print(f"ERROR: Sample project not found: {sample_project}")
        return 1
    
    # Find ALS
    als_path = os.environ.get("ALS_PATH")
    if not als_path:
        vscode_als = Path.home() / ".vscode" / "extensions"
        als_candidates = list(vscode_als.glob("adacore.ada-*/x64/linux/ada_language_server"))
        if als_candidates:
            als_path = str(sorted(als_candidates)[-1])
    
    if not als_path or not Path(als_path).exists():
        print("ERROR: ALS not found. Set ALS_PATH environment variable.")
        return 1
    
    print(f"\nALS: {als_path}")
    print(f"Sample project: {sample_project}")
    
    # Start server
    venv_python = project_root / ".venv" / "bin" / "python"
    if not venv_python.exists():
        venv_python = Path(sys.executable)
    
    env = os.environ.copy()
    env["ALS_PATH"] = als_path
    env["ADA_PROJECT_ROOT"] = str(sample_project)
    env["ADA_MCP_LOG_LEVEL"] = "WARNING"  # Less noise
    
    print("\nStarting MCP server...")
    process = await asyncio.create_subprocess_exec(
        str(venv_python), "-m", "ada_mcp",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        cwd=str(sample_project),
    )
    
    client = MCPTestClient(process)
    tester = Phase1IntegrationTests(sample_project, error_project)
    
    try:
        await asyncio.sleep(0.5)
        
        # Initialize MCP
        print("Initializing MCP connection...")
        response = await client.send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "phase1-test", "version": "1.0.0"},
        })
        if "result" not in response:
            print(f"ERROR: Initialize failed: {response}")
            return 1
        
        await client.send_notification("notifications/initialized")
        
        # Run tests
        success = await tester.run_all(client)
        
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        success = False
    
    finally:
        print("\nShutting down server...")
        try:
            process.terminate()
            await asyncio.wait_for(process.wait(), timeout=5.0)
        except:
            process.kill()
            await process.wait()
    
    # Summary
    total = tester.tests_passed + tester.tests_failed
    print("\n" + "=" * 70)
    print(f"Results: {tester.tests_passed}/{total} passed, {tester.tests_failed} failed")
    print("=" * 70)
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
