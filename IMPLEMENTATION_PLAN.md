# Ada MCP Server - Implementation Plan

This document provides granular implementation phases for the roadmap features.

---

## Phase 1: Body Stub Generation (1-2 days)
**Priority: HIGH | Impact: ⭐⭐⭐⭐⭐ | Effort: Low**

The most requested feature. ALS already provides this via code actions.

### 1.1 Research & Spike (2 hours)
- [ ] Test `ada_code_actions` on a spec file to see available actions
- [ ] Identify exact code action titles: "Generate Package Body", "Generate Subprogram Body"
- [ ] Understand the workspace edit format returned by ALS
- [ ] Determine if ALS requires `workspace/applyEdit` capability

### 1.2 Implement `ada_generate_body` Tool (4 hours)
**File:** `src/ada_mcp/tools/refactoring.py`

```python
async def handle_generate_body(
    client: ALSClient,
    spec_file: str,
    output_file: str | None = None,
) -> dict[str, Any]:
    """Generate body stub from spec file."""
```

**Steps:**
- [ ] Add tool registration in `server.py`
- [ ] Open spec file in ALS
- [ ] Request code actions at package declaration line
- [ ] Filter for "Generate Package Body" or "Generate Subprogram Body"
- [ ] Execute the code action command
- [ ] Return the generated content or file path

### 1.3 Handle Workspace Edits (2 hours)
- [ ] Implement `workspace/applyEdit` handler in `als/client.py`
- [ ] Write generated content to output file
- [ ] Handle case where body file already exists (update vs create)

### 1.4 Tests (2 hours)
**File:** `tests/test_generate_body.py`
- [ ] Test generating body from simple spec
- [ ] Test generating body with multiple subprograms
- [ ] Test update existing body (add missing stubs)
- [ ] Test error case: no subprograms to generate

### 1.5 Documentation
- [ ] Update README with new tool
- [ ] Add example usage

---

## Phase 2: Type Hierarchy (1-2 days)
**Priority: HIGH | Impact: ⭐⭐⭐⭐ | Effort: Medium**

Navigate tagged type inheritance trees.

### 2.1 Research LSP Protocol (1 hour)
- [ ] Review LSP 3.17 type hierarchy spec
- [ ] Test ALS support for `textDocument/prepareTypeHierarchy`
- [ ] Test `typeHierarchy/supertypes` and `typeHierarchy/subtypes`

### 2.2 Add Type Definitions (1 hour)
**File:** `src/ada_mcp/als/types.py`
```python
@dataclass
class TypeHierarchyItem:
    name: str
    kind: SymbolKind
    uri: str
    range: Range
    selectionRange: Range
    detail: str | None = None
    tags: list[int] | None = None
    data: Any | None = None
```

### 2.3 Implement `ada_type_hierarchy` Tool (3 hours)
**File:** `src/ada_mcp/tools/navigation.py`

```python
async def handle_type_hierarchy(
    client: ALSClient,
    file: str,
    line: int,
    column: int,
    direction: str = "both",  # "supertypes", "subtypes", "both"
) -> dict[str, Any]:
```

**Steps:**
- [ ] Call `textDocument/prepareTypeHierarchy` to get TypeHierarchyItem
- [ ] Based on direction, call `typeHierarchy/supertypes` and/or `typeHierarchy/subtypes`
- [ ] Recursively fetch full hierarchy tree
- [ ] Format response with file locations

### 2.4 Tool Registration (30 min)
**File:** `src/ada_mcp/server.py`
- [ ] Add tool definition with inputSchema
- [ ] Add case in `call_tool` handler

### 2.5 Tests (2 hours)
**File:** `tests/test_type_hierarchy.py`
- [ ] Create fixture with tagged type hierarchy
- [ ] Test supertypes navigation
- [ ] Test subtypes navigation
- [ ] Test both directions
- [ ] Test non-tagged type (should return empty/error)

---

## Phase 3: Alire Crate Search (0.5 days)
**Priority: HIGH | Impact: ⭐⭐⭐ | Effort: Low**

Simple wrapper around `alr search`.

### 3.1 Implement `ada_alire_search` Tool (2 hours)
**File:** `src/ada_mcp/tools/build.py`

```python
async def handle_alire_search(
    query: str,
    limit: int = 20,
) -> dict[str, Any]:
    """Search Alire crates."""
```

**Steps:**
- [ ] Run `alr search --crates <query>` via subprocess
- [ ] Parse output into structured format
- [ ] Include: crate name, version, description, website
- [ ] Handle "alr not found" gracefully

### 3.2 Parse Alire Output (1 hour)
- [ ] Handle different output formats (table vs JSON if available)
- [ ] Check if `alr search --format=json` is supported
- [ ] Fallback to parsing text output

### 3.3 Tool Registration (30 min)
- [ ] Add to server.py

### 3.4 Tests (1 hour)
- [ ] Mock subprocess for unit tests
- [ ] Test parsing various output formats
- [ ] Test empty results
- [ ] Test alr not installed

---

## Phase 4: Unused Import Detection (1 day)
**Priority: MEDIUM | Impact: ⭐⭐⭐ | Effort: Medium**

### 4.1 Research Options (2 hours)
- [ ] Check if ALS reports unused imports in diagnostics
- [ ] Test `gnatcheck` with `-rules +RUnused_With_Clauses`
- [ ] Evaluate static analysis approach

### 4.2 Option A: ALS Diagnostics (if supported)
**File:** `src/ada_mcp/tools/diagnostics.py`
- [ ] Filter diagnostics for "unused" or "not referenced" warnings
- [ ] Extract the import name from the diagnostic message

### 4.3 Option B: GNATcheck Integration (if needed)
**File:** `src/ada_mcp/tools/analysis.py` (new file)

```python
async def handle_unused_imports(
    file: str,
) -> dict[str, Any]:
    """Find unused with clauses."""
```

**Steps:**
- [ ] Run `gnatcheck -rules +RUnused_With_Clauses <file>`
- [ ] Parse output for unused import violations
- [ ] Return list with line numbers

### 4.4 Tests (2 hours)
- [ ] Create fixture with unused imports
- [ ] Test detection of simple unused import
- [ ] Test import used only in body (spec reports unused)
- [ ] Test all imports used (empty result)

---

## Phase 5: Project-Aware File Discovery (0.5 days)
**Priority: MEDIUM | Impact: ⭐⭐⭐ | Effort: Low**

### 5.1 Implement `ada_list_sources` (2 hours)
**File:** `src/ada_mcp/tools/project.py`

```python
async def handle_list_sources(
    gpr_file: str | None = None,
) -> dict[str, Any]:
    """List all Ada source files in project."""
```

**Steps:**
- [ ] Parse GPR for Source_Dirs
- [ ] Recursively find *.ads, *.adb files
- [ ] Optionally use `gprls -s` for accurate list
- [ ] Return with categorization (spec/body)

### 5.2 Implement `ada_list_units` (2 hours)
```python
async def handle_list_units(
    gpr_file: str | None = None,
) -> dict[str, Any]:
    """List all compilation units."""
```

**Steps:**
- [ ] Use `ada_document_symbols` on each source file
- [ ] Or parse ALI files for unit information
- [ ] Group by package hierarchy

### 5.3 Tests (1 hour)
- [ ] Test with sample project
- [ ] Test with nested source directories
- [ ] Test with excluded files

---

## Phase 6: GPR Validation (0.5 days)
**Priority: MEDIUM | Impact: ⭐⭐ | Effort: Low**

### 6.1 Implement `ada_validate_gpr` (3 hours)
**File:** `src/ada_mcp/tools/project.py`

```python
async def handle_validate_gpr(
    gpr_file: str,
) -> dict[str, Any]:
    """Validate GPR file syntax and semantics."""
```

**Steps:**
- [ ] Run `gprbuild -p -q -P <gpr_file> --dry-run` or similar
- [ ] Parse error/warning output
- [ ] Check for common issues:
  - Missing source directories
  - Invalid project references
  - Circular dependencies
- [ ] Return structured validation results

### 6.2 Tests (1 hour)
- [ ] Test valid GPR
- [ ] Test GPR with syntax error
- [ ] Test GPR with missing dependency

---

## Phase 7: Semantic Search by Signature (2 days)
**Priority: MEDIUM | Impact: ⭐⭐⭐ | Effort: High**

This is more complex - requires indexing.

### 7.1 Design Approach (2 hours)
- [ ] Option A: Workspace symbols + filtering (limited)
- [ ] Option B: Build index from document symbols
- [ ] Option C: Parse ALI files for signature info

### 7.2 Implement Indexing (4 hours)
**File:** `src/ada_mcp/utils/index.py` (new file)

```python
class SignatureIndex:
    """Index of subprogram signatures for semantic search."""
    
    async def build(self, client: ALSClient, gpr_file: str):
        """Build index from all project sources."""
    
    def find_by_parameter_type(self, type_name: str) -> list[SubprogramInfo]:
        """Find subprograms with parameter of given type."""
    
    def find_by_return_type(self, type_name: str) -> list[SubprogramInfo]:
        """Find functions returning given type."""
```

### 7.3 Implement `ada_find_by_signature` Tool (3 hours)
```python
async def handle_find_by_signature(
    client: ALSClient,
    parameter_type: str | None = None,
    return_type: str | None = None,
    kind: str = "all",
) -> dict[str, Any]:
```

### 7.4 Caching Strategy (2 hours)
- [ ] Cache index per project
- [ ] Invalidate on file changes
- [ ] Lazy loading for large projects

### 7.5 Tests (2 hours)
- [ ] Test find by parameter type
- [ ] Test find by return type
- [ ] Test combined search
- [ ] Test with no matches

---

## Phase 8: Generate Spec from Body (1 day)
**Priority: MEDIUM | Impact: ⭐⭐ | Effort: Medium**

### 8.1 Research (1 hour)
- [ ] Check if ALS has this capability
- [ ] Look at LAL_Refactor for relevant tools

### 8.2 Implement Extraction Logic (4 hours)
**File:** `src/ada_mcp/tools/refactoring.py`

```python
async def handle_generate_spec(
    client: ALSClient,
    body_file: str,
) -> dict[str, Any]:
    """Extract specification from body file."""
```

**Steps:**
- [ ] Parse body file symbols
- [ ] Identify public subprograms (those that should be in spec)
- [ ] Generate spec file content
- [ ] Handle existing spec (merge vs overwrite)

### 8.3 Tests (2 hours)
- [ ] Test simple procedure extraction
- [ ] Test with private subprograms (should not be in spec)
- [ ] Test with existing spec

---

## Implementation Order & Timeline

### Sprint 1 (Week 1)
| Day | Task | Phase |
|-----|------|-------|
| 1 | Body stub generation | Phase 1 |
| 2 | Body stub generation + tests | Phase 1 |
| 3 | Alire crate search | Phase 3 |
| 4 | Type hierarchy | Phase 2 |
| 5 | Type hierarchy + tests | Phase 2 |

### Sprint 2 (Week 2)
| Day | Task | Phase |
|-----|------|-------|
| 1 | Unused import detection | Phase 4 |
| 2 | Project file discovery | Phase 5 |
| 3 | GPR validation | Phase 6 |
| 4-5 | Semantic search | Phase 7 |

### Sprint 3 (Week 3)
| Day | Task | Phase |
|-----|------|-------|
| 1 | Generate spec from body | Phase 8 |
| 2-3 | Integration testing | All |
| 4-5 | Documentation & polish | All |

---

## Dependencies

```
Phase 1 (Body Gen) ─────────────────────────────────┐
                                                    │
Phase 2 (Type Hierarchy) ───────────────────────────┼─► Can be done in parallel
                                                    │
Phase 3 (Alire Search) ─────────────────────────────┘

Phase 4 (Unused Imports) ───► May depend on Phase 5 for project file list

Phase 5 (File Discovery) ───► Phase 7 depends on this for indexing

Phase 6 (GPR Validation) ───► Independent

Phase 7 (Semantic Search) ───► Depends on Phase 5

Phase 8 (Spec from Body) ───► May reuse patterns from Phase 1
```

---

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| ALS doesn't support type hierarchy | Fall back to parsing tagged type declarations manually |
| Code action execution requires workspace/applyEdit | Implement minimal applyEdit handler |
| Large projects slow for semantic search | Implement lazy indexing, limit results |
| GNATcheck not available | Make unused import detection optional |

---

## Success Criteria

- [ ] All 8 phases implemented with tests
- [ ] 95%+ test coverage on new code
- [ ] Documentation updated
- [ ] No regression in existing functionality
- [ ] Performance acceptable (<5s for most operations)

---

## Notes

- Each phase should be a separate PR
- Run full test suite before merging
- Update ROADMAP.md status after each phase
- Consider feature flags for experimental features
