# S.A.N.E. Command-Line Interface (CLI) Manual

## 1. Overview

The `sane` command-line utility provides developers and AI agents with direct access to indexing, health checks, symbol extraction, and MCP serving.

---

## 2. Command Reference

### `sane init`
Initializes a new S.A.N.E. configuration in the repository.
```bash
sane init [--repo <path>]
```
- Creates `.sane.toml` with default inclusions, exclusions, and worker settings.
- Automatically appends `.sane/` to `.gitignore`.

---

### `sane index`
Scans and indexes the repository into `.sane/index.db`.
```bash
sane index [--repo <path>]
```
- Performs fast drift check using file size and `mtime_ns`.
- Hashes and parses new or modified files.
- Executes cross-file occurrence resolution.
- Updates SQLite FTS5 index.

---

### `sane serve`
Starts the stdio JSON-RPC 2.0 MCP server.
```bash
sane serve [--repo <path>]
```
- Listens on `stdin` and writes JSON-RPC responses to `stdout`.
- Diagnostic logging is routed to `stderr`.

---

### `sane status`
Displays index health, statistics, file counts, and language breakdown.
```bash
sane status [--repo <path>]
```
**Example Output:**
```json
{
  "state": "ready",
  "files": 36,
  "symbols": 182,
  "docs": 28,
  "occurrences": 142,
  "resolved_edges": 84,
  "languages": {
    "python": 18,
    "java": 8,
    "kotlin": 6,
    "markdown": 4
  },
  "semantic_mode": "lexical-structural"
}
```

---

### `sane search <query>`
Searches symbols and documentation matching the query string.
```bash
sane search "PaymentService" [--limit 8] [--repo <path>]
```

---

### `sane skeleton <file>`
Displays the structural outline of a file with implementation bodies redacted.
```bash
sane skeleton src/auth.py [--repo <path>]
```

---

### `sane symbol <symbol>`
Extracts the exact declaration and body of a symbol with line numbers.
```bash
sane symbol "AuthService.validateToken" [--context 2] [--repo <path>]
```

---

### `sane usages <symbol>`
Finds all call sites and references to a symbol with AST-aware line context.
```bash
sane usages "capture" [--limit 10] [--repo <path>]
```

---

### `sane doctor`
Runs comprehensive system and health diagnostics:
```bash
sane doctor [--repo <path>]
```
- Verifies SQLite FTS5 extension availability.
- Validates Python runtime version (>=3.10).
- Confirms language parser registrations.
- Checks index write permissions and WAL mode.

---

### `sane setup <claude|cursor|vscode>`
Generates or writes configuration for AI coding agents.
```bash
# Print configuration
sane setup claude
sane setup cursor
sane setup vscode

# Write configuration file directly
sane setup cursor --write
sane setup vscode --write
```

---

### `sane clean`
Deletes the `.sane/` directory, removing the SQLite database and lock files.
```bash
sane clean [--repo <path>]
```

---

## 3. Configuration File (`.sane.toml`)

```toml
[repository]
respect_gitignore = true
max_file_bytes = 2097152 # 2MB

include = [
  "**/*.py",
  "**/*.java",
  "**/*.kt",
  "**/*.kts",
  "**/*.md",
]

exclude = [
  ".git/**",
  ".sane/**",
  "build/**",
  "dist/**",
  "node_modules/**",
  ".gradle/**",
  ".idea/**",
  ".venv/**",
  "__pycache__/**",
]

[index]
parse_workers = 4

[watch]
enabled = true
debounce_ms = 300

[search]
semantic = false
default_limit = 8

[output]
max_chars = 12000
max_usages = 20
```
