# Instructions for AI Coding Agents in this Repository

Welcome, Agent. This repository is powered by **S.A.N.E. (Semantic Agent Navigation Engine)**.

## Mandatory Navigation Protocol

To conserve context window tokens and maximize reasoning accuracy, you **MUST** follow S.A.N.E.'s progressive disclosure order:

### 1. New Concept Exploration
- Call `search_semantic(query="...")` to discover matching symbols and documentation.
- Do **NOT** run global `grep` commands across the repository.

### 2. Feature & Architectural Context
- Call `get_context(feature="...")` when you need to understand feature policies, retry strategies, or module design.

### 3. File Structure
- Call `get_skeleton(file_path="...")` before reading an unfamiliar source file.
- Skeletons provide class structure, method signatures, decorators, and docstrings with implementation bodies redacted.
- Do **NOT** read entire 500+ line source files merely to discover what functions they contain.

### 4. Implementation Reading
- Call `get_symbol_code(symbol="...")` to read only the specific class or function you need to inspect or edit.

### 5. Call Sites & References
- Call `find_usages(symbol="...")` to trace where a symbol is invoked across the repository.

### 6. Non-Symbol / Configuration Files
- Call `read_lines(file_path="...", start=X, end=Y)` for configuration files (`.toml`, `.json`, `.yml`).

---

## Escalation Summary

```text
search_semantic → get_context → get_skeleton → get_symbol_code → find_usages
```

Following this protocol ensures you solve the user's task using the smallest possible token footprint.
