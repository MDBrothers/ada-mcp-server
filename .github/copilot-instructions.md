# GitHub Copilot Instructions for Ada MCP Server

## Project Overview

This is an MCP (Model Context Protocol) server that wraps the Ada Language Server (ALS) to provide semantic Ada language features to AI coding agents. It acts as a bridge between AI tools and the Ada Language Server via the LSP protocol.

## Architecture

```
AI Agent (Copilot) <--MCP/JSON-RPC--> Ada MCP Server (Python) <--LSP/stdio--> Ada Language Server
```

## Technology Stack

- **Language**: Python 3.11+
- **Protocol**: MCP (Model Context Protocol) for AI agent communication
- **Backend**: Ada Language Server (ALS) via LSP
- **Async**: Uses `asyncio` and `anyio` for async operations
- **Validation**: Pydantic for data models

## Project Structure

- `src/ada_mcp/` - Main package
  - `__main__.py` - Entry point (`python -m ada_mcp`)
  - `server.py` - MCP server setup and tool registration
  - `als/` - Ada Language Server communication
    - `client.py` - LSP client wrapper
    - `process.py` - ALS process management
    - `types.py` - LSP type definitions
  - `tools/` - MCP tool implementations
    - `navigation.py` - goto_definition, find_references, hover
    - `symbols.py` - document/workspace symbols
    - `diagnostics.py` - error/warning retrieval
    - `project.py` - project info, call hierarchy
    - `refactoring.py` - rename, completions
  - `utils/` - Utility modules
    - `uri.py` - File URI handling
    - `position.py` - Line/column conversions (1-based to 0-based)
    - `cache.py` - Response caching
    - `errors.py` - Custom exceptions

## Coding Conventions

### Python Style

- Follow PEP 8 with line length of 100 characters
- Use type hints for all function signatures
- Use `async`/`await` for all I/O operations
- Prefer `dataclass` or Pydantic models for structured data
- Use `logging` module, not print statements

### LSP Protocol Notes

- LSP uses 0-based line and column numbers
- MCP tools expose 1-based line and column numbers (user-friendly)
- Always convert between them in the tools layer
- File URIs must use `file://` scheme

### Error Handling

- Wrap ALS communication in try/except blocks
- Return graceful error responses, don't crash
- Log errors with full context
- Use custom exception classes from `utils/errors.py`

### Testing

- Use pytest with pytest-asyncio
- Mock ALS client for unit tests
- Use fixtures in `tests/fixtures/` for integration tests
- Mark integration tests with `@pytest.mark.integration`

## Common Patterns

### Creating a new MCP tool

```python
from mcp.types import Tool, TextContent

@server.tool()
async def ada_new_tool(file: str, line: int, column: int) -> dict:
    """Description of what the tool does."""
    als = await get_als()
    
    # Convert 1-based to 0-based for LSP
    result = await als.send_request("textDocument/someMethod", {
        "textDocument": {"uri": path_to_uri(file)},
        "position": {"line": line - 1, "character": column - 1}
    })
    
    # Process and return result
    return {"found": bool(result), "data": result}
```

### LSP Request Pattern

```python
async def send_lsp_request(method: str, params: dict) -> Any:
    request = {
        "jsonrpc": "2.0",
        "id": self._next_id(),
        "method": method,
        "params": params
    }
    # Write to ALS stdin, read from stdout
```

## Key Dependencies

- `mcp` - Official MCP Python SDK
- `anyio` - Async compatibility layer
- `pydantic` - Data validation

## Environment Variables

- `ALS_PATH` - Path to Ada Language Server executable
- `ADA_PROJECT_FILE` - Path to .gpr project file
- `ADA_MCP_LOG_LEVEL` - Logging level (DEBUG, INFO, WARNING, ERROR)
- `ADA_MCP_TIMEOUT` - Request timeout in seconds

## References

- [MCP Specification](https://modelcontextprotocol.io/docs)
- [LSP Specification](https://microsoft.github.io/language-server-protocol/)
- [Ada Language Server](https://github.com/AdaCore/ada_language_server)
