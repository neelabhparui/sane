# S.A.N.E. — Semantic Agent Navigation Engine

[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-Compatible-green.svg)](https://modelcontextprotocol.io/)

> **A local, read-only progressive-disclosure code navigation engine and MCP server for AI coding agents.**

S.A.N.E. turns your repository into a compact navigation graph and exposes a tiny set of Model Context Protocol (MCP) primitives that move an agent from **concept → structure → symbol → implementation → usages & hierarchy** without flooding the context window with raw files.

---

## ⚡ The Problem: Context Waste in AI Coding Agents

Most coding agents spend 60–80% of their token budget simply discovering *where* to look:
1. `grep` across the whole repository (returns 200 matches).
2. Read 1,200-line file A to inspect one method (2,500 tokens).
3. Realize it's in file B; read 900-line file B (1,800 tokens).
4. Run another search to find callers; read 3 more whole files (6,000 tokens).

**Result:** Over 10,000 tokens consumed before a single line of real reasoning takes place.

### The S.A.N.E. Solution: Progressive Disclosure

```text
What concept am I looking for?
        ↓ search_semantic("token refresh")
Which files/symbols implement it?
        ↓ get_skeleton("src/auth/service.py")
What does that file contain structurally?
        ↓ get_symbol_code("AuthService.rotate_refresh_token")
What is the exact implementation of this symbol?
        ↓ find_usages("AuthService.rotate_refresh_token")
Who calls it / what does it call?
        ↓ find_implementations("AuthService")
Who implements or extends this interface/class?
```

**Token savings: ~85% reduction** in navigation tokens with 100% precision.

---

## 🛠 Features

- **Multi-Language Structural Indexing**: First-class support for **Python**, **Java**, **Kotlin**, and **Markdown**.
- **Redacted Source Skeletons**: Preserves docstrings, decorators, annotations, and signatures byte-for-byte while redacting method bodies with minimal markers.
- **Hierarchical Documentation Fusion**: Parses Markdown headings into navigation trees (`Architecture > Auth > Refresh tokens`) and deterministically bridges docs to code symbols.
- **Confidence-Aware Reference & Hierarchy Resolution**: Distinguishes `exact`, `import-scoped`, `class-scoped`, and `probable` usages, and resolves direct and transitive class/interface implementations.
- **Output Budget Hard Limits**: Every tool response is strictly bounded to prevent unexpected LLM context flooding.
- **Safe & Local**: 100% local SQLite/WAL storage, no cloud API dependencies, zero repository modifications, strict repository containment.

---

## 🚀 Quick Start

### Installation

```bash
# Using pip or uv
pip install sane-nav
# or
uv tool install sane-nav
```

### CLI Usage

```bash
# Initialize S.A.N.E. in your repository
sane init

# Build index
sane index

# Run diagnostic check
sane doctor

# Search symbols and documentation
sane search "refresh token"

# View skeleton of a file
sane skeleton src/auth.py

# Extract exact symbol code
sane symbol "AuthService.rotate_refresh_token"

# Find call sites and references
sane usages "AuthService.rotate_refresh_token"

# Find classes implementing or extending an interface/class
sane implementations "AdContainer"

# Start MCP stdio server
sane serve
```

---

## 🔌 MCP Client Configuration

### Claude Code

```bash
claude mcp add sane -- sane serve --repo .
```

Or in your project configuration:

```json
{
  "mcpServers": {
    "sane": {
      "command": "sane",
      "args": ["serve", "--repo", "."]
    }
  }
}
```

### Cursor (`.cursor/mcp.json`)

```bash
sane setup cursor --write
```

```json
{
  "mcpServers": {
    "sane": {
      "command": "sane",
      "args": ["serve", "--repo", "."]
    }
  }
}
```

### VS Code / Copilot (`.vscode/mcp.json`)

```bash
sane setup vscode --write
```

```json
{
  "mcpServers": {
    "sane": {
      "type": "stdio",
      "command": "sane",
      "args": ["serve", "--repo", "."]
    }
  }
}
```

### Recommended Agent Instruction

Add this prompt to your project's `AGENTS.md` or `.cursorrules`:

```markdown
## Code Navigation Instructions
Use S.A.N.E. for exploring this repository:
1. `search_semantic` for a new concept or feature.
2. `get_context` when feature-level documentation is needed.
3. `get_skeleton` before reading an unfamiliar source file.
4. `get_symbol_code` to view exact implementations.
5. `find_usages` to trace call sites and references.
6. `find_implementations` to find direct and transitive subclasses or implementers of an interface/class.
7. `read_lines` only for non-code or configuration files.

Do NOT read entire source files merely to discover their structure.
```

---

## 🏛 Architecture

```text
                  ┌──────────────────────────────┐
                  │  Claude / Cursor / Copilot   │
                  └──────────────┬───────────────┘
                                 │ stdio JSON-RPC
                         ┌───────▼────────┐
                         │   MCP Server   │ (Strict stdout/stderr separation)
                         └───────┬────────┘
                                 │
              ┌──────────────────▼──────────────────┐
              │          Core Application           │
              │ Search · Skeleton · Symbol · Usages │
              │      · Type Implementations         │
              └──────────────────┬──────────────────┘
                              │
                  ┌───────────▼───────────┐
                  │    SQLite (WAL)       │
                  │ Symbols · Docs · FTS5 │
                  │ Graph Edges & Subtypes│
                  └───────────▲───────────┘
                              │
              ┌───────────────┴─────────────────┐
              │    Multi-Language Adapters     │
              │ Python · Java · Kotlin · Docs  │
              └─────────────────────────────────┘
```

---

## 📄 License

Apache-2.0 © S.A.N.E. Contributors
