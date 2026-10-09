from __future__ import annotations

from typing import Any

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "search_semantic",
        "description": (
            "Searches symbols, docs, call-site occurrences, and file paths by concept, "
            "identifier, or bare filename (e.g. 'AudioUnifiedAdManager' finds that file "
            "even with no docstring match). Works best with 1-3 sharp tokens (a real "
            "identifier/class name) — a long natural-language phrase dilutes relevance, "
            "so narrow the query to the most literal term if results look off-topic."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Concept, identifier, or bare filename. Prefer short literal identifiers over long phrases."},
                "path_prefix": {"type": "string", "description": "Optional subdirectory prefix to limit search."},
                "kinds": {"type": "array", "items": {"type": "string"}, "description": "Optional list of symbol kinds (function, method, class, doc, file)."},
                "limit": {"type": "integer", "description": "Maximum number of candidates to return (default: 8)."},
                "context_symbol": {"type": "string", "description": "Optional symbol name/id or file path you are currently looking at. Results closer to it in the call graph (calls/implements/extends) are boosted over name-match alone — e.g. after reading UnifiedAdManager.kt, searching 'finish' with context_symbol='UnifiedAdManager' ranks nearby logger.finish() calls above unrelated Activity.finish() in test files."},
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
        "description": "Retrieves the exact code declaration and implementation body for a known symbol name without reading the entire file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Symbol name (e.g. 'AuthService.validateToken') or canonical symbol URI."},
                "context_lines": {"type": "integer", "description": "Additional surrounding lines of context (default: 0)."},
                "kind": {"type": "string", "description": "Optional symbol kind filter to disambiguate a common name (e.g. 'method', 'field', 'class')."},
                "class_context": {"type": "string", "description": "Optional owning class/type name to disambiguate a common method/field name (e.g. symbol='finish', class_context='InMobiLogger')."},
                "force": {"type": "boolean", "description": "Bypass session deduplication and force verbatim code re-emission (default: false)."},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "find_usages",
        "description": "Finds every call site / reference to a known symbol across the repository, with line numbers and resolution confidence.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Target symbol name or qualified name. For a common/generic method name (e.g. 'finish', 'close'), qualify it as 'Owner.method' (e.g. 'AdContainer.finish') to scope matches to that receiver and avoid noise from unrelated classes, or use kind/class_context instead."},
                "limit": {"type": "integer", "description": "Maximum number of usages to return (default: 10)."},
                "include_probable": {"type": "boolean", "description": "Whether to include probable heuristic matches (default: true)."},
                "kind": {"type": "string", "description": "Optional symbol kind filter for the target (e.g. 'method', 'field', 'class')."},
                "class_context": {"type": "string", "description": "Optional owning class/type name to scope matches to (e.g. symbol='finish', class_context='InMobiLogger'). Composable with the 'Owner.method' dotted form."},
                "min_confidence": {"type": "number", "description": "Optional lower bound (0.0-1.0) on resolution confidence. Set to 0.9 to see only exact, unambiguous usages and skip reading through probable/heuristic matches."},
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
        "name": "explore_flow",
        "description": "One-shot surgical flow exploration. Locates anchor symbol, extracts verbatim body, queries outbound calls (callees), inbound callers, and matching documentation into a compact, high-signal composite response under budget.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Target symbol name, qualified name, or symbol key (e.g. 'PaymentRetryCoordinator.should_retry')."},
                "max_depth": {"type": "integer", "description": "Call graph traversal depth for outbound callees (default: 1, max: 2)."},
                "max_chars": {"type": "integer", "description": "Output budget limit in characters (default: 12000)."},
                "force": {"type": "boolean", "description": "Bypass session deduplication and force verbatim code re-emission (default: false)."},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "analyze_impact",
        "description": "Transitive blast radius and refactor safety analysis. Discovers upstream callers up to depth N, direct and indirect interface/subclass implementers, and affected test suites before modifying code.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Target symbol name, qualified name, or symbol key."},
                "depth": {"type": "integer", "description": "Upstream caller recursion depth (default: 2, max: 4)."},
                "include_tests": {"type": "boolean", "description": "Whether to search and report affected test suites (default: true)."},
                "max_chars": {"type": "integer", "description": "Output budget limit in characters (default: 12000)."},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "read_file_structural",
        "description": "Drop-in file reader that attaches structural architectural context (declared symbols, upstream callers/dependents, linked documentation) to exact numbered lines so follow-up queries are unnecessary.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Repository-relative file path."},
                "start": {"type": "integer", "description": "1-based starting line number (default: 1)."},
                "end": {"type": "integer", "description": "1-based ending line number (default: up to 150 lines or file end)."},
                "max_chars": {"type": "integer", "description": "Output budget limit in characters (default: 12000)."},
            },
            "required": ["file_path"],
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
