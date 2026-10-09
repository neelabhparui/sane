"""Flow exploration service for S.A.N.E.

Implements one-shot surgical flow exploration (anchor symbol implementation +
outbound callees + inbound callers + fused documentation).
"""

from __future__ import annotations

from typing import Any, Optional

from sane_nav.mcp.session import SessionDedupTracker
from sane_nav.paths import RepoPaths
from sane_nav.rendering.budget import BudgetManager
from sane_nav.rendering.snippets import render_symbol_body
from sane_nav.storage.database import Database


class FlowExplorer:
    """Explores code flow around a focal anchor symbol in a single round-trip."""

    def __init__(self, repo_paths: RepoPaths, db: Database):
        self.repo_paths = repo_paths
        self.db = db

    def _detect_language(self, path: str) -> str:
        if path.endswith(".py"):
            return "python"
        if path.endswith(".java"):
            return "java"
        if path.endswith((".kt", ".kts")):
            return "kotlin"
        if path.endswith(".swift"):
            return "swift"
        if path.endswith(".md"):
            return "markdown"
        return "text"

    def explore(
        self,
        symbol: str,
        max_depth: int = 1,
        max_chars: int = 12000,
        session_tracker: Optional[SessionDedupTracker] = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Explores the full execution flow around symbol.

        Args:
            symbol: Symbol name, qualified name, or symbol key.
            max_depth: Call graph traversal depth for callees (default: 1, max: 2).
            max_chars: Output character limit.
            session_tracker: Optional session deduplication tracker.
            force: If True, bypasses session deduplication.

        Returns:
            Dictionary containing flow report and structured components.
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

        abs_p = self.repo_paths.resolve_user_path(anchor["file_path"])
        if not abs_p.exists() or not abs_p.is_file():
            return {
                "status": "not_found",
                "error": f"File '{anchor['file_path']}' is missing on disk.",
            }

        # Session deduplication check
        code_body = ""
        is_deduped = False
        if session_tracker and not force:
            emitted = session_tracker.get_emitted(
                symbol_key=anchor["symbol_key"],
                file_path=anchor["file_path"],
                start_line=anchor["start_line"],
                end_line=anchor["end_line"],
            )
            if emitted:
                code_body = session_tracker.format_back_reference(emitted)
                is_deduped = True

        if not is_deduped:
            code_body = render_symbol_body(
                file_path=abs_p,
                start_line=anchor["start_line"],
                end_line=anchor["end_line"],
            )
            if session_tracker:
                session_tracker.record(
                    symbol_key=anchor["symbol_key"],
                    symbol_name=anchor["name"],
                    file_path=anchor["file_path"],
                    start_line=anchor["start_line"],
                    end_line=anchor["end_line"],
                )

        # Outbound callees
        callee_rows = self.db.get_downstream_callees(anchor["id"], max_depth=max(1, min(max_depth, 2)))
        callees: list[dict[str, Any]] = []
        for crow in callee_rows:
            callees.append({
                "symbol_id": crow["symbol_key"],
                "name": crow["name"],
                "qualified_name": crow["qualified_name"],
                "kind": crow["kind"],
                "file": crow["file_path"],
                "lines": [crow["start_line"], crow["end_line"]],
                "signature": crow["signature"],
                "docstring": crow["docstring"],
                "depth": crow["depth"],
            })

        # Inbound callers
        caller_rows = self.db.get_upstream_callers(anchor["id"], max_depth=1)
        callers: list[dict[str, Any]] = []
        for crow in caller_rows:
            callers.append({
                "symbol_id": crow["symbol_key"],
                "name": crow["name"],
                "qualified_name": crow["qualified_name"],
                "kind": crow["kind"],
                "file": crow["file_path"],
                "lines": [crow["start_line"], crow["end_line"]],
                "signature": crow["signature"],
            })

        # Matching documentation
        doc_names = [anchor["name"]]
        if anchor["qualified_name"] and anchor["qualified_name"] != anchor["name"]:
            doc_names.append(anchor["qualified_name"])
        doc_rows = self.db.get_linked_docs(doc_names, file_path=anchor["file_path"], limit=2)
        docs: list[dict[str, Any]] = []
        for drow in doc_rows:
            docs.append({
                "doc_id": drow["id"],
                "heading": drow["heading"],
                "heading_path": drow["heading_path"],
                "file": drow["file_path"],
                "lines": [drow["start_line"], drow["end_line"]],
                "content": drow["content"],
            })

        # Render markdown under OutputBudget
        budget = BudgetManager.create(max_chars=max_chars)
        lang = self._detect_language(anchor["file_path"])

        lines: list[str] = [
            f"# Flow Analysis: `{anchor['qualified_name'] or anchor['name']}`",
            f"- **File**: `{anchor['file_path']}:{anchor['start_line']}-{anchor['end_line']}`",
            f"- **Kind**: `{anchor['kind']}`",
            f"- **Signature**: `{anchor['signature']}`",
            "",
            "## Verbatim Implementation",
        ]

        if is_deduped:
            lines.append(code_body)
        else:
            lines.append(f"```{lang}\n{code_body}\n```")

        lines.append("")
        lines.append(f"## Outbound Callees ({len(callees)})")
        if callees:
            for callee_item in callees:
                lines.append(
                    f"* `{callee_item['name']}` [{callee_item['kind']}] at `{callee_item['file']}:{callee_item['lines'][0]}` (depth {callee_item['depth']})"
                )
                if callee_item.get("signature"):
                    lines.append(f"  Signature: `{callee_item['signature']}`")
                if callee_item.get("docstring"):
                    first_doc = callee_item["docstring"].strip().split("\n")[0]
                    lines.append(f"  // Doc: {first_doc}")
        else:
            lines.append("* No outbound resolved callees recorded.")

        lines.append("")
        lines.append(f"## Inbound Callers ({len(callers)})")
        if callers:
            for caller_item in callers:
                lines.append(f"* `{caller_item['name']}` [{caller_item['kind']}] at `{caller_item['file']}:{caller_item['lines'][0]}`")
                if caller_item.get("signature"):
                    lines.append(f"  Signature: `{caller_item['signature']}`")
        else:
            lines.append("* No inbound callers recorded in graph.")

        if docs:
            lines.append("")
            lines.append(f"## Documentation Context ({len(docs)})")
            for doc_item in docs:
                heading = doc_item.get("heading_path") or doc_item.get("heading")
                lines.append(f"### {heading} (`{doc_item['file']}:L{doc_item['lines'][0]}`)")
                content_preview = doc_item["content"].strip()
                if len(content_preview) > 300:
                    content_preview = content_preview[:300] + "..."
                lines.append(content_preview)

        flow_markdown = budget.add("\n".join(lines))

        return {
            "status": "success",
            "symbol": anchor["name"],
            "symbol_id": anchor["symbol_key"],
            "qualified_name": anchor["qualified_name"],
            "file": anchor["file_path"],
            "lines": [anchor["start_line"], anchor["end_line"]],
            "kind": anchor["kind"],
            "is_deduplicated": is_deduped,
            "flow": flow_markdown,
            "callees": callees,
            "callers": callers,
            "docs": docs,
        }
