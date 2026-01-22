"""Symbol tools: document symbols and workspace symbol search."""

import logging
from typing import Any

from ada_mcp.als.client import ALSClient, LSPError
from ada_mcp.als.types import SymbolKind
from ada_mcp.utils.uri import file_to_uri, uri_to_file

logger = logging.getLogger(__name__)


async def handle_document_symbols(
    client: ALSClient,
    file: str,
) -> dict[str, Any]:
    """
    Get all symbols defined in an Ada file.

    Args:
        client: ALS client instance
        file: Absolute path to Ada file

    Returns:
        Dict with hierarchical symbol list
    """
    file_uri = file_to_uri(file)

    # Ensure file is open
    from ada_mcp.tools.navigation import _ensure_file_open

    await _ensure_file_open(client, file)

    try:
        result = await client.send_request(
            "textDocument/documentSymbol",
            {"textDocument": {"uri": file_uri}},
        )
    except LSPError as e:
        logger.error(f"LSP error in document_symbols: {e}")
        return {"symbols": [], "error": e.message}

    if not result:
        return {"symbols": []}

    # ALS returns either DocumentSymbol[] (hierarchical) or SymbolInformation[] (flat)
    symbols = []
    for item in result:
        if "location" in item:
            # SymbolInformation format (flat)
            symbols.append(_convert_symbol_information(item))
        else:
            # DocumentSymbol format (hierarchical)
            symbols.append(_convert_document_symbol(item))

    return {"symbols": symbols}


async def handle_workspace_symbols(
    client: ALSClient,
    query: str,
    kind: str = "all",
    limit: int = 50,
) -> dict[str, Any]:
    """
    Search for symbols by name across the workspace.

    Args:
        client: ALS client instance
        query: Symbol name or pattern to search for
        kind: Filter by kind - "package", "procedure", "function", "type", "variable", "all"
        limit: Maximum number of results

    Returns:
        Dict with matching symbols
    """
    try:
        result = await client.send_request(
            "workspace/symbol",
            {"query": query},
        )
    except LSPError as e:
        logger.error(f"LSP error in workspace_symbols: {e}")
        return {"symbols": [], "error": e.message}

    if not result:
        return {"symbols": []}

    # Filter by kind if specified
    kind_filter = _get_kind_filter(kind)

    symbols = []
    for item in result:
        symbol_kind = item.get("kind", 0)

        # Apply kind filter
        if kind_filter and symbol_kind not in kind_filter:
            continue

        location = item.get("location", {})
        loc_uri = location.get("uri", "")
        loc_range = location.get("range", {})
        start = loc_range.get("start", {})

        symbols.append(
            {
                "name": item.get("name", ""),
                "kind": _kind_to_string(symbol_kind),
                "file": uri_to_file(loc_uri) if loc_uri else "",
                "line": start.get("line", 0) + 1,
                "column": start.get("character", 0) + 1,
                "containerName": item.get("containerName", ""),
            }
        )

        if len(symbols) >= limit:
            break

    return {
        "symbols": symbols,
        "count": len(symbols),
        "truncated": len(result) > limit if result else False,
    }


def _convert_document_symbol(item: dict[str, Any]) -> dict[str, Any]:
    """Convert LSP DocumentSymbol to our format."""
    range_data = item.get("range", {})
    selection_range = item.get("selectionRange", range_data)
    start = selection_range.get("start", {})

    symbol = {
        "name": item.get("name", ""),
        "kind": _kind_to_string(item.get("kind", 0)),
        "line": start.get("line", 0) + 1,
        "column": start.get("character", 0) + 1,
        "range": {
            "start": range_data.get("start", {}).get("line", 0) + 1,
            "end": range_data.get("end", {}).get("line", 0) + 1,
        },
    }

    # Add detail if present
    if "detail" in item:
        symbol["detail"] = item["detail"]

    # Recursively convert children
    children = item.get("children", [])
    if children:
        symbol["children"] = [_convert_document_symbol(child) for child in children]

    return symbol


def _convert_symbol_information(item: dict[str, Any]) -> dict[str, Any]:
    """Convert LSP SymbolInformation to our format."""
    location = item.get("location", {})
    loc_range = location.get("range", {})
    start = loc_range.get("start", {})

    return {
        "name": item.get("name", ""),
        "kind": _kind_to_string(item.get("kind", 0)),
        "file": uri_to_file(location.get("uri", "")),
        "line": start.get("line", 0) + 1,
        "column": start.get("character", 0) + 1,
        "containerName": item.get("containerName", ""),
    }


def _get_kind_filter(kind: str) -> set[int] | None:
    """Get set of SymbolKind values to include based on filter string."""
    if kind == "all":
        return None

    kind_map = {
        "package": {SymbolKind.PACKAGE, SymbolKind.MODULE, SymbolKind.NAMESPACE},
        "procedure": {SymbolKind.FUNCTION, SymbolKind.METHOD},  # Ada procedures map to functions
        "function": {SymbolKind.FUNCTION, SymbolKind.METHOD},
        "type": {SymbolKind.CLASS, SymbolKind.STRUCT, SymbolKind.ENUM, SymbolKind.INTERFACE},
        "variable": {SymbolKind.VARIABLE, SymbolKind.CONSTANT, SymbolKind.FIELD},
        "constant": {SymbolKind.CONSTANT},
    }

    return kind_map.get(kind.lower())


def _kind_to_string(kind: int) -> str:
    """Convert LSP SymbolKind to human-readable string."""
    kind_names = {
        SymbolKind.FILE: "file",
        SymbolKind.MODULE: "module",
        SymbolKind.NAMESPACE: "namespace",
        SymbolKind.PACKAGE: "package",
        SymbolKind.CLASS: "class",
        SymbolKind.METHOD: "method",
        SymbolKind.PROPERTY: "property",
        SymbolKind.FIELD: "field",
        SymbolKind.CONSTRUCTOR: "constructor",
        SymbolKind.ENUM: "enum",
        SymbolKind.INTERFACE: "interface",
        SymbolKind.FUNCTION: "function",
        SymbolKind.VARIABLE: "variable",
        SymbolKind.CONSTANT: "constant",
        SymbolKind.STRING: "string",
        SymbolKind.NUMBER: "number",
        SymbolKind.BOOLEAN: "boolean",
        SymbolKind.ARRAY: "array",
        SymbolKind.OBJECT: "object",
        SymbolKind.KEY: "key",
        SymbolKind.NULL: "null",
        SymbolKind.ENUM_MEMBER: "enumMember",
        SymbolKind.STRUCT: "struct",
        SymbolKind.EVENT: "event",
        SymbolKind.OPERATOR: "operator",
        SymbolKind.TYPE_PARAMETER: "typeParameter",
    }
    return kind_names.get(kind, f"unknown({kind})")
