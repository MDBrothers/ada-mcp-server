# Ada Language Server MCP - Implementation Plan

## Overview

Create a Model Context Protocol (MCP) server that wraps the Ada Language Server (ALS) to provide semantic Ada language features to AI coding agents like GitHub Copilot.

### Why This Tool Exists

AI agents working with Ada code currently face significant limitations:
- **No semantic understanding**: Text-based grep searches miss context
- **Slow error feedback**: Must build to detect issues
- **No navigation**: Can't jump to definitions or find usages
- **No type awareness**: Missing context about Ada's strong type system

### Solution

An MCP server that exposes ALS capabilities as tools, enabling AI agents to:
- Navigate semantically (definitions, references, implementations)
- Get real-time diagnostics without building
- Understand types, packages, and project structure
- Perform safe refactorings with full code awareness

---

## AI Agent Usage Guide

This section explains **how AI agents should use this MCP server** to effectively work with Ada code.

### Recommended Workflow for AI Agents

```
1. UNDERSTAND CONTEXT
   └─→ ada_document_symbols - Get file structure
   └─→ ada_project_info - Understand project layout
   └─→ ada_diagnostics - Check current errors

2. NAVIGATE CODE
   └─→ ada_goto_definition - Find where symbol is defined
   └─→ ada_find_references - Find all usages
   └─→ ada_type_definition - Find type declaration
   └─→ ada_implementation - Find body/implementation

3. UNDERSTAND SYMBOLS
   └─→ ada_hover - Get type info and documentation
   └─→ ada_signature_help - Get subprogram signatures
   └─→ ada_call_hierarchy - See who calls what

4. MAKE CHANGES
   └─→ ada_completions - Get context-aware suggestions
   └─→ ada_rename_symbol - Safely rename across project
   └─→ ada_format_file - Format code consistently

5. VERIFY CHANGES
   └─→ ada_diagnostics - Confirm no new errors
   └─→ ada_build - Full compilation check
```

### Tool Selection Guidelines for AI Agents

| AI Agent Task | Recommended Tools |
|--------------|-------------------|
| "What type is this variable?" | `ada_hover` |
| "Where is this defined?" | `ada_goto_definition` |
| "Where is this used?" | `ada_find_references` |
| "Show me the structure of this file" | `ada_document_symbols` |
| "Find all symbols named X" | `ada_workspace_symbols` |
| "Are there any errors?" | `ada_diagnostics` |
| "Rename this safely" | `ada_rename_symbol` |
| "What can I type here?" | `ada_completions` |
| "Show the spec for this body" | `ada_get_spec` |
| "Show the body for this spec" | `ada_implementation` |
| "What calls this procedure?" | `ada_call_hierarchy` |

### Best Practices for AI Agents

1. **Always check diagnostics after editing** - Ada is strongly typed; verify your changes compile
2. **Use hover before making assumptions** - Get accurate type information
3. **Use find_references before refactoring** - Understand the full impact
4. **Use document_symbols for orientation** - Understand file structure before diving in
5. **Prefer rename_symbol over find-replace** - It handles all usages correctly

---

## Architecture

```
┌─────────────────┐     MCP/JSON-RPC      ┌─────────────────┐
│   AI Agent      │ ◄──────────────────► │  Ada MCP Server │
│ (Copilot, etc.) │     (NDJSON/stdio)    │    (Python)     │
└─────────────────┘                       └────────┬────────┘
                                                   │
                                                   │ LSP/JSON-RPC
                                                   │ (stdio)
                                                   ▼
                                          ┌─────────────────┐
                                          │ Ada Language    │
                                          │ Server (ALS)    │
                                          └────────┬────────┘
                                                   │
                                                   ▼
                                          ┌─────────────────┐
                                          │ Ada Project     │
                                          │ (.gpr, .ads,    │
                                          │  .adb files)    │
                                          └─────────────────┘
```

### Components

| Component | Technology | Purpose |
|-----------|------------|---------|
| MCP Server | Python 3.11+ | Expose tools via MCP protocol |
| LSP Client | asyncio / lsprotocol | Communicate with ALS |
| ALS | Ada (GNAT) | Provide semantic analysis |
| Process Manager | asyncio.subprocess | Spawn/manage ALS lifecycle |

---

## MCP Tools Specification

### Phase 1: Core Navigation (Foundation)

These tools provide essential code navigation capabilities.

#### `ada_goto_definition`

Find the definition of a symbol at a given location.

**When AI should use this**: When clicking on a symbol name to see where it's declared.

```python
async def ada_goto_definition(file: str, line: int, column: int) -> dict:
    """
    file: Absolute path to Ada source file
    line: 1-based line number
    column: 1-based column number
    """
```

**Returns:**
```json
{
    "found": true,
    "file": "/path/to/definition.ads",
    "line": 42,
    "column": 4,
    "preview": "procedure Initialize (Config : Configuration);"
}
```

#### `ada_hover`

Get type information and documentation for a symbol.

**When AI should use this**: To understand what type a variable is, or what a procedure does.

```python
async def ada_hover(file: str, line: int, column: int) -> dict:
    """Get type info and documentation for symbol at location."""
```

**Returns:**
```json
{
    "found": true,
    "contents": "function Calculate_Total (Items : Item_Array) return Natural",
    "documentation": "Sums all item values in the array.",
    "kind": "function"
}
```

#### `ada_diagnostics`

Get compiler diagnostics (errors, warnings) for files.

**When AI should use this**: Before and after making changes to verify code compiles.

```python
async def ada_diagnostics(
    file: str | None = None,
    severity: str = "all"  # "error" | "warning" | "hint" | "all"
) -> dict:
    """Get diagnostics. If file is None, return all project diagnostics."""
```

**Returns:**
```json
{
    "diagnostics": [
        {
            "file": "/path/to/main.adb",
            "line": 15,
            "column": 10,
            "severity": "error",
            "message": "expected type \"Integer\", found type \"String\"",
            "code": "type-mismatch"
        }
    ],
    "errorCount": 1,
    "warningCount": 0,
    "hintCount": 0
}
```

---

### Phase 2: Enhanced Navigation

#### `ada_find_references`

Find all references to a symbol across the project.

**When AI should use this**: Before renaming or refactoring to understand impact.

```python
async def ada_find_references(
    file: str,
    line: int,
    column: int,
    include_declaration: bool = True
) -> dict:
    """Find all usages of the symbol at the given location."""
```

**Returns:**
```json
{
    "symbol": "Calculate_Total",
    "kind": "function",
    "references": [
        {"file": "/path/to/utils.ads", "line": 10, "column": 4, "is_definition": true},
        {"file": "/path/to/main.adb", "line": 25, "column": 12, "is_definition": false},
        {"file": "/path/to/tests.adb", "line": 8, "column": 8, "is_definition": false}
    ],
    "totalCount": 3
}
```

#### `ada_document_symbols`

Get all symbols defined in a file.

**When AI should use this**: To understand the structure of a file before working with it.

```python
async def ada_document_symbols(file: str) -> dict:
    """Get hierarchical list of all symbols in the file."""
```

**Returns:**
```json
{
    "file": "/path/to/utils.ads",
    "symbols": [
        {
            "name": "Utils",
            "kind": "package",
            "line": 1,
            "children": [
                {"name": "Item_Type", "kind": "type", "line": 5, "children": []},
                {"name": "Calculate_Total", "kind": "function", "line": 12, "children": []}
            ]
        }
    ]
}
```

#### `ada_workspace_symbols`

Search for symbols across the entire workspace.

**When AI should use this**: To find a symbol when you don't know which file it's in.

```python
async def ada_workspace_symbols(
    query: str,
    kind: str = "all",      # "package" | "procedure" | "function" | "type" | "variable" | "all"
    max_results: int = 50
) -> dict:
    """Search for symbols by name (supports partial/fuzzy matching)."""
```

**Returns:**
```json
{
    "query": "Config",
    "symbols": [
        {"name": "Configuration", "kind": "type", "file": "/path/to/config.ads", "line": 8},
        {"name": "Config_Manager", "kind": "package", "file": "/path/to/managers.ads", "line": 1},
        {"name": "Load_Config", "kind": "procedure", "file": "/path/to/utils.ads", "line": 45}
    ],
    "totalCount": 3
}
```

#### `ada_type_definition`

Find the type definition for a symbol.

**When AI should use this**: To find where a type is defined, not just where a variable is declared.

```python
async def ada_type_definition(file: str, line: int, column: int) -> dict:
    """Find the type definition for the symbol at location."""
```

**Returns:**
```json
{
    "found": true,
    "file": "/path/to/types.ads",
    "line": 23,
    "column": 4,
    "preview": "type Configuration is record ... end record;"
}
```

#### `ada_implementation`

Find the implementation/body for a declaration.

**When AI should use this**: To jump from a spec (.ads) to the body (.adb).

```python
async def ada_implementation(file: str, line: int, column: int) -> dict:
    """Find the implementation/body for a declaration."""
```

**Returns:**
```json
{
    "found": true,
    "file": "/path/to/utils.adb",
    "line": 45,
    "column": 4,
    "preview": "function Calculate_Total (Items : Item_Array) return Natural is ..."
}
```

---

### Phase 3: Project Intelligence

#### `ada_project_info`

Get information about the Ada project structure.

**When AI should use this**: To understand project layout and configuration.

```python
async def ada_project_info() -> dict:
    """Get project structure, source dirs, dependencies."""
```

**Returns:**
```json
{
    "projectFile": "/path/to/project.gpr",
    "projectName": "My_Project",
    "sourceDirs": ["/path/to/src", "/path/to/include"],
    "objectDir": "/path/to/obj",
    "execDir": "/path/to/bin",
    "mainUnits": ["main.adb"],
    "dependencies": ["gnatcoll", "xmlada"],
    "adaVersion": "Ada2012"
}
```

#### `ada_call_hierarchy`

Get incoming/outgoing calls for a subprogram.

**When AI should use this**: To understand call relationships before refactoring.

```python
async def ada_call_hierarchy(
    file: str,
    line: int,
    column: int,
    direction: str = "both"  # "incoming" | "outgoing" | "both"
) -> dict:
    """Get call hierarchy for subprogram at location."""
```

**Returns:**
```json
{
    "symbol": "Process_Data",
    "kind": "procedure",
    "incoming": [
        {"name": "Main", "file": "/path/to/main.adb", "line": 12},
        {"name": "Run_Tests", "file": "/path/to/tests.adb", "line": 45}
    ],
    "outgoing": [
        {"name": "Validate_Input", "file": "/path/to/utils.ads", "line": 8},
        {"name": "Log_Message", "file": "/path/to/logger.ads", "line": 15}
    ]
}
```

#### `ada_dependency_graph`

Get package dependency information.

**When AI should use this**: To understand module relationships and avoid circular dependencies.

```python
async def ada_dependency_graph(package: str | None = None) -> dict:
    """Get dependency graph. If package is None, return full project graph."""
```

**Returns:**
```json
{
    "packages": [
        {
            "name": "Main",
            "file": "/path/to/main.adb",
            "depends_on": ["Utils", "Config", "Ada.Text_IO"],
            "depended_by": []
        },
        {
            "name": "Utils",
            "file": "/path/to/utils.ads",
            "depends_on": ["Config"],
            "depended_by": ["Main", "Tests"]
        }
    ]
}
```

---

### Phase 4: Code Intelligence

#### `ada_completions`

Get completion suggestions at a location.

**When AI should use this**: When writing code and need context-aware suggestions.

```python
async def ada_completions(
    file: str,
    line: int,
    column: int,
    trigger: str | None = None  # Trigger character like "." or "'"
) -> dict:
    """Get completion suggestions at location."""
```

**Returns:**
```json
{
    "completions": [
        {
            "label": "Calculate_Total",
            "kind": "function",
            "detail": "function (Items : Item_Array) return Natural",
            "documentation": "Sum all item values",
            "insertText": "Calculate_Total"
        },
        {
            "label": "Clear_Items",
            "kind": "procedure",
            "detail": "procedure (Container : in Out Item_List)",
            "insertText": "Clear_Items"
        }
    ],
    "isIncomplete": false
}
```

#### `ada_signature_help`

Get signature help for subprogram calls.

**When AI should use this**: When filling in parameters for a procedure/function call.

```python
async def ada_signature_help(file: str, line: int, column: int) -> dict:
    """Get parameter hints for subprogram at cursor."""
```

**Returns:**
```json
{
    "signatures": [
        {
            "label": "procedure Put_Line (File : File_Type; Item : String)",
            "parameters": [
                {"label": "File : File_Type", "documentation": "The output file"},
                {"label": "Item : String", "documentation": "The text to write"}
            ],
            "activeParameter": 1
        }
    ]
}
```

#### `ada_code_actions`

Get available code actions at a location.

**When AI should use this**: To discover automatic fixes or refactorings available.

```python
async def ada_code_actions(
    file: str,
    start_line: int,
    start_column: int,
    end_line: int,
    end_column: int
) -> dict:
    """Get available code actions for the selection/location."""
```

**Returns:**
```json
{
    "actions": [
        {
            "title": "Add missing 'with' clause for Ada.Text_IO",
            "kind": "quickfix",
            "isPreferred": true
        },
        {
            "title": "Extract to procedure",
            "kind": "refactor.extract"
        },
        {
            "title": "Generate body stub",
            "kind": "refactor.stub"
        }
    ]
}
```

---

### Phase 5: Refactoring & Code Generation

#### `ada_rename_symbol`

Rename a symbol across the entire project.

**When AI should use this**: To safely rename any identifier with all references updated.

```python
async def ada_rename_symbol(
    file: str,
    line: int,
    column: int,
    new_name: str,
    preview: bool = True  # If true, return changes without applying
) -> dict:
    """Rename symbol at location to new_name."""
```

**Returns:**
```json
{
    "oldName": "Process_Data",
    "newName": "Handle_Input",
    "changes": [
        {"file": "/path/to/utils.ads", "line": 12, "oldText": "Process_Data", "newText": "Handle_Input"},
        {"file": "/path/to/utils.adb", "line": 45, "oldText": "Process_Data", "newText": "Handle_Input"},
        {"file": "/path/to/main.adb", "line": 28, "oldText": "Process_Data", "newText": "Handle_Input"}
    ],
    "totalChanges": 3,
    "applied": false
}
```

#### `ada_format_file`

Format an Ada source file.

**When AI should use this**: After making changes to ensure consistent formatting.

```python
async def ada_format_file(
    file: str,
    options: dict | None = None  # Formatting options
) -> dict:
    """Format the specified Ada file."""
```

**Returns:**
```json
{
    "file": "/path/to/main.adb",
    "formatted": true,
    "changes": 15
}
```

#### `ada_get_spec`

Get the specification for a body, or find corresponding spec file.

**When AI should use this**: To navigate from body (.adb) to spec (.ads).

```python
async def ada_get_spec(file: str, line: int | None = None, column: int | None = None) -> dict:
    """Get specification for body at location, or find spec file."""
```

**Returns:**
```json
{
    "found": true,
    "specFile": "/path/to/utils.ads",
    "line": 12,
    "column": 4,
    "preview": "function Calculate_Total (Items : Item_Array) return Natural;"
}
```

#### `ada_stub_body`

Generate a body stub from a specification.

**When AI should use this**: When implementing a spec and need the body skeleton.

```python
async def ada_stub_body(file: str, line: int, column: int) -> dict:
    """Generate body stub for spec at location."""
```

**Returns:**
```json
{
    "generated": true,
    "stubCode": "function Calculate_Total (Items : Item_Array) return Natural is\nbegin\n   return 0;  --  TODO: Implement\nend Calculate_Total;",
    "targetFile": "/path/to/utils.adb",
    "insertLine": 45
}
```

---

### Phase 6: Build & Project Management

#### `ada_build`

Build the Ada project and return results.

**When AI should use this**: For full compilation check after significant changes.

```python
async def ada_build(
    target: str | None = None,  # Specific target or None for default
    clean: bool = False         # Clean before build
) -> dict:
    """Build the project and return compilation results."""
```

**Returns:**
```json
{
    "success": false,
    "exitCode": 1,
    "errors": [
        {
            "file": "/path/to/main.adb",
            "line": 25,
            "column": 10,
            "message": "missing \"end Main;\"",
            "severity": "error"
        }
    ],
    "warnings": [],
    "buildTime": 2.3
}
```

#### `ada_alire_info`

Get Alire project information (if using Alire).

**When AI should use this**: To understand project dependencies and configuration.

```python
async def ada_alire_info() -> dict:
    """Get Alire-specific project information."""
```

**Returns:**
```json
{
    "isAlireProject": true,
    "crateName": "my_project",
    "version": "0.1.0",
    "dependencies": [
        {"name": "gnatcoll", "version": "^24.0.0"},
        {"name": "xmlada", "version": "^24.0.0"}
    ],
    "buildProfile": "development",
    "toolchain": "gnat_native=14.2.1"
}
```

---

## Implementation Phases & Deliverables

### Phase 1: Foundation ✅ COMPLETE
Core infrastructure and basic navigation tools.

**Deliverables:**
- [x] MCP server skeleton with stdio transport
- [x] ALS process spawning and lifecycle management
- [x] LSP client with request/response handling
- [x] Basic error handling and logging
- [x] `ada_goto_definition` tool
- [x] `ada_hover` tool  
- [x] `ada_diagnostics` tool
- [x] Unit tests with mocked ALS
- [x] Integration tests with real ALS

**Test Criteria:**
- [x] Server starts and responds to MCP handshake
- [x] Can navigate to definition in sample project
- [x] Hover returns type information
- [x] Diagnostics reported for files with errors

**Unit Tests** (`tests/test_phase1_unit.py`):
- [ ] goto_definition: single/multiple locations, null response, empty array
- [ ] goto_definition: line/column conversion (1-based to 0-based)
- [ ] goto_definition: ALS error handling
- [ ] hover: markdown content, plaintext, marked string array
- [ ] hover: not found (null, empty)
- [ ] diagnostics: all files, single file, severity filtering
- [ ] diagnostics: line number conversion
- [ ] Input validation: missing params, empty paths, invalid values
- [ ] File path handling: relative paths, file:// URIs, normalization

**Integration Tests** (`scripts/test_phase1_integration.py`):
- [ ] goto_definition: procedure call → spec
- [ ] goto_definition: package name → spec  
- [ ] goto_definition: with clause → spec
- [ ] goto_definition: Ada.Text_IO → stdlib
- [ ] goto_definition: local variable → declaration
- [ ] goto_definition: keyword (no definition)
- [ ] goto_definition: whitespace, end of file
- [ ] goto_definition: non-existent file
- [ ] goto_definition: line 0, very large line number
- [ ] hover: procedure name, function call, variable
- [ ] hover: type name, package name
- [ ] hover: integer literal, parameter
- [ ] hover: keyword, empty line
- [ ] hover: non-existent file
- [ ] diagnostics: clean project, specific file
- [ ] diagnostics: filter errors, filter warnings
- [ ] diagnostics: non-existent file

**Test Fixtures:**
- `tests/fixtures/sample_project/` - Clean Ada project
- `tests/fixtures/error_project/` - Project with intentional errors

---

### Phase 2: Enhanced Navigation ✅ COMPLETE
Full navigation capabilities for code exploration.

**Deliverables:**
- [x] `ada_find_references` tool
- [x] `ada_document_symbols` tool
- [x] `ada_workspace_symbols` tool
- [x] `ada_type_definition` tool
- [x] `ada_implementation` tool
- [x] Integration tests for all tools

**Test Criteria:**
- [x] Find references returns all usages across files
- [x] Document symbols shows hierarchical structure
- [x] Workspace symbols finds symbols by partial name
- [x] Type definition navigates to type declaration
- [x] Implementation navigates from spec to body

---

### Phase 3: Project Intelligence
Project-level understanding and analysis.

**Deliverables:**
- [ ] `ada_project_info` tool
- [ ] `ada_call_hierarchy` tool
- [ ] `ada_dependency_graph` tool
- [ ] GPR file parsing for project info
- [ ] Package dependency analysis

**Test Criteria:**
- [ ] Project info returns accurate source directories
- [ ] Call hierarchy shows incoming/outgoing calls
- [ ] Dependency graph detects circular dependencies
- [ ] Works with multi-project setups

---

### Phase 4: Code Intelligence
Smart code assistance and suggestions.

**Deliverables:**
- [ ] `ada_completions` tool
- [ ] `ada_signature_help` tool
- [ ] `ada_code_actions` tool
- [ ] Context-aware completion filtering
- [ ] Parameter hint support

**Test Criteria:**
- [ ] Completions include relevant symbols only
- [ ] Signature help shows active parameter
- [ ] Code actions offer appropriate fixes
- [ ] Performance < 200ms for completions

---

### Phase 5: Refactoring & Code Generation
Safe code modifications and generation.

**Deliverables:**
- [ ] `ada_rename_symbol` tool
- [ ] `ada_format_file` tool
- [ ] `ada_get_spec` tool
- [ ] `ada_stub_body` tool
- [ ] Preview mode for all refactorings
- [ ] Undo support via change tracking

**Test Criteria:**
- [ ] Rename updates all references correctly
- [ ] Formatting matches GNATformat style
- [ ] Spec/body navigation works bidirectionally
- [ ] Stub generation produces compilable code

---

### Phase 6: Build & Project Management
Build integration and advanced project features.

**Deliverables:**
- [ ] `ada_build` tool
- [ ] `ada_alire_info` tool
- [ ] Build output parsing
- [ ] Alire manifest reading
- [ ] Multi-project support

**Test Criteria:**
- [ ] Build errors parsed correctly
- [ ] Alire projects detected automatically
- [ ] Build results match `gprbuild` output
- [ ] Works with aggregate projects

---

### Phase 7: Polish & Production
Production readiness and documentation.

**Deliverables:**
- [ ] Comprehensive error recovery
- [ ] ALS crash auto-restart
- [ ] Performance optimization (caching)
- [ ] Full documentation with examples
- [ ] CI/CD pipeline
- [ ] PyPI publication

**Test Criteria:**
- [ ] Survives ALS crashes gracefully
- [ ] Response time < 500ms for navigation
- [ ] Documentation covers all tools
- [ ] Works on Linux, macOS, Windows

---

## Project Structure

```
ada-mcp-server/
├── pyproject.toml
├── README.md
├── ADA_MCP_SERVER_PLAN.md
├── src/
│   └── ada_mcp/
│       ├── __init__.py
│       ├── __main__.py      # Entry point
│       ├── server.py         # MCP server setup
│       ├── als/
│       │   ├── __init__.py
│       │   ├── client.py     # LSP client
│       │   ├── process.py    # ALS lifecycle
│       │   └── types.py      # LSP type definitions
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── navigation.py # goto, references, hover
│       │   ├── symbols.py    # document/workspace symbols
│       │   ├── diagnostics.py# error/warning retrieval
│       │   ├── project.py    # project info, call hierarchy
│       │   ├── intelligence.py # completions, signatures
│       │   └── refactoring.py# rename, format, stubs
│       └── utils/
│           ├── __init__.py
│           ├── uri.py        # File URI handling
│           ├── position.py   # Line/column conversions
│           └── cache.py      # Response caching
├── tests/
│   ├── conftest.py           # pytest fixtures
│   ├── test_server.py
│   ├── test_navigation.py
│   ├── test_symbols.py
│   └── fixtures/
│       └── sample_project/   # Test Ada project
└── scripts/
    ├── test_integration.py   # E2E integration tests
    └── test_als_client.py    # ALS client tests
```

---

## Configuration

### MCP Server Configuration (VS Code settings.json)

```json
{
  "mcpServers": {
    "ada": {
      "command": "python",
      "args": ["-m", "ada_mcp"],
      "env": {
        "ALS_PATH": "/path/to/ada_language_server",
        "ADA_PROJECT_FILE": "project.gpr",
        "ADA_MCP_LOG_LEVEL": "INFO"
      }
    }
  }
}
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ALS_PATH` | `ada_language_server` | Path to ALS executable |
| `ADA_PROJECT_FILE` | Auto-detect | GPR project file |
| `ADA_MCP_LOG_LEVEL` | `INFO` | Logging level |
| `ADA_MCP_TIMEOUT` | `30` | Request timeout (seconds) |
| `ADA_MCP_CACHE_TTL` | `5` | Cache TTL (seconds) |

---

## Key Dependencies

```toml
[project]
name = "ada-mcp-server"
version = "0.1.0"
description = "MCP server wrapping Ada Language Server for AI agents"
requires-python = ">=3.11"
dependencies = [
    "mcp>=1.0.0",              # Official MCP Python SDK
    "lsprotocol>=2023.0.0",    # LSP type definitions
    "anyio>=4.0.0",            # Async compatibility layer
    "pydantic>=2.0.0",         # Data validation
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "ruff>=0.3.0",             # Linting
    "mypy>=1.9.0",             # Type checking
]

[project.scripts]
ada-mcp = "ada_mcp.__main__:main"
```

---

## ALS Installation

The Ada Language Server can be obtained via:

```bash
# Option 1: Alire (recommended)
alr get ada_language_server
alr build --release

# Option 2: Pre-built from GitHub releases
# https://github.com/AdaCore/ada_language_server/releases

# Option 3: GNAT Studio installation includes ALS

# Option 4: VS Code Ada extension (already installed)
# Usually at: ~/.vscode/extensions/adacore.ada-*/x64/linux/ada_language_server
```

---

## Alternative Configuration: Using uvx

For isolation, you can use uvx instead of pip:

```json
{
  "mcpServers": {
    "ada": {
      "command": "uvx",
      "args": ["ada-mcp-server"],
      "env": {
        "ALS_PATH": "ada_language_server"
      }
    }
  }
}
```

---

## Testing Strategy

### Test Levels

1. **Unit Tests**: Mock ALS client, test tool logic
2. **Integration Tests**: Real ALS, sample projects
3. **E2E Tests**: Full MCP protocol over stdio

### Sample Test Projects

```
tests/fixtures/
├── sample_project/      # Basic single-package project
│   ├── sample.gpr
│   ├── main.adb
│   ├── utils.ads
│   └── utils.adb
├── multi_package/       # Parent/child packages
│   ├── multi.gpr
│   └── src/
│       ├── parent.ads
│       ├── parent.adb
│       └── parent-child.ads
├── alire_project/       # With alire.toml
│   ├── alire.toml
│   ├── project.gpr
│   └── src/
├── error_project/       # Contains intentional errors
└── large_project/       # Stress test (~100 files)
```

### Unit Test Example

```python
# tests/test_navigation.py
import pytest
from unittest.mock import AsyncMock
from ada_mcp.tools.navigation import handle_goto_definition

@pytest.fixture
def mock_als():
    """Create a mock ALS client."""
    client = AsyncMock()
    return client

@pytest.mark.asyncio
async def test_goto_definition_found(mock_als):
    """Test successful goto definition."""
    mock_als.send_request.return_value = [{
        "uri": "file:///project/src/utils.ads",
        "range": {
            "start": {"line": 41, "character": 3},
            "end": {"line": 41, "character": 15}
        }
    }]
    
    result = await handle_goto_definition(mock_als, {
        "file": "/project/src/main.adb",
        "line": 10,
        "column": 5
    })
    
    assert result["found"] is True
    assert result["file"] == "/project/src/utils.ads"
    assert result["line"] == 42  # 1-based (LSP is 0-based)
    assert result["column"] == 4

@pytest.mark.asyncio
async def test_goto_definition_not_found(mock_als):
    """Test when symbol has no definition."""
    mock_als.send_request.return_value = None
    
    result = await handle_goto_definition(mock_als, {
        "file": "/project/src/main.adb",
        "line": 10,
        "column": 5
    })
    
    assert result["found"] is False
```

### Running Tests

```bash
# Unit tests (fast, no ALS needed)
pytest tests/ -m "not integration"

# Integration tests (needs ALS)
pytest tests/ -m integration

# All tests
pytest tests/

# With coverage
pytest tests/ --cov=ada_mcp --cov-report=html
```

---

## Success Criteria

### Functionality
- [ ] All Phase 1-6 tools implemented and working
- [ ] All tools return accurate, usable results
- [ ] Handles edge cases gracefully

### Performance
- [ ] Navigation queries < 500ms
- [ ] Completions < 200ms
- [ ] Server startup < 5s

### Reliability
- [ ] Survives ALS crashes with auto-restart
- [ ] No memory leaks on long sessions
- [ ] Clean shutdown on SIGTERM

### Documentation
- [ ] README with quick start guide
- [ ] Tool reference with examples
- [ ] AI agent usage guide
- [ ] Troubleshooting section

### Distribution
- [ ] Published to PyPI as `ada-mcp-server`
- [ ] Works with pip install
- [ ] Docker image available

---

## Timeline Estimate

| Phase | Effort | Status |
|-------|--------|--------|
| Phase 1: Foundation | 3 days | ✅ COMPLETE |
| Phase 2: Enhanced Navigation | 2 days | ✅ COMPLETE |
| Phase 3: Project Intelligence | 2 days | ⏳ Pending |
| Phase 4: Code Intelligence | 2 days | ⏳ Pending |
| Phase 5: Refactoring | 3 days | ⏳ Pending |
| Phase 6: Build & Project | 2 days | ⏳ Pending |
| Phase 7: Polish | 3 days | ⏳ Pending |

**Total: ~2.5 weeks** for full implementation

---

## Resources

- [MCP Specification](https://modelcontextprotocol.io/docs)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Ada Language Server](https://github.com/AdaCore/ada_language_server)
- [LSP Specification](https://microsoft.github.io/language-server-protocol/)
- [Alire Package Manager](https://alire.ada.dev/)

---

## Open Questions

1. **File synchronization** - How to handle files open in editor vs. disk?
   - Option: Support `textDocument/didChange` for open files
   - Option: Always read from disk (simpler but may be stale)

2. **Incremental updates** - Should we support `textDocument/didChange`?
   - Pros: More accurate for unsaved changes
   - Cons: Complexity, need to track document versions

3. **Multiple projects** - How to handle multi-root workspaces?
   - Option: One ALS per project root
   - Option: Single ALS with multiple workspace folders

4. **ALS version compatibility** - Which versions to support?
   - Target: ALS 24.x and newer (Alire versions)
   - Test matrix in CI

5. **Performance** - Cache strategy for large projects?
   - TTL-based cache for symbols, diagnostics
   - Invalidate on file changes
