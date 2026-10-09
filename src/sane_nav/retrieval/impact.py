"""Impact analysis service for S.A.N.E.

Implements transitive blast radius and refactor safety analysis (upstream callers
up to depth N + subclass/interface implementers + affected test suites).
"""

from __future__ import annotations

from typing import Any

from sane_nav.paths import RepoPaths
from sane_nav.rendering.budget import BudgetManager
from sane_nav.storage.database import Database


class ImpactAnalyzer:
    """Computes the transitive blast radius and refactoring impact for a symbol."""

    def __init__(self, repo_paths: RepoPaths, db: Database):
        self.repo_paths = repo_paths
        self.db = db

    def analyze(
        self,
        symbol: str,
        depth: int = 2,
        include_tests: bool = True,
        max_chars: int = 12000,
    ) -> dict[str, Any]:
        """Analyzes code and test impact if symbol is modified or deleted.

        Args:
            symbol: Target symbol name or symbol key.
            depth: Upstream caller recursion depth (default: 2, max: 4).
            include_tests: Whether to inspect test occurrences.
            max_chars: Output character limit.

        Returns:
            Dictionary with impact metrics, caller hierarchy, implementers, tests, and report.
        """
        candidates = self.db.get_symbol_by_id_or_name(symbol)
        if not candidates:
            return {
                "status": "not_found",
                "error": f"Symbol '{symbol}' not found in index.",
            }

        if len(candidates) > 1:
            exact = [c for c in candidates if symbol in (c["symbol_key"], c["qualified_name"])]
            if len(exact) == 1:
                anchor = exact[0]
            else:
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
        else:
            anchor = candidates[0]

        depth_limit = max(1, min(depth, 4))

        # 1. Recursive upstream callers
        caller_rows = self.db.get_upstream_callers(anchor["id"], max_depth=depth_limit)
        direct_callers: list[dict[str, Any]] = []
        transitive_callers: list[dict[str, Any]] = []

        for r in caller_rows:
            item = {
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
                direct_callers.append(item)
            else:
                transitive_callers.append(item)

        # 2. Implementers and subclasses (recursive CTE)
        imp_rows = self.db.get_implementations(anchor["symbol_key"], transitive=True)
        implementers: list[dict[str, Any]] = []
        for r in imp_rows:
            implementers.append({
                "symbol_id": r["symbol_key"],
                "name": r["name"],
                "qualified_name": r["qualified_name"],
                "kind": r["kind"],
                "file": r["file_path"],
                "lines": [r["start_line"], r["end_line"]],
                "signature": r["signature"],
                "depth": r["depth"],
            })

        # 3. Affected test suites and occurrences
        affected_symbol_ids = [anchor["id"]] + [r["id"] for r in imp_rows]
        affected_tests: list[dict[str, Any]] = []
        test_files_set: set[str] = set()

        if include_tests:
            test_rows = self.db.get_affected_tests(affected_symbol_ids)
            for r in test_rows:
                test_files_set.add(r["file_path"])
                affected_tests.append({
                    "file": r["file_path"],
                    "line": r["start_line"],
                    "spelling": r["spelling"],
                    "role": r["role"],
                    "confidence": r["confidence"],
                    "test_suite_or_method": r["test_suite_or_method"],
                    "target_symbol": r["target_symbol_name"],
                })

        # Render report under OutputBudget
        budget = BudgetManager.create(max_chars=max_chars)
        total_callers = len(direct_callers) + len(transitive_callers)

        report_lines: list[str] = [
            f"# Impact Analysis: `{anchor['qualified_name'] or anchor['name']}`",
            f"- **Target**: `{anchor['file_path']}:{anchor['start_line']}-{anchor['end_line']}` [{anchor['kind']}]",
            f"- **Signature**: `{anchor['signature']}`",
            f"- **Blast Radius**: {total_callers} callers ({len(direct_callers)} direct, {len(transitive_callers)} transitive), {len(implementers)} implementers, {len(test_files_set)} test files",
            "",
            f"## Upstream Callers ({total_callers}) [Depth \u2264 {depth_limit}]",
        ]

        if direct_callers:
            report_lines.append(f"### Direct Callers (Depth 1: {len(direct_callers)})")
            for c in direct_callers:
                report_lines.append(f"* `{c['name']}` [{c['kind']}] at `{c['file']}:{c['lines'][0]}`")
                if c.get("signature"):
                    report_lines.append(f"  `{c['signature']}`")

        if transitive_callers:
            report_lines.append(f"### Transitive Callers (Depth 2-{depth_limit}: {len(transitive_callers)})")
            for c in transitive_callers:
                report_lines.append(f"* `{c['name']}` (depth {c['depth']}) [{c['kind']}] at `{c['file']}:{c['lines'][0]}`")
                if c.get("signature"):
                    report_lines.append(f"  `{c['signature']}`")

        if not direct_callers and not transitive_callers:
            report_lines.append("* No upstream callers found in call graph.")

        if implementers:
            report_lines.append("")
            report_lines.append(f"## Subclasses & Implementers ({len(implementers)})")
            for imp in implementers:
                rel = "Direct" if imp["depth"] == 1 else f"Transitive (depth {imp['depth']})"
                report_lines.append(f"* `{imp['name']}` [{imp['kind']}] ({rel}) at `{imp['file']}:{imp['lines'][0]}`")
                if imp.get("signature"):
                    report_lines.append(f"  `{imp['signature']}`")

        if include_tests:
            report_lines.append("")
            report_lines.append(f"## Affected Test Suites ({len(test_files_set)} files, {len(affected_tests)} occurrences)")
            if affected_tests:
                # Group by file
                tests_by_file: dict[str, list[dict[str, Any]]] = {}
                for t in affected_tests:
                    tests_by_file.setdefault(t["file"], []).append(t)

                for f_path, t_items in tests_by_file.items():
                    report_lines.append(f"### `{f_path}` ({len(t_items)} references)")
                    for item in t_items[:5]:  # limit occurrences per file in report
                        context = f"in `{item['test_suite_or_method']}`" if item.get("test_suite_or_method") else ""
                        report_lines.append(f"* L{item['line']}: call to `{item['spelling']}` {context}".strip())
                    if len(t_items) > 5:
                        report_lines.append(f"* ... +{len(t_items) - 5} more references in this test file")
            else:
                report_lines.append("* No direct test references found.")

        report_markdown = budget.add("\n".join(report_lines))

        return {
            "status": "success",
            "symbol": anchor["name"],
            "symbol_id": anchor["symbol_key"],
            "qualified_name": anchor["qualified_name"],
            "file": anchor["file_path"],
            "lines": [anchor["start_line"], anchor["end_line"]],
            "kind": anchor["kind"],
            "summary": {
                "direct_callers": len(direct_callers),
                "transitive_callers": len(transitive_callers),
                "total_callers": total_callers,
                "implementers": len(implementers),
                "affected_test_files": len(test_files_set),
                "affected_test_occurrences": len(affected_tests),
                "max_depth": depth_limit,
            },
            "upstream_callers": direct_callers + transitive_callers,
            "implementers": implementers,
            "affected_tests": affected_tests,
            "report": report_markdown,
        }
