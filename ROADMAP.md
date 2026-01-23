# Ada MCP Server - Future Roadmap

This document outlines potential future enhancements for the Ada MCP Server.

## Near-term Enhancements

### 1. Shared ALS Instance Support
**Priority: High**

Currently, the MCP server spawns its own Ada Language Server instance. This is wasteful when VS Code's AdaCore Ada extension is already running ALS.

**Potential approaches:**
- **LSP Proxy Mode**: Connect to an existing ALS via a socket/pipe instead of spawning a new process
- **VS Code Extension Bridge**: Create a companion VS Code extension that exposes the existing ALS to the MCP server
- **Named Pipe/Socket Configuration**: Allow configuring `ALS_SOCKET` to connect to an existing ALS instance

**Benefits:**
- Reduced memory footprint (ALS can use 500MB+ per instance)
- Shared project indexing state
- Consistent diagnostics between IDE and AI agent

**Configuration example:**
```json
{
  "ALS_MODE": "connect",  // "spawn" (default) or "connect"
  "ALS_SOCKET": "/tmp/als.sock"
}
```

---

### 2. `ada_stub_body` Tool
**Priority: Medium**

Generate body stubs from Ada specifications - useful for AI-assisted code generation.

```python
@server.tool()
async def ada_stub_body(spec_file: str) -> dict:
    """Generate body stub from an Ada specification file."""
```

**Returns:** Generated `.adb` content with procedure/function stubs.

---

### 3. Project-Aware File Discovery
**Priority: Medium**

Add tools to discover Ada project structure:

```python
@server.tool()
async def ada_list_sources() -> dict:
    """List all Ada source files in the current project."""

@server.tool()  
async def ada_list_units() -> dict:
    """List all compilation units (packages, procedures) in the project."""
```

---

### 4. Semantic Code Search
**Priority: Medium**

Search for Ada constructs semantically:

```python
@server.tool()
async def ada_find_types(pattern: str, kind: str = "all") -> dict:
    """Find type declarations matching a pattern.
    
    Args:
        pattern: Name pattern (supports wildcards)
        kind: "record", "tagged", "enum", "access", "all"
    """

@server.tool()
async def ada_find_subprograms(pattern: str) -> dict:
    """Find procedures/functions matching a pattern."""
```

---

## Medium-term Enhancements

### 5. SPARK/GNATprove Integration
**Priority: Medium**

Add tools for SPARK proof analysis:

```python
@server.tool()
async def ada_prove(file: str, level: int = 2) -> dict:
    """Run GNATprove on a file and return proof results."""

@server.tool()
async def ada_spark_status(file: str) -> dict:
    """Get SPARK status (SPARK_Mode, proof obligations) for a file."""
```

---

### 6. Test Integration
**Priority: Low**

Integration with AUnit test framework:

```python
@server.tool()
async def ada_run_tests(test_file: str = None) -> dict:
    """Run AUnit tests and return results."""

@server.tool()
async def ada_generate_test_stub(unit: str) -> dict:
    """Generate AUnit test stub for a package."""
```

---

### 7. Cross-Reference Database
**Priority: Low**

Expose ALI file information for deep code analysis:

```python
@server.tool()
async def ada_xref(identifier: str) -> dict:
    """Get complete cross-reference info from ALI files."""

@server.tool()
async def ada_dependencies(unit: str, direction: str = "both") -> dict:
    """Get unit dependencies (with/use clauses, semantic dependencies)."""
```

---

## Long-term Vision

### 8. Multi-Project Support
Support workspaces with multiple GPR projects, aggregate projects, and project hierarchies.

### 9. Refactoring Tools
- Extract subprogram
- Introduce parameter
- Change signature
- Move to package

### 10. Code Generation
- Generate getters/setters for record types
- Generate equality/hash functions
- Generate stream attributes
- Convert between Ada versions (83 → 95 → 2012 → 2022)

### 11. Documentation Generation
- Generate AdaDoc comments
- Extract API documentation
- Generate package specifications from bodies

### 12. Performance Profiling
- Integration with gprof/perf
- Memory analysis tools
- Timing instrumentation

---

## Configuration Enhancements

### Environment Variables (Planned)

| Variable | Description | Status |
|----------|-------------|--------|
| `ALS_PATH` | Path to ALS executable | ✅ Implemented |
| `ADA_PROJECT_FILE` | GPR project file | ✅ Implemented |
| `ADA_PROJECT_ROOT` | Project root directory | ✅ Implemented |
| `ADA_MCP_LOG_LEVEL` | Logging verbosity | ✅ Implemented |
| `ADA_MCP_TIMEOUT` | Request timeout | ✅ Implemented |
| `ALS_MODE` | "spawn" or "connect" | 🔲 Planned |
| `ALS_SOCKET` | Socket path for connect mode | 🔲 Planned |
| `ADA_MCP_CACHE_TTL` | Cache time-to-live | 🔲 Planned |
| `ADA_MCP_CACHE_SIZE` | Max cache entries | 🔲 Planned |

---

## Contributing

If you'd like to contribute to any of these features, please:
1. Open an issue to discuss the approach
2. Reference this roadmap in your PR
3. Add tests for new functionality

## Feedback

Have ideas for other features? Open an issue with the `enhancement` label.
