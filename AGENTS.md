# Instructions for AI Coding Agents in this Repository

Welcome, Agent. This repository is powered by **S.A.N.E. (Semantic Agent Navigation Engine)**.

## MANDATORY RULE: NEVER USE GREP, RIPGREP, OR FIND FOR CODE EXPLORATION

You MUST always activate and use the **`sane-nav` skill** and `sane` CLI commands instead of `grep`, `rg`, `find`, or dumping raw files. 

### Why Grep is Forbidden Here:
- Brute-force `grep` floods the context window with raw code, causing attention degradation and missing semantic call hierarchy.
- `sane` queries the local AST and SQLite call graph, returning precise, bounded context under token budget.

---

## Grep Replacement Cheat-Sheet (Pick `sane` Over Grep)

| Task / Intent | Do NOT Run (Anti-Pattern) | ALWAYS Run Instead (`sane`) | Benefit |
| :--- | :--- | :--- | :--- |
| **Search identifier or keyword** | `grep -rn "pattern" .` / `rg "pattern"` | `sane search "<query>"` | Ranks AST symbols & docs; ignores build/test noise; provides exact line numbers. |
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

### 1. One-Shot Flow & Understanding (Preferred First Step)
- Run `sane flow "<Symbol>"` to get the verbatim implementation, outbound callees, inbound callers, and fused documentation in a single step.

### 2. Refactor Blast Radius (Before Modifying Code)
- Run `sane impact "<Symbol>"` to inspect upstream callers (depth 2), direct & indirect implementers, and affected test suites before editing or refactoring code.

### 3. Concept & Identifier Discovery
- Run `sane search "<query>"` with 1–3 sharp keywords to locate symbol names and documentation.

### 4. File Structure Inspection
- Run `sane skeleton "<file_path>"` before reading an unfamiliar source file.

### 5. Implementation Reading
- Run `sane symbol "<Symbol>"` to extract only the specific class or function you need to inspect or edit.

### 6. Call Sites & References
- Run `sane usages "<Symbol>"` to trace where a symbol is invoked across the repository.

### 7. Interface & Class Implementations
- Run `sane implementations "<Symbol>"` to find all subclasses or implementers of an interface/class.

### 8. Structural Line Reading
- Run `sane read "<file_path>" --start X --end Y` to read exact line ranges with attached architectural context.

### 9. Feature & Domain Documentation
- Run `sane context "<feature>"` for feature specifications and key symbol signatures.

---

## Escalation Summary

```text
sane flow (1-shot) OR sane search → sane skeleton → sane symbol → sane usages → sane impact
```

Following this protocol ensures you solve the user's task using the smallest possible token footprint.
