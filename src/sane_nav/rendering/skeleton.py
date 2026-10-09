from __future__ import annotations

import re
from typing import TYPE_CHECKING, Optional

from sane_nav.parsing.registry import ParserRegistry
from sane_nav.paths import RepoPaths
from sane_nav.storage.database import Database

if TYPE_CHECKING:
    from sane_nav.mcp.session import SessionDedupTracker


class SkeletonRenderer:
    def __init__(self, repo_paths: RepoPaths, db: Database, registry: ParserRegistry):
        self.repo_paths = repo_paths
        self.db = db
        self.registry = registry

    def render_file_skeleton(
        self,
        rel_path: str,
        max_chars: int = 12000,
        session_tracker: Optional[SessionDedupTracker] = None,
    ) -> str:
        abs_p = self.repo_paths.resolve_user_path(rel_path)
        if not abs_p.exists():
            return f"[Error: File '{rel_path}' does not exist]"

        source_bytes = abs_p.read_bytes()
        adapter = self.registry.for_path(rel_path)
        parsed = adapter.parse(rel_path, source_bytes)
        skeleton = adapter.render_skeleton(source_bytes, parsed)

        if session_tracker:
            comment_char = "#" if rel_path.endswith(".py") else "//"
            for sym in parsed.symbols:
                emitted = session_tracker.get_emitted(
                    symbol_key=sym.symbol_key,
                    file_path=rel_path,
                    start_line=sym.full_range.start_line,
                    end_line=sym.full_range.end_line,
                )
                if emitted:
                    back_ref = session_tracker.format_back_reference(emitted)
                    sig_anchor = sym.signature.splitlines()[0].strip() if sym.signature else sym.name
                    pat = rf"({re.escape(sig_anchor)}[\s\S]*?\n\s*{re.escape(comment_char)}\s*)\.\.\. implementation omitted \.\.\."
                    new_skeleton, num_subs = re.subn(pat, rf"\g<1>{back_ref}", skeleton, count=1)
                    if num_subs > 0:
                        skeleton = new_skeleton
                    else:
                        pat_fallback = rf"({re.escape(sym.name)}[\s\S]*?\n\s*{re.escape(comment_char)}\s*)\.\.\. implementation omitted \.\.\."
                        skeleton = re.sub(pat_fallback, rf"\g<1>{back_ref}", skeleton, count=1)

        if len(skeleton) > max_chars:
            return skeleton[:max_chars] + f"\n\n... [Skeleton truncated at {max_chars} chars. Request specific symbols directly]"

        return skeleton
