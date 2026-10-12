# Changelog

All notable changes to `sane-nav` will be documented in this file.

## [0.5.0] - 2026-10-12

### Changed
- **CLI-Only Architecture**: Transitioned S.A.N.E. into a strictly CLI-only code navigation engine, eliminating background daemon requirements and MCP schema context bloat.
- **Agent Skills Integration (`sane-nav`)**: Implemented the standardized Agent Skills specification for AI coding agents (Universal `.agents/skills`, Claude Code, Cursor, Gemini CLI, OpenAI Codex, and VS Code).
- **Target Selection Prompt**: `sane init` interactively installs `sane-nav` skill files directly for selected agents.
- **Enhanced CLI Commands**:
  - `sane read`: Bounded structural file reading with attached architectural headers.
  - `sane context`: Feature and architecture documentation synthesis.
  - `sane tree`: Gitignore-aware structural file tree.
  - `sane setup`: Generate and write skills for any supported agent target.
  - `sane doctor`: Diagnostics now verify installed agent skills alongside SQLite FTS5 and parsers.

### Removed
- **MCP Server**: Removed `sane serve` stdio JSON-RPC server and MCP dependencies to prevent context window bloating and tool misuse.

## [0.1.0] - 2026-10-01

### Added
- **Core Engine**: Local transactional SQLite index with WAL mode and FTS5 full-text search.
- **Language Adapters**:
  - Python AST parser with support for decorators, async functions, classes, docstrings, calls, and redacted skeletons.
  - Java parser supporting classes, interfaces, records, annotations, Javadoc, method bodies, and calls.
  - Kotlin parser supporting data/sealed classes, suspend functions, KDocs, companion objects, and expressions.
  - Markdown hierarchical heading section parser (`#`, `##`, `###`) with heading paths and symbol mention extraction.
- **Progressive Disclosure Rendering**:
  - Redacted skeletons preserving declarations while hiding implementation bodies.
  - AST-aware snippet renderer with line numbers and `>` focus indicators.
  - Hard output budget manager (`max_chars`, `max_items`).
- **Resolver**: Multi-stage reference resolver categorizing `exact`, `import-scoped`, `class-scoped`, and `probable` usages.
- **Retrieval & Context**: Hybrid search combining exact symbol names, identifier tokenization, and FTS5 BM25 ranking, plus deterministic feature context stitcher.
- **MCP Server**: Stdio JSON-RPC 2.0 server with 8 tools (`search_semantic`, `get_context`, `get_skeleton`, `get_symbol_code`, `find_usages`, `read_lines`, `get_file_tree`, `index_status`).
- **CLI**: `sane init`, `sane index`, `sane serve`, `sane status`, `sane search`, `sane skeleton`, `sane symbol`, `sane usages`, `sane clean`, `sane doctor`, and `sane setup`.
