"""Pytest configuration and fixtures for Ada MCP Server tests."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the path to the test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def mock_als_client() -> AsyncMock:
    """Create a mock ALS client for unit tests."""
    client = AsyncMock()
    client.send_request = AsyncMock()
    client.send_notification = AsyncMock()
    return client


@pytest.fixture
def sample_ada_file(tmp_path: Path) -> Path:
    """Create a sample Ada file for testing."""
    ada_file = tmp_path / "test.adb"
    ada_file.write_text("""\
with Ada.Text_IO;

procedure Test is
   X : Integer := 42;
begin
   Ada.Text_IO.Put_Line ("Hello, Ada!");
end Test;
""")
    return ada_file
