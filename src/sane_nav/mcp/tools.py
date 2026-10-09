"""Application services layer for Model Context Protocol (MCP) tool execution.

Orchestrates search, context synthesis, skeleton extraction, symbol code lookup,
usage tracing, bounded line reading, directory traversal, type hierarchy traversal,
one-shot flow exploration, and transitive impact analysis.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

from sane_nav.indexing.discovery import FileDiscovery
from sane_nav.indexing.indexer import Indexer
from sane_nav.mcp.session import SessionDedupTracker
from sane_nav.parsing.registry import ParserRegistry
from sane_nav.paths import RepoPaths
from sane_nav.rendering.budget import BudgetManager
from sane_nav.rendering.skeleton import SkeletonRenderer
from sane_nav.rendering.snippets import render_code_snippet, render_symbol_body
from sane_nav.retrieval.context import ContextStitcher
from sane_nav.retrieval.flow import FlowExplorer
from sane_nav.retrieval.impact import ImpactAnalyzer
from sane_nav.retrieval.lexical import LexicalRetriever
from sane_nav.retrieval.ranking import HybridRanker
from sane_nav.storage.database import Database


class McpToolService:
    """Core domain service implementing all MCP tool operations."""

    def __init__(
        self,
        repo_root: Path,
        session_tracker: Optional[SessionDedupTracker] = None,
    ):
        """Initializes dependencies, database connection, and indexing engines."""
        self.repo_paths = RepoPaths(repo_root)
        self.db = Database(self.repo_paths.db_path)
        self.registry = ParserRegistry()
        self.indexer = Indexer(self.repo_paths, self.db, registry=self.registry)
        self.lexical = LexicalRetriever(self.db)
        self.ranker = HybridRanker()
        self.context_stitcher = ContextStitcher(self.db, self.lexical)
        self.skeleton_renderer = SkeletonRenderer(self.repo_paths, self.db, self.registry)
        self.session_tracker = session_tracker or SessionDedupTracker()
        self.flow_explorer = FlowExplorer(self.repo_paths, self.db)
        self.impact_analyzer = ImpactAnalyzer(self.repo_paths, self.db)

    def search_semantic(
        self,
        query: str,
        path_prefix: Optional[str] = None,
        kinds: Optional[list[str]] = None,
        limit: int = 8,
        context_symbol: Optional[str] = None,
    ) -> dict[str, Any]:
        """Executes hybrid lexical and full-text search across symbols and docs.

        Args:
            query: Concept, identifier, or keyword to search for.
            path_prefix: Optional directory prefix to scope search.
            kinds: Optional filter on symbol kinds (e.g. ['class', 'method']).
            limit: Maximum number of results to return.
            context_symbol: Optional symbol name/id the caller is currently
                looking at.

        Returns:
            Dictionary containing query metadata and ranked results.
        """
        limit = min(limit or 8, 20)
        fetch_limit = limit * 3 if context_symbol else limit
        exacts = self.lexical.search_exact(query, limit=fetch_limit)
        fts = self.lexical.search_fts(query, path_prefix=path_prefix, limit=fetch_limit * 2)

        ranked = self.ranker.fuse_and_rank(exacts, fts, query=query, limit=fetch_limit)

        if context_symbol:
            ranked = self._rerank_by_proximity(ranked, context_symbol, limit)

        if kinds:
            ranked = [r for r in ranked if r.get("kind") in kinds or r.get("entity_type") in kinds]

        is_filename_shaped = bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(\.\w+)?", query.strip()))
        if (
            is_filename_shaped
            and (not kinds or "file" in kinds)
            and not any(r.get("qualified_name") == query or r.get("name") == query for r in ranked)
        ):
            file_rows = self.db.search_files_by_name(query.strip(), limit=limit)
            existing_paths = {r.get("file_path") for r in ranked}
            for frow in file_rows:
                if frow["path"] in existing_paths:
                    continue
                ranked.append({
                    "entity_type": "file",
                    "file_path": frow["path"],
                    "title": frow["path"].rsplit("/", 1)[-1],
                    "start_line": 1,
                    "end_line": 1,
                    "match_reason": "filename_match",
                    "score": 0.0,
                })

        results = []
        for r in ranked:
            if r.get("entity_type") == "file":
                results.append({
                    "file": r.get("file_path"),
                    "title": r.get("title"),
                    "kind": "file",
                    "next_tool": "get_skeleton",
                    "match": {
                        "rank": r.get("rank"),
                        "score": r.get("score"),
                        "reason": r.get("match_reason"),
                        "proximity_depth": r.get("proximity_depth"),
                    },
                })
            elif r.get("entity_type") == "symbol":
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
                        "proximity_depth": r.get("proximity_depth"),
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
                        "proximity_depth": r.get("proximity_depth"),
                    },
                })

        results = results[:limit]
        return {
            "query": query,
            "retrieval_mode": "lexical-structural",
            "count": len(results),
            "results": results,
        }

    def _rerank_by_proximity(
        self,
        ranked: list[dict[str, Any]],
        context_symbol: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Reorders ranked results by call-graph distance from context_symbol."""
        seed_candidates = self.db.get_symbol_by_id_or_name(context_symbol)
        seed_ids: set[int] = set()
        if seed_candidates:
            seed_ids.update(c["id"] for c in seed_candidates)
            seed_ids.update(
                row["id"] for row in self.db.get_file_symbols(seed_candidates[0]["file_path"])
            )
        else:
            seed_ids.update(row["id"] for row in self.db.get_file_symbols(context_symbol))

        if not seed_ids:
            return ranked[:limit]

        distances = self.db.get_graph_proximity(sorted(seed_ids), max_depth=3)
        if not distances:
            return ranked[:limit]

        if not ranked:
            return []

        max_lexical_score = max(((r.get("score") or 0.0) for r in ranked), default=1.0) or 1.0
        for r in ranked:
            r["_rerank_score"] = r.get("score") or 0.0
            if r.get("entity_type") != "symbol":
                continue
            sym_id = r.get("entity_id")
            if sym_id is not None:
                depth = distances.get(sym_id)
                if depth is not None:
                    proximity_bonus = max_lexical_score * (0.5 / (1 + depth))
                    r["proximity_depth"] = depth
                    r["_rerank_score"] += proximity_bonus

        ranked.sort(key=lambda r: r["_rerank_score"], reverse=True)
        for idx, r in enumerate(ranked[:limit]):
            r["rank"] = idx + 1
            r.pop("_rerank_score", None)
        return ranked[:limit]

    def get_context(
        self,
        feature: str,
        path_prefix: Optional[str] = None,
        max_chars: int = 10000,
    ) -> dict[str, Any]:
        """Synthesizes deterministic feature documentation and key symbol signatures."""
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
        """Returns the structural skeleton of a file with implementation bodies redacted."""
        safe_path = self.repo_paths.resolve_user_path(file_path)
        if not safe_path.exists():
            return {"error": f"File '{file_path}' does not exist"}
        if not safe_path.is_file():
            return {"error": f"Path '{file_path}' is not a file"}

        skeleton = self.skeleton_renderer.render_file_skeleton(
            rel_path=self.repo_paths.to_relative(safe_path),
            max_chars=max_chars or 12000,
            session_tracker=self.session_tracker,
        )
        return {
            "file": file_path,
            "skeleton": skeleton,
        }

    def get_symbol_code(
        self,
        symbol: str,
        context_lines: int = 0,
        kind: Optional[str] = None,
        class_context: Optional[str] = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Retrieves exact declaration and implementation code for a specific symbol."""
        candidates = self.db.get_symbol_by_id_or_name(symbol)
        if not candidates:
            return {
                "status": "not_found",
                "error": f"Symbol '{symbol}' not found in index.",
            }

        if kind:
            kind_scoped = [c for c in candidates if c["kind"] == kind]
            if kind_scoped:
                candidates = kind_scoped
        if class_context:
            class_scoped = [c for c in candidates if class_context in (c["qualified_name"] or "")]
            if class_scoped:
                candidates = class_scoped

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
        if not abs_p.exists() or not abs_p.is_file():
            return {
                "status": "not_found",
                "error": f"Indexed file '{cand['file_path']}' is missing or not a regular file on disk.",
            }

        # Deduplication check
        if not force and self.session_tracker:
            emitted = self.session_tracker.get_emitted(
                symbol_key=cand["symbol_key"],
                file_path=cand["file_path"],
                start_line=cand["start_line"],
                end_line=cand["end_line"],
            )
            if emitted:
                return {
                    "status": "success",
                    "symbol_id": cand["symbol_key"],
                    "name": cand["name"],
                    "qualified_name": cand["qualified_name"],
                    "file": cand["file_path"],
                    "lines": [cand["start_line"], cand["end_line"]],
                    "kind": cand["kind"],
                    "is_deduplicated": True,
                    "code": self.session_tracker.format_back_reference(emitted),
                }

        code = render_symbol_body(
            file_path=abs_p,
            start_line=cand["start_line"],
            end_line=cand["end_line"],
            context_lines=context_lines or 0,
        )

        if self.session_tracker:
            self.session_tracker.record(
                symbol_key=cand["symbol_key"],
                symbol_name=cand["name"],
                file_path=cand["file_path"],
                start_line=cand["start_line"],
                end_line=cand["end_line"],
            )

        return {
            "status": "success",
            "symbol_id": cand["symbol_key"],
            "name": cand["name"],
            "qualified_name": cand["qualified_name"],
            "file": cand["file_path"],
            "lines": [cand["start_line"], cand["end_line"]],
            "kind": cand["kind"],
            "is_deduplicated": False,
            "code": code,
        }

    _NOISE_PATH_MARKERS = ("/test/", "/tests/", "/sample/", "/samples/", "/demo/", "/benchmark/", "/mock/")

    @classmethod
    def _is_noise_path(cls, file_path: str) -> bool:
        lowered = f"/{file_path.lower()}"
        return any(marker in lowered for marker in cls._NOISE_PATH_MARKERS)

    def find_usages(
        self,
        symbol: str,
        limit: int = 10,
        include_probable: bool = True,
        kind: Optional[str] = None,
        class_context: Optional[str] = None,
        min_confidence: Optional[float] = None,
    ) -> dict[str, Any]:
        """Finds cross-file references and call sites with AST-aware line context."""
        limit = min(limit or 10, 30)

        owner_hint: Optional[str] = class_context
        bare_name = symbol
        if "." in symbol:
            dotted_owner, bare_name = symbol.rsplit(".", 1)
            owner_hint = owner_hint or dotted_owner

        candidates = self.db.get_symbol_by_id_or_name(bare_name if owner_hint else symbol)
        if owner_hint and candidates:
            scoped = [c for c in candidates if owner_hint in (c["qualified_name"] or "")]
            if scoped:
                candidates = scoped
        if kind and candidates:
            kind_scoped = [c for c in candidates if c["kind"] == kind]
            if kind_scoped:
                candidates = kind_scoped

        def _count_matches(where_clause: str, params: tuple) -> int:
            with self.db.get_connection() as conn:
                row = conn.execute(
                    f"SELECT COUNT(*) as c FROM occurrences o LEFT JOIN symbols s ON o.enclosing_symbol_id = s.id WHERE {where_clause}",
                    params,
                ).fetchone()
                return row["c"]

        if not candidates:
            where = "o.spelling = ?"
            params: tuple = (bare_name,)
            if owner_hint:
                where += " AND o.receiver_text LIKE ?"
                params = (bare_name, f"%{owner_hint}%")

            total_matches = _count_matches(where, params)
            with self.db.get_connection() as conn:
                occs = conn.execute(
                    f"""
                    SELECT o.*, f.path as file_path, s.name as enclosing_name, s.kind as enclosing_kind
                    FROM occurrences o
                    JOIN files f ON o.file_id = f.id
                    LEFT JOIN symbols s ON o.enclosing_symbol_id = s.id
                    WHERE {where}
                    ORDER BY f.path
                    LIMIT ?
                    """,
                    (*params, limit * 4),
                ).fetchall()
        else:
            target_ids = [c["id"] for c in candidates]
            placeholders = ",".join("?" for _ in target_ids)
            where = f"(o.target_symbol_id IN ({placeholders}) OR o.spelling = ?)"
            params = (*target_ids, candidates[0]["name"])
            if owner_hint:
                where += f" AND (o.target_symbol_id IN ({placeholders}) OR (o.target_symbol_id IS NULL AND o.receiver_text LIKE ?))"
                params = (*params, *target_ids, f"%{owner_hint}%")

            total_matches = _count_matches(where, params)
            with self.db.get_connection() as conn:
                occs = conn.execute(
                    f"""
                    SELECT o.*, f.path as file_path, s.name as enclosing_name,
                           s.qualified_name as enclosing_qual, s.kind as enclosing_kind
                    FROM occurrences o
                    JOIN files f ON o.file_id = f.id
                    LEFT JOIN symbols s ON o.enclosing_symbol_id = s.id
                    WHERE {where}
                    ORDER BY f.path
                    LIMIT ?
                    """,
                    (*params, limit * 4),
                ).fetchall()

        exact_usages: list[dict[str, Any]] = []
        probable_usages: list[dict[str, Any]] = []
        noise_hidden = 0
        confidence_filtered = 0

        effective_include_probable = include_probable if min_confidence is None else True

        for o in occs:
            if self._is_noise_path(o["file_path"]):
                noise_hidden += 1
                continue
            occ_confidence = o["confidence"] or 0.0
            if min_confidence is not None and occ_confidence < min_confidence:
                confidence_filtered += 1
                continue
            if occ_confidence < 0.9 and not effective_include_probable:
                confidence_filtered += 1
                continue

            active_count = len(exact_usages) + (len(probable_usages) if effective_include_probable else 0)
            if active_count >= limit:
                break

            abs_p = self.repo_paths.resolve_user_path(o["file_path"])
            if not abs_p.exists() or not abs_p.is_file():
                continue
            snippet = render_code_snippet(abs_p, target_line=o["start_line"], context_lines=2)
            item = {
                "file": o["file_path"],
                "enclosing_symbol": o["enclosing_name"],
                "enclosing_kind": o["enclosing_kind"],
                "occurrence_role": o["role"],
                "line": o["start_line"],
                "resolution": o["resolution_kind"] or "probable",
                "confidence": o["confidence"] or 0.8,
                "snippet": snippet,
            }
            if occ_confidence >= 0.9:
                exact_usages.append(item)
            else:
                probable_usages.append(item)

        all_usages = exact_usages + (probable_usages if effective_include_probable else [])
        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in all_usages:
            grouped.setdefault(item["file"], []).append(item)
        usages_by_file = [
            {"file": f, "count": len(items), "usages": items}
            for f, items in grouped.items()
        ]

        result: dict[str, Any] = {
            "symbol": symbol,
            "total_found": len(all_usages),
            "exact_count": len(exact_usages),
            "probable_count": len(probable_usages) if effective_include_probable else 0,
            "usages_by_file": usages_by_file,
        }

        notes = []
        if noise_hidden:
            notes.append(f"+{noise_hidden} test/sample/demo/benchmark matches hidden. Pass a path_prefix-equivalent via class_context or widen kind to inspect them.")
        if confidence_filtered:
            notes.append(f"+{confidence_filtered} matches below confidence threshold hidden.")
        if notes:
            result["note"] = " ".join(notes)

        if not owner_hint and total_matches > limit * 3:
            result["warning"] = (
                f"'{symbol}' is a generic name with {total_matches} total matches in the index; "
                f"only {limit} are shown. Qualify via 'Owner.{symbol}' or class_context= to scope to a "
                f"specific receiver/type and get relevant results."
            )

        return result

    def find_implementations(
        self,
        symbol: str,
        transitive: bool = True,
    ) -> dict[str, Any]:
        """Finds all classes or interfaces that implement or extend a symbol."""
        candidates = self.db.get_symbol_by_id_or_name(symbol)
        rows = self.db.get_implementations(symbol, transitive=transitive)

        target_info = None
        if candidates:
            target_info = {
                "symbol_id": candidates[0]["symbol_key"],
                "name": candidates[0]["name"],
                "qualified_name": candidates[0]["qualified_name"],
                "kind": candidates[0]["kind"],
                "file": candidates[0]["file_path"],
                "lines": [candidates[0]["start_line"], candidates[0]["end_line"]],
            }

        direct = []
        indirect = []
        for r in rows:
            entry = {
                "symbol_id": r["symbol_key"],
                "name": r["name"],
                "qualified_name": r["qualified_name"],
                "kind": r["kind"],
                "file": r["file_path"],
                "lines": [r["start_line"], r["end_line"]],
                "signature": r["signature"],
                "depth": r["depth"],
            }
            if r["depth"] == 1:
                direct.append(entry)
            else:
                indirect.append(entry)

        return {
            "symbol": symbol,
            "target": target_info,
            "total_found": len(rows),
            "direct_count": len(direct),
            "indirect_count": len(indirect),
            "direct_implementers": direct,
            "indirect_implementers": indirect if transitive else [],
        }

    def read_lines(self, file_path: str, start: int, end: int) -> dict[str, Any]:
        """Reads a bounded slice of lines from a non-symbol or configuration file."""
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

    def read_file_structural(
        self,
        file_path: str,
        start: int = 1,
        end: Optional[int] = None,
        max_chars: int = 12000,
    ) -> dict[str, Any]:
        """Reads bounded lines from a file with attached architectural context."""
        safe_path = self.repo_paths.resolve_user_path(file_path)
        if not safe_path.exists():
            return {"error": f"File '{file_path}' does not exist"}
        if not safe_path.is_file():
            return {"error": f"Path '{file_path}' is not a file"}

        rel_path = self.repo_paths.to_relative(safe_path)
        lines = safe_path.read_text(encoding="utf-8", errors="replace").splitlines()
        total = len(lines)

        s_idx = max(1, start or 1)
        e_idx = min(total, end) if end is not None else min(total, s_idx + 150)

        if s_idx > e_idx or s_idx > total:
            selected_lines = []
        else:
            selected_lines = lines[s_idx - 1 : e_idx]

        # 1. Declared symbols
        symbols_rows = self.db.get_file_symbols(rel_path)
        symbols = [
            {
                "name": s["name"],
                "qualified_name": s["qualified_name"],
                "kind": s["kind"],
                "lines": [s["start_line"], s["end_line"]],
                "signature": s["signature"],
            }
            for s in symbols_rows
        ]

        # 2. Upstream dependents
        dependents = self.db.get_file_dependents(rel_path)

        # 3. Linked documentation
        symbol_names = [s["name"] for s in symbols_rows[:5]]
        docs_rows = self.db.get_linked_docs(symbol_names, file_path=rel_path, limit=3)
        linked_docs = [
            {
                "heading": d["heading"],
                "heading_path": d["heading_path"],
                "file": d["file_path"],
                "line": d["start_line"],
            }
            for d in docs_rows
        ]

        # Assemble structural header
        header_lines = [
            f"=== Structural Context: {rel_path} ===",
            f"Lines: {s_idx}-{e_idx} of {total}",
            "",
            f"Declared Symbols ({len(symbols)}):",
        ]
        if symbols:
            for s in symbols[:10]:
                sig = f" — {s['signature']}" if s.get("signature") else ""
                header_lines.append(f"  * {s['name']} [{s['kind']}] (L{s['lines'][0]}-L{s['lines'][1]}){sig}")
            if len(symbols) > 10:
                header_lines.append(f"  * ... +{len(symbols) - 10} more symbols")
        else:
            header_lines.append("  * None declared in this file.")

        header_lines.append("")
        header_lines.append(f"Upstream Dependents ({len(dependents)} files import/call this file):")
        if dependents:
            for dep in dependents[:6]:
                header_lines.append(f"  * {dep}")
            if len(dependents) > 6:
                header_lines.append(f"  * ... +{len(dependents) - 6} more dependent files")
        else:
            header_lines.append("  * No upstream dependent files recorded.")

        if linked_docs:
            header_lines.append("")
            header_lines.append(f"Linked Documentation ({len(linked_docs)} sections):")
            for doc in linked_docs:
                header_lines.append(f"  * {doc['heading_path'] or doc['heading']} ({doc['file']}:L{doc['line']})")

        header_lines.append("================================================================================")
        header_lines.append("")

        formatted_body = [f"{i + s_idx:4d} | {line}" for i, line in enumerate(selected_lines)]
        full_text = "\n".join(header_lines) + "\n" + "\n".join(formatted_body)

        budget = BudgetManager.create(max_chars=max_chars)
        bounded_content = budget.add(full_text)

        return {
            "file": rel_path,
            "start": s_idx,
            "end": e_idx,
            "total_lines": total,
            "symbols": symbols,
            "upstream_dependents": dependents,
            "linked_docs": linked_docs,
            "content": bounded_content,
        }

    def explore_flow(
        self,
        symbol: str,
        max_depth: int = 1,
        max_chars: int = 12000,
        force: bool = False,
    ) -> dict[str, Any]:
        """One-shot surgical flow exploration (anchor + callees + callers + docs)."""
        return self.flow_explorer.explore(
            symbol=symbol,
            max_depth=max_depth,
            max_chars=max_chars,
            session_tracker=self.session_tracker,
            force=force,
        )

    def analyze_impact(
        self,
        symbol: str,
        depth: int = 2,
        include_tests: bool = True,
        max_chars: int = 12000,
    ) -> dict[str, Any]:
        """Transitive blast radius and refactor safety analysis for a symbol."""
        return self.impact_analyzer.analyze(
            symbol=symbol,
            depth=depth,
            include_tests=include_tests,
            max_chars=max_chars,
        )

    def get_file_tree(
        self,
        dir_path: Optional[str] = None,
        depth: int = 3,
        max_entries: int = 100,
    ) -> dict[str, Any]:
        """Returns bounded repository directory structure respecting ignore patterns."""
        safe_path = self.repo_paths.resolve_user_path(dir_path or ".")
        if not safe_path.exists() or not safe_path.is_dir():
            return {"error": f"Directory '{dir_path}' does not exist"}

        discovery = FileDiscovery(self.repo_paths, self.indexer.config, self.registry)
        prefix = self.repo_paths.to_relative(safe_path)
        if prefix == ".":
            prefix = ""

        entries: list[dict[str, Any]] = []
        for df in discovery.discover():
            if prefix and not df.rel_path.startswith(prefix):
                continue
            rel_to_prefix = df.rel_path[len(prefix) :].lstrip("/") if prefix else df.rel_path
            if depth is not None and rel_to_prefix.count("/") >= depth:
                continue
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
