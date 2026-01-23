"""Position conversion utilities for LSP (0-based) to user (1-based) coordinates."""

from ada_mcp.als.types import Position


def to_lsp_position(line: int, column: int) -> dict[str, int]:
    """
    Convert 1-based user coordinates to 0-based LSP position dict.

    Args:
        line: 1-based line number
        column: 1-based column number

    Returns:
        LSP Position dict (0-based) with 'line' and 'character' keys
    """
    return {"line": line - 1, "character": column - 1}


def from_lsp_position(position: Position) -> tuple[int, int]:
    """
    Convert 0-based LSP position to 1-based user coordinates.

    Args:
        position: LSP Position (0-based)

    Returns:
        Tuple of (line, column) in 1-based coordinates
    """
    return (position.line + 1, position.character + 1)


def from_lsp_position_dict(position: dict[str, int]) -> tuple[int, int]:
    """
    Convert 0-based LSP position dict to 1-based user coordinates.

    Args:
        position: Dict with 'line' and 'character' keys (0-based)

    Returns:
        Tuple of (line, column) in 1-based coordinates
    """
    return (position["line"] + 1, position["character"] + 1)
