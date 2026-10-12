# Ada MCP Server

[![CI](https://github.com/ada-mcp/ada-mcp-server/workflows/CI/badge.svg)](https://github.com/ada-mcp/ada-mcp-server/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An MCP (Model Context Protocol) server that wraps the Ada Language Server (ALS) to provide semantic Ada language features to AI coding agents like GitHub Copilot.

## Why Ada MCP Server?

AI agents working with Ada code face significant limitations without semantic understanding:

| Without This Tool | With Ada MCP Server |
|-------------------|---------------------|
| Text-based grep searches miss context | Semantic navigation to exact definitions |
| Must build to detect type errors | Real-time diagnostics without compilation |
| Can't jump to definitions or usages | Full code navigation (definitions, references, implementations) |
| No awareness of Ada's strong types | Type information via hover and completions |

## Features

- **🧭 Semantic Navigation**: Go to definition, find references, type definitions, implementations
- **🔍 Symbol Search**: Document and workspace symbol search with filtering
- **⚠️ Diagnostics**: Real-time compiler errors and warnings  
- **📁 Project Intelligence**: GPR project parsing, call hierarchy, dependency graphs
- **✨ Code Intelligence**: Context-aware completions, signature help
- **🔧 Refactoring**: Safe symbol renaming, code formatting
- **🏗️ Build Integration**: GPRbuild integration, Alire support
- **💪 Reliability**: Auto-restart on crashes with exponential backoff
- **⚡ Performance**: TTL-based caching for faster responses

## Prerequisites

### 1. Ada Language Server (ALS)

Install via one of these methods:

```bash
# Option 1: Alire (recommended)
alr get ada_language_server
cd ada_language_server*
alr build --release
# Binary will be at ./bin/ada_language_server

# Option 2: Pre-built from GitHub releases
# https://github.com/AdaCore/ada_language_server/releases

# Option 3: VS Code Ada extension (usually already installed)
# Found at: ~/.vscode/extensions/adacore.ada-*/x64/linux/ada_language_server
```

### 2. Python 3.11+

```bash
python --version  # Should be 3.11 or higher
```

## Installation

```bash
# From PyPI
pip install ada-mcp-server

# From source
git clone https://github.com/ada-mcp/ada-mcp-server
cd ada-mcp-server
pip install -e .

# With uvx (isolated environment)
uvx --from ada-mcp-server ada-mcp
```

## Quick Start

### VS Code / Copilot Configuration

Add to your VS Code `settings.json`:

```json
{
  "mcpServers": {
    "ada": {
      "command": "ada-mcp",
      "env": {
        "ALS_PATH": "/path/to/ada_language_server",
        "ADA_PROJECT_ROOT": "/path/to/your/ada/project"
      }
    }
  }
}
```

### Using uvx (Recommended for Isolation)

```json
{
  "mcpServers": {
    "ada": {
      "command": "uvx",
      "args": ["--from", "ada-mcp-server", "ada-mcp"],
      "env": {
        "ALS_PATH": "ada_language_server",
        "ADA_PROJECT_FILE": "project.gpr"
      }
    }
  }
}
```

### Direct Execution

```bash
# Set environment
export ALS_PATH=/path/to/ada_language_server
export ADA_PROJECT_ROOT=/path/to/project

# Run the server
ada-mcp

# Or via Python module
python -m ada_mcp
```

---

## Available Tools

### Navigation Tools

| Tool | Description |
|------|-------------|
| `ada_goto_definition` | Navigate to symbol definition |
| `ada_find_references` | Find all references to a symbol |
| `ada_type_definition` | Navigate to a symbol's type definition |
| `ada_implementation` | Navigate from spec to body |
| `ada_hover` | Get type info and documentation |
| `ada_get_spec` | Navigate from body to spec |

### Symbol Tools

| Tool | Description |
|------|-------------|
| `ada_document_symbols` | List all symbols in a file (outline) |
| `ada_workspace_symbols` | Search symbols across workspace |

### Diagnostics & Build

| Tool | Description |
|------|-------------|
| `ada_diagnostics` | Get compiler errors and warnings |
| `ada_build` | Build project with GPRbuild |
| `ada_alire_info` | Get Alire project information |

### Code Intelligence

| Tool | Description |
|------|-------------|
| `ada_completions` | Get context-aware completions |
| `ada_signature_help` | Get function signature hints |
| `ada_code_actions` | Get available quick fixes |

### Project Tools

| Tool | Description |
|------|-------------|
| `ada_project_info` | Get project structure info |
| `ada_call_hierarchy` | Get incoming/outgoing calls |
| `ada_dependency_graph` | Get package dependencies |

### Refactoring

| Tool | Description |
|------|-------------|
| `ada_rename_symbol` | Rename symbol across project |
| `ada_format_file` | Format Ada source file |

---

## Tool Examples

### ada_goto_definition

Navigate to where a symbol is defined.

```json
{
  "file": "/project/src/main.adb",
  "line": 10,
  "column": 12
}
```

**Response:**
```json
{
  "found": true,
  "file": "/project/src/utils.ads",
  "line": 25,
  "column": 4,
  "preview": "procedure Process_Data (Input : String);"
}
```

### ada_find_references

Find all usages of a symbol across the project.

```json
{
  "file": "/project/src/utils.ads",
  "line": 25,
  "column": 12,
  "include_declaration": true
}
```

**Response:**
```json
{
  "symbol": "Process_Data",
  "references": [
    {"file": "/project/src/utils.ads", "line": 25, "column": 12, "isDefinition": true},
    {"file": "/project/src/main.adb", "line": 10, "column": 4, "isDefinition": false},
    {"file": "/project/src/tests.adb", "line": 8, "column": 8, "isDefinition": false}
  ],
  "totalCount": 3
}
```

### ada_hover

Get type information and documentation for a symbol.

```json
{
  "file": "/project/src/main.adb",
  "line": 15,
  "column": 8
}
```

**Response:**
```json
{
  "found": true,
  "contents": "function Calculate_Sum (A, B : Integer) return Integer",
  "documentation": "Calculate the sum of two integers.",
  "range": {"start": {"line": 15, "column": 4}, "end": {"line": 15, "column": 17}}
}
```

### ada_diagnostics

Get compiler errors and warnings.

```json
{
  "file": "/project/src/main.adb",
  "severity": "error"
}
```

**Response:**
```json
{
  "diagnostics": [
    {
      "file": "/project/src/main.adb",
      "line": 12,
      "column": 10,
      "severity": "error",
      "message": "expected type \"Integer\", found type \"String\""
    }
  ],
  "errorCount": 1,
  "warningCount": 0,
  "hintCount": 0
}
```

### ada_document_symbols

Get all symbols in a file (outline view).

```json
{
  "file": "/project/src/utils.ads"
}
```

**Response:**
```json
{
  "file": "/project/src/utils.ads",
  "symbols": [
    {
      "name": "Utils",
      "kind": "package",
      "line": 1,
      "children": [
        {"name": "Process_Data", "kind": "procedure", "line": 10, "children": []},
        {"name": "Calculate_Sum", "kind": "function", "line": 15, "children": []}
      ]
    }
  ]
}
```

### ada_completions

Get context-aware code completions.

```json
{
  "file": "/project/src/main.adb",
  "line": 20,
  "column": 10,
  "trigger": "."
}
```

**Response:**
```json
{
  "completions": [
    {
      "label": "Process_Data",
      "kind": "procedure",
      "detail": "procedure (Input : String)",
      "insertText": "Process_Data"
    },
    {
      "label": "Calculate_Sum",
      "kind": "function",
      "detail": "function (A, B : Integer) return Integer",
      "insertText": "Calculate_Sum"
    }
  ],
  "isIncomplete": false
}
```

### ada_rename_symbol

Rename a symbol across the entire project.

```json
{
  "file": "/project/src/utils.ads",
  "line": 10,
  "column": 12,
  "new_name": "Handle_Data",
  "preview": true
}
```

**Response:**
```json
{
  "oldName": "Process_Data",
  "newName": "Handle_Data",
  "changes": [
    {"file": "/project/src/utils.ads", "line": 10, "oldText": "Process_Data", "newText": "Handle_Data"},
    {"file": "/project/src/utils.adb", "line": 25, "oldText": "Process_Data", "newText": "Handle_Data"},
    {"file": "/project/src/main.adb", "line": 12, "oldText": "Process_Data", "newText": "Handle_Data"}
  ],
  "totalChanges": 3,
  "applied": false
}
```

### ada_build

Build the project with GPRbuild.

```json
{
  "clean": false
}
```

**Response:**
```json
{
  "success": true,
  "exitCode": 0,
  "errors": [],
  "warnings": [],
  "buildTime": 2.5
}
```

### ada_project_info

Get project structure information.

```json
{}
```

**Response:**
```json
{
  "projectFile": "/project/project.gpr",
  "projectName": "My_Project",
  "sourceDirs": ["/project/src"],
  "objectDir": "/project/obj",
  "execDir": "/project/bin",
  "mainUnits": ["main.adb"]
}
```

### ada_call_hierarchy

Get call relationships for a subprogram.

```json
{
  "file": "/project/src/utils.adb",
  "line": 25,
  "column": 12,
  "direction": "both"
}
```

**Response:**
```json
{
  "symbol": "Process_Data",
  "kind": "procedure",
  "incoming": [
    {"name": "Main", "file": "/project/src/main.adb", "line": 12}
  ],
  "outgoing": [
    {"name": "Validate_Input", "file": "/project/src/validators.ads", "line": 8}
  ]
}
```

---

## AI Agent Usage Guide

### Recommended Workflow

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

### Tool Selection Guidelines

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

### Best Practices

1. **Always check diagnostics after editing** - Ada is strongly typed; verify your changes compile
2. **Use hover before making assumptions** - Get accurate type information
3. **Use find_references before refactoring** - Understand the full impact
4. **Use document_symbols for orientation** - Understand file structure before diving in
5. **Prefer rename_symbol over find-replace** - It handles all usages correctly

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ALS_PATH` | `ada_language_server` | Path to ALS executable |
| `ADA_PROJECT_FILE` | Auto-detect | GPR project file path |
| `ADA_PROJECT_ROOT` | Current directory | Project root directory |
| `ADA_MCP_LOG_LEVEL` | `INFO` | Logging verbosity (DEBUG, INFO, WARNING, ERROR) |
| `ADA_MCP_TIMEOUT` | `30` | Request timeout in seconds |
| `ADA_MCP_CACHE_TTL` | `5` | Cache time-to-live in seconds |

### Logging

Set `ADA_MCP_LOG_LEVEL` to adjust verbosity:

```bash
# Debug mode (verbose)
export ADA_MCP_LOG_LEVEL=DEBUG

# Production mode (errors only)
export ADA_MCP_LOG_LEVEL=ERROR
```

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

### Reliability Features

- **Auto-restart**: If ALS crashes, the server automatically restarts it with exponential backoff
- **Health monitoring**: Background task monitors ALS process health
- **Response caching**: TTL-based caching reduces redundant ALS queries

---

## Development

```bash
# Clone repository
git clone https://github.com/ada-mcp/ada-mcp-server
cd ada-mcp-server

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linter
ruff check src/

# Format code
ruff format src/

# Type checking
mypy src/
```

### Project Structure

```
ada-mcp-server/
├── src/ada_mcp/
│   ├── __main__.py      # Entry point
│   ├── server.py        # MCP server setup
│   ├── als/             # ALS communication
│   │   ├── client.py    # LSP client
│   │   ├── process.py   # ALS lifecycle & health monitoring
│   │   └── types.py     # LSP type definitions
│   ├── tools/           # MCP tool implementations
│   │   ├── navigation.py
│   │   ├── symbols.py
│   │   ├── diagnostics.py
│   │   ├── project.py
│   │   ├── refactoring.py
│   │   └── build.py
│   └── utils/           # Utilities
│       ├── cache.py     # Response caching
│       ├── position.py  # Line/column conversions
│       └── uri.py       # File URI handling
├── tests/               # Unit tests
└── scripts/             # Integration test scripts
```

## Testing

### Unit Tests (CI)

Unit tests with mocked ALS run in GitHub Actions:

```bash
pytest tests/ -v
```

### Integration Tests (Local Only)

Integration tests require the actual Ada Language Server:

```bash
# Set ALS path
export ALS_PATH=/path/to/ada_language_server

# Run integration tests
python scripts/test_phase1_integration.py
```

---

## Troubleshooting

### ALS not found

```
Error: FileNotFoundError: ada_language_server
```

**Solution**: Set `ALS_PATH` to the full path of the ALS executable:

```bash
export ALS_PATH=/home/user/.local/bin/ada_language_server
```

### No GPR file found

```
Warning: No GPR project file found. Disabling ALS indexing...
```

**Solution**: Set `ADA_PROJECT_FILE` or ensure your project has a `.gpr` file:

```bash
export ADA_PROJECT_FILE=my_project.gpr
```

### ALS crashes repeatedly

The server will attempt to restart ALS with exponential backoff (up to 5 attempts). Check:

1. ALS version compatibility (use ALS 24.x or newer)
2. GPR file validity
3. Available system memory

### Slow responses

Try reducing cache TTL for fresher results:

```bash
export ADA_MCP_CACHE_TTL=2
```

Or increase it for better performance on stable codebases:

```bash
export ADA_MCP_CACHE_TTL=30
```

### Debug logging

Enable debug logging for troubleshooting:

```bash
export ADA_MCP_LOG_LEVEL=DEBUG
ada-mcp 2>&1 | tee mcp-debug.log
```

---

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass (`pytest`)
5. Submit a pull request

## License

MIT License - see [LICENSE](LICENSE) for details.

## Related Projects

- [Ada Language Server](https://github.com/AdaCore/ada_language_server) - The underlying LSP server
- [MCP Specification](https://modelcontextprotocol.io/docs) - Model Context Protocol documentation
- [Alire](https://alire.ada.dev/) - Ada package manager
