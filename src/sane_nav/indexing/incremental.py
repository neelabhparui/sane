from __future__ import annotations

import logging
from pathlib import Path

from sane_nav.indexing.indexer import Indexer

logger = logging.getLogger("sane_nav.incremental")


class IncrementalSync:
    def __init__(self, indexer: Indexer):
        self.indexer = indexer

    def sync_changed_path(self, path: Path | str) -> bool:
        """Processes a single modified or deleted file path."""
        rel_path = self.indexer.repo_paths.to_relative(path)
        logger.debug(f"Syncing path: {rel_path}")
        return self.indexer.index_single_file(rel_path)

    def scan_for_drift(self) -> dict[str, int]:
        """Runs a fast drift scan across the repository."""
        return self.indexer.index_all()
