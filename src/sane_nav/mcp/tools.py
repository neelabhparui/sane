"""Application services layer for Model Context Protocol (MCP) tool execution.

Orchestrates search, context synthesis, skeleton extraction, symbol code lookup,
usage tracing, bounded line reading, and directory traversal.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from sane_nav.core.models import OutputBudget
from sane_nav.indexing.discovery import FileDiscovery
from sane_nav.indexing.indexer import Indexer
from sane_nav.parsing.registry import ParserRegistry
from sane_nav.paths import RepoPaths
from sane_nav.rendering.budget import BudgetManager
from sane_nav.rendering.skeleton import SkeletonRenderer
from sane_nav.rendering.snippets import render_code_snippet, render_symbol_body
from sane_nav.retrieval.context import ContextStitcher
from sane_nav.retrieval.lexical import LexicalRetriever
from sane_nav.retrieval.ranking import HybridRanker
from sane_nav.storage.database import Database


class McpToolService:
    """Core domain service implementing all MCP tool operations."""

    def __init__(self, repo_root: Path):
        """Initializes dependencies, database connection, and indexing engines."""
        self.repo_paths = RepoPaths(repo_root)
        self.db = Database(self.repo_paths.db_path)
        self.registry = ParserRegistry()
        self.indexer = Indexer(self.repo_paths, self.db, registry=self.registry)
        self.lexical = LexicalRetriever(self.db)
        self.ranker = HybridRanker()
        self.context_stitcher = ContextStitcher(self.db, self.lexical)
        self.skeleton_renderer = SkeletonRenderer(self.repo_paths, self.db, self.registry)

    def search_semantic(
        self,
        query: str,
        path_prefix: Optional[str] = None,
        kinds: Optional[list[str]] = None,
        limit: int = 8,
    ) -> dict[str, Any]:
        """Executes hybrid lexical and full-text search across symbols and docs.

        Args:
            query: Concept, identifier, or keyword to search for.
            path_prefix: Optional directory prefix to scope search.
            kinds: Optional filter on symbol kinds (e.g. ['class', 'method']).
            limit: Maximum number of results to return.

        Returns:
            Dictionary containing query metadata and ranked results.
        """
        limit = min(limit or 8, 20)
        exacts = self.lexical.search_exact(query, limit=limit)
        fts = self.lexical.search_fts(query, path_prefix=path_prefix, limit=limit * 2)

        ranked = self.ranker.fuse_and_rank(exacts, fts, query=query, limit=limit)

        if kinds:
            ranked = [r for r in ranked if r.get("kind") in kinds or r.get("entity_type") in kinds]

        results = []
        for r in ranked:
            if r.get("entity_type") == "symbol":
                results.append({
                    "symbol_id": r.get("symbol_key"),
                    "name": r.get("name"),
                    "qualified_name": r.get("qualified_name"),
                    "kind": r.get("kind"),
                    "file": r.get("file_path"),
                    "lines": [r.get("start_line"), r.get("end_line")],
                    "signature": r.get("signature"),
                    "match": {
                        "rank": r.get("rank"),
                        "score": r.get("score"),
                        "reason": r.get("match_reason"),
                    },
                })
            else:
                results.append({
                    "doc_id": r.get("entity_id"),
                    "title": r.get("title"),
                    "file": r.get("file_path"),
                    "lines": [r.get("start_line", 1), r.get("end_line", 1)],
                    "kind": "doc",
                    "preview": (r.get("body") or "")[:200],
                    "match": {
                        "rank": r.get("rank"),
                        "score": r.get("score"),
                        "reason": r.get("match_reason"),
                    },
                })

        return {
            "query": query,
            "retrieval_mode": "lexical-structural",
            "count": len(results),
            "results": results,
        }

    def get_context(
        self,
        feature: str,
        path_prefix: Optional[str] = None,
        max_chars: int = 10000,
    ) -> dict[str, Any]:
        """Synthesizes deterministic feature documentation and key symbol signatures.

        Args:
            feature: Concept or module description.
            path_prefix: Optional directory prefix.
            max_chars: Maximum characters allowed in response.

        Returns:
            Dictionary with stitched markdown and symbol signatures.
        """
        content = self.context_stitcher.get_feature_context(
            feature=feature,
            path_prefix=path_prefix,
            max_chars=max_chars or 10000,
        )
        return {
            "feature": feature,
            "content": content,
        }

    def get_skeleton(self, file_path: str, max_chars: int = 12000) -> dict[str, Any]:
        """Returns the structural skeleton of a file with implementation bodies redacted.

        Args:
            file_path: Relative path to the source file.
            max_chars: Character limit for response.

        Returns:
            Dictionary with file path and redacted skeleton text.
        """
        safe_path = self.repo_paths.resolve_user_path(file_path)
        skeleton = self.skeleton_renderer.render_file_skeleton(
            rel_path=self.repo_paths.to_relative(safe_path),
            max_chars=max_chars or 12000,
        )
        return {
            "file": file_path,
            "skeleton": skeleton,
        }

    def get_symbol_code(self, symbol: str, context_lines: int = 0) -> dict[str, Any]:
        """Retrieves exact declaration and implementation code for a specific symbol.

        Args:
            symbol: Symbol name, qualified name, or canonical URI.
            context_lines: Number of surrounding context lines.

        Returns:
            Dictionary with code, line numbers, or ambiguous candidate list.
        """
        candidates = self.db.get_symbol_by_id_or_name(symbol)
        if not candidates:
            return {
                "status": "not_found",
                "error": f"Symbol '{symbol}' not found in index.",
            }

        if len(candidates) > 1:
            return {
                "status": "ambiguous",
                "message": f"Symbol '{symbol}' matched {len(candidates)} locations. Specify exact symbol_id.",
                "candidates": [
                    {
                        "symbol_id": c["symbol_key"],
                        "name": c["name"],
                        "qualified_name": c["qualified_name"],
                        "file": c["file_path"],
                        "lines": [c["start_line"], c["end_line"]],
                        "signature": c["signature"],
                    }
                    for c in candidates
                ],
            }

        cand = candidates[0]
        abs_p = self.repo_paths.resolve_user_path(cand["file_path"])
        code = render_symbol_body(
            file_path=abs_p,
            start_line=cand["start_line"],
            end_line=cand["end_line"],
            context_lines=context_lines or 0,
        )

        return {
            "status": "success",
            "symbol_id": cand["symbol_key"],
            "name": cand["name"],
            "qualified_name": cand["qualified_name"],
            "file": cand["file_path"],
            "lines": [cand["start_line"], cand["end_line"]],
            "kind": cand["kind"],
            "code": code,
        }

    def find_usages(
        self,
        symbol: str,
        limit: int = 10,
        include_probable: bool = True,
    ) -> dict[str, Any]:
        """Finds cross-file references and call sites with AST-aware line context.

        Args:
            symbol: Target symbol name.
            limit: Maximum usages to return.
            include_probable: If True, includes probable heuristic resolutions.

        Returns:
            Dictionary with exact and probable usage snippets.
        """
        limit = min(limit or 10, 30)
        # Find target symbol id
        candidates = self.db.get_symbol_by_id_or_name(symbol)
        if not candidates:
            # Check by spelling across occurrences
            with self.db.get_connection() as conn:
                occs = conn.execute(
                    """
                    SELECT o.*, f.path as file_path, s.name as enclosing_name
                    FROM occurrences o
                    JOIN files f ON o.file_id = f.id
                    LEFT JOIN symbols s ON o.enclosing_symbol_id = s.id
                    WHERE o.spelling = ?
                    LIMIT ?
                    """,
                    (symbol.split(".")[-1], limit),
                ).fetchall()
        else:
            target_ids = [c["id"] for c in candidates]
            placeholders = ",".join("?" for _ in target_ids)
            with self.db.get_connection() as conn:
                occs = conn.execute(
                    f"""
                    SELECT o.*, f.path as file_path, s.name as enclosing_name, s.qualified_name as enclosing_qual
                    FROM occurrences o
                    JOIN files f ON o.file_id = f.id
                    LEFT JOIN symbols s ON o.enclosing_symbol_id = s.id
                    WHERE o.target_symbol_id IN ({placeholders})
                       OR o.spelling = ?
                    LIMIT ?
                    """,
                    (*target_ids, candidates[0]["name"], limit),
                ).fetchall()

        exact_usages = []
        probable_usages = []

        for o in occs:
            abs_p = self.repo_paths.resolve_user_path(o["file_path"])
            snippet = render_code_snippet(abs_p, target_line=o["start_line"], context_lines=2)
            item = {
                "file": o["file_path"],
                "enclosing_symbol": o["enclosing_name"],
                "line": o["start_line"],
                "resolution": o["resolution_kind"] or "probable",
                "confidence": o["confidence"] or 0.8,
                "snippet": snippet,
            }
            if (o["confidence"] or 0.0) >= 0.9:
                exact_usages.append(item)
            else:
                probable_usages.append(item)

        return {
            "symbol": symbol,
            "total_found": len(exact_usages) + len(probable_usages),
            "exact_usages": exact_usages,
            "probable_usages": probable_usages if include_probable else [],
        }

    def read_lines(self, file_path: str, start: int, end: int) -> dict[str, Any]:
        """Reads a bounded slice of lines from a non-symbol or configuration file.

        Args:
            file_path: Relative file path.
            start: 1-indexed start line.
            end: 1-indexed end line (inclusive).

        Returns:
            Dictionary with selected lines and content.
        """
        safe_path = self.repo_paths.resolve_user_path(file_path)
        if not safe_path.exists():
            return {"error": f"File '{file_path}' does not exist"}

        lines = safe_path.read_text(encoding="utf-8", errors="replace").splitlines()
        total = len(lines)

        s_idx = max(1, start)
        e_idx = min(total, end)

        if s_idx > e_idx or s_idx > total:
            return {"file": file_path, "lines": [], "content": ""}

        selected = lines[s_idx - 1 : e_idx]
        formatted = [f"{i + s_idx:4d} | {line}" for i, line in enumerate(selected)]

        return {
            "file": file_path,
            "start": s_idx,
            "end": e_idx,
            "total_lines": total,
            "content": "\n".join(formatted),
        }

    def get_file_tree(
        self,
        dir_path: Optional[str] = None,
        depth: int = 3,
        max_entries: int = 100,
    ) -> dict[str, Any]:
        """Returns bounded repository directory structure respecting ignore patterns.

        Args:
            dir_path: Optional root directory to traverse.
            depth: Maximum traversal depth.
            max_entries: Maximum files to return.

        Returns:
            Dictionary with file entries and counts.
        """
        target_dir = self.repo_paths.resolve_user_path(dir_path or ".")
        discovery = FileDiscovery(self.repo_paths, self.indexer.config, self.registry)

        entries: list[dict[str, Any]] = []
        for df in discovery.discover():
            if len(entries) >= (max_entries or 100):
                break
            entries.append({
                "path": df.rel_path,
                "size_bytes": df.size_bytes,
                "language": df.language,
            })

        return {
            "base_dir": str(dir_path or "."),
            "entries_count": len(entries),
            "files": entries,
        }

    def index_status(self) -> dict[str, Any]:
        """Returns statistics on indexed files, symbols, docs, and health."""
        return self.db.get_stats()
