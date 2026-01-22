"""Navigation tools: goto definition, find references, hover."""

import logging
from pathlib import Path
from typing import Any

from ada_mcp.als.client import ALSClient, LSPError
from ada_mcp.utils.uri import file_to_uri, uri_to_file

logger = logging.getLogger(__name__)


async def handle_goto_definition(
    client: ALSClient,
    file: str,
    line: int,
    column: int,
) -> dict[str, Any]:
    """
    Navigate to the definition of a symbol at a given location.

    Args:
        client: ALS client instance
        file: Absolute path to Ada file
        line: 1-based line number
        column: 1-based column number

    Returns:
        Dict with definition location or not found status
    """
    file_uri = file_to_uri(file)

    # Ensure file is open in ALS
    await _ensure_file_open(client, file)

    try:
        result = await client.send_request(
            "textDocument/definition",
            {
                "textDocument": {"uri": file_uri},
                "position": {
                    "line": line - 1,  # Convert to 0-based
                    "character": column - 1,
                },
            },
        )
    except LSPError as e:
        logger.error(f"LSP error in goto_definition: {e}")
        return {"found": False, "error": e.message}

    if not result:
        return {"found": False}

    # Handle both single location and array of locations
    if isinstance(result, list):
        location = result[0] if result else None
    else:
        location = result

    if not location:
        return {"found": False}

    # Handle LocationLink vs Location
    if "targetUri" in location:
        # LocationLink format
        target_uri = location["targetUri"]
        target_range = location.get("targetSelectionRange", location.get("targetRange", {}))
    else:
        # Location format
        target_uri = location.get("uri", "")
        target_range = location.get("range", {})

    start = target_range.get("start", {})
    target_file = uri_to_file(target_uri)

    # Get preview line
    preview = await _get_line_preview(target_file, start.get("line", 0))

    return {
        "found": True,
        "file": target_file,
        "line": start.get("line", 0) + 1,  # Convert to 1-based
        "column": start.get("character", 0) + 1,
        "preview": preview,
    }


async def handle_find_references(
    client: ALSClient,
    file: str,
    line: int,
    column: int,
    include_declaration: bool = True,
) -> dict[str, Any]:
    """
    Find all references to a symbol across the project.

    Args:
        client: ALS client instance
        file: Absolute path to Ada file
        line: 1-based line number
        column: 1-based column number
        include_declaration: Whether to include the declaration in results

    Returns:
        Dict with list of references and count
    """
    file_uri = file_to_uri(file)

    # Ensure file is open in ALS
    await _ensure_file_open(client, file)

    try:
        result = await client.send_request(
            "textDocument/references",
            {
                "textDocument": {"uri": file_uri},
                "position": {
                    "line": line - 1,
                    "character": column - 1,
                },
                "context": {"includeDeclaration": include_declaration},
            },
        )
    except LSPError as e:
        logger.error(f"LSP error in find_references: {e}")
        return {"references": [], "count": 0, "error": e.message}

    if not result:
        return {"references": [], "count": 0}

    references = []
    for loc in result:
        loc_uri = loc.get("uri", "")
        loc_range = loc.get("range", {})
        start = loc_range.get("start", {})

        ref_file = uri_to_file(loc_uri)
        ref_line = start.get("line", 0) + 1

        preview = await _get_line_preview(ref_file, start.get("line", 0))

        references.append(
            {
                "file": ref_file,
                "line": ref_line,
                "column": start.get("character", 0) + 1,
                "preview": preview,
            }
        )

    return {
        "references": references,
        "count": len(references),
    }


async def handle_type_definition(
    client: ALSClient,
    file: str,
    line: int,
    column: int,
) -> dict[str, Any]:
    """
    Navigate to the type definition of a symbol at a given location.

    This is useful for finding where a type is defined, not just where
    a variable is declared. For example, given a variable of type Config,
    this returns the location where Config type is defined.

    Args:
        client: ALS client instance
        file: Absolute path to Ada file
        line: 1-based line number
        column: 1-based column number

    Returns:
        Dict with type definition location or not found status
    """
    file_uri = file_to_uri(file)

    # Ensure file is open in ALS
    await _ensure_file_open(client, file)

    try:
        result = await client.send_request(
            "textDocument/typeDefinition",
            {
                "textDocument": {"uri": file_uri},
                "position": {
                    "line": line - 1,  # Convert to 0-based
                    "character": column - 1,
                },
            },
        )
    except LSPError as e:
        logger.error(f"LSP error in type_definition: {e}")
        return {"found": False, "error": e.message}

    if not result:
        return {"found": False}

    # Handle both single location and array of locations
    if isinstance(result, list):
        location = result[0] if result else None
    else:
        location = result

    if not location:
        return {"found": False}

    # Handle LocationLink vs Location
    if "targetUri" in location:
        target_uri = location["targetUri"]
        target_range = location.get("targetSelectionRange", location.get("targetRange", {}))
    else:
        target_uri = location.get("uri", "")
        target_range = location.get("range", {})

    start = target_range.get("start", {})
    target_file = uri_to_file(target_uri)

    # Get preview line
    preview = await _get_line_preview(target_file, start.get("line", 0))

    return {
        "found": True,
        "file": target_file,
        "line": start.get("line", 0) + 1,  # Convert to 1-based
        "column": start.get("character", 0) + 1,
        "preview": preview,
    }


async def handle_implementation(
    client: ALSClient,
    file: str,
    line: int,
    column: int,
) -> dict[str, Any]:
    """
    Navigate from a declaration to its implementation/body.

    This is useful for jumping from a spec (.ads) to the body (.adb).
    For example, given a function declaration in a package spec,
    this returns the location of the function body.

    Args:
        client: ALS client instance
        file: Absolute path to Ada file
        line: 1-based line number
        column: 1-based column number

    Returns:
        Dict with implementation location or not found status
    """
    file_uri = file_to_uri(file)

    # Ensure file is open in ALS
    await _ensure_file_open(client, file)

    try:
        result = await client.send_request(
            "textDocument/implementation",
            {
                "textDocument": {"uri": file_uri},
                "position": {
                    "line": line - 1,  # Convert to 0-based
                    "character": column - 1,
                },
            },
        )
    except LSPError as e:
        logger.error(f"LSP error in implementation: {e}")
        return {"found": False, "error": e.message}

    if not result:
        return {"found": False}

    # Handle both single location and array of locations
    if isinstance(result, list):
        location = result[0] if result else None
    else:
        location = result

    if not location:
        return {"found": False}

    # Handle LocationLink vs Location
    if "targetUri" in location:
        target_uri = location["targetUri"]
        target_range = location.get("targetSelectionRange", location.get("targetRange", {}))
    else:
        target_uri = location.get("uri", "")
        target_range = location.get("range", {})

    start = target_range.get("start", {})
    target_file = uri_to_file(target_uri)

    # Get preview line
    preview = await _get_line_preview(target_file, start.get("line", 0))

    return {
        "found": True,
        "file": target_file,
        "line": start.get("line", 0) + 1,  # Convert to 1-based
        "column": start.get("character", 0) + 1,
        "preview": preview,
    }


async def handle_hover(
    client: ALSClient,
    file: str,
    line: int,
    column: int,
) -> dict[str, Any]:
    """
    Get type information and documentation for a symbol.

    Args:
        client: ALS client instance
        file: Absolute path to Ada file
        line: 1-based line number
        column: 1-based column number

    Returns:
        Dict with hover information
    """
    file_uri = file_to_uri(file)

    # Ensure file is open in ALS
    await _ensure_file_open(client, file)

    try:
        result = await client.send_request(
            "textDocument/hover",
            {
                "textDocument": {"uri": file_uri},
                "position": {
                    "line": line - 1,
                    "character": column - 1,
                },
            },
        )
    except LSPError as e:
        logger.error(f"LSP error in hover: {e}")
        return {"found": False, "error": e.message}

    if not result:
        return {"found": False}

    contents = result.get("contents", {})

    # Parse contents - can be string, MarkupContent, or MarkedString[]
    if isinstance(contents, str):
        text = contents
    elif isinstance(contents, dict):
        text = contents.get("value", str(contents))
    elif isinstance(contents, list):
        # Array of MarkedString
        parts = []
        for item in contents:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(item.get("value", str(item)))
        text = "\n".join(parts)
    else:
        text = str(contents)

    return {
        "found": True,
        "contents": text,
    }


# Cache of open files to avoid reopening
_open_files: set[str] = set()


async def _ensure_file_open(client: ALSClient, file_path: str) -> None:
    """Ensure a file is open in ALS."""
    file_uri = file_to_uri(file_path)

    if file_uri in _open_files:
        return

    path = Path(file_path)
    if not path.exists():
        logger.warning(f"File not found: {file_path}")
        return

    # Determine language ID
    suffix = path.suffix.lower()
    if suffix in (".ads", ".adb"):
        language_id = "ada"
    elif suffix == ".gpr":
        language_id = "gpr"
    else:
        language_id = "ada"  # Default

    try:
        await client.send_notification(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": file_uri,
                    "languageId": language_id,
                    "version": 1,
                    "text": path.read_text(),
                }
            },
        )
        _open_files.add(file_uri)
        logger.debug(f"Opened file in ALS: {file_path}")
    except Exception as e:
        logger.warning(f"Failed to open file in ALS: {e}")


async def _get_line_preview(file_path: str, line_0based: int) -> str:
    """Get a preview of a specific line from a file."""
    try:
        path = Path(file_path)
        if not path.exists():
            return ""

        lines = path.read_text().splitlines()
        if 0 <= line_0based < len(lines):
            return lines[line_0based].rstrip()
        return ""
    except Exception:
        return ""


def clear_open_files_cache() -> None:
    """Clear the open files cache (useful for testing)."""
    _open_files.clear()
