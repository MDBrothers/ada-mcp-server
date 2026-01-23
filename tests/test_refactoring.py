"""Unit tests for Phase 4 & 5: Code Intelligence and Refactoring tools."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from ada_mcp.tools.refactoring import (
    _is_valid_ada_identifier,
    handle_code_actions,
    handle_completions,
    handle_format_file,
    handle_get_spec,
    handle_rename_symbol,
    handle_signature_help,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_als_client():
    """Create a mock ALS client."""
    client = AsyncMock()
    client.send_request = AsyncMock()
    return client


@pytest.fixture
def sample_ada_file():
    """Path to sample Ada file."""
    return Path(__file__).parent / "fixtures" / "sample_project" / "src" / "main.adb"


# ============================================================================
# ada_completions Tests (Tasks 4.1 & 4.2)
# ============================================================================


class TestCompletions:
    """Tests for ada_completions tool."""

    @pytest.mark.asyncio
    async def test_completions_basic(self, mock_als_client):
        """Test basic completion request."""
        mock_als_client.send_request.return_value = {
            "isIncomplete": False,
            "items": [
                {"label": "Add", "kind": 3, "detail": "function"},
                {"label": "Multiply", "kind": 3, "detail": "function"},
            ],
        }

        result = await handle_completions(
            mock_als_client,
            "/test/main.adb",
            line=5,
            column=10,
        )

        assert result["count"] == 2
        assert result["is_incomplete"] is False
        assert result["completions"][0]["label"] == "Add"
        assert result["completions"][0]["kind"] == "Function"

    @pytest.mark.asyncio
    async def test_completions_with_trigger(self, mock_als_client):
        """Test completion with trigger character."""
        mock_als_client.send_request.return_value = {
            "isIncomplete": False,
            "items": [
                {"label": "Text_IO", "kind": 9, "detail": "package"},
            ],
        }

        result = await handle_completions(
            mock_als_client,
            "/test/main.adb",
            line=1,
            column=6,
            trigger_character=".",
        )

        # Check that trigger was passed correctly
        call_args = mock_als_client.send_request.call_args
        assert call_args[0][1]["context"]["triggerKind"] == 2
        assert call_args[0][1]["context"]["triggerCharacter"] == "."

        assert result["count"] == 1
        assert result["completions"][0]["label"] == "Text_IO"

    @pytest.mark.asyncio
    async def test_completions_empty(self, mock_als_client):
        """Test empty completion response."""
        mock_als_client.send_request.return_value = None

        result = await handle_completions(
            mock_als_client,
            "/test/main.adb",
            line=1,
            column=1,
        )

        assert result["count"] == 0
        assert result["completions"] == []
        assert result["is_incomplete"] is False

    @pytest.mark.asyncio
    async def test_completions_list_response(self, mock_als_client):
        """Test completion returning array instead of CompletionList."""
        mock_als_client.send_request.return_value = [
            {"label": "Integer", "kind": 7},
            {"label": "Float", "kind": 7},
        ]

        result = await handle_completions(
            mock_als_client,
            "/test/main.adb",
            line=5,
            column=12,
        )

        assert result["count"] == 2
        assert result["completions"][0]["kind"] == "Class"

    @pytest.mark.asyncio
    async def test_completions_with_documentation(self, mock_als_client):
        """Test completion with documentation."""
        mock_als_client.send_request.return_value = {
            "isIncomplete": False,
            "items": [
                {
                    "label": "Put_Line",
                    "kind": 3,
                    "detail": "procedure",
                    "documentation": {"kind": "markdown", "value": "Outputs text to stdout"},
                }
            ],
        }

        result = await handle_completions(
            mock_als_client,
            "/test/main.adb",
            line=6,
            column=15,
        )

        assert result["completions"][0]["documentation"] == "Outputs text to stdout"

    @pytest.mark.asyncio
    async def test_completions_limit(self, mock_als_client):
        """Test completion limit."""
        mock_als_client.send_request.return_value = {
            "isIncomplete": True,
            "items": [{"label": f"Item{i}", "kind": 6} for i in range(100)],
        }

        result = await handle_completions(
            mock_als_client,
            "/test/main.adb",
            line=5,
            column=10,
            limit=10,
        )

        assert result["count"] == 10
        assert result["is_incomplete"] is True


# ============================================================================
# ada_signature_help Tests (Task 4.3)
# ============================================================================


class TestSignatureHelp:
    """Tests for ada_signature_help tool."""

    @pytest.mark.asyncio
    async def test_signature_help_basic(self, mock_als_client):
        """Test basic signature help."""
        mock_als_client.send_request.return_value = {
            "signatures": [
                {
                    "label": "Add (A : Integer; B : Integer) return Integer",
                    "parameters": [
                        {"label": "A : Integer"},
                        {"label": "B : Integer"},
                    ],
                }
            ],
            "activeSignature": 0,
            "activeParameter": 0,
        }

        result = await handle_signature_help(
            mock_als_client,
            "/test/main.adb",
            line=5,
            column=20,
        )

        assert result["found"] is True
        assert len(result["signatures"]) == 1
        assert "Add" in result["signatures"][0]["label"]
        assert len(result["signatures"][0]["parameters"]) == 2
        assert result["active_parameter"] == 0

    @pytest.mark.asyncio
    async def test_signature_help_second_param(self, mock_als_client):
        """Test signature help with second parameter active."""
        mock_als_client.send_request.return_value = {
            "signatures": [
                {
                    "label": "Add (A : Integer; B : Integer) return Integer",
                    "parameters": [
                        {"label": "A : Integer"},
                        {"label": "B : Integer"},
                    ],
                }
            ],
            "activeSignature": 0,
            "activeParameter": 1,
        }

        result = await handle_signature_help(
            mock_als_client,
            "/test/main.adb",
            line=5,
            column=25,
        )

        assert result["found"] is True
        assert result["active_parameter"] == 1

    @pytest.mark.asyncio
    async def test_signature_help_not_found(self, mock_als_client):
        """Test signature help when not in function call."""
        mock_als_client.send_request.return_value = None

        result = await handle_signature_help(
            mock_als_client,
            "/test/main.adb",
            line=1,
            column=1,
        )

        assert result["found"] is False
        assert result["signatures"] == []

    @pytest.mark.asyncio
    async def test_signature_help_with_documentation(self, mock_als_client):
        """Test signature help with parameter documentation."""
        mock_als_client.send_request.return_value = {
            "signatures": [
                {
                    "label": "Put_Line (Item : String)",
                    "documentation": "Outputs a line to stdout",
                    "parameters": [
                        {
                            "label": "Item : String",
                            "documentation": "The text to output",
                        }
                    ],
                }
            ],
            "activeSignature": 0,
            "activeParameter": 0,
        }

        result = await handle_signature_help(
            mock_als_client,
            "/test/main.adb",
            line=7,
            column=20,
        )

        assert result["signatures"][0]["documentation"] == "Outputs a line to stdout"
        assert result["signatures"][0]["parameters"][0]["documentation"] == "The text to output"

    @pytest.mark.asyncio
    async def test_signature_help_multiple_overloads(self, mock_als_client):
        """Test signature help with multiple overloaded signatures."""
        mock_als_client.send_request.return_value = {
            "signatures": [
                {"label": "Put (Item : Integer)", "parameters": [{"label": "Item : Integer"}]},
                {"label": "Put (Item : String)", "parameters": [{"label": "Item : String"}]},
                {"label": "Put (Item : Float)", "parameters": [{"label": "Item : Float"}]},
            ],
            "activeSignature": 1,
            "activeParameter": 0,
        }

        result = await handle_signature_help(
            mock_als_client,
            "/test/main.adb",
            line=7,
            column=10,
        )

        assert result["found"] is True
        assert len(result["signatures"]) == 3
        assert result["active_signature"] == 1


# ============================================================================
# ada_code_actions Tests (Task 4.4)
# ============================================================================


class TestCodeActions:
    """Tests for ada_code_actions tool."""

    @pytest.mark.asyncio
    async def test_code_actions_basic(self, mock_als_client):
        """Test basic code actions request."""
        mock_als_client.send_request.return_value = [
            {
                "title": "Add missing 'with' clause",
                "kind": "quickfix",
                "isPreferred": True,
                "edit": {
                    "changes": {
                        "file:///test/main.adb": [{"range": {}, "newText": "with Utils;\n"}]
                    }
                },
            }
        ]

        result = await handle_code_actions(
            mock_als_client,
            "/test/main.adb",
            start_line=5,
            start_column=1,
        )

        assert result["count"] == 1
        assert result["actions"][0]["title"] == "Add missing 'with' clause"
        assert result["actions"][0]["kind"] == "quickfix"
        assert result["actions"][0]["is_preferred"] is True
        assert result["actions"][0]["has_edit"] is True

    @pytest.mark.asyncio
    async def test_code_actions_with_range(self, mock_als_client):
        """Test code actions with explicit range."""
        mock_als_client.send_request.return_value = [
            {"title": "Extract to procedure", "kind": "refactor.extract"}
        ]

        result = await handle_code_actions(
            mock_als_client,
            "/test/main.adb",
            start_line=5,
            start_column=1,
            end_line=10,
            end_column=20,
        )

        # Check that range was set correctly
        call_args = mock_als_client.send_request.call_args
        assert call_args[0][1]["range"]["start"]["line"] == 4  # 0-based
        assert call_args[0][1]["range"]["end"]["line"] == 9  # 0-based

        assert result["count"] == 1

    @pytest.mark.asyncio
    async def test_code_actions_empty(self, mock_als_client):
        """Test empty code actions response."""
        mock_als_client.send_request.return_value = []

        result = await handle_code_actions(
            mock_als_client,
            "/test/main.adb",
            start_line=1,
            start_column=1,
        )

        assert result["count"] == 0
        assert result["actions"] == []

    @pytest.mark.asyncio
    async def test_code_actions_with_command(self, mock_als_client):
        """Test code action with command."""
        mock_als_client.send_request.return_value = [
            {
                "title": "Organize imports",
                "kind": "source.organizeImports",
                "command": {
                    "title": "Organize Imports",
                    "command": "ada.organizeImports",
                    "arguments": [],
                },
            }
        ]

        result = await handle_code_actions(
            mock_als_client,
            "/test/main.adb",
            start_line=1,
            start_column=1,
        )

        assert result["actions"][0]["command"] == "Organize Imports"
        assert result["actions"][0]["has_edit"] is False

    @pytest.mark.asyncio
    async def test_code_actions_multiple_files(self, mock_als_client):
        """Test code action affecting multiple files."""
        mock_als_client.send_request.return_value = [
            {
                "title": "Rename symbol",
                "kind": "refactor.rename",
                "edit": {
                    "changes": {
                        "file:///test/main.adb": [{"range": {}, "newText": "NewName"}],
                        "file:///test/utils.ads": [{"range": {}, "newText": "NewName"}],
                        "file:///test/utils.adb": [{"range": {}, "newText": "NewName"}],
                    }
                },
            }
        ]

        result = await handle_code_actions(
            mock_als_client,
            "/test/main.adb",
            start_line=5,
            start_column=10,
        )

        assert result["actions"][0]["files_affected"] == 3

    @pytest.mark.asyncio
    async def test_code_actions_null_response(self, mock_als_client):
        """Test null code actions response."""
        mock_als_client.send_request.return_value = None

        result = await handle_code_actions(
            mock_als_client,
            "/test/main.adb",
            start_line=1,
            start_column=1,
        )

        assert result["count"] == 0
        assert result["actions"] == []


# ============================================================================
# Phase 5: Refactoring Tests
# ============================================================================


class TestAdaIdentifierValidation:
    """Tests for Ada identifier validation."""

    def test_valid_simple_identifier(self):
        """Test valid simple identifiers."""
        assert _is_valid_ada_identifier("Name")
        assert _is_valid_ada_identifier("x")
        assert _is_valid_ada_identifier("Count")
        assert _is_valid_ada_identifier("My_Variable")

    def test_valid_identifier_with_numbers(self):
        """Test valid identifiers with numbers."""
        assert _is_valid_ada_identifier("Item1")
        assert _is_valid_ada_identifier("Value123")
        assert _is_valid_ada_identifier("V2_Test")

    def test_invalid_empty(self):
        """Test empty string is invalid."""
        assert not _is_valid_ada_identifier("")

    def test_invalid_starts_with_number(self):
        """Test identifiers starting with number are invalid."""
        assert not _is_valid_ada_identifier("1Name")
        assert not _is_valid_ada_identifier("123")

    def test_invalid_starts_with_underscore(self):
        """Test identifiers starting with underscore are invalid."""
        assert not _is_valid_ada_identifier("_Name")

    def test_invalid_consecutive_underscores(self):
        """Test consecutive underscores are invalid."""
        assert not _is_valid_ada_identifier("My__Name")

    def test_invalid_ends_with_underscore(self):
        """Test identifiers ending with underscore are invalid."""
        assert not _is_valid_ada_identifier("Name_")

    def test_invalid_special_characters(self):
        """Test special characters are invalid."""
        assert not _is_valid_ada_identifier("Name$")
        assert not _is_valid_ada_identifier("My-Name")
        assert not _is_valid_ada_identifier("Name.Value")


class TestRenameSymbol:
    """Tests for ada_rename_symbol tool."""

    @pytest.mark.asyncio
    async def test_rename_basic(self, mock_als_client):
        """Test basic rename operation."""
        # Setup mock responses
        mock_als_client.send_request.side_effect = [
            # prepareRename response
            {"placeholder": "Old_Name"},
            # rename response
            {
                "changes": {
                    "file:///test/main.adb": [
                        {
                            "range": {
                                "start": {"line": 4, "character": 10},
                                "end": {"line": 4, "character": 18},
                            },
                            "newText": "New_Name",
                        }
                    ],
                    "file:///test/utils.ads": [
                        {
                            "range": {
                                "start": {"line": 2, "character": 4},
                                "end": {"line": 2, "character": 12},
                            },
                            "newText": "New_Name",
                        }
                    ],
                }
            },
        ]

        result = await handle_rename_symbol(
            mock_als_client,
            "/test/main.adb",
            line=5,
            column=11,
            new_name="New_Name",
        )

        assert result["success"] is True
        assert result["new_name"] == "New_Name"
        assert result["total_changes"] == 2
        assert result["files_affected"] == 2

    @pytest.mark.asyncio
    async def test_rename_invalid_identifier(self, mock_als_client):
        """Test rename with invalid Ada identifier."""
        result = await handle_rename_symbol(
            mock_als_client,
            "/test/main.adb",
            line=5,
            column=10,
            new_name="123Invalid",
        )

        assert result["success"] is False
        assert "Invalid Ada identifier" in result["error"]
        # ALS should not be called
        mock_als_client.send_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_rename_cannot_rename(self, mock_als_client):
        """Test rename when symbol cannot be renamed."""
        mock_als_client.send_request.return_value = None

        result = await handle_rename_symbol(
            mock_als_client,
            "/test/main.adb",
            line=5,
            column=10,
            new_name="New_Name",
        )

        assert result["success"] is False
        assert "Cannot rename" in result["error"]

    @pytest.mark.asyncio
    async def test_rename_with_document_changes(self, mock_als_client):
        """Test rename with documentChanges format."""
        mock_als_client.send_request.side_effect = [
            {"placeholder": "Old_Name"},
            {
                "documentChanges": [
                    {
                        "textDocument": {"uri": "file:///test/main.adb", "version": 1},
                        "edits": [
                            {
                                "range": {
                                    "start": {"line": 4, "character": 10},
                                    "end": {"line": 4, "character": 18},
                                },
                                "newText": "New_Name",
                            }
                        ],
                    }
                ]
            },
        ]

        result = await handle_rename_symbol(
            mock_als_client,
            "/test/main.adb",
            line=5,
            column=11,
            new_name="New_Name",
        )

        assert result["success"] is True
        assert result["total_changes"] == 1


class TestFormatFile:
    """Tests for ada_format_file tool."""

    @pytest.mark.asyncio
    async def test_format_basic(self, mock_als_client):
        """Test basic format operation."""
        mock_als_client.send_request.return_value = [
            {
                "range": {
                    "start": {"line": 0, "character": 0},
                    "end": {"line": 0, "character": 10},
                },
                "newText": "procedure ",
            },
            {
                "range": {"start": {"line": 2, "character": 0}, "end": {"line": 2, "character": 3}},
                "newText": "   ",
            },
        ]

        result = await handle_format_file(
            mock_als_client,
            "/test/main.adb",
        )

        assert result["formatted"] is True
        assert result["changes"] == 2
        assert len(result["edits"]) == 2

    @pytest.mark.asyncio
    async def test_format_no_changes(self, mock_als_client):
        """Test format when file is already formatted."""
        mock_als_client.send_request.return_value = []

        result = await handle_format_file(
            mock_als_client,
            "/test/main.adb",
        )

        assert result["formatted"] is True
        assert result["changes"] == 0

    @pytest.mark.asyncio
    async def test_format_null_response(self, mock_als_client):
        """Test format with null response."""
        mock_als_client.send_request.return_value = None

        result = await handle_format_file(
            mock_als_client,
            "/test/main.adb",
        )

        assert result["formatted"] is False
        assert result["changes"] == 0

    @pytest.mark.asyncio
    async def test_format_custom_options(self, mock_als_client):
        """Test format with custom tab size."""
        mock_als_client.send_request.return_value = []

        await handle_format_file(
            mock_als_client,
            "/test/main.adb",
            tab_size=4,
            insert_spaces=False,
        )

        call_args = mock_als_client.send_request.call_args
        assert call_args[0][1]["options"]["tabSize"] == 4
        assert call_args[0][1]["options"]["insertSpaces"] is False


class TestGetSpec:
    """Tests for ada_get_spec tool."""

    @pytest.mark.asyncio
    async def test_get_spec_with_position(self, mock_als_client, tmp_path):
        """Test get spec with position using LSP."""
        spec_file = tmp_path / "utils.ads"
        spec_file.write_text("package Utils is\n   procedure Do_Something;\nend Utils;")

        mock_als_client.send_request.return_value = {
            "uri": f"file://{spec_file}",
            "range": {"start": {"line": 1, "character": 3}, "end": {"line": 1, "character": 15}},
        }

        body_file = tmp_path / "utils.adb"

        result = await handle_get_spec(
            mock_als_client,
            str(body_file),
            line=5,
            column=10,
        )

        assert result["found"] is True
        assert result["line"] == 2
        assert result["column"] == 4

    @pytest.mark.asyncio
    async def test_get_spec_file_fallback(self, mock_als_client, tmp_path):
        """Test get spec fallback to file-based lookup."""
        spec_file = tmp_path / "utils.ads"
        spec_file.write_text("package Utils is\n   procedure Test;\nend Utils;")
        body_file = tmp_path / "utils.adb"
        body_file.write_text("package body Utils is\nend Utils;")

        mock_als_client.send_request.return_value = None

        result = await handle_get_spec(
            mock_als_client,
            str(body_file),
            line=1,
            column=1,
        )

        assert result["found"] is True
        assert result["spec_file"] == str(spec_file)
        assert "package Utils" in result["preview"]

    @pytest.mark.asyncio
    async def test_get_spec_no_position(self, mock_als_client, tmp_path):
        """Test get spec without position - just file lookup."""
        spec_file = tmp_path / "main.ads"
        spec_file.write_text("-- Main spec\npackage Main is\nend Main;")
        body_file = tmp_path / "main.adb"
        body_file.write_text("package body Main is\nend Main;")

        result = await handle_get_spec(
            mock_als_client,
            str(body_file),
        )

        assert result["found"] is True
        assert result["spec_file"] == str(spec_file)
        assert result["preview"] == "package Main is"  # First non-comment line

    @pytest.mark.asyncio
    async def test_get_spec_not_found(self, mock_als_client, tmp_path):
        """Test get spec when no spec exists."""
        body_file = tmp_path / "main.adb"
        body_file.write_text("procedure Main is\nbegin\n   null;\nend Main;")

        mock_als_client.send_request.return_value = None

        result = await handle_get_spec(
            mock_als_client,
            str(body_file),
        )

        assert result["found"] is False
        assert "No spec file found" in result.get("error", "")
