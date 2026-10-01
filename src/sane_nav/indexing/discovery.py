from __future__ import annotations

import fnmatch
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from sane_nav.config import SaneConfig
from sane_nav.parsing.registry import ParserRegistry
from sane_nav.paths import RepoPaths


@dataclass(frozen=True)
class DiscoveredFile:
    rel_path: str
    abs_path: Path
    size_bytes: int
    mtime_ns: int
    language: str


def compute_content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class FileDiscovery:
    def __init__(self, repo_paths: RepoPaths, config: SaneConfig, registry: ParserRegistry):
        self.repo_paths = repo_paths
        self.config = config
        self.registry = registry
        self._gitignore_patterns: list[str] = []
        if self.config.repository.respect_gitignore:
            self._load_gitignore()

    def _load_gitignore(self) -> None:
        gi = self.repo_paths.repo_root / ".gitignore"
        if gi.exists():
            for line in gi.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    self._gitignore_patterns.append(line)

    def is_ignored(self, rel_path: str) -> bool:
        # Check explicit exclude patterns
        for pattern in self.config.repository.exclude:
            if fnmatch.fnmatch(rel_path, pattern):
                return True
            if pattern.endswith("/**") and rel_path.startswith(pattern[:-3]):
                return True

        # Check gitignore patterns
        for pattern in self._gitignore_patterns:
            p = pattern.rstrip("/")
            if fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(Path(rel_path).name, pattern):
                return True
            if "/" not in p:
                # Matches filename anywhere
                if fnmatch.fnmatch(Path(rel_path).name, p):
                    return True
            elif rel_path.startswith(p):
                return True

        return False

    def discover(self) -> Iterator[DiscoveredFile]:
        root = self.repo_paths.repo_root
        for dirpath, dirnames, filenames in os.walk(root):
            # Prune ignored directories in-place for speed
            rel_dir = os.path.relpath(dirpath, root).replace("\\", "/")
            if rel_dir == ".":
                rel_dir = ""

            dirnames[:] = [
                d for d in dirnames
                if not d.startswith(".")
                and not self.is_ignored(f"{rel_dir}/{d}" if rel_dir else d)
            ]

            for fname in filenames:
                if fname.startswith("."):
                    continue
                rel_path = f"{rel_dir}/{fname}" if rel_dir else fname
                if self.is_ignored(rel_path):
                    continue

                if not self.registry.is_supported(fname):
                    continue

                abs_p = Path(dirpath) / fname
                try:
                    stat = abs_p.stat()
                except OSError:
                    continue

                if stat.st_size > self.config.repository.max_file_bytes:
                    continue

                adapter = self.registry.for_path(fname)
                yield DiscoveredFile(
                    rel_path=rel_path,
                    abs_path=abs_p,
                    size_bytes=stat.st_size,
                    mtime_ns=stat.st_mtime_ns,
                    language=adapter.language,
                )
