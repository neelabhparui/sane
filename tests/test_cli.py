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
        agents="claude,cursor,vscode,codex",
        no_agents=False,
    )
    code = cli.cmd_init(args)
    assert code == 0
    assert (sample_cli_repo / ".sane.toml").exists()
    assert ".sane/" in gitignore.read_text(encoding="utf-8")
    assert (sample_cli_repo / ".mcp.json").exists()
    assert (sample_cli_repo / ".cursor" / "mcp.json").exists()
    assert (sample_cli_repo / ".vscode" / "mcp.json").exists()
    assert (sample_cli_repo / ".codex" / "config.toml").exists()

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


def test_cli_setup(sample_cli_repo: Path):
    # Claude
    code = cli.cmd_setup(argparse.Namespace(repo=str(sample_cli_repo), client="claude", write=False))
    assert code == 0

    # Cursor dry-run and write
    code = cli.cmd_setup(argparse.Namespace(repo=str(sample_cli_repo), client="cursor", write=False))
    assert code == 0
    code = cli.cmd_setup(argparse.Namespace(repo=str(sample_cli_repo), client="cursor", write=True))
    assert code == 0
    assert (sample_cli_repo / ".cursor" / "mcp.json").exists()

    # VSCode dry-run and write
    code = cli.cmd_setup(argparse.Namespace(repo=str(sample_cli_repo), client="vscode", write=False))
    assert code == 0
    code = cli.cmd_setup(argparse.Namespace(repo=str(sample_cli_repo), client="vscode", write=True))
    assert code == 0
    assert (sample_cli_repo / ".vscode" / "mcp.json").exists()

    # Unknown
    code = cli.cmd_setup(argparse.Namespace(repo=str(sample_cli_repo), client="unsupported", write=False))
    assert code == 1


def test_cli_serve(sample_cli_repo: Path):
    with patch("sane_nav.mcp.server.McpServer.run_stdio") as mock_run:
        args = argparse.Namespace(repo=str(sample_cli_repo))
        code = cli.cmd_serve(args)
        assert code == 0
        mock_run.assert_called_once()


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
