# S.A.N.E. Model Context Protocol (MCP) Specification

**Protocol Version:** `2024-11-05`  
**Transport:** `stdio` (JSON-RPC 2.0)  
**Encoding:** UTF-8  

---

## 1. Protocol Transport & Invariants

S.A.N.E. implements the standard Model Context Protocol over `stdio`:
- **Standard Input (`stdin`)**: Receives JSON-RPC 2.0 requests from the host agent (Claude Code, Cursor, Copilot, etc.).
- **Standard Output (`stdout`)**: Dedicated **strictly to JSON-RPC responses**. Under no circumstances does S.A.N.E. emit logs, banners, or debug messages to `stdout`.
- **Standard Error (`stderr`)**: Used exclusively for diagnostic logging and telemetry.

### Initialization Handshake
1. Client sends `initialize` request.
2. Server responds with `serverInfo` (`name: "sane-nav"`, `version: "0.1.0"`) and capabilities (`tools: { listChanged: false }`).
3. Client sends `notifications/initialized`.

---

## 2. Tool Reference

### 2.1 `search_semantic`
Searches repository symbols and documentation by concept, feature description, or identifier.

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "query": { "type": "string", "description": "Concept, feature description, or identifier to search for." },
    "path_prefix": { "type": "string", "description": "Optional directory filter." },
    "kinds": { "type": "array", "items": { "type": "string" }, "description": "Filter by kind: class, method, function, doc." },
    "limit": { "type": "integer", "description": "Maximum candidates to return (default: 8)." }
  },
  "required": ["query"]
}
```

**Example Response:**
```json
{
  "query": "PaymentService.capture",
  "retrieval_mode": "lexical-structural",
  "count": 1,
  "results": [
    {
      "symbol_id": "python://python/payment_service.py::PaymentService#capture@L49",
      "name": "capture",
      "qualified_name": "PaymentService.capture",
      "kind": "method",
      "file": "python/payment_service.py",
      "lines": [49, 54],
      "signature": "def capture(self, token: PaymentToken) -> bool:",
      "match": {
        "rank": 1,
        "score": 0.061,
        "reason": "title_exact_phrase_match"
      }
    }
  ]
}
```

---

### 2.2 `get_context`
Synthesizes deterministic feature-level context by connecting relevant documentation sections to core symbols and signatures.

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "feature": { "type": "string", "description": "Feature, module, or architecture concept." },
    "path_prefix": { "type": "string", "description": "Optional directory filter." },
    "max_chars": { "type": "integer", "description": "Character budget (default: 10000)." }
  },
  "required": ["feature"]
}
```

---

### 2.3 `get_skeleton`
Returns the structural skeleton of a file with function and method implementation bodies redacted, preserving docstrings, type annotations, and decorators.

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "file_path": { "type": "string", "description": "Repository-relative file path." },
    "max_chars": { "type": "integer", "description": "Character budget (default: 12000)." }
  },
  "required": ["file_path"]
}
```

---

### 2.4 `get_symbol_code`
Retrieves the exact code declaration and implementation body for a specific symbol without reading the entire file.

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "symbol": { "type": "string", "description": "Symbol name (e.g. 'AuthService.validateToken') or canonical symbol URI." },
    "context_lines": { "type": "integer", "description": "Additional surrounding lines of context (default: 0)." }
  },
  "required": ["symbol"]
}
```

**Ambiguity Handling:**
If multiple symbols match the short name, S.A.N.E. never guesses. It returns a candidate list with stable `symbol_id` URIs:
```json
{
  "status": "ambiguous",
  "message": "Symbol 'validateToken' matched 2 locations. Specify exact symbol_id.",
  "candidates": [
    { "symbol_id": "java://com.acme/AuthService#validateToken", "file": "AuthService.java" },
    { "symbol_id": "java://com.acme/LegacyAuth#validateToken", "file": "LegacyAuth.java" }
  ]
}
```

---

### 2.5 `find_usages`
Finds call sites and references to a symbol across the repository, returning AST-aware code previews with line numbers and resolution confidence.

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "symbol": { "type": "string", "description": "Target symbol name or qualified name." },
    "limit": { "type": "integer", "description": "Maximum usages to return (default: 10)." },
    "include_probable": { "type": "boolean", "description": "Include heuristic matches (default: true)." }
  },
  "required": ["symbol"]
}
```

---

### 2.6 `read_lines`
Reads a precise, bounded slice of lines from a non-symbol or configuration file.

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "file_path": { "type": "string", "description": "Repository-relative file path." },
    "start": { "type": "integer", "description": "1-based starting line number." },
    "end": { "type": "integer", "description": "1-based ending line number (inclusive)." }
  },
  "required": ["file_path", "start", "end"]
}
```

---

### 2.7 `get_file_tree`
Returns a bounded file tree of the repository or a subdirectory, respecting ignore rules.

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "dir_path": { "type": "string", "description": "Subdirectory to inspect (default: repository root)." },
    "depth": { "type": "integer", "description": "Directory depth (default: 3)." },
    "max_entries": { "type": "integer", "description": "Maximum file entries (default: 100)." }
  }
}
```

---

### 2.8 `index_status`
Reports indexing statistics, file counts, symbol counts, and health of the S.A.N.E. engine.
