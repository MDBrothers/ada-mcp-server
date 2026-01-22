"""Diagnostics tool: get compiler errors and warnings."""

import logging
from typing import Any

from ada_mcp.als.client import ALSClient
from ada_mcp.als.types import DiagnosticSeverity
from ada_mcp.utils.uri import file_to_uri, uri_to_file

logger = logging.getLogger(__name__)


async def handle_diagnostics(
    client: ALSClient,
    file: str | None = None,
    severity: str = "all",
) -> dict[str, Any]:
    """
    Get compiler diagnostics (errors, warnings) for Ada files.

    Args:
        client: ALS client instance
        file: Absolute path to Ada file, or None for all files
        severity: Filter by severity - "error", "warning", "hint", or "all"

    Returns:
        Dict with diagnostics list and counts
    """
    # Get diagnostics from client's cache (populated via notifications)
    async with client._diagnostics_lock:
        all_diagnostics = dict(client._diagnostics)

    # Filter by file if specified
    if file:
        file_uri = file_to_uri(file)
        all_diagnostics = {uri: diags for uri, diags in all_diagnostics.items() if uri == file_uri}

    # Map severity filter to LSP severity values
    severity_filter = _get_severity_filter(severity)

    # Build result
    result_diagnostics = []
    error_count = 0
    warning_count = 0
    hint_count = 0

    for uri, diags in all_diagnostics.items():
        file_path = uri_to_file(uri)

        for diag in diags:
            # Filter by severity
            if severity_filter and diag.severity not in severity_filter:
                continue

            diag_severity = _severity_to_string(diag.severity)

            # Count by severity
            if diag.severity == DiagnosticSeverity.ERROR:
                error_count += 1
            elif diag.severity == DiagnosticSeverity.WARNING:
                warning_count += 1
            elif diag.severity in (DiagnosticSeverity.INFORMATION, DiagnosticSeverity.HINT):
                hint_count += 1

            result_diagnostics.append(
                {
                    "file": file_path,
                    "line": diag.range.start.line + 1,  # Convert to 1-based
                    "column": diag.range.start.character + 1,
                    "endLine": diag.range.end.line + 1,
                    "endColumn": diag.range.end.character + 1,
                    "severity": diag_severity,
                    "message": diag.message,
                    "code": diag.code,
                    "source": diag.source or "ada",
                }
            )

    return {
        "diagnostics": result_diagnostics,
        "errorCount": error_count,
        "warningCount": warning_count,
        "hintCount": hint_count,
        "totalCount": len(result_diagnostics),
    }


def _get_severity_filter(severity: str) -> set[DiagnosticSeverity] | None:
    """Get set of severity values to include based on filter string."""
    if severity == "all":
        return None  # Include all

    severity_map = {
        "error": {DiagnosticSeverity.ERROR},
        "warning": {DiagnosticSeverity.WARNING},
        "hint": {DiagnosticSeverity.HINT, DiagnosticSeverity.INFORMATION},
        "info": {DiagnosticSeverity.INFORMATION},
    }

    return severity_map.get(severity.lower())


def _severity_to_string(severity: DiagnosticSeverity) -> str:
    """Convert LSP severity to human-readable string."""
    return {
        DiagnosticSeverity.ERROR: "error",
        DiagnosticSeverity.WARNING: "warning",
        DiagnosticSeverity.INFORMATION: "info",
        DiagnosticSeverity.HINT: "hint",
    }.get(severity, "unknown")
