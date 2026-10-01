from __future__ import annotations

from pathlib import Path
from typing import Optional

from sane_nav.core.models import ParsedFile
from sane_nav.parsing.registry import ParserRegistry
from sane_nav.paths import RepoPaths
from sane_nav.storage.database import Database


class SkeletonRenderer:
    def __init__(self, repo_paths: RepoPaths, db: Database, registry: ParserRegistry):
        self.repo_paths = repo_paths
        self.db = db
        self.registry = registry

    def render_file_skeleton(self, rel_path: str, max_chars: int = 12000) -> str:
        abs_p = self.repo_paths.resolve_user_path(rel_path)
        if not abs_p.exists():
            return f"[Error: File '{rel_path}' does not exist]"

        source_bytes = abs_p.read_bytes()
        adapter = self.registry.for_path(rel_path)
        parsed = adapter.parse(rel_path, source_bytes)
        skeleton = adapter.render_skeleton(source_bytes, parsed)

        if len(skeleton) > max_chars:
            return skeleton[:max_chars] + f"\n\n... [Skeleton truncated at {max_chars} chars. Request specific symbols directly]"

        return skeleton
