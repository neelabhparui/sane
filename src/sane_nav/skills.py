"""Agent skills definition and installer for S.A.N.E. navigation.

Packages procedural workflows, progressive disclosure rules, and CLI invocation
instructions for AI coding agents (Claude Code, Cursor, Gemini, Codex, VS Code,
and Universal Agent Skills standard).
"""

from __future__ import annotations

from pathlib import Path

SKILL_NAME = "sane-nav"

# Agent targets mapped to their respective project-relative skill paths
AGENT_SKILL_PATHS: dict[str, str] = {
    "universal": ".agents/skills/sane-nav/SKILL.md",
    "agents": ".agents/skills/sane-nav/SKILL.md",
    "claude": ".claude/skills/sane-nav/SKILL.md",
    "cursor": ".cursor/skills/sane-nav/SKILL.md",
    "gemini": ".gemini/skills/sane-nav/SKILL.md",
    "codex": ".codex/skills/sane-nav/SKILL.md",
    "vscode": ".vscode/skills/sane-nav/SKILL.md",
}

SKILL_TEMPLATE = """---
name: sane-nav
description: MANDATORY code exploration, search, and navigation tool. Always use instead of grep, ripgrep, find, or reading raw files whenever searching symbols, locating definitions or usages, inspecting file structure, tracing call graphs, reading code, or analyzing refactoring impact in this repository.
---

# S.A.N.E. Navigation Skill (`sane-nav`)

Always use the `sane` CLI for code exploration, search, architecture discovery, and context building in this repository.

> **CRITICAL RULE: NEVER USE GREP, RIPGREP, FIND, OR RAW FILE READS**
> Brute-force `grep -rn` or reading entire files floods your context window, causes attention degradation, and misses semantic call hierarchy.
> You MUST use `sane` CLI commands instead of `grep`, `rg`, `find`, or `cat`.

## Grep Replacement Cheat-Sheet (Pick `sane` Over Grep)

| Task / Intent | Do NOT Run (Anti-Pattern) | ALWAYS Run Instead (`sane`) | Why It Wins |
| :--- | :--- | :--- | :--- |
| **Search identifier or keyword** | `grep -rn "pattern" .` / `rg "pattern"` | `sane search "<query>"` | Ranks AST symbols & docs; ignores build/test noise; provides exact lines. |
| **Find call sites / usages** | `grep -rn "func_name(" .` | `sane usages "<symbol>"` | Distinguishes exact vs probable call sites with AST line context. |
| **Trace execution / call flow** | Multi-turn manual grepping | `sane flow "<Symbol>"` | **1-Shot**: Anchor implementation + callers + callees + docs in 1 command. |
| **Pre-refactor blast radius** | Grepping across repo | `sane impact "<Symbol>"` | Recursive callers (depth ≤ 4) + subclasses/implementers + affected tests. |
| **Inspect unfamiliar file** | `cat file` / `head -n 500 file` | `sane skeleton "<path/to/file>"` | Preserves docstrings & signatures byte-for-byte; redacts bodies (90% token saving). |
| **Inspect function / class body** | Reading full file | `sane symbol "<Symbol>"` | Extracts only the exact symbol declaration and body without reading the file. |
| **Find subclasses / implementers** | `grep -rn "implements Foo"` | `sane implementations "<Symbol>"` | Resolves full AST inheritance and direct/indirect interface implementations. |
| **Read exact lines to edit** | Raw file reading | `sane read "<file>" --start X --end Y` | Attaches architectural header (declared symbols, upstream callers, linked docs). |
| **Explore directory layout** | `find .` / `tree` | `sane tree [dir]` | Clean, gitignore-aware structural tree with symbol counts. |

---

## Navigation Protocol & Decision Tree

### 1. One-Shot Flow Exploration (Recommended First Step)
When you need to understand how a function, method, or class works, what it calls, and what calls it:
```bash
sane flow "<Symbol>" [--depth 1|2]
```
- Returns verbatim anchor implementation, outbound callees, inbound callers, and linked documentation in a single bounded response.
- Eliminates multi-turn tool round-trips and context degradation.

### 2. Refactor Blast Radius & Impact Analysis (Before Modifying Code)
Before editing or deleting an existing function, class, or interface:
```bash
sane impact "<Symbol>" [--depth 2]
```
- Reports upstream callers up to depth N, direct & indirect subclasses/implementers, and affected test suites before refactoring.

### 3. Concept & Identifier Search
When you don't know the exact symbol name or file location:
```bash
sane search "<query>" [--limit 8]
```
- Use 1–3 sharp tokens (e.g. `PaymentService`, `token refresh`).
- Returns ranked symbols and doc sections with exact line numbers.

### 4. File Structure Inspection (Before Opening a File)
Before inspecting an unfamiliar source file:
```bash
sane skeleton "<path/to/file>"
```
- Shows class definitions, method signatures, decorators, and docstrings with implementation bodies redacted.
- Preserves your context window budget.

### 5. Targeted Symbol Extraction
When you know the symbol name and only need its implementation:
```bash
sane symbol "<Symbol>" [--context 2]
```
- If the symbol is ambiguous across files, qualify it with `Class.method` or use the reported `symbol_id`.

### 6. Call Sites & Usages
To locate where a symbol is invoked:
```bash
sane usages "<Symbol>" [--limit 10]
```
- Differentiates exact call sites from probable occurrences with surrounding lines.

### 7. Interface & Class Implementations
To find classes implementing an interface or extending a base class:
```bash
sane implementations "<InterfaceOrClass>" [--direct-only]
```

### 8. Structural Line Reading
When you must read a specific line range in a source file:
```bash
sane read "<path/to/file>" --start <start_line> --end <end_line>
```
- Injects architectural context (declared symbols, callers, linked docs) above the requested lines.

### 9. Feature & Domain Documentation
```bash
sane context "<feature>"
```
- Synthesizes architecture documentation and relevant symbol signatures.

---

## Output Processing Rules
1. **Ambiguous Matches**: If a command returns `Ambiguous: matched N locations`, rerun using the specific `symbol_id` or fully-qualified name (e.g., `PaymentService.capture`).
2. **Linked Docs**: If output includes `[DOC]` or `Linked Documentation`, read the architectural constraints before writing code.
3. **Budget Bounds**: `sane` output is strictly bounded to prevent context window bloat. Trust the returned summaries and extract specifics as needed.
"""


def get_skill_markdown() -> str:
    """Returns the standardized SKILL.md specification for sane-nav."""
    return SKILL_TEMPLATE.strip() + "\n"


def install_skill(agent: str, repo_root: Path) -> Path | None:
    """Installs the sane-nav skill for a given agent target in repo_root.

    Args:
        agent: Agent name ('universal', 'agents', 'claude', 'cursor', 'gemini', 'codex', 'vscode').
        repo_root: Root directory of target repository.

    Returns:
        Path to the written SKILL.md file, or None if agent is unknown.
    """
    agent_key = agent.lower().strip()
    rel_path = AGENT_SKILL_PATHS.get(agent_key)
    if not rel_path:
        return None

    target_path = repo_root / rel_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(get_skill_markdown(), encoding="utf-8")
    return target_path
