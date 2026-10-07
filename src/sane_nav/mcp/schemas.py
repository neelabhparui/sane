from __future__ import annotations

from typing import Any

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "search_semantic",
        "description": "Searches repository symbols and documentation by concept or identifier. Returns concise candidates with file paths, signatures, line numbers, and match reasons.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Concept, feature description, or identifier to search for."},
                "path_prefix": {"type": "string", "description": "Optional subdirectory prefix to limit search."},
                "kinds": {"type": "array", "items": {"type": "string"}, "description": "Optional list of symbol kinds (function, method, class, doc)."},
                "limit": {"type": "integer", "description": "Maximum number of candidates to return (default: 8)."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_context",
        "description": "Synthesizes deterministic feature-level context by connecting documentation sections to relevant core symbols and signatures.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "feature": {"type": "string", "description": "Feature, module, or architecture concept."},
                "path_prefix": {"type": "string", "description": "Optional directory filter."},
                "max_chars": {"type": "integer", "description": "Output budget limit in characters (default: 10000)."},
            },
            "required": ["feature"],
        },
    },
    {
        "name": "get_skeleton",
        "description": "Returns the structural skeleton of a file with function and method implementation bodies redacted, preserving docstrings, type annotations, and decorators.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Repository-relative path of the file."},
                "max_chars": {"type": "integer", "description": "Output budget limit (default: 12000)."},
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "get_symbol_code",
        "description": "Retrieves the exact code declaration and implementation body for a specific symbol without reading the entire file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Symbol name (e.g. 'AuthService.validateToken') or canonical symbol URI."},
                "context_lines": {"type": "integer", "description": "Additional surrounding lines of context (default: 0)."},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "find_usages",
        "description": "Finds call sites and references to a symbol across the repository, returning AST-aware code previews with line numbers and resolution confidence.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Target symbol name or qualified name."},
                "limit": {"type": "integer", "description": "Maximum number of usages to return (default: 10)."},
                "include_probable": {"type": "boolean", "description": "Whether to include probable heuristic matches (default: true)."},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "find_implementations",
        "description": "Finds all classes or interfaces that directly or transitively implement or extend a given class or interface across the repository.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Target interface or class name or qualified name."},
                "transitive": {"type": "boolean", "description": "Whether to recursively include indirect implementers / subclasses (default: true)."},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "read_lines",
        "description": "Reads a precise, bounded slice of lines from a non-symbol or configuration file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Repository-relative file path."},
                "start": {"type": "integer", "description": "1-based starting line number."},
                "end": {"type": "integer", "description": "1-based ending line number (inclusive)."},
            },
            "required": ["file_path", "start", "end"],
        },
    },
    {
        "name": "get_file_tree",
        "description": "Returns a bounded file tree of the repository or a subdirectory, respecting ignore rules.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dir_path": {"type": "string", "description": "Subdirectory to inspect (default: repository root)."},
                "depth": {"type": "integer", "description": "Maximum directory depth to traverse (default: 3)."},
                "max_entries": {"type": "integer", "description": "Maximum number of entries to return (default: 100)."},
            },
        },
    },
    {
        "name": "index_status",
        "description": "Reports indexing statistics, file counts, symbol counts, and health of the S.A.N.E. engine.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]
