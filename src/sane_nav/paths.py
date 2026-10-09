"""Path containment and repository boundary security.

Enforces strict containment of all accessed file paths within the configured
repository root to prevent directory traversal attacks, symlink escapes,
and unauthorized access to sensitive credential stores.
"""

from __future__ import annotations

from pathlib import Path

from sane_nav.core.errors import PathOutsideRepository

SENSITIVE_PATTERNS = {
    ".env",
    ".env.local",
    ".env.production",
    "id_rsa",
    "id_ed25519",
}

SENSITIVE_EXTENSIONS = {
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".keystore",
}


class RepoPaths:
    """Manages repository path resolution and security validation."""

    def __init__(self, repo_root: str | Path):
        """Initializes with the resolved root path of the target repository."""
        self.repo_root = Path(repo_root).resolve()

    def resolve_user_path(self, user_path: str | Path, allow_sensitive: bool = False) -> Path:
        """Resolves a user-provided path and verifies it strictly stays within the repo root.

        Rejects paths escaping repository boundary or symlinks pointing outside.

        Args:
            user_path: Relative or absolute path requested by an agent or user.
            allow_sensitive: If True, bypasses secret file checks (.env, .pem).

        Returns:
            Resolved absolute Path guaranteed to be within the repository.

        Raises:
            PathOutsideRepository: If the path escapes the repository root
                or points to a blocked sensitive credential store.
        """
        raw_path = Path(user_path)
        if raw_path.is_absolute():
            candidate = raw_path.resolve()
        else:
            candidate = (self.repo_root / raw_path).resolve()

        try:
            candidate.relative_to(self.repo_root)
        except ValueError as exc:
            raise PathOutsideRepository(
                f"Security violation: path '{user_path}' escapes repository root '{self.repo_root}'"
            ) from exc

        if not allow_sensitive:
            if candidate.name in SENSITIVE_PATTERNS or candidate.suffix in SENSITIVE_EXTENSIONS:
                raise PathOutsideRepository(
                    f"Access to sensitive file '{candidate.name}' is blocked by default security policy."
                )

        return candidate

    def to_relative(self, path: str | Path) -> str:
        """Converts an absolute path to clean posix relative path from repo root."""
        p = Path(path).resolve()
        try:
            rel = p.relative_to(self.repo_root)
            return rel.as_posix()
        except ValueError:
            return p.as_posix()

    @property
    def sane_dir(self) -> Path:
        """Directory storing S.A.N.E. index and locks: .sane/"""
        return self.repo_root / ".sane"

    @property
    def db_path(self) -> Path:
        """Absolute path to the SQLite index database."""
        return self.sane_dir / "index.db"

    @property
    def lock_path(self) -> Path:
        """Absolute path to the advisory single-writer lock."""
        return self.sane_dir / "writer.lock"
