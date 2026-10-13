import argparse
from pathlib import Path
from unittest.mock import patch
import pytest

from sane_nav import cli
from sane_nav.mcp.tools import McpToolService
from sane_nav.paths import RepoPaths


@pytest.fixture
def sample_cli_repo(tmp_path: Path) -> Path:
    fixtures_dir = Path(__file__).parent / "fixtures"
    python_dir = tmp_path / "src"
    python_dir.mkdir(parents=True)
    (python_dir / "payment_service.py").write_bytes(
        (fixtures_dir / "python" / "payment_service.py").read_bytes()
    )

    kt_dir = tmp_path / "kotlin" / "com" / "acme" / "checkout"
    kt_dir.mkdir(parents=True)
    (kt_dir / "CheckoutService.kt").write_bytes(
        (fixtures_dir / "kotlin" / "CheckoutService.kt").read_bytes()
    )

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True)
    (docs_dir / "architecture.md").write_bytes(
        (fixtures_dir / "markdown" / "architecture.md").read_bytes()
    )

    return tmp_path


def test_cli_doctor(sample_cli_repo: Path, capsys):
    args = argparse.Namespace(repo=str(sample_cli_repo))
    code = cli.cmd_doctor(args)
    assert code == 0
    captured = capsys.readouterr()
    assert "SQLite FTS5" in captured.out
    assert "Python runtime" in captured.out


def test_cli_clean(sample_cli_repo: Path, capsys):
    # Before clean (no .sane directory)
    args = argparse.Namespace(repo=str(sample_cli_repo))
    code = cli.cmd_clean(args)
    assert code == 0
    captured = capsys.readouterr()
    assert "Nothing to clean" in captured.out

    # After creating .sane
    paths = RepoPaths(sample_cli_repo)
    paths.sane_dir.mkdir(parents=True, exist_ok=True)
    code = cli.cmd_clean(args)
    assert code == 0
    assert not paths.sane_dir.exists()


def test_cli_status(sample_cli_repo: Path, capsys):
    args = argparse.Namespace(repo=str(sample_cli_repo))
    # DB does not exist yet
    code = cli.cmd_status(args)
    assert code == 1

    # Index first
    cli.cmd_index(args)
    code = cli.cmd_status(args)
    assert code == 0
    captured = capsys.readouterr()
    assert "files" in captured.out


def test_cli_init_and_reinit(sample_cli_repo: Path):
    # Create a gitignore to test gitignore updating
    gitignore = sample_cli_repo / ".gitignore"
    gitignore.write_text("*.pyc\n", encoding="utf-8")

    # 1. Init with agents specified
    args = argparse.Namespace(
        repo=str(sample_cli_repo),
        agents="universal,claude,cursor,gemini,codex,vscode",
        no_agents=False,
    )
    code = cli.cmd_init(args)
    assert code == 0
    assert (sample_cli_repo / ".sane.toml").exists()
    assert ".sane/" in gitignore.read_text(encoding="utf-8")
    assert (sample_cli_repo / ".agents" / "skills" / "sane-nav" / "SKILL.md").exists()
    assert (sample_cli_repo / ".claude" / "skills" / "sane-nav" / "SKILL.md").exists()
    assert (sample_cli_repo / ".cursor" / "skills" / "sane-nav" / "SKILL.md").exists()
    assert (sample_cli_repo / ".gemini" / "skills" / "sane-nav" / "SKILL.md").exists()
    assert (sample_cli_repo / ".codex" / "skills" / "sane-nav" / "SKILL.md").exists()
    assert (sample_cli_repo / ".vscode" / "skills" / "sane-nav" / "SKILL.md").exists()

    # Verify skill file contains expected content
    skill_content = (sample_cli_repo / ".agents" / "skills" / "sane-nav" / "SKILL.md").read_text(encoding="utf-8")
    assert "name: sane-nav" in skill_content
    assert "sane flow" in skill_content

    # Re-run init when config already exists
    code = cli.cmd_init(args)
    assert code == 0

    # 2. Reinit with keep_config=True
    reinit_args = argparse.Namespace(
        repo=str(sample_cli_repo),
        keep_config=True,
        agents=None,
        no_agents=True,
    )
    code = cli.cmd_reinit(reinit_args)
    assert code == 0
    assert (sample_cli_repo / ".sane.toml").exists()

    # 3. Reinit without keep_config
    reinit_clean_args = argparse.Namespace(
        repo=str(sample_cli_repo),
        keep_config=False,
        agents=None,
        no_agents=True,
    )
    code = cli.cmd_reinit(reinit_clean_args)
    assert code == 0
    assert (sample_cli_repo / ".sane.toml").exists()


def test_cli_search_and_skeleton(sample_cli_repo: Path, capsys):
    # Index repo first
    service = McpToolService(sample_cli_repo)
    service.indexer.index_all()

    # Search for doc
    s_args = argparse.Namespace(repo=str(sample_cli_repo), query="architecture", limit=5)
    code = cli.cmd_search(s_args)
    assert code == 0
    captured = capsys.readouterr()
    assert "Search results" in captured.out

    # Search for code symbol
    s_args2 = argparse.Namespace(repo=str(sample_cli_repo), query="PaymentService", limit=5)
    code2 = cli.cmd_search(s_args2)
    assert code2 == 0

    # Skeleton
    skel_args = argparse.Namespace(repo=str(sample_cli_repo), file="src/payment_service.py")
    code_skel = cli.cmd_skeleton(skel_args)
    assert code_skel == 0
    captured_skel = capsys.readouterr()
    assert "PaymentService" in captured_skel.out


def test_cli_symbol(sample_cli_repo: Path, capsys):
    service = McpToolService(sample_cli_repo)
    service.indexer.index_all()

    # Success
    args = argparse.Namespace(repo=str(sample_cli_repo), symbol="PaymentService.capture", context=2)
    code = cli.cmd_symbol(args)
    assert code == 0
    captured = capsys.readouterr()
    assert "def capture" in captured.out

    # Not found
    args_nf = argparse.Namespace(repo=str(sample_cli_repo), symbol="NonExistentSymbol", context=0)
    code_nf = cli.cmd_symbol(args_nf)
    assert code_nf == 1

    # Ambiguous candidate simulation
    mock_candidates = [{"symbol_id": "sym1", "file": "f1.py", "lines": [1, 10]}]
    with patch.object(
        McpToolService,
        "get_symbol_code",
        return_value={"status": "ambiguous", "message": "Multiple matches", "candidates": mock_candidates},
    ):
        code_amb = cli.cmd_symbol(args)
        assert code_amb == 0


def test_cli_usages_and_implementations(sample_cli_repo: Path, capsys):
    service = McpToolService(sample_cli_repo)
    service.indexer.index_all()

    # Usages
    u_args = argparse.Namespace(repo=str(sample_cli_repo), symbol="capture", limit=10)
    code_u = cli.cmd_usages(u_args)
    assert code_u == 0
    captured_u = capsys.readouterr()
    assert "Usages for 'capture'" in captured_u.out

    # Implementations
    imp_args = argparse.Namespace(repo=str(sample_cli_repo), symbol="PaymentGateway", direct_only=False)
    code_imp = cli.cmd_implementations(imp_args)
    assert code_imp == 0
    captured_imp = capsys.readouterr()
    assert "Implementations" in captured_imp.out


def test_cli_flow_and_impact(sample_cli_repo: Path):
    service = McpToolService(sample_cli_repo)
    service.indexer.index_all()

    # Flow success
    f_args = argparse.Namespace(repo=str(sample_cli_repo), symbol="PaymentService.capture", depth=1)
    code_f = cli.cmd_flow(f_args)
    assert code_f == 0

    # Flow not found
    f_nf = argparse.Namespace(repo=str(sample_cli_repo), symbol="UnknownSymbol", depth=1)
    code_f_nf = cli.cmd_flow(f_nf)
    assert code_f_nf == 1

    # Flow ambiguous
    mock_candidates = [{"symbol_id": "sym1", "file": "f1.py", "lines": [1, 10]}]
    with patch.object(
        McpToolService,
        "explore_flow",
        return_value={"status": "ambiguous", "message": "Multiple matches", "candidates": mock_candidates},
    ):
        assert cli.cmd_flow(f_args) == 0

    # Impact success
    imp_args = argparse.Namespace(repo=str(sample_cli_repo), symbol="PaymentService.capture", depth=2, no_tests=False)
    code_imp = cli.cmd_impact(imp_args)
    assert code_imp == 0

    # Impact not found
    imp_nf = argparse.Namespace(repo=str(sample_cli_repo), symbol="UnknownSymbol", depth=2, no_tests=False)
    code_imp_nf = cli.cmd_impact(imp_nf)
    assert code_imp_nf == 1

    # Impact ambiguous
    with patch.object(
        McpToolService,
        "analyze_impact",
        return_value={"status": "ambiguous", "message": "Multiple matches", "candidates": mock_candidates},
    ):
        assert cli.cmd_impact(imp_args) == 0


def test_cli_read_context_tree(sample_cli_repo: Path, capsys):
    service = McpToolService(sample_cli_repo)
    service.indexer.index_all()

    # 1. sane read
    read_args = argparse.Namespace(
        repo=str(sample_cli_repo),
        file="src/payment_service.py",
        start=1,
        end=30,
        max_chars=10000,
    )
    code_read = cli.cmd_read(read_args)
    assert code_read == 0
    captured = capsys.readouterr()
    assert "Structural Context" in captured.out
    assert "PaymentService" in captured.out

    # 2. sane read non-existent
    read_bad = argparse.Namespace(
        repo=str(sample_cli_repo),
        file="non_existent.py",
        start=1,
        end=10,
        max_chars=10000,
    )
    assert cli.cmd_read(read_bad) == 1

    # 3. sane context
    ctx_args = argparse.Namespace(
        repo=str(sample_cli_repo),
        feature="architecture",
        prefix=None,
        max_chars=10000,
    )
    code_ctx = cli.cmd_context(ctx_args)
    assert code_ctx == 0
    captured_ctx = capsys.readouterr()
    assert "Context for 'architecture'" in captured_ctx.out

    # 4. sane tree
    tree_args = argparse.Namespace(
        repo=str(sample_cli_repo),
        dir=None,
        depth=3,
        max_entries=100,
    )
    code_tree = cli.cmd_tree(tree_args)
    assert code_tree == 0
    captured_tree = capsys.readouterr()
    assert "File Tree" in captured_tree.out


def test_cli_setup(sample_cli_repo: Path):
    # Claude dry-run and write
    code = cli.cmd_setup(argparse.Namespace(repo=str(sample_cli_repo), client="claude", write=False))
    assert code == 0
    code = cli.cmd_setup(argparse.Namespace(repo=str(sample_cli_repo), client="claude", write=True))
    assert code == 0
    assert (sample_cli_repo / ".claude" / "skills" / "sane-nav" / "SKILL.md").exists()

    # Cursor write
    code = cli.cmd_setup(argparse.Namespace(repo=str(sample_cli_repo), client="cursor", write=True))
    assert code == 0
    assert (sample_cli_repo / ".cursor" / "skills" / "sane-nav" / "SKILL.md").exists()

    # Universal / Open Agent Standards write
    code = cli.cmd_setup(argparse.Namespace(repo=str(sample_cli_repo), client="universal", write=True))
    assert code == 0
    assert (sample_cli_repo / ".agents" / "skills" / "sane-nav" / "SKILL.md").exists()

    # Unknown client
    code = cli.cmd_setup(argparse.Namespace(repo=str(sample_cli_repo), client="unsupported", write=False))
    assert code == 1


def test_cli_checkbox_prompt_non_tty():
    with patch("sys.stdin.isatty", return_value=False):
        res = cli._checkbox_prompt(["a", "b"], "Select:")
        assert res == []


def test_cli_main_entrypoint(sample_cli_repo: Path):
    # Run sane doctor via main()
    with patch("sys.argv", ["sane", "doctor", "--repo", str(sample_cli_repo)]):
        with pytest.raises(SystemExit) as exc:
            cli.main()
        assert exc.value.code == 0

def test_cli_watch(sample_cli_repo: Path):
    from unittest.mock import AsyncMock
    with patch("sane_nav.indexing.watcher.RepoWatcher.start", new_callable=AsyncMock) as mock_start:
        args = argparse.Namespace(repo=str(sample_cli_repo), debounce=50)
        code = cli.cmd_watch(args)
        assert code == 0
        mock_start.assert_called_once()


def test_skeleton_collapses_imports(sample_cli_repo: Path, capsys):
    from sane_nav.rendering.skeleton import collapse_imports
    service = McpToolService(sample_cli_repo)
    service.indexer.index_all()

    # 1. Via CLI skeleton
    skel_args = argparse.Namespace(repo=str(sample_cli_repo), file="src/payment_service.py")
    code = cli.cmd_skeleton(skel_args)
    assert code == 0
    captured = capsys.readouterr()
    assert "# [imports omitted]" in captured.out
    assert "from dataclasses import dataclass" not in captured.out
    assert "from typing import Optional" not in captured.out
    assert "class PaymentService:" in captured.out

    # 2. collapse_imports unit tests across languages
    py_code = '"""Doc"""\n\nimport os\nimport sys\nfrom typing import List\n\ndef foo(): pass'
    assert "# [imports omitted]" in collapse_imports(py_code, "foo.py")
    assert "import os" not in collapse_imports(py_code, "foo.py")

    java_code = 'package com.acme;\n\nimport java.util.List;\nimport java.util.Map;\n\nclass Foo {}'
    assert "// [imports omitted]" in collapse_imports(java_code, "Foo.java")
    assert "import java.util.List" not in collapse_imports(java_code, "Foo.java")

    kt_code = 'package com.acme\n\nimport com.acme.model.*\n\nclass Foo'
    assert "// [imports omitted]" in collapse_imports(kt_code, "Foo.kt")

    no_imports = 'def add(a, b):\n    return a + b\n'
    assert collapse_imports(no_imports, "math.py") == no_imports


def test_cli_output_no_bloat(sample_cli_repo: Path, capsys):
    service = McpToolService(sample_cli_repo)
    service.indexer.index_all()

    # Search output has no match score bloat
    s_args = argparse.Namespace(repo=str(sample_cli_repo), query="PaymentService", limit=5)
    cli.cmd_search(s_args)
    out_search = capsys.readouterr().out
    assert "Match:" not in out_search
    assert "score:" not in out_search
    assert "[CLASS] PaymentService" in out_search

    # Usages output has no redundant confidence text
    u_args = argparse.Namespace(repo=str(sample_cli_repo), symbol="capture", limit=5)
    cli.cmd_usages(u_args)
    out_usages = capsys.readouterr().out
    assert "confidence" not in out_usages
    assert "[PROBABLE]" in out_usages or "[EXACT]" in out_usages


def test_watcher_daemon_lifecycle(sample_cli_repo: Path, capsys):
    from sane_nav.indexing.watcher import start_daemon, status_daemon, stop_daemon

    # Status when not running
    st = status_daemon(sample_cli_repo)
    assert st["running"] is False

    # CLI watch --status
    code = cli.cmd_watch(argparse.Namespace(repo=str(sample_cli_repo), status=True))
    assert code == 0
    assert "STOPPED" in capsys.readouterr().out

    # Start daemon
    started, _, pid = start_daemon(sample_cli_repo, debounce_ms=100)
    assert started is True
    assert pid is not None

    try:
        # Status when running
        st2 = status_daemon(sample_cli_repo)
        assert st2["running"] is True
        assert st2["pid"] == pid

        # CLI watch --status
        cli.cmd_watch(argparse.Namespace(repo=str(sample_cli_repo), status=True))
        assert "RUNNING" in capsys.readouterr().out

        # CLI doctor reports daemon
        cli.cmd_doctor(argparse.Namespace(repo=str(sample_cli_repo)))
        assert "Background watcher daemon: Running" in capsys.readouterr().out
    finally:
        # Stop daemon
        stopped, _ = stop_daemon(sample_cli_repo)
        assert stopped is True
        st3 = status_daemon(sample_cli_repo)
        assert st3["running"] is False
