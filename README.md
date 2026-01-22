# Ada MCP Server

An MCP (Model Context Protocol) server that wraps the Ada Language Server (ALS) to provide semantic Ada language features to AI coding agents like GitHub Copilot.

## Features

- **Semantic Navigation**: Go to definition, find references, hover information
- **Symbol Search**: Document and workspace symbol search
- **Diagnostics**: Real-time compiler errors and warnings
- **Project Intelligence**: GPR project parsing, call hierarchy
- **Completions**: Context-aware code completions

## Prerequisites

1. **Ada Language Server (ALS)** - Install via one of:
   ```bash
   # Option 1: Alire (recommended)
   alr get ada_language_server
   cd ada_language_server*
   alr build --release
   
   # Option 2: Pre-built from GitHub releases
   # https://github.com/AdaCore/ada_language_server/releases
   ```

2. **Python 3.11+**

## Installation

```bash
# From PyPI (when published)
pip install ada-mcp-server

# From source
git clone https://github.com/ada-mcp/ada-mcp-server
cd ada-mcp-server
pip install -e .
```

## Usage

### VS Code Configuration

Add to your `settings.json`:

```json
{
  "mcpServers": {
    "ada": {
      "command": "ada-mcp",
      "env": {
        "ALS_PATH": "/path/to/ada_language_server",
        "ADA_PROJECT_FILE": "my_project.gpr"
      }
    }
  }
}
```

### Using uvx (isolated execution)

```json
{
  "mcpServers": {
    "ada": {
      "command": "uvx",
      "args": ["ada-mcp-server"]
    }
  }
}
```

### Direct Execution

```bash
# Run the server
ada-mcp

# Or via Python module
python -m ada_mcp
```

## Available Tools

| Tool | Description |
|------|-------------|
| `ada_goto_definition` | Navigate to symbol definition |
| `ada_find_references` | Find all references to a symbol |
| `ada_hover` | Get type info and documentation |
| `ada_diagnostics` | Get compiler errors/warnings |
| `ada_document_symbols` | List symbols in a file |
| `ada_workspace_symbols` | Search symbols across workspace |
| `ada_project_info` | Get project structure info |
| `ada_completions` | Get code completions |

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `ALS_PATH` | `ada_language_server` | Path to ALS executable |
| `ADA_PROJECT_FILE` | Auto-detect | GPR project file path |
| `ADA_MCP_LOG_LEVEL` | `INFO` | Logging verbosity |
| `ADA_MCP_TIMEOUT` | `30` | Request timeout (seconds) |

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linter
ruff check src/

# Type checking
mypy src/
```

## Testing

### Unit Tests (CI)

Unit tests with mocked ALS run in GitHub Actions CI:

```bash
pytest tests/test_phase1_unit.py -v
```

These tests validate tool logic, input handling, and error cases without requiring the actual Ada Language Server.

### Integration Tests (Local Only)

Integration tests require the Ada Language Server binary and must be run locally:

```bash
# Set ALS path (or ensure it's in PATH)
export ALS_PATH=/path/to/ada_language_server

# Run integration tests
python scripts/test_phase1_integration.py
```

**Why can't integration tests run in CI?**

The Ada Language Server (ALS) is a compiled binary that requires:
- The GNAT toolchain or pre-built binaries from AdaCore
- Platform-specific executables (Linux/Windows/macOS)
- Significant disk space and build time if compiling from source

For full test coverage, run integration tests locally before pushing changes.

## Continuous Integration

GitHub Actions runs on every push and PR:

| Job | Description |
|-----|-------------|
| **test** | Unit tests with mocked ALS |
| **lint** | Code style (ruff check + format) |
| **mypy** | Static type checking |

**CI Limitations:**
- ❌ Cannot test actual ALS communication
- ❌ Cannot verify LSP protocol handling with real server
- ✅ Validates code quality, imports, and mocked behavior

## License

MIT License - see [LICENSE](LICENSE) for details.
