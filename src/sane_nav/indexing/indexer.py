from __future__ import annotations

import logging
from typing import Callable, Optional

from sane_nav.config import SaneConfig
from sane_nav.indexing.discovery import FileDiscovery, compute_content_hash
from sane_nav.indexing.resolver import SymbolResolver
from sane_nav.parsing.registry import ParserRegistry
from sane_nav.paths import RepoPaths
from sane_nav.storage.database import Database

logger = logging.getLogger("sane_nav.indexer")


class Indexer:
    def __init__(
        self,
        repo_paths: RepoPaths,
        db: Database,
        config: Optional[SaneConfig] = None,
        registry: Optional[ParserRegistry] = None,
    ):
        self.repo_paths = repo_paths
        self.db = db
        self.config = config or SaneConfig.load(repo_paths.repo_root)
        self.registry = registry or ParserRegistry()
        self.discovery = FileDiscovery(repo_paths, self.config, self.registry)
        self.resolver = SymbolResolver(db)

    def index_all(self, on_progress: Optional[Callable[[str, int, int], None]] = None) -> dict[str, int]:
        """Performs a full or incremental scan of the repository."""
        discovered = list(self.discovery.discover())
        total = len(discovered)
        indexed_count = 0
        skipped_count = 0

        for idx, file_info in enumerate(discovered):
            if on_progress:
                on_progress(file_info.rel_path, idx + 1, total)

            # Check existing file record and content hash for fast drift check
            existing = self.db.get_file(file_info.rel_path)
            content = file_info.abs_path.read_bytes()
            chash = compute_content_hash(content)

            if existing and existing["content_hash"] == chash:
                skipped_count += 1
                continue

            try:
                adapter = self.registry.for_path(file_info.rel_path)
                parsed = adapter.parse(file_info.rel_path, content)
                self.db.upsert_file_index(
                    file_path=file_info.rel_path,
                    language=file_info.language,
                    content_hash=chash,
                    size_bytes=file_info.size_bytes,
                    mtime_ns=file_info.mtime_ns,
                    parsed=parsed,
                )
                indexed_count += 1
            except Exception as e:
                logger.error(f"Error indexing {file_info.rel_path}: {e}")

        # Post-index resolution
        resolved_count = self.resolver.resolve_all_occurrences()

        return {
            "total_files": total,
            "indexed_files": indexed_count,
            "skipped_files": skipped_count,
            "resolved_references": resolved_count,
        }

    def index_single_file(self, rel_path: str) -> bool:
        abs_p = self.repo_paths.resolve_user_path(rel_path)
        if not abs_p.exists():
            with self.db.get_connection() as conn:
                self.db.delete_file_index(conn, rel_path)
                conn.commit()
            return True

        if not self.registry.is_supported(rel_path):
            return False

        content = abs_p.read_bytes()
        chash = compute_content_hash(content)
        stat = abs_p.stat()
        adapter = self.registry.for_path(rel_path)
        parsed = adapter.parse(rel_path, content)

        self.db.upsert_file_index(
            file_path=rel_path,
            language=adapter.language,
            content_hash=chash,
            size_bytes=stat.st_size,
            mtime_ns=stat.st_mtime_ns,
            parsed=parsed,
        )
        self.resolver.resolve_all_occurrences()
        return True
