"""Build and project management tools for Ada MCP server.

Provides tools for:
- Building Ada projects with GPRbuild
- Parsing build errors
- Reading Alire project information
"""

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore

from ada_mcp.als.process import get_alire_environment

logger = logging.getLogger(__name__)


# GPRbuild error line pattern: file.adb:line:column: message
GPRBUILD_ERROR_PATTERN = re.compile(
    r"^(.+?):(\d+):(\d+):\s*(?:(error|warning|note|info))?\s*:?\s*(.*)$", re.IGNORECASE
)


def _parse_gprbuild_output(output: str) -> list[dict[str, Any]]:
    """Parse gprbuild output for errors and warnings.

    Args:
        output: Raw gprbuild output

    Returns:
        List of parsed diagnostic messages
    """
    diagnostics = []

    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue

        match = GPRBUILD_ERROR_PATTERN.match(line)
        if match:
            file_path, line_num, col_num, severity, message = match.groups()

            # Normalize severity
            if severity:
                severity = severity.lower()
                if severity == "note" or severity == "info":
                    severity = "hint"
            else:
                # Default to error if no severity specified
                severity = "error"

            diagnostics.append(
                {
                    "file": file_path,
                    "line": int(line_num),
                    "column": int(col_num),
                    "severity": severity,
                    "message": message,
                }
            )

    return diagnostics


async def handle_build(
    gpr_file: str | None = None,
    target: str | None = None,
    clean: bool = False,
    extra_args: list[str] | None = None,
) -> dict[str, Any]:
    """Handle ada_build tool request.

    Args:
        gpr_file: Path to GPR project file (auto-detect if not provided)
        target: Specific build target (main unit name)
        clean: If True, clean before building
        extra_args: Additional arguments to pass to gprbuild

    Returns:
        Dictionary with build results
    """
    # Find GPR file
    if gpr_file:
        gpr_path = Path(gpr_file)
    else:
        # Try to find from environment or current directory
        env_gpr = os.environ.get("ADA_PROJECT_FILE")
        if env_gpr:
            gpr_path = Path(env_gpr)
        else:
            # Search in current directory
            gpr_files = list(Path.cwd().glob("*.gpr"))
            if not gpr_files:
                return {
                    "success": False,
                    "error": "No GPR project file found",
                    "errors": [],
                    "warnings": [],
                }
            gpr_path = gpr_files[0]

    if not gpr_path.exists():
        return {
            "success": False,
            "error": f"GPR file not found: {gpr_path}",
            "errors": [],
            "warnings": [],
        }

    # Get project directory and check for Alire environment
    project_dir = gpr_path.parent
    alire_env = await get_alire_environment(project_dir)
    if alire_env:
        logger.info(f"Using Alire environment for build in {project_dir}")

    # Build command
    cmd = ["gprbuild", "-P", str(gpr_path)]

    if clean:
        # Run gprclean first
        clean_cmd = ["gprclean", "-P", str(gpr_path)]
        try:
            clean_proc = await asyncio.create_subprocess_exec(
                *clean_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=alire_env,
            )
            await clean_proc.wait()
        except FileNotFoundError:
            pass  # gprclean not available, continue anyway

    if target:
        cmd.append(target)

    if extra_args:
        cmd.extend(extra_args)

    # Run gprbuild with Alire environment if available
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=alire_env,
        )
        stdout, stderr = await proc.communicate()

        output = stdout.decode("utf-8", errors="replace")
        error_output = stderr.decode("utf-8", errors="replace")
        combined_output = output + "\n" + error_output

        # Parse diagnostics
        diagnostics = _parse_gprbuild_output(combined_output)

        errors = [d for d in diagnostics if d["severity"] == "error"]
        warnings = [d for d in diagnostics if d["severity"] == "warning"]
        hints = [d for d in diagnostics if d["severity"] == "hint"]

        return {
            "success": proc.returncode == 0,
            "exit_code": proc.returncode,
            "errors": errors,
            "warnings": warnings,
            "hints": hints,
            "error_count": len(errors),
            "warning_count": len(warnings),
            "gpr_file": str(gpr_path),
            "output": combined_output if proc.returncode != 0 else "",
        }

    except FileNotFoundError:
        return {
            "success": False,
            "error": "gprbuild not found in PATH",
            "errors": [],
            "warnings": [],
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "errors": [],
            "warnings": [],
        }


async def handle_alire_info(
    project_dir: str | None = None,
) -> dict[str, Any]:
    """Handle ada_alire_info tool request.

    Args:
        project_dir: Directory containing alire.toml (defaults to cwd)

    Returns:
        Dictionary with Alire project information
    """
    if project_dir:
        root = Path(project_dir)
    else:
        root = Path.cwd()

    alire_file = root / "alire.toml"

    if not alire_file.exists():
        return {
            "is_alire_project": False,
            "error": f"No alire.toml found in {root}",
        }

    try:
        with open(alire_file, "rb") as f:
            data = tomllib.load(f)

        # Extract project info
        name = data.get("name", "")
        version = data.get("version", "")
        description = data.get("description", "")
        authors = data.get("authors", [])
        maintainers = data.get("maintainers", [])
        licenses = data.get("licenses", [])
        website = data.get("website", "")
        tags = data.get("tags", [])

        # Extract dependencies
        deps = data.get("depends-on", [])
        dependencies = []
        for dep in deps:
            if isinstance(dep, dict):
                for dep_name, dep_version in dep.items():
                    dependencies.append(
                        {
                            "name": dep_name,
                            "version": str(dep_version) if dep_version else "*",
                        }
                    )

        # Extract build profile
        build_profiles = data.get("build-profiles", {})

        # Extract GPR externals
        gpr_externals = data.get("gpr-externals", {})

        # Extract GPR set externals
        gpr_set_externals = data.get("gpr-set-externals", {})

        # Extract executables
        executables = data.get("executables", [])

        # Extract project files
        project_files = data.get("project-files", [])

        return {
            "is_alire_project": True,
            "name": name,
            "version": version,
            "description": description,
            "authors": authors,
            "maintainers": maintainers,
            "licenses": licenses,
            "website": website,
            "tags": tags,
            "dependencies": dependencies,
            "build_profiles": build_profiles,
            "gpr_externals": gpr_externals,
            "gpr_set_externals": gpr_set_externals,
            "executables": executables,
            "project_files": project_files,
            "alire_file": str(alire_file),
        }

    except Exception as e:
        return {
            "is_alire_project": False,
            "error": f"Failed to parse alire.toml: {e}",
        }
