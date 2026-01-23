"""Project intelligence tools for Ada MCP server.

Provides tools for:
- Project information from GPR files
- Call hierarchy (incoming/outgoing calls)
- Dependency graph analysis
"""

import re
from pathlib import Path
from typing import Any

from ..utils.uri import file_to_uri, uri_to_file
from ..utils.position import to_lsp_position


def _to_dict(obj: Any) -> Any:
    """Recursively convert LSP objects to plain dictionaries."""
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_to_dict(item) for item in obj]
    elif hasattr(obj, 'to_dict'):
        # Has a to_dict method (like Position, Range)
        return obj.to_dict()
    elif hasattr(obj, 'model_dump'):
        # Pydantic v2
        return obj.model_dump()
    elif hasattr(obj, 'dict'):
        # Pydantic v1
        return obj.dict()
    elif hasattr(obj, '__dict__'):
        # Generic object with attributes
        return {k: _to_dict(v) for k, v in obj.__dict__.items()}
    else:
        return obj


def parse_gpr_file(gpr_path: str | Path) -> dict[str, Any]:
    """Parse a GPR file to extract project information.
    
    Args:
        gpr_path: Path to the .gpr file
        
    Returns:
        Dictionary with:
        - project_name: Name of the project
        - source_dirs: List of source directories
        - object_dir: Object directory
        - exec_dir: Executable directory
        - main_units: List of main units
    """
    gpr_path = Path(gpr_path)
    if not gpr_path.exists():
        return {
            "project_name": None,
            "source_dirs": [],
            "object_dir": None,
            "exec_dir": None,
            "main_units": []
        }
    
    content = gpr_path.read_text()
    
    # Extract project name: project ProjectName is
    project_match = re.search(r'project\s+(\w+)\s+is', content, re.IGNORECASE)
    project_name = project_match.group(1) if project_match else None
    
    # Extract source directories: for Source_Dirs use ("src", "other");
    source_dirs = []
    source_match = re.search(r'for\s+Source_Dirs\s+use\s*\((.*?)\);', content, re.IGNORECASE | re.DOTALL)
    if source_match:
        dirs_str = source_match.group(1)
        # Find all quoted strings
        source_dirs = re.findall(r'"([^"]+)"', dirs_str)
    
    # Extract object directory: for Object_Dir use "obj";
    object_dir = None
    obj_match = re.search(r'for\s+Object_Dir\s+use\s*"([^"]+)";', content, re.IGNORECASE)
    if obj_match:
        object_dir = obj_match.group(1)
    
    # Extract exec directory: for Exec_Dir use "bin";
    exec_dir = None
    exec_match = re.search(r'for\s+Exec_Dir\s+use\s*"([^"]+)";', content, re.IGNORECASE)
    if exec_match:
        exec_dir = exec_match.group(1)
    
    # Extract main units: for Main use ("main.adb", "test.adb");
    main_units = []
    main_match = re.search(r'for\s+Main\s+use\s*\((.*?)\);', content, re.IGNORECASE | re.DOTALL)
    if main_match:
        mains_str = main_match.group(1)
        main_units = re.findall(r'"([^"]+)"', mains_str)
    
    return {
        "project_name": project_name,
        "source_dirs": source_dirs,
        "object_dir": object_dir,
        "exec_dir": exec_dir,
        "main_units": main_units
    }


async def handle_project_info(gpr_file: str) -> dict[str, Any]:
    """Handle ada_project_info tool request.
    
    Args:
        gpr_file: Path to the .gpr project file
        
    Returns:
        Project information dictionary
    """
    gpr_path = Path(gpr_file)
    info = parse_gpr_file(gpr_path)
    
    # Convert relative paths to absolute
    base_dir = gpr_path.parent
    
    # Make source directories absolute
    absolute_source_dirs = []
    for src_dir in info["source_dirs"]:
        abs_path = (base_dir / src_dir).resolve()
        absolute_source_dirs.append(str(abs_path))
    
    return {
        "project_file": str(gpr_path.resolve()),
        "project_name": info["project_name"],
        "source_dirs": absolute_source_dirs,
        "object_dir": str((base_dir / info["object_dir"]).resolve()) if info["object_dir"] else None,
        "exec_dir": str((base_dir / info["exec_dir"]).resolve()) if info["exec_dir"] else None,
        "main_units": info["main_units"]
    }


async def handle_call_hierarchy(
    als_client,
    file: str,
    line: int,
    column: int,
    direction: str = "outgoing"
) -> dict[str, Any]:
    """Handle ada_call_hierarchy tool request.
    
    Args:
        als_client: ALS client instance
        file: Path to the source file
        line: Line number (1-based)
        column: Column number (1-based)
        direction: "outgoing", "incoming", or "both"
        
    Returns:
        Dictionary with call hierarchy information
    """
    file_uri = file_to_uri(file)
    lsp_pos = to_lsp_position(line, column)
    
    # First, prepare call hierarchy
    prepare_result = await als_client.send_request(
        "textDocument/prepareCallHierarchy",
        {
            "textDocument": {"uri": file_uri},
            "position": lsp_pos
        }
    )
    
    if not prepare_result:
        return {
            "found": False,
            "outgoing_calls": [],
            "incoming_calls": []
        }
    
    # Get the first item (usually the symbol at the position)
    item = prepare_result[0] if isinstance(prepare_result, list) else prepare_result
    
    # Convert item to plain dict to avoid serialization issues
    item_dict = _to_dict(item)
    
    outgoing = []
    incoming = []
    
    # Get outgoing calls if requested
    if direction in ("outgoing", "both"):
        outgoing_result = await als_client.send_request(
            "callHierarchy/outgoingCalls",
            {"item": item_dict}
        )
        if outgoing_result:
            for call in outgoing_result:
                to_item = call.get("to", {})
                outgoing.append({
                    "name": to_item.get("name", ""),
                    "kind": to_item.get("kind", 0),
                    "file": uri_to_file(to_item.get("uri", "")),
                    "line": to_item.get("range", {}).get("start", {}).get("line", 0) + 1,
                    "column": to_item.get("range", {}).get("start", {}).get("character", 0) + 1
                })
    
    # Get incoming calls if requested
    if direction in ("incoming", "both"):
        incoming_result = await als_client.send_request(
            "callHierarchy/incomingCalls",
            {"item": item_dict}
        )
        if incoming_result:
            for call in incoming_result:
                from_item = call.get("from", {})
                incoming.append({
                    "name": from_item.get("name", ""),
                    "kind": from_item.get("kind", 0),
                    "file": uri_to_file(from_item.get("uri", "")),
                    "line": from_item.get("range", {}).get("start", {}).get("line", 0) + 1,
                    "column": from_item.get("range", {}).get("start", {}).get("character", 0) + 1
                })
    
    return {
        "found": True,
        "symbol": item_dict.get("name", "") if isinstance(item_dict, dict) else str(item_dict),
        "outgoing_calls": outgoing,
        "incoming_calls": incoming,
        "outgoing_count": len(outgoing),
        "incoming_count": len(incoming)
    }


async def handle_dependency_graph(file: str) -> dict[str, Any]:
    """Handle ada_dependency_graph tool request.
    
    Parses 'with' clauses to build a dependency graph.
    
    Args:
        file: Path to the source file or directory
        
    Returns:
        Dictionary with dependency information
    """
    path = Path(file)
    
    if not path.exists():
        return {
            "dependencies": [],
            "package_count": 0
        }
    
    # Collect all .ads and .adb files
    ada_files = []
    if path.is_dir():
        ada_files = list(path.rglob("*.ads")) + list(path.rglob("*.adb"))
    else:
        ada_files = [path]
    
    # Parse dependencies from each file
    dependencies = []
    seen_packages = set()
    
    for ada_file in ada_files:
        content = ada_file.read_text()
        
        # Extract package or procedure name from this file
        pkg_match = re.search(r'(?:package|procedure|function)\s+(?:body\s+)?(\w+(?:\.\w+)*)', content, re.IGNORECASE)
        if not pkg_match:
            continue
        
        package_name = pkg_match.group(1)
        seen_packages.add(package_name)
        
        # Find all 'with' clauses
        with_clauses = re.findall(r'^\s*with\s+([\w.]+(?:\s*,\s*[\w.]+)*)\s*;', content, re.MULTILINE | re.IGNORECASE)
        
        imported_packages = set()
        for clause in with_clauses:
            # Split by comma for multiple imports
            packages = [p.strip() for p in clause.split(',')]
            imported_packages.update(packages)
        
        if imported_packages:
            dependencies.append({
                "package": package_name,
                "file": str(ada_file),
                "depends_on": sorted(list(imported_packages))
            })
    
    return {
        "dependencies": dependencies,
        "package_count": len(seen_packages)
    }
