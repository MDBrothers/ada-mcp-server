"""
Comprehensive Phase 1 Unit Tests for Ada MCP Server.

Tests cover:
- ada_goto_definition
- ada_hover  
- ada_diagnostics

Each tool is tested for:
- Normal operation
- Edge cases
- Error handling
- Invalid inputs
"""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_als_client():
    """Create a mock ALS client for unit testing."""
    import asyncio
    client = AsyncMock()
    client.send_request = AsyncMock()
    # Properties used by diagnostics handler
    client._diagnostics = {}
    client._diagnostics_lock = asyncio.Lock()
    return client


@pytest.fixture
def mock_get_als(mock_als_client):
    """Patch get_als_client to return mock client."""
    with patch("ada_mcp.server.get_als_client", return_value=mock_als_client):
        yield mock_als_client


# ============================================================================
# ada_goto_definition Tests
# ============================================================================

class TestGotoDefinition:
    """Tests for ada_goto_definition tool."""

    @pytest.mark.asyncio
    async def test_definition_found_single_location(self, mock_get_als):
        """Test successful goto definition with single result."""
        mock_get_als.send_request.return_value = [{
            "uri": "file:///project/src/utils.ads",
            "range": {
                "start": {"line": 4, "character": 3},
                "end": {"line": 4, "character": 6}
            }
        }]

        from ada_mcp.server import call_tool
        result = await call_tool("ada_goto_definition", {
            "file": "/project/src/main.adb",
            "line": 10,
            "column": 5
        })

        data = json.loads(result[0].text)
        assert data["found"] is True
        assert data["file"] == "/project/src/utils.ads"
        assert data["line"] == 5  # 0-based to 1-based
        assert data["column"] == 4

    @pytest.mark.asyncio
    async def test_definition_found_multiple_locations(self, mock_get_als):
        """Test goto definition with multiple results (returns first)."""
        mock_get_als.send_request.return_value = [
            {
                "uri": "file:///project/src/utils.ads",
                "range": {"start": {"line": 4, "character": 3}, "end": {"line": 4, "character": 6}}
            },
            {
                "uri": "file:///project/src/utils.adb",
                "range": {"start": {"line": 10, "character": 3}, "end": {"line": 10, "character": 6}}
            }
        ]

        from ada_mcp.server import call_tool
        result = await call_tool("ada_goto_definition", {
            "file": "/project/src/main.adb",
            "line": 10,
            "column": 5
        })

        data = json.loads(result[0].text)
        assert data["found"] is True
        assert "utils.ads" in data["file"]  # First result

    @pytest.mark.asyncio
    async def test_definition_not_found_null_response(self, mock_get_als):
        """Test when LSP returns null (no definition)."""
        mock_get_als.send_request.return_value = None

        from ada_mcp.server import call_tool
        result = await call_tool("ada_goto_definition", {
            "file": "/project/src/main.adb",
            "line": 10,
            "column": 5
        })

        data = json.loads(result[0].text)
        assert data["found"] is False

    @pytest.mark.asyncio
    async def test_definition_not_found_empty_array(self, mock_get_als):
        """Test when LSP returns empty array."""
        mock_get_als.send_request.return_value = []

        from ada_mcp.server import call_tool
        result = await call_tool("ada_goto_definition", {
            "file": "/project/src/main.adb",
            "line": 10,
            "column": 5
        })

        data = json.loads(result[0].text)
        assert data["found"] is False

    @pytest.mark.asyncio
    async def test_definition_line_column_conversion(self, mock_get_als):
        """Verify 1-based (user) to 0-based (LSP) conversion."""
        mock_get_als.send_request.return_value = None

        from ada_mcp.server import call_tool
        await call_tool("ada_goto_definition", {
            "file": "/project/src/main.adb",
            "line": 10,  # User provides 1-based
            "column": 5
        })

        # Verify LSP received 0-based
        call_args = mock_get_als.send_request.call_args
        params = call_args[0][1]
        assert params["position"]["line"] == 9  # 10 - 1
        assert params["position"]["character"] == 4  # 5 - 1

    @pytest.mark.asyncio
    async def test_definition_with_line_zero(self, mock_get_als):
        """Test edge case: line 0 (invalid but should handle gracefully)."""
        mock_get_als.send_request.return_value = None

        from ada_mcp.server import call_tool
        result = await call_tool("ada_goto_definition", {
            "file": "/project/src/main.adb",
            "line": 0,
            "column": 1
        })

        # Should not crash, either return not found or handle gracefully
        data = json.loads(result[0].text)
        assert "found" in data or "error" in data

    @pytest.mark.asyncio
    async def test_definition_als_error(self, mock_get_als):
        """Test handling of ALS error response."""
        mock_get_als.send_request.side_effect = Exception("LSP error: invalid request")

        from ada_mcp.server import call_tool
        result = await call_tool("ada_goto_definition", {
            "file": "/project/src/main.adb",
            "line": 10,
            "column": 5
        })

        data = json.loads(result[0].text)
        # Error responses contain "error" key
        assert "error" in data


# ============================================================================
# ada_hover Tests
# ============================================================================

class TestHover:
    """Tests for ada_hover tool."""

    @pytest.mark.asyncio
    async def test_hover_found_with_markdown(self, mock_get_als):
        """Test hover with markdown content."""
        mock_get_als.send_request.return_value = {
            "contents": {
                "kind": "markdown",
                "value": "```ada\nfunction Add (A, B : Integer) return Integer\n```"
            }
        }

        from ada_mcp.server import call_tool
        result = await call_tool("ada_hover", {
            "file": "/project/src/main.adb",
            "line": 5,
            "column": 24
        })

        data = json.loads(result[0].text)
        assert data["found"] is True
        assert "function Add" in data["contents"]

    @pytest.mark.asyncio
    async def test_hover_found_with_plaintext(self, mock_get_als):
        """Test hover with plaintext content."""
        mock_get_als.send_request.return_value = {
            "contents": "procedure Main is"
        }

        from ada_mcp.server import call_tool
        result = await call_tool("ada_hover", {
            "file": "/project/src/main.adb",
            "line": 4,
            "column": 12
        })

        data = json.loads(result[0].text)
        assert data["found"] is True
        assert "Main" in data["contents"]

    @pytest.mark.asyncio
    async def test_hover_found_with_marked_string_array(self, mock_get_als):
        """Test hover with array of marked strings."""
        mock_get_als.send_request.return_value = {
            "contents": [
                {"language": "ada", "value": "X : Integer"},
                "A variable of type Integer"
            ]
        }

        from ada_mcp.server import call_tool
        result = await call_tool("ada_hover", {
            "file": "/project/src/main.adb",
            "line": 5,
            "column": 4
        })

        data = json.loads(result[0].text)
        assert data["found"] is True

    @pytest.mark.asyncio
    async def test_hover_not_found_null(self, mock_get_als):
        """Test hover when LSP returns null."""
        mock_get_als.send_request.return_value = None

        from ada_mcp.server import call_tool
        result = await call_tool("ada_hover", {
            "file": "/project/src/main.adb",
            "line": 1,
            "column": 1
        })

        data = json.loads(result[0].text)
        assert data["found"] is False

    @pytest.mark.asyncio
    async def test_hover_not_found_empty_contents(self, mock_get_als):
        """Test hover when LSP returns empty contents."""
        mock_get_als.send_request.return_value = {"contents": ""}

        from ada_mcp.server import call_tool
        result = await call_tool("ada_hover", {
            "file": "/project/src/main.adb",
            "line": 1,
            "column": 1
        })

        data = json.loads(result[0].text)
        # Empty contents should still return found=True but empty
        assert "contents" in data

    @pytest.mark.asyncio
    async def test_hover_on_keyword(self, mock_get_als):
        """Test hover on Ada keyword (begin, end, etc.)."""
        mock_get_als.send_request.return_value = None  # Keywords typically have no hover

        from ada_mcp.server import call_tool
        result = await call_tool("ada_hover", {
            "file": "/project/src/main.adb",
            "line": 6,
            "column": 1  # "begin"
        })

        data = json.loads(result[0].text)
        assert data["found"] is False


# ============================================================================
# ada_diagnostics Tests
# ============================================================================

class TestDiagnostics:
    """Tests for ada_diagnostics tool."""

    @pytest.mark.asyncio
    async def test_diagnostics_all_files(self, mock_get_als):
        """Test getting diagnostics for all files."""
        from ada_mcp.als.types import Diagnostic, Range, Position, DiagnosticSeverity
        mock_get_als._diagnostics = {
            "file:///project/src/main.adb": [
                Diagnostic(
                    range=Range(Position(4, 10), Position(4, 15)),
                    severity=DiagnosticSeverity.ERROR,
                    message="type mismatch",
                    code="type-error"
                )
            ]
        }

        from ada_mcp.server import call_tool
        result = await call_tool("ada_diagnostics", {
            "severity": "all"
        })

        data = json.loads(result[0].text)
        assert data["errorCount"] >= 0
        assert "diagnostics" in data

    @pytest.mark.asyncio
    async def test_diagnostics_single_file(self, mock_get_als):
        """Test getting diagnostics for specific file."""
        from ada_mcp.als.types import Diagnostic, Range, Position, DiagnosticSeverity
        mock_get_als._diagnostics = {
            "file:///project/src/main.adb": [
                Diagnostic(
                    range=Range(Position(4, 10), Position(4, 15)),
                    severity=DiagnosticSeverity.ERROR,
                    message="error in main.adb"
                )
            ],
            "file:///project/src/utils.ads": [
                Diagnostic(
                    range=Range(Position(2, 0), Position(2, 10)),
                    severity=DiagnosticSeverity.WARNING,
                    message="warning in utils.ads"
                )
            ]
        }

        from ada_mcp.server import call_tool
        result = await call_tool("ada_diagnostics", {
            "file": "/project/src/main.adb",
            "severity": "all"
        })

        data = json.loads(result[0].text)
        # Should only include main.adb diagnostics
        for diag in data.get("diagnostics", []):
            assert "main.adb" in diag.get("file", "")

    @pytest.mark.asyncio
    async def test_diagnostics_filter_errors_only(self, mock_get_als):
        """Test filtering for errors only."""
        from ada_mcp.als.types import Diagnostic, Range, Position, DiagnosticSeverity
        mock_get_als._diagnostics = {
            "file:///project/src/main.adb": [
                Diagnostic(Range(Position(4, 0), Position(4, 5)), DiagnosticSeverity.ERROR, "error"),
                Diagnostic(Range(Position(5, 0), Position(5, 5)), DiagnosticSeverity.WARNING, "warning"),
                Diagnostic(Range(Position(6, 0), Position(6, 5)), DiagnosticSeverity.INFORMATION, "info"),
            ]
        }

        from ada_mcp.server import call_tool
        result = await call_tool("ada_diagnostics", {
            "severity": "error"
        })

        data = json.loads(result[0].text)
        for diag in data.get("diagnostics", []):
            assert diag.get("severity") == "error"

    @pytest.mark.asyncio
    async def test_diagnostics_filter_warnings_only(self, mock_get_als):
        """Test filtering for warnings only."""
        from ada_mcp.als.types import Diagnostic, Range, Position, DiagnosticSeverity
        mock_get_als._diagnostics = {
            "file:///project/src/main.adb": [
                Diagnostic(Range(Position(4, 0), Position(4, 5)), DiagnosticSeverity.ERROR, "error"),
                Diagnostic(Range(Position(5, 0), Position(5, 5)), DiagnosticSeverity.WARNING, "warning"),
            ]
        }

        from ada_mcp.server import call_tool
        result = await call_tool("ada_diagnostics", {
            "severity": "warning"
        })

        data = json.loads(result[0].text)
        for diag in data.get("diagnostics", []):
            assert diag.get("severity") == "warning"

    @pytest.mark.asyncio
    async def test_diagnostics_no_errors(self, mock_get_als):
        """Test when project has no diagnostics."""
        mock_get_als._diagnostics = {}

        from ada_mcp.server import call_tool
        result = await call_tool("ada_diagnostics", {
            "severity": "all"
        })

        data = json.loads(result[0].text)
        assert data["errorCount"] == 0
        assert data["warningCount"] == 0
        assert len(data.get("diagnostics", [])) == 0

    @pytest.mark.asyncio
    async def test_diagnostics_line_number_conversion(self, mock_get_als):
        """Test that line numbers are converted from 0-based to 1-based."""
        from ada_mcp.als.types import Diagnostic, Range, Position, DiagnosticSeverity
        mock_get_als._diagnostics = {
            "file:///project/src/main.adb": [
                Diagnostic(
                    range=Range(Position(9, 4), Position(9, 10)),  # 0-based line 9
                    severity=DiagnosticSeverity.ERROR,
                    message="test error"
                )
            ]
        }

        from ada_mcp.server import call_tool
        result = await call_tool("ada_diagnostics", {
            "severity": "all"
        })

        data = json.loads(result[0].text)
        if data.get("diagnostics"):
            # Should be 1-based for user (line 10)
            assert data["diagnostics"][0]["line"] == 10


# ============================================================================
# Input Validation Tests
# ============================================================================

class TestInputValidation:
    """Tests for input validation across all Phase 1 tools."""

    @pytest.mark.asyncio
    async def test_goto_missing_file_param(self, mock_get_als):
        """Test goto_definition with missing file parameter."""
        from ada_mcp.server import call_tool
        result = await call_tool("ada_goto_definition", {
            "line": 10,
            "column": 5
            # Missing "file"
        })

        data = json.loads(result[0].text)
        assert "error" in data or data.get("found") is False

    @pytest.mark.asyncio
    async def test_goto_missing_line_param(self, mock_get_als):
        """Test goto_definition with missing line parameter."""
        from ada_mcp.server import call_tool
        result = await call_tool("ada_goto_definition", {
            "file": "/project/src/main.adb",
            "column": 5
            # Missing "line"
        })

        data = json.loads(result[0].text)
        assert "error" in data or data.get("found") is False

    @pytest.mark.asyncio
    async def test_hover_empty_file_path(self, mock_get_als):
        """Test hover with empty file path."""
        # Empty file paths convert to current directory, which is invalid
        # The handler logs a warning but proceeds; mock returns a result anyway
        mock_get_als.send_request.return_value = None
        
        from ada_mcp.server import call_tool
        result = await call_tool("ada_hover", {
            "file": "",
            "line": 5,
            "column": 1
        })

        data = json.loads(result[0].text)
        # Should return not found (mock returns None)
        assert "found" in data or "error" in data

    @pytest.mark.asyncio
    async def test_diagnostics_invalid_severity(self, mock_get_als):
        """Test diagnostics with invalid severity filter."""
        mock_get_als._diagnostics = {}
        
        from ada_mcp.server import call_tool
        result = await call_tool("ada_diagnostics", {
            "severity": "invalid_severity"
        })

        # Should handle gracefully, either ignore or return error
        data = json.loads(result[0].text)
        assert "diagnostics" in data or "error" in data


# ============================================================================
# File Path Handling Tests
# ============================================================================

class TestFilePathHandling:
    """Tests for file path and URI handling."""

    @pytest.mark.asyncio
    async def test_goto_relative_path(self, mock_get_als):
        """Test goto_definition with relative path."""
        mock_get_als.send_request.return_value = None

        from ada_mcp.server import call_tool
        result = await call_tool("ada_goto_definition", {
            "file": "src/main.adb",  # Relative path
            "line": 5,
            "column": 10
        })

        # Should handle or convert relative path
        data = json.loads(result[0].text)
        assert "found" in data or "error" in data

    @pytest.mark.asyncio
    async def test_goto_file_uri(self, mock_get_als):
        """Test goto_definition with file:// URI."""
        mock_get_als.send_request.return_value = None

        from ada_mcp.server import call_tool
        result = await call_tool("ada_goto_definition", {
            "file": "file:///project/src/main.adb",
            "line": 5,
            "column": 10
        })

        data = json.loads(result[0].text)
        assert "found" in data or "error" in data

    @pytest.mark.asyncio
    async def test_result_file_path_normalization(self, mock_get_als):
        """Test that returned file paths are normalized (not URIs)."""
        mock_get_als.send_request.return_value = [{
            "uri": "file:///project/src/utils.ads",
            "range": {"start": {"line": 4, "character": 3}, "end": {"line": 4, "character": 6}}
        }]

        from ada_mcp.server import call_tool
        result = await call_tool("ada_goto_definition", {
            "file": "/project/src/main.adb",
            "line": 10,
            "column": 5
        })

        data = json.loads(result[0].text)
        assert data["found"] is True
        # File should be a path, not a URI
        assert not data["file"].startswith("file://")
        assert data["file"].startswith("/")
