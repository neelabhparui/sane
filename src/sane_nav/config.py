from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib  # type: ignore
    except ImportError:
        tomllib = None  # type: ignore


@dataclass
class RepositoryConfig:
    respect_gitignore: bool = True
    max_file_bytes: int = 2 * 1024 * 1024  # 2MB
    include: list[str] = field(default_factory=lambda: [
        "**/*.py",
        "**/*.java",
        "**/*.kt",
        "**/*.kts",
        "**/*.md",
    ])
    exclude: list[str] = field(default_factory=lambda: [
        ".git/**",
        ".sane/**",
        "build/**",
        "dist/**",
        "node_modules/**",
        ".gradle/**",
        ".idea/**",
        ".venv/**",
        "__pycache__/**",
        "*.pyc",
    ])


@dataclass
class IndexConfig:
    parse_workers: int = 4


@dataclass
class WatchConfig:
    enabled: bool = True
    debounce_ms: int = 300


@dataclass
class SearchConfig:
    semantic: bool = False
    default_limit: int = 8


@dataclass
class OutputConfig:
    max_chars: int = 12000
    max_usages: int = 20


@dataclass
class SaneConfig:
    repository: RepositoryConfig = field(default_factory=RepositoryConfig)
    index: IndexConfig = field(default_factory=IndexConfig)
    watch: WatchConfig = field(default_factory=WatchConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    output: OutputConfig = field(default_factory=OutputConfig)

    @classmethod
    def load(cls, repo_root: Path) -> "SaneConfig":
        config_file = repo_root / ".sane.toml"
        if not config_file.exists():
            return cls()

        if tomllib is None:
            # Fallback simple parser for .sane.toml if tomllib/tomli is not yet installed
            return cls._load_simple(config_file)

        try:
            with open(config_file, "rb") as f:
                data = tomllib.load(f)
            return cls.from_dict(data)
        except Exception:
            return cls()

    @classmethod
    def _load_simple(cls, config_file: Path) -> "SaneConfig":
        # Basic key-value parser for simple toml files
        return cls()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SaneConfig":
        repo_data = data.get("repository", {})
        index_data = data.get("index", {})
        watch_data = data.get("watch", {})
        search_data = data.get("search", {})
        output_data = data.get("output", {})

        return cls(
            repository=RepositoryConfig(
                respect_gitignore=repo_data.get("respect_gitignore", True),
                max_file_bytes=repo_data.get("max_file_bytes", 2097152),
                include=repo_data.get("include", RepositoryConfig().include),
                exclude=repo_data.get("exclude", RepositoryConfig().exclude),
            ),
            index=IndexConfig(
                parse_workers=index_data.get("parse_workers", 4),
            ),
            watch=WatchConfig(
                enabled=watch_data.get("enabled", True),
                debounce_ms=watch_data.get("debounce_ms", 300),
            ),
            search=SearchConfig(
                semantic=search_data.get("semantic", False),
                default_limit=search_data.get("default_limit", 8),
            ),
            output=OutputConfig(
                max_chars=output_data.get("max_chars", 12000),
                max_usages=output_data.get("max_usages", 20),
            ),
        )
