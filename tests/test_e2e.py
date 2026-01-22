"""End-to-end integration tests for Ada MCP Server."""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
async def test_server_e2e():
    """Run end-to-end server test as a pytest test."""
    # Import here to avoid issues if script has missing deps
    import sys
    from pathlib import Path

    # Add scripts to path
    scripts_dir = Path(__file__).parent.parent / "scripts"
    sys.path.insert(0, str(scripts_dir))

    from test_server_e2e import run_tests

    success = await run_tests()
    assert success, "End-to-end tests failed"
