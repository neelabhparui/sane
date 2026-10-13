from __future__ import annotations

import asyncio
import logging
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from sane_nav.indexing.incremental import IncrementalSync

try:
    from watchfiles import awatch
except ImportError:
    awatch = None  # type: ignore

logger = logging.getLogger("sane_nav.watcher")


class RepoWatcher:
    """Continuously monitors repository files and triggers incremental AST indexing."""

    def __init__(self, repo_root: Path, sync: IncrementalSync, debounce_ms: int = 300):
        self.repo_root = Path(repo_root)
        self.sync = sync
        self.debounce_ms = debounce_ms
        self._running = False

    async def start(self) -> None:
        self._running = True
        if awatch is not None:
            logger.info(f"Started watchfiles on {self.repo_root}")
            async for changes in awatch(self.repo_root, debounce=self.debounce_ms):
                if not self._running:
                    break
                for _, path_str in changes:
                    if ".sane" in path_str or ".git" in path_str:
                        continue
                    self.sync.sync_changed_path(path_str)
        else:
            logger.info("watchfiles not installed; watcher running in periodic polling fallback mode.")
            while self._running:
                await asyncio.sleep(self.debounce_ms / 1000.0 * 10)
                self.sync.scan_for_drift()

    def stop(self) -> None:
        self._running = False


def get_pid_file(repo_root: Path) -> Path:
    """Returns the path to the background watcher PID file."""
    return Path(repo_root) / ".sane" / "watcher.pid"


def get_log_file(repo_root: Path) -> Path:
    """Returns the path to the background watcher log file."""
    return Path(repo_root) / ".sane" / "watcher.log"


def is_pid_alive(pid: int) -> bool:
    """Checks whether a process with the given PID is currently active."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def start_daemon(repo_root: Path, debounce_ms: int = 300) -> tuple[bool, str, Optional[int]]:
    """Starts the repository watcher as a detached background daemon.

    Returns:
        (success, message, pid)
    """
    repo_root = Path(repo_root).resolve()
    pid_file = get_pid_file(repo_root)
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
            if is_pid_alive(pid):
                return False, f"Watcher daemon is already running (PID {pid})", pid
        except (ValueError, OSError):
            pass

    log_path = get_log_file(repo_root)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        "-m",
        "sane_nav.cli",
        "watch",
        "--repo",
        str(repo_root),
        "--foreground",
        "--debounce",
        str(debounce_ms),
    ]

    with open(log_path, "a", encoding="utf-8") as f:
        proc = subprocess.Popen(  # pylint: disable=consider-using-with
            cmd,
            stdout=f,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    pid_file.write_text(str(proc.pid), encoding="utf-8")
    return True, f"Started background watcher daemon (PID {proc.pid})", proc.pid


def stop_daemon(repo_root: Path) -> tuple[bool, str]:
    """Stops the running background watcher daemon."""
    repo_root = Path(repo_root).resolve()
    pid_file = get_pid_file(repo_root)
    if not pid_file.exists():
        return False, "Watcher daemon is not running"

    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except ValueError:
        pid_file.unlink(missing_ok=True)
        return False, "Invalid watcher PID file removed"

    if is_pid_alive(pid):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError as e:
            return False, f"Failed to stop watcher daemon (PID {pid}): {e}"

    pid_file.unlink(missing_ok=True)
    return True, f"Stopped watcher daemon (PID {pid})"


def status_daemon(repo_root: Path) -> dict[str, Any]:
    """Queries the operational status of the background watcher daemon."""
    repo_root = Path(repo_root).resolve()
    pid_file = get_pid_file(repo_root)
    log_file = get_log_file(repo_root)

    if not pid_file.exists():
        return {"running": False, "pid": None, "log_file": str(log_file)}

    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
        alive = is_pid_alive(pid)
        if not alive:
            pid_file.unlink(missing_ok=True)
            return {"running": False, "pid": None, "log_file": str(log_file)}
        return {"running": True, "pid": pid, "log_file": str(log_file)}
    except ValueError:
        pid_file.unlink(missing_ok=True)
        return {"running": False, "pid": None, "log_file": str(log_file)}
