"""Unit tests for Phase 3: Project Intelligence tools."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from ada_mcp.tools.project import (
    parse_gpr_file,
    handle_project_info,
    handle_call_hierarchy,
    handle_dependency_graph
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_gpr_path():
    """Path to sample GPR file."""
    return Path(__file__).parent / "fixtures" / "sample_project" / "sample.gpr"


@pytest.fixture
def sample_ada_file():
    """Path to sample Ada file."""
    return Path(__file__).parent / "fixtures" / "sample_project" / "src" / "main.adb"


@pytest.fixture
def mock_als_client():
    """Create a mock ALS client."""
    client = AsyncMock()
    client.send_request = AsyncMock()
    return client


# ============================================================================
# GPR File Parser Tests (Task 3.1)
# ============================================================================

class TestGPRParser:
    """Tests for GPR file parsing."""
    
    def test_parse_gpr_basic(self, sample_gpr_path):
        """Test basic GPR file parsing."""
        result = parse_gpr_file(sample_gpr_path)
        
        assert result["project_name"] == "Sample"
        assert "src" in result["source_dirs"]
        assert result["object_dir"] == "obj"
        assert result["exec_dir"] == "bin"
        assert "main.adb" in result["main_units"]
    
    def test_parse_gpr_nonexistent(self):
        """Test parsing non-existent GPR file."""
        result = parse_gpr_file("/nonexistent/project.gpr")
        
        assert result["project_name"] is None
        assert result["source_dirs"] == []
        assert result["object_dir"] is None
        assert result["main_units"] == []
    
    def test_parse_gpr_multiple_sources(self, tmp_path):
        """Test parsing GPR with multiple source directories."""
        gpr_file = tmp_path / "multi.gpr"
        gpr_file.write_text("""
project Multi is
   for Source_Dirs use ("src", "tests", "lib");
   for Object_Dir use "build";
   for Main use ("app.adb", "test.adb");
end Multi;
""")
        
        result = parse_gpr_file(gpr_file)
        
        assert result["project_name"] == "Multi"
        assert len(result["source_dirs"]) == 3
        assert "src" in result["source_dirs"]
        assert "tests" in result["source_dirs"]
        assert "lib" in result["source_dirs"]
        assert len(result["main_units"]) == 2


# ============================================================================
# ada_project_info Tests (Task 3.2)
# ============================================================================

class TestProjectInfo:
    """Tests for ada_project_info tool."""
    
    @pytest.mark.asyncio
    async def test_project_info_basic(self, sample_gpr_path):
        """Test basic project info retrieval."""
        result = await handle_project_info(str(sample_gpr_path))
        
        assert "project_file" in result
        assert "project_name" in result
        assert result["project_name"] == "Sample"
        assert len(result["source_dirs"]) > 0
        assert all(Path(d).is_absolute() for d in result["source_dirs"])
        assert "main.adb" in result["main_units"]
    
    @pytest.mark.asyncio
    async def test_project_info_absolute_paths(self, sample_gpr_path):
        """Test that returned paths are absolute."""
        result = await handle_project_info(str(sample_gpr_path))
        
        assert Path(result["project_file"]).is_absolute()
        for src_dir in result["source_dirs"]:
            assert Path(src_dir).is_absolute()
        if result["object_dir"]:
            assert Path(result["object_dir"]).is_absolute()
    
    @pytest.mark.asyncio
    async def test_project_info_nonexistent(self):
        """Test project info for non-existent file."""
        result = await handle_project_info("/nonexistent/project.gpr")
        
        assert result["project_name"] is None
        assert result["source_dirs"] == []


# ============================================================================
# ada_call_hierarchy Tests (Task 3.3 & 3.4)
# ============================================================================

class TestCallHierarchy:
    """Tests for ada_call_hierarchy tool."""
    
    @pytest.mark.asyncio
    async def test_call_hierarchy_outgoing(self, mock_als_client):
        """Test outgoing call hierarchy."""
        # Mock prepare call hierarchy
        mock_als_client.send_request.side_effect = [
            # prepareCallHierarchy response
            [{
                "name": "Main",
                "kind": 12,
                "uri": "file:///test/main.adb",
                "range": {"start": {"line": 3, "character": 10}}
            }],
            # outgoingCalls response
            [{
                "to": {
                    "name": "Utils.Add",
                    "kind": 12,
                    "uri": "file:///test/utils.adb",
                    "range": {"start": {"line": 4, "character": 12}}
                }
            }]
        ]
        
        result = await handle_call_hierarchy(
            mock_als_client,
            "/test/main.adb",
            line=4,
            column=11,
            direction="outgoing"
        )
        
        assert result["found"] is True
        assert result["symbol"] == "Main"
        assert len(result["outgoing_calls"]) == 1
        assert result["outgoing_calls"][0]["name"] == "Utils.Add"
        assert result["outgoing_count"] == 1
        assert len(result["incoming_calls"]) == 0
    
    @pytest.mark.asyncio
    async def test_call_hierarchy_incoming(self, mock_als_client):
        """Test incoming call hierarchy."""
        mock_als_client.send_request.side_effect = [
            # prepareCallHierarchy response
            [{
                "name": "Add",
                "kind": 12,
                "uri": "file:///test/utils.adb",
                "range": {"start": {"line": 4, "character": 12}}
            }],
            # incomingCalls response
            [{
                "from": {
                    "name": "Main",
                    "kind": 12,
                    "uri": "file:///test/main.adb",
                    "range": {"start": {"line": 5, "character": 4}}
                }
            }]
        ]
        
        result = await handle_call_hierarchy(
            mock_als_client,
            "/test/utils.adb",
            line=5,
            column=13,
            direction="incoming"
        )
        
        assert result["found"] is True
        assert len(result["incoming_calls"]) == 1
        assert result["incoming_calls"][0]["name"] == "Main"
        assert result["incoming_count"] == 1
        assert len(result["outgoing_calls"]) == 0
    
    @pytest.mark.asyncio
    async def test_call_hierarchy_both(self, mock_als_client):
        """Test both incoming and outgoing calls."""
        mock_als_client.send_request.side_effect = [
            # prepareCallHierarchy response
            [{
                "name": "Process",
                "kind": 12,
                "uri": "file:///test/process.adb",
                "range": {"start": {"line": 10, "character": 12}}
            }],
            # outgoingCalls response
            [{"to": {"name": "Helper", "kind": 12, "uri": "file:///test/helper.adb", "range": {"start": {"line": 5, "character": 4}}}}],
            # incomingCalls response
            [{"from": {"name": "Main", "kind": 12, "uri": "file:///test/main.adb", "range": {"start": {"line": 8, "character": 4}}}}]
        ]
        
        result = await handle_call_hierarchy(
            mock_als_client,
            "/test/process.adb",
            line=11,
            column=13,
            direction="both"
        )
        
        assert result["found"] is True
        assert len(result["outgoing_calls"]) == 1
        assert len(result["incoming_calls"]) == 1
        assert result["outgoing_count"] == 1
        assert result["incoming_count"] == 1
    
    @pytest.mark.asyncio
    async def test_call_hierarchy_not_found(self, mock_als_client):
        """Test call hierarchy when symbol not found."""
        mock_als_client.send_request.return_value = None
        
        result = await handle_call_hierarchy(
            mock_als_client,
            "/test/main.adb",
            line=1,
            column=1,
            direction="outgoing"
        )
        
        assert result["found"] is False
        assert result["outgoing_calls"] == []
        assert result["incoming_calls"] == []


# ============================================================================
# ada_dependency_graph Tests (Task 3.5)
# ============================================================================

class TestDependencyGraph:
    """Tests for ada_dependency_graph tool."""
    
    @pytest.mark.asyncio
    async def test_dependency_graph_single_file(self, tmp_path):
        """Test dependency graph for a single file."""
        ada_file = tmp_path / "utils.ads"
        ada_file.write_text("""
with Ada.Text_IO;
with Ada.Strings;

package Utils is
   function Add (A, B : Integer) return Integer;
end Utils;
""")
        
        result = await handle_dependency_graph(str(ada_file))
        
        assert result["package_count"] == 1
        assert len(result["dependencies"]) == 1
        dep = result["dependencies"][0]
        assert dep["package"] == "Utils"
        assert "Ada.Text_IO" in dep["depends_on"]
        assert "Ada.Strings" in dep["depends_on"]
    
    @pytest.mark.asyncio
    async def test_dependency_graph_directory(self, sample_ada_file):
        """Test dependency graph for a directory."""
        src_dir = sample_ada_file.parent
        
        result = await handle_dependency_graph(str(src_dir))
        
        assert result["package_count"] >= 1
        assert len(result["dependencies"]) >= 1
    
    @pytest.mark.asyncio
    async def test_dependency_graph_multiple_with(self, tmp_path):
        """Test parsing multiple packages in one with clause."""
        ada_file = tmp_path / "main.adb"
        ada_file.write_text("""
with Ada.Text_IO, Ada.Strings, Utils;

procedure Main is
begin
   null;
end Main;
""")
        
        result = await handle_dependency_graph(str(ada_file))
        
        assert len(result["dependencies"]) == 1
        deps = result["dependencies"][0]["depends_on"]
        assert "Ada.Text_IO" in deps
        assert "Ada.Strings" in deps
        assert "Utils" in deps
    
    @pytest.mark.asyncio
    async def test_dependency_graph_nonexistent(self):
        """Test dependency graph for non-existent path."""
        result = await handle_dependency_graph("/nonexistent/path")
        
        assert result["dependencies"] == []
        assert result["package_count"] == 0
    
    @pytest.mark.asyncio
    async def test_dependency_graph_package_body(self, tmp_path):
        """Test dependency graph includes package bodies."""
        ada_file = tmp_path / "utils.adb"
        ada_file.write_text("""
with Ada.Text_IO;

package body Utils is
   function Add (A, B : Integer) return Integer is
   begin
      return A + B;
   end Add;
end Utils;
""")
        
        result = await handle_dependency_graph(str(ada_file))
        
        assert result["package_count"] == 1
        assert len(result["dependencies"]) == 1
        assert result["dependencies"][0]["package"] == "Utils"
        assert "Ada.Text_IO" in result["dependencies"][0]["depends_on"]
