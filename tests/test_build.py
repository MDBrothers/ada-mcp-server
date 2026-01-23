"""Unit tests for Phase 6: Build and Project Management tools."""

from unittest.mock import AsyncMock, patch

import pytest

from ada_mcp.tools.build import (
    _parse_gprbuild_output,
    handle_alire_info,
    handle_build,
)

# ============================================================================
# GPRbuild Output Parsing Tests
# ============================================================================


class TestGprbuildParsing:
    """Tests for GPRbuild output parsing."""

    def test_parse_error_line(self):
        """Test parsing a simple error line."""
        output = 'main.adb:10:5: error: missing ";"'
        result = _parse_gprbuild_output(output)

        assert len(result) == 1
        assert result[0]["file"] == "main.adb"
        assert result[0]["line"] == 10
        assert result[0]["column"] == 5
        assert result[0]["severity"] == "error"
        assert 'missing ";"' in result[0]["message"]

    def test_parse_warning_line(self):
        """Test parsing a warning line."""
        output = 'utils.ads:25:1: warning: variable "X" is never used'
        result = _parse_gprbuild_output(output)

        assert len(result) == 1
        assert result[0]["severity"] == "warning"
        assert "never used" in result[0]["message"]

    def test_parse_multiple_diagnostics(self):
        """Test parsing multiple diagnostics."""
        output = """main.adb:5:1: error: compilation unit expected
utils.adb:10:3: warning: unreferenced variable
main.adb:20:15: error: type mismatch"""
        result = _parse_gprbuild_output(output)

        assert len(result) == 3
        assert result[0]["severity"] == "error"
        assert result[1]["severity"] == "warning"
        assert result[2]["severity"] == "error"

    def test_parse_note_as_hint(self):
        """Test that notes are parsed as hints."""
        output = "main.adb:10:5: note: see declaration at line 5"
        result = _parse_gprbuild_output(output)

        assert len(result) == 1
        assert result[0]["severity"] == "hint"

    def test_parse_full_path(self):
        """Test parsing with full file path."""
        output = "/home/user/project/src/main.adb:10:5: error: missing type"
        result = _parse_gprbuild_output(output)

        assert len(result) == 1
        assert result[0]["file"] == "/home/user/project/src/main.adb"

    def test_parse_empty_output(self):
        """Test parsing empty output."""
        result = _parse_gprbuild_output("")
        assert len(result) == 0

    def test_parse_non_diagnostic_lines(self):
        """Test that non-diagnostic lines are ignored."""
        output = """gprbuild: building main.adb
gcc -c main.adb
main.adb:5:1: error: syntax error
gprbuild: compilation failed"""
        result = _parse_gprbuild_output(output)

        assert len(result) == 1
        assert result[0]["file"] == "main.adb"


# ============================================================================
# ada_build Tool Tests
# ============================================================================


class TestBuild:
    """Tests for ada_build tool."""

    @pytest.mark.asyncio
    async def test_build_no_gpr_file(self, tmp_path, monkeypatch):
        """Test build when no GPR file is found."""
        monkeypatch.chdir(tmp_path)

        result = await handle_build()

        assert result["success"] is False
        assert "No GPR project file found" in result["error"]

    @pytest.mark.asyncio
    async def test_build_gpr_not_found(self):
        """Test build with nonexistent GPR file."""
        result = await handle_build(gpr_file="/nonexistent/project.gpr")

        assert result["success"] is False
        assert "GPR file not found" in result["error"]

    @pytest.mark.asyncio
    async def test_build_success(self, tmp_path):
        """Test successful build."""
        # Create a dummy GPR file
        gpr_file = tmp_path / "test.gpr"
        gpr_file.write_text("project Test is\nend Test;")

        # Mock subprocess
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate = AsyncMock(return_value=(b"", b""))
            mock_exec.return_value = mock_proc

            result = await handle_build(gpr_file=str(gpr_file))

        assert result["success"] is True
        assert result["exit_code"] == 0
        assert result["error_count"] == 0

    @pytest.mark.asyncio
    async def test_build_with_errors(self, tmp_path):
        """Test build with compilation errors."""
        gpr_file = tmp_path / "test.gpr"
        gpr_file.write_text("project Test is\nend Test;")

        error_output = b"main.adb:10:5: error: missing semicolon"

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 1
            mock_proc.communicate = AsyncMock(return_value=(error_output, b""))
            mock_exec.return_value = mock_proc

            result = await handle_build(gpr_file=str(gpr_file))

        assert result["success"] is False
        assert result["error_count"] == 1
        assert result["errors"][0]["line"] == 10

    @pytest.mark.asyncio
    async def test_build_gprbuild_not_found(self, tmp_path):
        """Test build when gprbuild is not in PATH."""
        gpr_file = tmp_path / "test.gpr"
        gpr_file.write_text("project Test is\nend Test;")

        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
            result = await handle_build(gpr_file=str(gpr_file))

        assert result["success"] is False
        assert "gprbuild not found" in result["error"]


# ============================================================================
# ada_alire_info Tool Tests
# ============================================================================


class TestAlireInfo:
    """Tests for ada_alire_info tool."""

    @pytest.mark.asyncio
    async def test_alire_not_found(self, tmp_path):
        """Test when no alire.toml exists."""
        result = await handle_alire_info(project_dir=str(tmp_path))

        assert result["is_alire_project"] is False
        assert "No alire.toml found" in result["error"]

    @pytest.mark.asyncio
    async def test_alire_basic(self, tmp_path):
        """Test parsing basic alire.toml."""
        alire_file = tmp_path / "alire.toml"
        alire_file.write_text("""
name = "my_project"
version = "1.0.0"
description = "A test project"
authors = ["Test Author"]
""")

        result = await handle_alire_info(project_dir=str(tmp_path))

        assert result["is_alire_project"] is True
        assert result["name"] == "my_project"
        assert result["version"] == "1.0.0"
        assert result["description"] == "A test project"
        assert "Test Author" in result["authors"]

    @pytest.mark.asyncio
    async def test_alire_with_dependencies(self, tmp_path):
        """Test parsing alire.toml with dependencies."""
        alire_file = tmp_path / "alire.toml"
        alire_file.write_text("""
name = "my_project"
version = "0.1.0"

[[depends-on]]
gnatcoll = "^24.0.0"

[[depends-on]]
xmlada = "*"
""")

        result = await handle_alire_info(project_dir=str(tmp_path))

        assert result["is_alire_project"] is True
        assert len(result["dependencies"]) == 2

        dep_names = [d["name"] for d in result["dependencies"]]
        assert "gnatcoll" in dep_names
        assert "xmlada" in dep_names

    @pytest.mark.asyncio
    async def test_alire_with_executables(self, tmp_path):
        """Test parsing alire.toml with executables."""
        alire_file = tmp_path / "alire.toml"
        alire_file.write_text("""
name = "my_project"
version = "1.0.0"
executables = ["my_app", "my_tool"]
""")

        result = await handle_alire_info(project_dir=str(tmp_path))

        assert result["is_alire_project"] is True
        assert "my_app" in result["executables"]
        assert "my_tool" in result["executables"]

    @pytest.mark.asyncio
    async def test_alire_with_gpr_externals(self, tmp_path):
        """Test parsing alire.toml with GPR externals."""
        alire_file = tmp_path / "alire.toml"
        alire_file.write_text("""
name = "my_project"
version = "1.0.0"

[gpr-externals]
BUILD_MODE = ["debug", "release"]

[gpr-set-externals]
BUILD_MODE = "debug"
""")

        result = await handle_alire_info(project_dir=str(tmp_path))

        assert result["is_alire_project"] is True
        assert "BUILD_MODE" in result["gpr_externals"]
        assert result["gpr_set_externals"]["BUILD_MODE"] == "debug"

    @pytest.mark.asyncio
    async def test_alire_malformed(self, tmp_path):
        """Test handling malformed alire.toml."""
        alire_file = tmp_path / "alire.toml"
        alire_file.write_text("this is not valid toml {{{{")

        result = await handle_alire_info(project_dir=str(tmp_path))

        assert result["is_alire_project"] is False
        assert "Failed to parse" in result["error"]
