import asyncio
from pathlib import Path
from unittest.mock import patch
import pytest

from sane_nav.config import RepositoryConfig, SaneConfig
from sane_nav.core.errors import PathOutsideRepository
from sane_nav.indexing.discovery import FileDiscovery
from sane_nav.indexing.incremental import IncrementalSync
from sane_nav.indexing.indexer import Indexer
from sane_nav.indexing.watcher import RepoWatcher
from sane_nav.parsing.registry import ParserRegistry
from sane_nav.paths import RepoPaths
from sane_nav.storage.database import Database


@pytest.fixture
def index_repo(tmp_path: Path) -> Path:
    fixtures_dir = Path(__file__).parent / "fixtures"
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True)
    (src_dir / "payment_service.py").write_bytes(
        (fixtures_dir / "python" / "payment_service.py").read_bytes()
    )
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True)
    (docs_dir / "architecture.md").write_bytes(
        (fixtures_dir / "markdown" / "architecture.md").read_bytes()
    )
    return tmp_path


def test_paths_security_and_containment(tmp_path: Path):
    paths = RepoPaths(tmp_path)

    # Valid relative path
    p = paths.resolve_user_path("src/app.py")
    assert p == tmp_path / "src" / "app.py"

    # Valid absolute path inside repo
    abs_sub = tmp_path / "src" / "mod.py"
    assert paths.resolve_user_path(abs_sub) == abs_sub

    # Path traversal attack
    with pytest.raises(PathOutsideRepository):
        paths.resolve_user_path("../../etc/passwd")

    with pytest.raises(PathOutsideRepository):
        paths.resolve_user_path("/etc/passwd")

    # Sensitive files blocked
    with pytest.raises(PathOutsideRepository):
        paths.resolve_user_path(".env")

    with pytest.raises(PathOutsideRepository):
        paths.resolve_user_path("certs/server.pem")

    with pytest.raises(PathOutsideRepository):
        paths.resolve_user_path("id_rsa")

    # Sensitive files allowed when allow_sensitive=True
    allowed = paths.resolve_user_path(".env", allow_sensitive=True)
    assert allowed == tmp_path / ".env"

    # to_relative
    assert paths.to_relative(tmp_path / "src" / "app.py") == "src/app.py"
    assert paths.to_relative(Path("/somewhere/else/file.py")) == "/somewhere/else/file.py"

    # sane_dir, db_path, lock_path
    assert paths.sane_dir == tmp_path / ".sane"
    assert paths.db_path == tmp_path / ".sane" / "index.db"
    assert paths.lock_path == tmp_path / ".sane" / "writer.lock"


def test_file_discovery_filtering(tmp_path: Path):
    paths = RepoPaths(tmp_path)
    registry = ParserRegistry()

    # Create files
    (tmp_path / "test.py").write_text("print('hello')", encoding="utf-8")
    (tmp_path / "test.txt").write_text("plain text", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config.py").write_text("secret", encoding="utf-8")

    # Large file (> max_file_bytes)
    large_file = tmp_path / "large.py"
    large_file.write_bytes(b"x" * 200)

    cfg = SaneConfig(
        repository=RepositoryConfig(
            max_file_bytes=100,  # 100 bytes limit
            include=["**/*.py"],
            exclude=[".git/**"],
        )
    )

    discovery = FileDiscovery(paths, cfg, registry)
    discovered = discovery.discover()
    discovered_paths = [df.rel_path for df in discovered]

    assert "test.py" in discovered_paths
    assert "test.txt" not in discovered_paths  # not supported by registry
    assert ".git/config.py" not in discovered_paths  # excluded
    assert "large.py" not in discovered_paths  # exceeds max_file_bytes


def test_indexer_incremental_and_pruning(index_repo: Path):
    paths = RepoPaths(index_repo)
    db = Database(paths.db_path)
    indexer = Indexer(paths, db)

    # 1. Full index
    stats1 = indexer.index_all()
    assert stats1["indexed_files"] == 2
    assert stats1["skipped_files"] == 0

    # 2. Second index without changes -> files are skipped
    stats2 = indexer.index_all()
    assert stats2["indexed_files"] == 0
    assert stats2["skipped_files"] == 2

    # 3. Single file index on non-supported file -> False
    unsupported = index_repo / "notes.txt"
    unsupported.write_text("notes", encoding="utf-8")
    assert indexer.index_single_file("notes.txt") is False

    # 4. Modify existing file and re-index single file -> True
    py_file = index_repo / "src" / "payment_service.py"
    py_file.write_text("def new_func(): pass\n", encoding="utf-8")
    assert indexer.index_single_file("src/payment_service.py") is True

    # 5. Delete file and re-index single file -> True (prunes from db)
    py_file.unlink()
    assert indexer.index_single_file("src/payment_service.py") is True
    with db.get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) as c FROM files WHERE path = 'src/payment_service.py'").fetchone()
        assert row["c"] == 0


def test_incremental_sync_and_watcher(index_repo: Path):
    paths = RepoPaths(index_repo)
    db = Database(paths.db_path)
    indexer = Indexer(paths, db)
    sync = IncrementalSync(indexer)

    # scan_for_drift
    drift_stats = sync.scan_for_drift()
    assert "total_files" in drift_stats

    # sync_changed_path
    res = sync.sync_changed_path(index_repo / "docs" / "architecture.md")
    assert res is True

    # RepoWatcher start and stop
    watcher = RepoWatcher(index_repo, sync, debounce_ms=10)
    assert watcher._running is False

    # Mock awatch generator for testing watcher loop
    async def run_watcher():
        async def mock_awatch(*_args, **_kwargs):
            yield {(1, str(index_repo / "docs" / "architecture.md"))}
            watcher.stop()

        with patch("sane_nav.indexing.watcher.awatch", mock_awatch):
            await watcher.start()

    asyncio.run(run_watcher())
    assert watcher._running is False


def test_database_queries(index_repo: Path):
    paths = RepoPaths(index_repo)
    db = Database(paths.db_path)
    indexer = Indexer(paths, db)
    indexer.index_all()

    # Stats
    stats = db.get_stats()
    assert stats["files"] == 2
    assert stats["symbols"] > 0
    assert stats["docs"] > 0

    # Symbols in file
    syms = db.get_file_symbols("src/payment_service.py")
    assert len(syms) > 0
    assert any(s["name"] == "PaymentGateway" for s in syms)

    # Linked docs
    docs = db.get_linked_docs(["PaymentRetryCoordinator", "Retry"], file_path="src/payment_service.py")
    assert isinstance(docs, list)

    # Search symbol by id or name
    matches = db.get_symbol_by_id_or_name("PaymentService")
    assert len(matches) > 0
    assert matches[0]["name"] == "PaymentService"

    # Search files by name
    file_matches = db.search_files_by_name("payment_service")
    assert len(file_matches) > 0

    # Upstream callers for non-existent id
    assert db.get_upstream_callers(999999) == []

    # Proximity for empty seeds
    assert db.get_graph_proximity([]) == {}
