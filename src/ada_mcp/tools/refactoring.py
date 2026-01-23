"""Code intelligence and refactoring tools for Ada MCP server.

Provides tools for:
- Code completions
- Signature help
- Code actions (quick fixes)
- Symbol renaming
- File formatting
- Spec/body navigation
"""

import re
from pathlib import Path
from typing import Any

from ..utils.position import from_lsp_position_dict, to_lsp_position
from ..utils.uri import file_to_uri, uri_to_file

# LSP Completion Item Kind mapping
COMPLETION_ITEM_KIND = {
    1: "Text",
    2: "Method",
    3: "Function",
    4: "Constructor",
    5: "Field",
    6: "Variable",
    7: "Class",
    8: "Interface",
    9: "Module",
    10: "Property",
    11: "Unit",
    12: "Value",
    13: "Enum",
    14: "Keyword",
    15: "Snippet",
    16: "Color",
    17: "File",
    18: "Reference",
    19: "Folder",
    20: "EnumMember",
    21: "Constant",
    22: "Struct",
    23: "Event",
    24: "Operator",
    25: "TypeParameter",
}


async def handle_completions(
    als_client,
    file: str,
    line: int,
    column: int,
    trigger_character: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Handle ada_completions tool request.

    Args:
        als_client: ALS client instance
        file: Path to the source file
        line: Line number (1-based)
        column: Column number (1-based)
        trigger_character: Optional trigger character (e.g., '.', ':')
        limit: Maximum number of completions to return

    Returns:
        Dictionary with completion items
    """
    file_uri = file_to_uri(file)
    lsp_pos = to_lsp_position(line, column)

    # Build completion context if trigger character provided
    params: dict[str, Any] = {
        "textDocument": {"uri": file_uri},
        "position": lsp_pos,
    }

    if trigger_character:
        params["context"] = {
            "triggerKind": 2,  # TriggerCharacter
            "triggerCharacter": trigger_character,
        }
    else:
        params["context"] = {
            "triggerKind": 1,  # Invoked
        }

    result = await als_client.send_request("textDocument/completion", params)

    if not result:
        return {
            "completions": [],
            "count": 0,
            "is_incomplete": False,
        }

    # Handle both CompletionList and CompletionItem[] responses
    if isinstance(result, dict):
        items = result.get("items", [])
        is_incomplete = result.get("isIncomplete", False)
    else:
        items = result if isinstance(result, list) else []
        is_incomplete = False

    # Parse completion items
    completions = []
    for item in items[:limit]:
        kind_num = item.get("kind", 1)
        completions.append(
            {
                "label": item.get("label", ""),
                "kind": COMPLETION_ITEM_KIND.get(kind_num, "Unknown"),
                "detail": item.get("detail", ""),
                "documentation": _extract_documentation(item.get("documentation")),
                "insert_text": item.get("insertText", item.get("label", "")),
                "sort_text": item.get("sortText", ""),
            }
        )

    return {
        "completions": completions,
        "count": len(completions),
        "is_incomplete": is_incomplete,
    }


def _extract_documentation(doc: Any) -> str:
    """Extract documentation string from various formats."""
    if doc is None:
        return ""
    if isinstance(doc, str):
        return doc
    if isinstance(doc, dict):
        # MarkupContent
        return doc.get("value", "")
    return str(doc)


async def handle_signature_help(
    als_client,
    file: str,
    line: int,
    column: int,
) -> dict[str, Any]:
    """Handle ada_signature_help tool request.

    Args:
        als_client: ALS client instance
        file: Path to the source file
        line: Line number (1-based)
        column: Column number (1-based)

    Returns:
        Dictionary with signature information
    """
    file_uri = file_to_uri(file)
    lsp_pos = to_lsp_position(line, column)

    result = await als_client.send_request(
        "textDocument/signatureHelp",
        {
            "textDocument": {"uri": file_uri},
            "position": lsp_pos,
        },
    )

    if not result or not result.get("signatures"):
        return {
            "found": False,
            "signatures": [],
            "active_signature": 0,
            "active_parameter": 0,
        }

    signatures = []
    for sig in result.get("signatures", []):
        params = []
        for param in sig.get("parameters", []):
            params.append(
                {
                    "label": param.get("label", ""),
                    "documentation": _extract_documentation(param.get("documentation")),
                }
            )

        signatures.append(
            {
                "label": sig.get("label", ""),
                "documentation": _extract_documentation(sig.get("documentation")),
                "parameters": params,
            }
        )

    return {
        "found": True,
        "signatures": signatures,
        "active_signature": result.get("activeSignature", 0),
        "active_parameter": result.get("activeParameter", 0),
    }


async def handle_code_actions(
    als_client,
    file: str,
    start_line: int,
    start_column: int,
    end_line: int | None = None,
    end_column: int | None = None,
    diagnostics: list[dict] | None = None,
) -> dict[str, Any]:
    """Handle ada_code_actions tool request.

    Args:
        als_client: ALS client instance
        file: Path to the source file
        start_line: Start line number (1-based)
        start_column: Start column number (1-based)
        end_line: End line number (1-based), defaults to start_line
        end_column: End column number (1-based), defaults to start_column
        diagnostics: Optional list of diagnostics to get fixes for

    Returns:
        Dictionary with available code actions
    """
    file_uri = file_to_uri(file)

    # Build range
    start_pos = to_lsp_position(start_line, start_column)
    end_pos = to_lsp_position(
        end_line if end_line is not None else start_line,
        end_column if end_column is not None else start_column,
    )

    params: dict[str, Any] = {
        "textDocument": {"uri": file_uri},
        "range": {
            "start": start_pos,
            "end": end_pos,
        },
        "context": {
            "diagnostics": diagnostics or [],
            "only": None,  # Request all kinds of code actions
        },
    }

    result = await als_client.send_request("textDocument/codeAction", params)

    if not result:
        return {
            "actions": [],
            "count": 0,
        }

    actions = []
    for action in result:
        if isinstance(action, dict):
            # Could be CodeAction or Command
            if "title" in action:
                action_info = {
                    "title": action.get("title", ""),
                    "kind": action.get("kind", ""),
                    "is_preferred": action.get("isPreferred", False),
                }

                # Check if it has edits
                if "edit" in action:
                    action_info["has_edit"] = True
                    # Count number of files affected
                    changes = action.get("edit", {}).get("changes", {})
                    doc_changes = action.get("edit", {}).get("documentChanges", [])
                    action_info["files_affected"] = len(changes) or len(doc_changes)
                else:
                    action_info["has_edit"] = False
                    action_info["files_affected"] = 0

                # Check if it has a command
                if "command" in action:
                    cmd = action["command"]
                    action_info["command"] = cmd.get("title", cmd.get("command", ""))

                actions.append(action_info)

    return {
        "actions": actions,
        "count": len(actions),
    }


# Ada identifier validation pattern
ADA_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def _is_valid_ada_identifier(name: str) -> bool:
    """Check if name is a valid Ada identifier."""
    if not name:
        return False
    # Check basic pattern
    if not ADA_IDENTIFIER_PATTERN.match(name):
        return False
    # Check no consecutive underscores
    if "__" in name:
        return False
    # Check doesn't end with underscore
    if name.endswith("_"):
        return False
    return True


async def handle_rename_symbol(
    als_client,
    file: str,
    line: int,
    column: int,
    new_name: str,
    preview: bool = True,
) -> dict[str, Any]:
    """Handle ada_rename_symbol tool request.

    Args:
        als_client: ALS client instance
        file: Path to the source file
        line: Line number (1-based)
        column: Column number (1-based)
        new_name: New name for the symbol
        preview: If True, only return changes without applying

    Returns:
        Dictionary with rename changes
    """
    # Validate new name
    if not _is_valid_ada_identifier(new_name):
        return {
            "success": False,
            "error": f"Invalid Ada identifier: '{new_name}'",
            "changes": [],
            "total_changes": 0,
        }

    file_uri = file_to_uri(file)
    lsp_pos = to_lsp_position(line, column)

    # First, check if rename is valid using prepareRename
    prepare_result = await als_client.send_request(
        "textDocument/prepareRename",
        {
            "textDocument": {"uri": file_uri},
            "position": lsp_pos,
        },
    )

    if not prepare_result:
        return {
            "success": False,
            "error": "Cannot rename symbol at this location",
            "changes": [],
            "total_changes": 0,
        }

    # Get the old name from prepareRename result
    old_name = ""
    if isinstance(prepare_result, dict):
        if "placeholder" in prepare_result:
            old_name = prepare_result["placeholder"]
        elif "start" in prepare_result:
            # It's a Range, we need to extract the text
            old_name = prepare_result.get("placeholder", "")

    # Perform the rename
    result = await als_client.send_request(
        "textDocument/rename",
        {
            "textDocument": {"uri": file_uri},
            "position": lsp_pos,
            "newName": new_name,
        },
    )

    if not result:
        return {
            "success": False,
            "error": "Rename operation failed",
            "changes": [],
            "total_changes": 0,
        }

    # Parse workspace edit
    changes = []

    # Handle both 'changes' and 'documentChanges' formats
    if "changes" in result:
        for uri, edits in result["changes"].items():
            file_path = uri_to_file(uri)
            for edit in edits:
                line_num, col_num = from_lsp_position_dict(edit["range"]["start"])
                changes.append(
                    {
                        "file": file_path,
                        "line": line_num,
                        "column": col_num,
                        "old_text": old_name,
                        "new_text": new_name,
                    }
                )

    if "documentChanges" in result:
        for doc_change in result["documentChanges"]:
            if "textDocument" in doc_change:
                uri = doc_change["textDocument"]["uri"]
                file_path = uri_to_file(uri)
                for edit in doc_change.get("edits", []):
                    line_num, col_num = from_lsp_position_dict(edit["range"]["start"])
                    changes.append(
                        {
                            "file": file_path,
                            "line": line_num,
                            "column": col_num,
                            "old_text": old_name,
                            "new_text": new_name,
                        }
                    )

    # Count files affected
    files_affected = len(set(c["file"] for c in changes))

    return {
        "success": True,
        "old_name": old_name,
        "new_name": new_name,
        "changes": changes,
        "total_changes": len(changes),
        "files_affected": files_affected,
        "applied": not preview,
    }


async def handle_format_file(
    als_client,
    file: str,
    tab_size: int = 3,
    insert_spaces: bool = True,
) -> dict[str, Any]:
    """Handle ada_format_file tool request.

    Args:
        als_client: ALS client instance
        file: Path to the source file
        tab_size: Tab width (default 3 for Ada)
        insert_spaces: Use spaces instead of tabs

    Returns:
        Dictionary with formatting result
    """
    file_uri = file_to_uri(file)

    result = await als_client.send_request(
        "textDocument/formatting",
        {
            "textDocument": {"uri": file_uri},
            "options": {
                "tabSize": tab_size,
                "insertSpaces": insert_spaces,
            },
        },
    )

    if result is None:
        return {
            "formatted": False,
            "file": file,
            "changes": 0,
            "edits": [],
        }

    # Parse text edits (empty list means already formatted)
    edits = []
    for edit in result:
        start_line, start_col = from_lsp_position_dict(edit["range"]["start"])
        end_line, end_col = from_lsp_position_dict(edit["range"]["end"])
        edits.append(
            {
                "start_line": start_line,
                "start_column": start_col,
                "end_line": end_line,
                "end_column": end_col,
                "new_text": edit["newText"],
            }
        )

    return {
        "formatted": True,
        "file": file,
        "changes": len(edits),
        "edits": edits,
    }


async def handle_get_spec(
    als_client,
    file: str,
    line: int | None = None,
    column: int | None = None,
) -> dict[str, Any]:
    """Handle ada_get_spec tool request.

    Navigate from body to spec, or find corresponding spec file.

    Args:
        als_client: ALS client instance
        file: Path to the source file (usually .adb)
        line: Optional line number (1-based)
        column: Optional column number (1-based)

    Returns:
        Dictionary with spec location
    """
    file_path = Path(file)

    # If line/column provided, use LSP to find declaration
    if line is not None and column is not None:
        file_uri = file_to_uri(file)
        lsp_pos = to_lsp_position(line, column)

        # Use textDocument/declaration to find spec
        result = await als_client.send_request(
            "textDocument/declaration",
            {
                "textDocument": {"uri": file_uri},
                "position": lsp_pos,
            },
        )

        if result:
            # Handle single location or array
            location = result[0] if isinstance(result, list) else result
            if isinstance(location, dict) and "uri" in location:
                spec_file = uri_to_file(location["uri"])
                loc_line, loc_col = from_lsp_position_dict(location["range"]["start"])

                # Read preview line
                preview = ""
                try:
                    with open(spec_file) as f:
                        lines = f.readlines()
                        if loc_line <= len(lines):
                            preview = lines[loc_line - 1].strip()
                except Exception:
                    pass

                return {
                    "found": True,
                    "spec_file": spec_file,
                    "line": loc_line,
                    "column": loc_col,
                    "preview": preview,
                }

    # Fallback: Find corresponding .ads file
    if file_path.suffix.lower() == ".adb":
        spec_file = file_path.with_suffix(".ads")
        if spec_file.exists():
            # Read first non-comment line for preview
            preview = ""
            try:
                with open(spec_file) as f:
                    for spec_line in f:
                        stripped = spec_line.strip()
                        if stripped and not stripped.startswith("--"):
                            preview = stripped
                            break
            except Exception:
                pass

            return {
                "found": True,
                "spec_file": str(spec_file),
                "line": 1,
                "column": 1,
                "preview": preview,
            }

    return {
        "found": False,
        "spec_file": None,
        "line": None,
        "column": None,
        "preview": "",
        "error": "No spec file found",
    }
