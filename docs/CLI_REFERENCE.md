# S.A.N.E. Command-Line Interface (CLI) Manual

## 1. Overview

The `sane` command-line utility provides developers and AI agents with direct, token-efficient access to progressive-disclosure code navigation, architecture discovery, and impact analysis.

---

## 2. Command Reference

### `sane init`
Initializes a new S.A.N.E. configuration, builds the repository index, configures agent skills, and starts the background watcher daemon.
```bash
sane init [--repo <path>] [--agents <list>] [--no-agents]
```
- Creates `.sane.toml` with default inclusions, exclusions, and worker settings.
- Appends `.sane/` to `.gitignore`.
- Indexes all discovered source files into `.sane/index.db`.
- Installs the `sane-nav` skill for selected agents (`universal`, `claude`, `cursor`, `gemini`, `codex`, `vscode`).
- Automatically launches the background watcher daemon (`.sane/watcher.pid`, `.sane/watcher.log`).

---

### `sane index`
Scans and indexes the repository into `.sane/index.db`.
```bash
sane index [--repo <path>]
```
- Performs fast drift check using file size and `mtime_ns`.
- Hashes and parses new or modified files.
- Executes cross-file occurrence and reference resolution.
- Updates SQLite FTS5 index.

---

### `sane flow <symbol>`
One-shot surgical flow exploration (anchor body + outbound callees + inbound callers + fused documentation).
```bash
sane flow "PaymentService.capture" [--depth 1] [--repo <path>]
```

---

### `sane impact <symbol>`
Computes transitive blast radius and refactor safety (callers up to depth N + subclasses/implementers + affected test suites).
```bash
sane impact "PaymentService.capture" [--depth 2] [--no-tests] [--repo <path>]
```

---

### `sane search <query>`
Searches symbols and documentation matching the query string without scoring bloat.
```bash
sane search "PaymentService" [--limit 8] [--repo <path>]
```

---

### `sane skeleton <file>`
Displays the structural outline of a file with implementation bodies redacted and verbose import statements collapsed to save tokens.
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

### `sane implementations <symbol>`
Finds classes and interfaces implementing or extending the target symbol.
```bash
sane implementations "PaymentGateway" [--direct-only] [--repo <path>]
```

---

### `sane read <file>`
Bounded structural file reader with attached architectural header (declared symbols, callers, linked docs).
```bash
sane read src/payment_service.py [--start 1] [--end 50] [--max-chars 12000] [--repo <path>]
```

---

### `sane context <feature>`
Synthesizes architecture documentation and relevant symbol signatures for a feature or module.
```bash
sane context "Retry Policy" [--prefix src/] [--max-chars 10000] [--repo <path>]
```

---

### `sane tree [dir]`
Displays a clean, gitignore-respecting structural file tree.
```bash
sane tree [dir] [--depth 3] [--max-entries 100] [--repo <path>]
```

---

### `sane status`
Displays index health, statistics, file counts, and language breakdown.
```bash
sane status [--repo <path>]
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
- Checks background watcher daemon operational status.
- Checks target repository and installed agent skills.

---

### `sane watch`
Manages the background filesystem watcher daemon or runs in the foreground with live logs.
```bash
sane watch [--daemon|--start] [--stop] [--status] [--foreground] [--debounce 300] [--repo <path>]
```
- Automatically started in the background by `sane init`.
- Tracks daemon process in `.sane/watcher.pid` and logs to `.sane/watcher.log`.
- `--status`: Inspects whether the daemon process is active and displays log path.
- `--stop`: Gracefully terminates the running background daemon.
- `--daemon` / `--start`: Starts or restarts the detached background daemon.
- Default invocation without flags runs in the foreground with live terminal output.

---

### `sane setup <client>`
Inspects or writes the `sane-nav` skill configuration for AI coding agents.
```bash
# Print skill to stdout
sane setup claude
sane setup cursor
sane setup universal

# Write skill file directly
sane setup claude --write
sane setup cursor --write
sane setup universal --write
```

---

### `sane clean`
Stops running watcher daemon and deletes the `.sane/` directory, removing the SQLite database and lock files.
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
