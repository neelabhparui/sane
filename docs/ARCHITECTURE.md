# S.A.N.E. Architecture & Design Rationale

**Document Version:** 1.0.0  
**Status:** Approved  
**Author:** S.A.N.E. Core Engineering Team  

---

## 1. Executive Summary

S.A.N.E. (**Semantic Agent Navigation Engine**) is a local, token-efficient, progressive-disclosure code navigation engine and Model Context Protocol (MCP) server for AI coding agents. 

Rather than treating code navigation as generic semantic search / RAG (which typically embeds arbitrary 500-token chunks and dumps whole files into an agent's context), S.A.N.E. models the exploration process on **how senior human engineers navigate codebases in modern IDEs**:

```text
What high-level concept am I looking for?
        ↓ [search_semantic]
Which files/symbols implement it?
        ↓ [get_context]
What does the relevant documentation say and what are the key symbols?
        ↓ [get_skeleton]
What is the structural contract of this file (with bodies redacted)?
        ↓ [get_symbol_code]
What is the exact implementation of this target symbol?
        ↓ [find_usages]
Where is this symbol called across the repository?
```

This sequence prevents LLM context exhaustion, reducing navigation tokens by **70% to 90%** compared to naive `grep` and raw file reading.

---

## 2. Architectural Layers

```text
                       ┌─────────────────────────────┐
                       │  Claude / Cursor / Copilot  │
                       └──────────────┬──────────────┘
                                      │ stdio JSON-RPC (MCP)
                              ┌───────▼────────┐
                              │   MCP Server   │ (Strict stdout/stderr separation)
                              └───────┬────────┘
                                      │
               ┌──────────────────────▼──────────────────────┐
               │              Application Services           │
               │                                              │
               │ Search  Context  Skeleton  Symbol  Usages   │
               └───────────────┬──────────────────────────────┘
                               │
              ┌────────────────▼────────────────┐
              │       Retrieval / Resolver      │
              │  exact + FTS5 + rank fusion     │
              └────────────────┬────────────────┘
                               │
                  ┌────────────▼────────────┐
                  │    SQLite (WAL Mode)    │
                  │ files / symbols / docs  │
                  │ occurrences / edges     │
                  └────────────▲────────────┘
                               │
               ┌───────────────┴────────────────┐
               │       Incremental Indexer      │
               │ discovery / parsing / resolve │
               └───────────────▲────────────────┘
                               │
            ┌──────────────────┴───────────────────┐
            │          Language Adapters           │
            │  Python / Java / Kotlin / Markdown   │
            └──────────────────────────────────────┘
```

### 2.1 The Invariant Boundary Rule
> **Nothing inside `indexing`, `parsing`, `storage`, `retrieval`, or `rendering` knows that MCP exists.**

The MCP server (`sane_nav.mcp`) and the CLI (`sane_nav.cli`) are strictly thin adapter layers invoking common application services (`McpToolService`). This makes all functionality equally testable via unit tests, headless CLI commands, and JSON-RPC agents.

---

## 3. Storage Model & SQLite Concurrency

S.A.N.E. stores all state in `.sane/index.db` using **SQLite with Write-Ahead Logging (WAL)**:

```sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
```

### 3.1 Concurrency Model
- **Readers**: Multiple MCP clients (e.g. Claude Code CLI and Cursor running concurrently) maintain concurrent, non-blocking read transactions.
- **Writer**: All index writes are serialized through a single transaction per file batch.
- **Lock File**: `.sane/writer.lock` ensures only one process acts as the background watcher/writer. Secondary server instances operate in read-only query mode.

### 3.2 Schema Architecture
1. **`files`**: Stores file path, language, content hash (SHA-256), file size, nanosecond mtime, and parse error count.
2. **`symbols`**: Stores canonical symbol keys, qualified names, kinds (`class`, `method`, `function`), signatures, docstrings, and exact byte/line ranges (distinguishing signature from implementation body).
3. **`occurrences`**: Captures every syntactic reference/call site with spelling, receiver text, enclosing symbol, byte/line positions, target symbol ID, resolution kind, and confidence score.
4. **`edges`**: Relational graph edges (`calls`, `implements`, `extends`) linking source symbol to target symbol.
5. **`docs`**: Hierarchical Markdown sections with heading level, title, heading path (`System > Auth > Tokens`), content, and line numbers.
6. **`search_documents` & `search_fts`**: External-content FTS5 virtual table providing BM25 lexical ranking and prefix search over symbol signatures, docstrings, and documentation.

---

## 4. Progressive Disclosure Pipeline

### 4.1 Skeleton Redaction
Rather than pretty-printing an AST (which risks losing decorators, annotations, generic bounds, and whitespace), S.A.N.E. performs **source redaction**:
1. Identify the exact start and end byte offsets of implementation bodies.
2. Preserve class declarations, imports, decorators, annotations, signatures, and docstrings byte-for-byte.
3. Replace implementation body spans with concise markers:
   - Python: `# ... implementation omitted ...`
   - Java / Kotlin: `// ... implementation omitted ...`

### 4.2 AST-Aware Usage Snippets
Bare line numbers force agents to make follow-up read calls. S.A.N.E. generates self-contained usage windows:
```text
CheckoutService.kt:14-22 (in submitOrder, confidence 0.95):
  15 |         inventoryManager.reserve(orderId)
  16 | 
> 17 |         val result = paymentProcessor.capture(
  18 |             token,
  19 |             total,
  20 |         )
```
The `>` character immediately directs the LLM's attention to the targeted statement.

### 4.3 Output Budget Enforcement
Every renderer routes output through `OutputBudget`:
- `max_chars`: Default 12,000 characters
- `max_items`: Default 10 candidates
- Safe truncation message: `... [Showing X of Y items. Refine query or request sub-range]`

---

## 5. Security & Isolation

1. **Strict Repository Boundary**: All user paths are checked with `candidate.resolve().is_relative_to(repo_root.resolve())`. Any traversal escaping root raises `PathOutsideRepository`.
2. **Sensitive File Blocking**: `.env`, `.env.*`, `*.pem`, `*.key`, `id_rsa`, and credential stores are blocked by default.
3. **Read-Only Operation**: S.A.N.E. never executes repository code, never modifies user source files, and does not open outbound internet connections.
4. **Prompt Injection Hardening**: Source code comments and markdown bodies are labeled as repository data and never concatenated into agent system instructions.
