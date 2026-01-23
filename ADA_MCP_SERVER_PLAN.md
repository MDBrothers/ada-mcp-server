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
- [x] goto_definition: single/multiple locations, null response, empty array
- [x] goto_definition: line/column conversion (1-based to 0-based)
- [x] goto_definition: ALS error handling
- [x] goto_definition: line zero, invalid inputs
- [x] hover: markdown content, plaintext, marked string array
- [x] hover: not found (null, empty)
- [x] hover: keyword, empty line
- [x] diagnostics: all files, single file, severity filtering
- [x] diagnostics: line number conversion
- [x] diagnostics: no errors, error filtering
- [x] Input validation: missing params, empty paths, invalid values
- [x] File path handling: relative paths, file:// URIs, normalization
- [x] All 26 unit tests passing with mocked ALS

**Integration Tests** (`scripts/test_phase1_integration.py`):
- [x] goto_definition: procedure call → spec
- [x] goto_definition: package name → spec  
- [x] goto_definition: with clause → spec
- [x] goto_definition: Ada.Text_IO → stdlib
- [x] goto_definition: local variable → declaration
- [x] goto_definition: keyword (no definition)
- [x] goto_definition: whitespace, end of file
- [x] goto_definition: non-existent file
- [x] goto_definition: line 0, very large line number
- [x] hover: procedure name, function call, variable
- [x] hover: type name, package name
- [x] hover: integer literal, parameter
- [x] hover: function in spec/body, keyword, empty line
- [x] hover: non-existent file
- [x] diagnostics: clean project, specific file
- [x] diagnostics: filter errors, filter warnings
- [x] diagnostics: non-existent file
- [x] type_definition: variable → type, parameter → type
- [x] type_definition: function name, keyword, non-existent file
- [x] implementation: spec → body, body function, package spec → body
- [x] implementation: variable, non-existent file
- [x] find_references: function Add, local variable
- [x] find_references: exclude declaration
- [x] document_symbols: main.adb, utils.ads
- [x] workspace_symbols: search 'Add', search 'Main'
- [x] All 47 integration tests passing with real ALS

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

### Phase 3: Project Intelligence ✅ COMPLETE

**Summary:** All 3 tools implemented with 15 unit tests + 7 integration tests passing.

#### 3.1: GPR File Parser ✅
- [x] Create `src/ada_mcp/tools/project.py` file  
- [x] Implement `parse_gpr_file()` function with source dirs, object dir, main units
- [x] Add unit tests (3 tests: basic, nonexistent, multiple sources)
- [x] Tested with `tests/fixtures/sample_project/sample.gpr`

#### 3.2: ada_project_info Tool ✅
- [x] Add `ada_project_info` to MCP server tool list
- [x] Implement `handle_project_info()` returning absolute paths
- [x] Add unit tests (3 tests: basic, absolute paths, nonexistent)
- [x] Add integration tests (2 tests passing)

#### 3.3 & 3.4: Call Hierarchy ✅
- [x] Add `ada_call_hierarchy` to MCP server tool list
- [x] Implement `handle_call_hierarchy()` with LSP callHierarchy APIs
- [x] Support outgoing, incoming, and both directions
- [x] Add unit tests (4 tests: outgoing, incoming, both, not found)
- [x] Add integration tests (3 tests passing)
- [x] Fixed Position serialization issue in `to_lsp_position()`

#### 3.5: Dependency Graph ✅
- [x] Add `ada_dependency_graph` to MCP server tool list
- [x] Implement `handle_dependency_graph()` parsing `with` clauses
- [x] Support single files and directories
- [x] Add unit tests (5 tests: single file, directory, multiple with, nonexistent, package body)
- [x] Add integration tests (2 tests passing)

**Test Results:**
- Unit tests: 15/15 passing (`tests/test_project.py`)
- Integration tests: 54/54 passing (7 new Phase 3 tests)
- Total: All tests passing ✅

**Files to modify:**
- `src/ada_mcp/server.py` (add tool)
- `src/ada_mcp/tools/project.py` (add handle_dependency_graph)
- `tests/test_project.py` (add test)
- `scripts/test_phase1_integration.py` (add test case)

**Test command:** `pytest tests/test_project.py::test_dependency_graph -v`

### Phase 4: Code Intelligence (Granular Tasks)

#### 4.1: Completions - Basic
**Goal:** Provide basic code completion suggestions.

**Tasks:**
- [ ] Create `src/ada_mcp/tools/refactoring.py` file
- [ ] Add `ada_completions` to MCP server tool list
- [ ] Implement `handle_completions()` using LSP `textDocument/completion`
- [ ] Return list of completion items with labels and kinds
- [ ] Add unit test with mocked ALS response

**Files to modify:**
- `src/ada_mcp/tools/refactoring.py` (create new)
- `src/ada_mcp/server.py` (add tool)
- `src/ada_mcp/tools/__init__.py` (add import)
- `tests/test_refactoring.py` (create new)

**Test command:** `pytest tests/test_refactoring.py::test_completions_basic -v`

#### 4.2: Completions - Context Parsing
**Goal:** Parse completion context for better suggestions.

**Tasks:**
- [ ] Extend `handle_completions()` to parse trigger characters
- [ ] Handle different completion contexts (dot, colon, etc.)
- [ ] Filter completions based on context
- [ ] Add unit tests for different contexts
- [ ] Add integration test with real completion scenarios

**Files to modify:**
- `src/ada_mcp/tools/refactoring.py` (modify handle_completions)
- `tests/test_refactoring.py` (add tests)
- `scripts/test_phase1_integration.py` (add test cases)

**Test command:** `pytest tests/test_refactoring.py -k "completions" -v`

#### 4.3: Signature Help
**Goal:** Show function signatures as you type.

**Tasks:**
- [ ] Add `ada_signature_help` to MCP server tool list
- [ ] Implement `handle_signature_help()` using LSP `textDocument/signatureHelp`
- [ ] Parse and return active parameter, signatures list
- [ ] Add unit test with mocked response
- [ ] Add integration test for function calls

**Files to modify:**
- `src/ada_mcp/server.py` (add tool)
- `src/ada_mcp/tools/refactoring.py` (add handle_signature_help)
- `tests/test_refactoring.py` (add test)
- `scripts/test_phase1_integration.py` (add test case)

**Test command:** `pytest tests/test_refactoring.py::test_signature_help -v`

#### 4.4: Code Actions
**Goal:** Provide quick fixes and refactoring suggestions.

**Tasks:**
- [ ] Add `ada_code_actions` to MCP server tool list
- [ ] Implement `handle_code_actions()` using LSP `textDocument/codeAction`
- [ ] Return list of available code actions
- [ ] Add unit test with mocked response
- [ ] Add integration test for common code actions

**Files to modify:**
- `src/ada_mcp/server.py` (add tool)
- `src/ada_mcp/tools/refactoring.py` (add handle_code_actions)
- `tests/test_refactoring.py` (add test)
- `scripts/test_phase1_integration.py` (add test case)

**Test command:** `pytest tests/test_refactoring.py::test_code_actions -v`

### Phase 5: Refactoring & Code Generation (Granular Tasks)

#### 5.1: Rename Symbol - Basic
**Goal:** Rename symbols with basic validation.

**Tasks:**
- [ ] Add `ada_rename_symbol` to MCP server tool list
- [ ] Implement `handle_rename_symbol()` using LSP `textDocument/rename`
- [ ] Validate new name (Ada identifier rules)
- [ ] Return workspace edits for all changes
- [ ] Add unit test with mocked response

**Files to modify:**
- `src/ada_mcp/server.py` (add tool)
- `src/ada_mcp/tools/refactoring.py` (add handle_rename_symbol)
- `tests/test_refactoring.py` (add test)

**Test command:** `pytest tests/test_refactoring.py::test_rename_basic -v`

#### 5.2: Rename Symbol - Apply Changes
**Goal:** Apply rename changes to files.

**Tasks:**
- [ ] Extend `handle_rename_symbol()` to apply workspace edits
- [ ] Handle file modifications safely
- [ ] Add integration test that actually renames a symbol
- [ ] Test with multiple files affected
- [ ] Add error handling for failed renames

**Files to modify:**
- `src/ada_mcp/tools/refactoring.py` (modify handle_rename_symbol)
- `tests/test_refactoring.py` (add integration test)
- `scripts/test_phase1_integration.py` (add test case)

**Test command:** `pytest tests/test_refactoring.py::test_rename_apply -v`

#### 5.3: Format File
**Goal:** Format Ada files using GNATformat.

**Tasks:**
- [ ] Add `ada_format_file` to MCP server tool list
- [ ] Implement `handle_format_file()` using LSP `textDocument/formatting`
- [ ] Return formatted text or apply changes
- [ ] Add unit test with mocked response
- [ ] Add integration test with actual formatting

**Files to modify:**
- `src/ada_mcp/server.py` (add tool)
- `src/ada_mcp/tools/refactoring.py` (add handle_format_file)
- `tests/test_refactoring.py` (add test)
- `scripts/test_phase1_integration.py` (add test case)

**Test command:** `pytest tests/test_refactoring.py::test_format_file -v`

#### 5.4: Spec Navigation
**Goal:** Navigate between spec and body files.

**Tasks:**
- [ ] Add `ada_get_spec` to MCP server tool list
- [ ] Implement `handle_get_spec()` that finds corresponding spec/body
- [ ] Use file naming conventions (.ads/.adb)
- [ ] Add unit test with file path logic
- [ ] Add integration test with real files

**Files to modify:**
- `src/ada_mcp/server.py` (add tool)
- `src/ada_mcp/tools/refactoring.py` (add handle_get_spec)
- `tests/test_refactoring.py` (add test)
- `scripts/test_phase1_integration.py` (add test case)

**Test command:** `pytest tests/test_refactoring.py::test_get_spec -v`

#### 5.5: Stub Generation
**Goal:** Generate body stubs from specs.

**Tasks:**
- [ ] Add `ada_stub_body` to MCP server tool list
- [ ] Implement `handle_stub_body()` using LSP `textDocument/implementation`
- [ ] Generate basic procedure/function bodies
- [ ] Add unit test with mocked response
- [ ] Add integration test that creates stub file

**Files to modify:**
- `src/ada_mcp/server.py` (add tool)
- `src/ada_mcp/tools/refactoring.py` (add handle_stub_body)
- `tests/test_refactoring.py` (add test)
- `scripts/test_phase1_integration.py` (add test case)

**Test command:** `pytest tests/test_refactoring.py::test_stub_body -v`

### Phase 6: Build & Project Management (Granular Tasks)

#### 6.1: Build Tool - Basic
**Goal:** Run GPRbuild and parse results.

**Tasks:**
- [ ] Create `src/ada_mcp/tools/build.py` file
- [ ] Add `ada_build` to MCP server tool list
- [ ] Implement `handle_build()` that runs `gprbuild`
- [ ] Parse build output for errors/warnings
- [ ] Return structured build results
- [ ] Add unit test with mocked subprocess

**Files to modify:**
- `src/ada_mcp/tools/build.py` (create new)
- `src/ada_mcp/server.py` (add tool)
- `src/ada_mcp/tools/__init__.py` (add import)
- `tests/test_build.py` (create new)

**Test command:** `pytest tests/test_build.py::test_build_basic -v`

#### 6.2: Build Tool - Error Parsing
**Goal:** Parse GPRbuild error messages.

**Tasks:**
- [ ] Extend `handle_build()` to parse error locations
- [ ] Convert file:line:column format to structured data
- [ ] Handle different error message formats
- [ ] Add unit tests for various error formats
- [ ] Add integration test with actual build errors

**Files to modify:**
- `src/ada_mcp/tools/build.py` (modify handle_build)
- `tests/test_build.py` (add tests)
- `scripts/test_phase1_integration.py` (add test case)

**Test command:** `pytest tests/test_build.py -k "build" -v`

#### 6.3: Alire Info Tool
**Goal:** Read Alire project information.

**Tasks:**
- [ ] Add `ada_alire_info` to MCP server tool list
- [ ] Implement `handle_alire_info()` that reads `alire.toml`
- [ ] Parse TOML and return project metadata
- [ ] Add unit test with sample alire.toml
- [ ] Add integration test with real Alire project

**Files to modify:**
- `src/ada_mcp/server.py` (add tool)
- `src/ada_mcp/tools/build.py` (add handle_alire_info)
- `tests/test_build.py` (add test)
- `scripts/test_phase1_integration.py` (add test case)

**Test command:** `pytest tests/test_build.py::test_alire_info -v`

#### 6.4: Multi-Project Support
**Goal:** Handle aggregate GPR projects.

**Tasks:**
- [ ] Extend GPR parser for aggregate projects
- [ ] Support multiple GPR files in one workspace
- [ ] Add project selection parameter to tools
- [ ] Add unit tests for aggregate parsing
- [ ] Add integration test with multi-project setup

**Files to modify:**
- `src/ada_mcp/tools/project.py` (modify GPR parser)
- `src/ada_mcp/tools/build.py` (add multi-project support)
- `tests/test_project.py` (add tests)
- `tests/test_build.py` (add tests)

**Test command:** `pytest tests/test_project.py::test_aggregate_project -v`

### Phase 7: Polish & Production (Granular Tasks)

#### 7.1: Error Recovery - ALS Restart
**Goal:** Handle ALS crashes gracefully.

**Tasks:**
- [ ] Add ALS health monitoring to `src/ada_mcp/als/process.py`
- [ ] Implement auto-restart on crash detection
- [ ] Add exponential backoff for restart attempts
- [ ] Add unit test for crash recovery
- [ ] Add integration test that kills ALS and verifies restart

**Files to modify:**
- `src/ada_mcp/als/process.py` (add health monitoring)
- `tests/test_als_process.py` (add test)

**Test command:** `pytest tests/test_als_process.py::test_als_restart -v`

#### 7.2: Performance Optimization - Caching
**Goal:** Add response caching for better performance.

**Tasks:**
- [ ] Extend `src/ada_mcp/utils/cache.py` with TTL caching
- [ ] Add cache decorators to expensive operations
- [ ] Cache invalidation on file changes
- [ ] Add cache metrics and monitoring
- [ ] Add unit tests for cache behavior

**Files to modify:**
- `src/ada_mcp/utils/cache.py` (extend caching)
- `src/ada_mcp/tools/navigation.py` (add caching)
- `tests/test_cache.py` (add tests)

**Test command:** `pytest tests/test_cache.py -v`

#### 7.3: Documentation - Tool Examples
**Goal:** Create comprehensive documentation.

**Tasks:**
- [ ] Update README.md with all tool examples
- [ ] Add usage examples for each MCP tool
- [ ] Document configuration options
- [ ] Add troubleshooting section
- [ ] Add performance benchmarks

**Files to modify:**
- `README.md` (comprehensive update)

**Test command:** Manual review of documentation

#### 7.4: CI/CD Pipeline - Final
**Goal:** Complete production CI/CD.

**Tasks:**
- [ ] Add release workflow to GitHub Actions
- [ ] Add PyPI publication on tag
- [ ] Add cross-platform testing (Linux/macOS/Windows)
- [ ] Add performance regression tests
- [ ] Add security scanning

**Files to modify:**
- `.github/workflows/ci.yml` (extend)
- `.github/workflows/release.yml` (create new)

**Test command:** CI passes on all platforms

#### 7.5: PyPI Publication
**Goal:** Publish to PyPI.

**Tasks:**
- [ ] Configure pyproject.toml for PyPI
- [ ] Add version management
- [ ] Create distribution packages
- [ ] Test installation from PyPI
- [ ] Add package metadata and classifiers

**Files to modify:**
- `pyproject.toml` (add PyPI config)

**Test command:** `pip install ada-mcp-server` works

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
| Phase 3: Project Intelligence | 2 days | ✅ COMPLETE |
| Phase 4: Code Intelligence | 2 days | ✅ COMPLETE |
| Phase 5: Refactoring | 3 days | ✅ COMPLETE |
| Phase 6: Build & Project | 2 days | ✅ COMPLETE |
| Phase 7: Polish | 3 days | ⏳ In Progress |

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
