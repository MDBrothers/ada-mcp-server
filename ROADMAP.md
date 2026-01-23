# Ada MCP Server - Future Roadmap

This document outlines potential future enhancements for the Ada MCP Server.

## Near-term Enhancements

### 1. Body Stub Generation ⭐ Most Requested
**Priority: High**

Generate body stubs from Ada specifications - the #1 requested feature. ALS already supports this via code actions (`Generate Package Body`, `Generate Subprogram Body`).

**Option A: Dedicated tool (easier to discover)**
```python
@server.tool()
async def ada_generate_body(
    spec_file: str,
    output_file: str = None  # None = auto-detect from spec
) -> dict:
    """Generate body stub from an Ada specification file.
    
    Creates a .adb file with procedure/function stubs for all
    declarations in the spec that don't have implementations.
    """
```

**Option B: Enhance `ada_code_actions` with filtering**
```python
# Request code actions filtered to refactoring
result = await ada_code_actions(file, line, col, kind="refactor.rewrite")
# Returns: "Generate Package Body", "Generate Subprogram Body", etc.
```

**Returns:** Generated `.adb` content or workspace edits to apply.

---

### 2. Type Hierarchy Navigation
**Priority: High**

Ada's tagged types (OOP) benefit from hierarchy navigation. ALS supports `textDocument/prepareTypeHierarchy`.

```python
@server.tool()
async def ada_type_hierarchy(
    file: str,
    line: int,
    column: int,
    direction: str = "both"  # "supertypes", "subtypes", "both"
) -> dict:
    """Get type hierarchy for a tagged type.
    
    Example: "Show all types derived from Entity_Status"
    """
```

**Returns:** Tree of parent/child types with locations.

---

### 3. Alire Crate Search
**Priority: High**

Search for Alire crates without leaving the editor.

```python
@server.tool()
async def ada_alire_search(
    query: str,
    limit: int = 20
) -> dict:
    """Search Alire crates by name or description.
    
    Example: "What crates provide JSON support?"
    """
```

**Implementation:** Wrap `alr search --crates <query>` command.

---

### 4. Shared ALS Instance Support
**Priority: Medium**

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

### 5. Project-Aware File Discovery
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

### 6. Unused Import Detection
**Priority: Medium**

Detect `with` clauses that aren't actually used.

```python
@server.tool()
async def ada_unused_imports(file: str) -> dict:
    """Find unused with clauses in an Ada file.
    
    Returns list of imports that can be safely removed.
    """
```

**Implementation options:**
- Check ALS diagnostics for unused import warnings
- Use `gnatcheck` with appropriate rule
- Parse and analyze `with` vs actual usage

---

### 7. Semantic Code Search
**Priority: Medium**

Search for Ada constructs semantically:

```python
@server.tool()
async def ada_find_by_signature(
    parameter_type: str = None,
    return_type: str = None,
    kind: str = "all"  # "procedure", "function", "all"
) -> dict:
    """Find subprograms by signature pattern.
    
    Example: "Find all procedures that take Entity_ID parameter"
    """

@server.tool()
async def ada_find_types(pattern: str, kind: str = "all") -> dict:
    """Find type declarations matching a pattern.
    
    Args:
        pattern: Name pattern (supports wildcards)
        kind: "record", "tagged", "enum", "access", "all"
    """
```

---

## Medium-term Enhancements

### 8. SPARK/GNATprove Integration
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

### 9. GPR Validation
**Priority: Medium**

Validate GPR project files before attempting builds.

```python
@server.tool()
async def ada_validate_gpr(gpr_file: str) -> dict:
    """Check GPR file syntax and semantics.
    
    Returns errors/warnings about project configuration
    without running a full build.
    """
```

**Implementation:** Use `gprbuild -p -q` dry-run or parse GPR directly.

---

### 10. Generate Spec from Body
**Priority: Medium**

Reverse of body stub generation - extract a spec from implementation.

```python
@server.tool()
async def ada_generate_spec(body_file: str) -> dict:
    """Generate package specification from a body file.
    
    Extracts public declarations from .adb to create .ads
    """
```

---

### 11. Test Integration
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

### 12. Cross-Reference Database
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

### 13. Multi-Project Support
Support workspaces with multiple GPR projects, aggregate projects, and project hierarchies.

**Status:** ✅ Partially implemented - ALS pool supports multiple projects with LRU eviction.

### 14. Advanced Refactoring Tools
ALS already supports many refactorings via code actions. We could expose dedicated tools for:

- Extract subprogram
- Introduce parameter  
- Change signature
- Move to package
- Add/remove/reorder parameters
- Named parameters conversion

### 15. Code Generation
- Generate getters/setters for record types
- Generate equality/hash functions
- Generate stream attributes
- Convert between Ada versions (83 → 95 → 2012 → 2022)

### 16. Documentation Generation
- Generate AdaDoc comments
- Extract API documentation
- Generate package specifications from bodies

### 17. Performance Profiling
- Integration with gprof/perf
- Memory analysis tools
- Timing instrumentation

---

## Implementation Status

### Implemented ✅
| Feature | Tool | Notes |
|---------|------|-------|
| Go to definition | `ada_goto_definition` | |
| Find references | `ada_find_references` | |
| Hover/type info | `ada_hover` | |
| Document symbols | `ada_document_symbols` | |
| Workspace symbols | `ada_workspace_symbols` | |
| Diagnostics | `ada_diagnostics` | |
| Type definition | `ada_type_definition` | |
| Implementation (spec↔body) | `ada_implementation` | |
| Call hierarchy | `ada_call_hierarchy` | Incoming/outgoing calls |
| Dependency graph | `ada_dependency_graph` | With clause analysis |
| Code actions | `ada_code_actions` | Includes refactorings |
| Completions | `ada_completions` | |
| Signature help | `ada_signature_help` | |
| Rename symbol | `ada_rename_symbol` | Project-wide |
| Format file | `ada_format_file` | GNATformat |
| Get spec | `ada_get_spec` | Navigate to .ads |
| Build | `ada_build` | gprbuild integration |
| Alire info | `ada_alire_info` | Project metadata |
| Project info | `ada_project_info` | GPR parsing |
| Multi-project support | ALSPool | LRU eviction, 3 instances |
| Alire environment | auto | Toolchain from `alr printenv` |

### Next Priority 🎯
| Feature | Effort | Impact |
|---------|--------|--------|
| Body stub generation | Low | ⭐⭐⭐⭐⭐ |
| Type hierarchy | Medium | ⭐⭐⭐⭐ |
| Alire crate search | Low | ⭐⭐⭐ |
| Unused import detection | Medium | ⭐⭐⭐ |

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
