"""File URI handling utilities."""

from pathlib import Path
from urllib.parse import unquote, urlparse


def file_to_uri(file_path: str | Path) -> str:
    """
    Convert a file path to a file:// URI.

    Args:
        file_path: Absolute or relative file path

    Returns:
        File URI string (e.g., "file:///home/user/project/main.adb")
    """
    path = Path(file_path).resolve()
    # Use Path.as_uri() for proper encoding
    return path.as_uri()


def uri_to_file(uri: str) -> str:
    """
    Convert a file:// URI to a file path.

    Args:
        uri: File URI string

    Returns:
        Absolute file path string
    """
    parsed = urlparse(uri)

    if parsed.scheme != "file":
        raise ValueError(f"Expected file:// URI, got: {uri}")

    # Handle URL encoding
    path = unquote(parsed.path)

    # On Windows, remove leading slash from /C:/path
    # (not relevant for Linux but good for portability)
    if len(path) > 2 and path[0] == "/" and path[2] == ":":
        path = path[1:]

    return path


def normalize_uri(uri: str) -> str:
    """
    Normalize a file URI for consistent comparison.

    Args:
        uri: File URI string

    Returns:
        Normalized URI with resolved path
    """
    if uri.startswith("file://"):
        path = uri_to_file(uri)
        return file_to_uri(path)
    return uri
