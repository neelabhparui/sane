from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Callable, Optional

from sane_nav.indexing.incremental import IncrementalSync

logger = logging.getLogger("sane_nav.watcher")


class RepoWatcher:
    def __init__(self, repo_root: Path, sync: IncrementalSync, debounce_ms: int = 300):
        self.repo_root = Path(repo_root)
        self.sync = sync
        self.debounce_ms = debounce_ms
        self._running = False

    async def start(self) -> None:
        self._running = True
        try:
            from watchfiles import awatch

            logger.info(f"Started watchfiles on {self.repo_root}")
            async for changes in awatch(self.repo_root, debounce=self.debounce_ms):
                if not self._running:
                    break
                for change_type, path_str in changes:
                    if ".sane" in path_str or ".git" in path_str:
                        continue
                    self.sync.sync_changed_path(path_str)
        except ImportError:
            logger.info("watchfiles not installed; watcher running in periodic polling fallback mode.")
            while self._running:
                await asyncio.sleep(self.debounce_ms / 1000.0 * 10)
                self.sync.scan_for_drift()

    def stop(self) -> None:
        self._running = False
