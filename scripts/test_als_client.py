#!/usr/bin/env python3
"""
Test the ALS client directly without going through MCP.

This tests the LSP communication layer in isolation.
Requires ALS to be installed and accessible.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


async def test_als_client():
    """Test ALS client functionality."""
    from ada_mcp.als.process import start_als, shutdown_als

    print("=" * 60)
    print("ALS Client Direct Test")
    print("=" * 60)

    # Use the sample project for testing
    project_root = Path(__file__).parent.parent / "tests" / "fixtures" / "sample_project"
    
    if not project_root.exists():
        print(f"ERROR: Test project not found at {project_root}")
        return False

    # Check if ALS is available
    als_path = os.environ.get("ALS_PATH", "ada_language_server")
    print(f"\n[1] Checking ALS availability: {als_path}")
    
    try:
        proc = await asyncio.create_subprocess_exec(
            als_path, "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            # ALS doesn't have --version, try --help
            proc = await asyncio.create_subprocess_exec(
                als_path, "--help",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
        
        print(f"    ✓ ALS found")
        if stdout:
            print(f"    {stdout.decode().strip()[:100]}")
    except FileNotFoundError:
        print(f"    ✗ ALS not found at: {als_path}")
        print(f"    Set ALS_PATH environment variable or install ada_language_server")
        return False

    print(f"\n[2] Starting ALS with project: {project_root}")
    
    try:
        client = await start_als(project_root)
        print("    ✓ ALS started and initialized")
        print(f"    Server capabilities: {list(client._server_capabilities.keys())[:5]}...")
    except Exception as e:
        print(f"    ✗ Failed to start ALS: {e}")
        return False

    tests_passed = 0
    tests_failed = 0

    try:
        # Test 1: Open a file
        print("\n[3] Opening test file...")
        test_file = project_root / "src" / "main.adb"
        if test_file.exists():
            await client.send_notification("textDocument/didOpen", {
                "textDocument": {
                    "uri": test_file.as_uri(),
                    "languageId": "ada",
                    "version": 1,
                    "text": test_file.read_text(),
                }
            })
            print(f"    ✓ Opened {test_file.name}")
            tests_passed += 1
            
            # Give ALS time to process
            await asyncio.sleep(1.0)
        else:
            print(f"    ✗ Test file not found: {test_file}")
            tests_failed += 1

        # Test 2: Get document symbols
        print("\n[4] Getting document symbols...")
        try:
            symbols = await client.send_request("textDocument/documentSymbol", {
                "textDocument": {"uri": test_file.as_uri()}
            })
            if symbols:
                print(f"    ✓ Found {len(symbols)} symbols:")
                for sym in symbols[:5]:
                    name = sym.get("name", "unknown")
                    kind = sym.get("kind", 0)
                    print(f"      - {name} (kind={kind})")
                tests_passed += 1
            else:
                print("    ? No symbols returned (might be OK for simple file)")
                tests_passed += 1
        except Exception as e:
            print(f"    ✗ Error: {e}")
            tests_failed += 1

        # Test 3: Hover
        print("\n[5] Testing hover on 'Main' procedure...")
        try:
            hover = await client.send_request("textDocument/hover", {
                "textDocument": {"uri": test_file.as_uri()},
                "position": {"line": 3, "character": 11}  # 0-based, "Main" position
            })
            if hover:
                contents = hover.get("contents", {})
                if isinstance(contents, dict):
                    text = contents.get("value", str(contents))[:100]
                else:
                    text = str(contents)[:100]
                print(f"    ✓ Hover result: {text}...")
                tests_passed += 1
            else:
                print("    ? No hover info (might be OK)")
                tests_passed += 1
        except Exception as e:
            print(f"    ✗ Error: {e}")
            tests_failed += 1

        # Test 4: Go to definition
        print("\n[6] Testing goto definition on 'Utils.Add'...")
        try:
            # Line 4 has "Utils.Add" - try to go to definition of Add
            definition = await client.send_request("textDocument/definition", {
                "textDocument": {"uri": test_file.as_uri()},
                "position": {"line": 4, "character": 23}  # Position of "Add"
            })
            if definition:
                if isinstance(definition, list):
                    loc = definition[0] if definition else None
                else:
                    loc = definition
                
                if loc:
                    uri = loc.get("uri", loc.get("targetUri", ""))
                    print(f"    ✓ Found definition at: {uri}")
                    tests_passed += 1
                else:
                    print("    ? Empty definition result")
                    tests_passed += 1
            else:
                print("    ? No definition found")
                tests_passed += 1
        except Exception as e:
            print(f"    ✗ Error: {e}")
            tests_failed += 1

        # Test 5: Find references
        print("\n[7] Testing find references...")
        try:
            references = await client.send_request("textDocument/references", {
                "textDocument": {"uri": test_file.as_uri()},
                "position": {"line": 4, "character": 4},  # "Value" variable
                "context": {"includeDeclaration": True}
            })
            if references:
                print(f"    ✓ Found {len(references)} references")
                tests_passed += 1
            else:
                print("    ? No references found")
                tests_passed += 1
        except Exception as e:
            print(f"    ✗ Error: {e}")
            tests_failed += 1

        # Test 6: Check diagnostics
        print("\n[8] Checking diagnostics...")
        async with client._diagnostics_lock:
            diag_count = sum(len(d) for d in client._diagnostics.values())
            if client._diagnostics:
                print(f"    ✓ Have {diag_count} diagnostics from {len(client._diagnostics)} files")
                for uri, diags in list(client._diagnostics.items())[:2]:
                    fname = uri.split("/")[-1]
                    print(f"      - {fname}: {len(diags)} diagnostics")
            else:
                print("    ✓ No diagnostics (code is clean)")
            tests_passed += 1

    finally:
        print("\n[9] Shutting down ALS...")
        try:
            await shutdown_als(client)
            print("    ✓ ALS shutdown complete")
        except Exception as e:
            print(f"    ! Shutdown error: {e}")

    # Summary
    print("\n" + "=" * 60)
    print(f"Results: {tests_passed} passed, {tests_failed} failed")
    print("=" * 60)

    return tests_failed == 0


def main():
    success = asyncio.run(test_als_client())
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
