# S.A.N.E. — Semantic Agent Navigation Engine

[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-Compatible-green.svg)](https://modelcontextprotocol.io/)

> **A local, read-only progressive-disclosure and composite code navigation engine & MCP server for AI coding agents.**

S.A.N.E. turns your repository into a compact navigation graph and exposes a focused set of Model Context Protocol (MCP) primitives that move an agent from **concept → structure → symbol → implementation → usages & hierarchy**—or in **1 single composite call** (`explore_flow`, `analyze_impact`)—without flooding the context window with raw files.

---

## ⚡ The Problem: Context Waste & Multi-Turn Drift

Most coding agents suffer from two competing failure modes on large codebases:
1. **Uncurated Context Dumps** (e.g. dumping 40–50 KB of source files in one turn): causes attention degradation and "Lost in the Middle" errors for small-to-mid models (8B–70B, Claude 3.5 Haiku, Gemini 1.5 Flash).
2. **Excessive Tool Round-Trips** (e.g. 7–10 sequential tool calls to trace a single execution path): smaller models frequently suffer from multi-turn plan deviation, agent drift, or early loop termination.

### The S.A.N.E. Solution: Compact Composite Flow & Progressive Disclosure

S.A.N.E. provides a **strictly superior middle ground**: compact, high-signal responses (~1,200 tokens) that give an agent complete surgical flow in **1 single call**, with in-memory session deduplication across multi-turn sessions.

```text
── Option A: Composite Flow & Blast Radius (1-Turn Surgical Exploration) ──
How does symbol X work and what does it call?
        ↓ explore_flow("PaymentService.capture")
        ↳ Verbatim code + outbound callees + inbound callers + fused docs in 1 call!

What code and tests will break if I modify symbol X?
        ↓ analyze_impact("PaymentService.capture")
        ↳ Transitive callers (depth ≤ 4) + subclasses/implementers + affected test suites!

Need to read exact lines with architectural context?
        ↓ read_file_structural("src/payment_service.py", start=1, end=50)
        ↳ Exact lines + declared symbols + upstream dependents + linked documentation!

── Option B: Step-by-Step Progressive Disclosure (Token-Minimal Navigation) ──
What concept am I looking for?
        ↓ search_semantic("token refresh")
Which files/symbols implement it?
        ↓ get_skeleton("src/auth/service.py")
What does that file contain structurally?
        ↓ get_symbol_code("AuthService.rotate_refresh_token")
Who calls it / what does it call?
        ↓ find_usages("AuthService.rotate_refresh_token")
Who implements or extends this interface/class?
        ↓ find_implementations("AuthService")
```

**Token savings: ~85% reduction** in navigation tokens with 100% precision.

---

## 🛠 Features

- **Multi-Language Structural Indexing**: First-class support for **Python**, **Java**, **Kotlin**, **Swift**, and **Markdown**.
- **One-Shot Flow Exploration (`explore_flow`)**: Fuses verbatim anchor implementation, outbound callees, inbound callers, and matching documentation into a single bounded response.
- **Transitive Impact Analysis (`analyze_impact`)**: Computes recursive upstream callers (depth up to 4), class/interface implementers, and affected test suites before refactoring.
- **Structural File Reading (`read_file_structural`)**: Replaces blind line reads by attaching declared symbols, upstream callers, and doc sections directly above numbered lines.
- **In-Memory Session Deduplication (`SessionDedupTracker`)**: Eliminates redundant token spend across multi-turn conversations by replacing previously emitted symbol bodies with back-references:
  `[Source for Symbol X already provided in Turn N (L12-L35). Omitted to preserve token budget.]`
- **Redacted Source Skeletons**: Preserves docstrings, decorators, annotations, and signatures byte-for-byte while redacting method bodies with minimal markers.
- **Hierarchical Documentation Fusion**: Parses Markdown headings into navigation trees (`Architecture > Auth > Refresh tokens`) and deterministically bridges docs to code symbols.
- **Confidence-Aware Reference & Hierarchy Resolution**: Distinguishes `exact`, `import-scoped`, `class-scoped`, and `probable` usages, and resolves direct and transitive class/interface implementations.
- **Output Budget Hard Limits**: Every tool response is strictly bounded to prevent unexpected LLM context flooding.
- **Safe & Local**: 100% local SQLite/WAL storage, no cloud API dependencies, zero repository modifications, strict repository containment.

---

## 🚀 Quick Start

### Installation

```bash
# Recommended: pipx installs into an isolated env and puts `sane` on your
# PATH automatically (no manual shell config needed)
pipx install sane-nav

# or: uv tool install also handles PATH automatically
uv tool install sane-nav

# or: plain pip
pip install sane-nav
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

# One-shot flow exploration (code + callees + callers + docs)
sane flow "PaymentService.capture"

# Transitive impact analysis & blast radius (callers + implementers + tests)
sane impact "PaymentService.capture"

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
1. `explore_flow` when tracing how a function/method works and what it calls (1-shot code + callees + callers + docs).
2. `analyze_impact` before modifying code to see upstream callers, implementers, and affected test suites.
3. `read_file_structural` when reading source files to edit (attaches declared symbols, callers, and doc links).
4. `search_semantic` for a new concept, identifier, or bare filename.
5. `get_context` when feature-level documentation is needed.
6. `get_skeleton` before reading an unfamiliar source file.
7. `get_symbol_code` to view exact implementations.
8. `find_usages` to trace call sites and references.
9. `find_implementations` to find direct and transitive subclasses or implementers of an interface/class.
10. `read_lines` only for non-code or configuration files.

Do NOT read entire source files merely to discover their structure.
```

---

## 🏛 Architecture

```text
                  ┌──────────────────────────────┐
                  │  Claude / Cursor / Copilot   │
                  └──────────────┬───────────────┘
                                 │ stdio JSON-RPC (Turn-Aware Session Dedup)
                         ┌───────▼────────┐
                         │   MCP Server   │ (Strict stdout/stderr separation)
                         └───────┬────────┘
                                 │
              ┌──────────────────▼──────────────────┐
              │          Core Application           │
              │ explore_flow · analyze_impact       │
              │ · read_file_structural · Search     │
              │ · Skeleton · Symbol · Usages        │
              │ · Type Implementations & Blast Map  │
              └──────────────────┬──────────────────┘
                              │
                  ┌──────────────▼──────────┐
                  │    SQLite (WAL)         │
                  │ Symbols · Docs · FTS5   │
                  │ Recursive CTE Call Graph│
                  │ Upstream/Downstream Hop │
                  └──────────────▲──────────┘
                              │
              ┌───────────────┴─────────────────┐
              │    Multi-Language Adapters      │
              │ Python · Java · Kotlin · Swift  │
              │             · Docs              │
              └─────────────────────────────────┘
```

---

## 📄 License

Apache-2.0 © S.A.N.E. Contributors
