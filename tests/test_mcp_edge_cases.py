import io
import json
from pathlib import Path
from unittest.mock import patch
import pytest

from sane_nav.mcp import server as mcp_server_module
from sane_nav.mcp.server import McpServer
from sane_nav.mcp.session import SessionDedupTracker
from sane_nav.mcp.tools import McpToolService


@pytest.fixture
def mcp_edge_repo(tmp_path: Path) -> Path:
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


def test_mcp_server_request_routing(mcp_edge_repo: Path):
    server = McpServer(mcp_edge_repo)
    server.service.indexer.index_all()

    # notifications/initialized -> None
    notif_resp = server.handle_request({
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
        "params": {},
    })
    assert notif_resp is None

    # ping
    ping_resp = server.handle_request({
        "jsonrpc": "2.0",
        "id": 10,
        "method": "ping",
        "params": {},
    })
    assert ping_resp["result"] == {}

    # Unknown method
    unknown_method_resp = server.handle_request({
        "jsonrpc": "2.0",
        "id": 11,
        "method": "non_existent_method",
        "params": {},
    })
    assert unknown_method_resp["error"]["code"] == -32601

    # Unknown tool
    unknown_tool_resp = server.handle_request({
        "jsonrpc": "2.0",
        "id": 12,
        "method": "tools/call",
        "params": {"name": "invalid_tool", "arguments": {}},
    })
    assert unknown_tool_resp["error"]["code"] == -32601

    # All standard tools invocation via server
    for tool_name, args in [
        ("index_status", {}),
        ("read_lines", {"file_path": "src/payment_service.py", "start": 1, "end": 5}),
        ("get_file_tree", {"depth": 2}),
        ("read_file_structural", {"file_path": "src/payment_service.py", "start": 1, "end": 10}),
        ("find_implementations", {"symbol": "PaymentGateway"}),
    ]:
        resp = server.handle_request({
            "jsonrpc": "2.0",
            "id": 100,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": args},
        })
        assert resp["result"]["isError"] is False

    # Tool error handling
    with patch.object(McpToolService, "read_lines", side_effect=RuntimeError("Disk failure")):
        err_resp = server.handle_request({
            "jsonrpc": "2.0",
            "id": 13,
            "method": "tools/call",
            "params": {"name": "read_lines", "arguments": {"file_path": "test", "start": 1, "end": 2}},
        })
        assert err_resp["result"]["isError"] is True
        assert "Disk failure" in err_resp["result"]["content"][0]["text"]


def test_mcp_server_run_stdio_and_main(mcp_edge_repo: Path):
    server = McpServer(mcp_edge_repo)

    # Simulate stdin with empty lines, invalid JSON, and a valid ping
    input_data = "\n\n{invalid json}\n" + json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}) + "\n"
    stdin_stream = io.StringIO(input_data)
    stdout_stream = io.StringIO()

    with patch("sys.stdin", stdin_stream), patch("sys.stdout", stdout_stream):
        server.run_stdio()

    out_lines = [line_str for line_str in stdout_stream.getvalue().splitlines() if line_str.strip()]
    assert len(out_lines) == 1
    resp = json.loads(out_lines[0])
    assert resp["id"] == 1
    assert resp["result"] == {}

    # server main entrypoint
    with patch("sys.argv", ["sane-server", "--repo", str(mcp_edge_repo)]), patch.object(McpServer, "run_stdio"):
        mcp_server_module.main()


def test_mcp_tools_edge_cases(mcp_edge_repo: Path):
    service = McpToolService(mcp_edge_repo)
    service.indexer.index_all()

    # 1. search_semantic with context_symbol
    res_ctx = service.search_semantic("charge", context_symbol="PaymentService")
    assert res_ctx["count"] >= 0

    # search_semantic with file path context_symbol
    res_ctx_file = service.search_semantic("charge", context_symbol="src/payment_service.py")
    assert res_ctx_file["count"] >= 0

    # 2. get_symbol_code filtering by kind and class_context
    sym_cls = service.get_symbol_code("capture", class_context="PaymentService")
    assert sym_cls["status"] == "success"

    sym_kind = service.get_symbol_code("PaymentToken", kind="class")
    assert sym_kind["status"] == "success"

    # get_symbol_code not found
    sym_nf = service.get_symbol_code("NonExistentMethod")
    assert sym_nf["status"] == "not_found"

    # 3. read_lines edge cases
    rl_not_found = service.read_lines("non_existent.py", 1, 10)
    assert "error" in rl_not_found

    rl_out_of_bounds = service.read_lines("src/payment_service.py", 5000, 6000)
    assert rl_out_of_bounds["content"] == ""

    # 4. read_file_structural edge cases
    rfs_not_found = service.read_file_structural("non_existent.py")
    assert "error" in rfs_not_found

    rfs_dir = service.read_file_structural("src")
    assert "error" in rfs_dir

    # 5. get_file_tree edge cases
    tree_not_found = service.get_file_tree("non_existent_dir")
    assert "error" in tree_not_found

    tree_valid = service.get_file_tree(".", depth=2, max_entries=5)
    assert "files" in tree_valid

    # 6. explore_flow and analyze_impact not_found
    flow_nf = service.explore_flow("GhostSymbol")
    assert flow_nf["status"] == "not_found"

    impact_nf = service.analyze_impact("GhostSymbol")
    assert impact_nf["status"] == "not_found"


def test_session_tracker_methods():
    tracker = SessionDedupTracker()
    assert tracker.current_turn == 1

    span = tracker.record(
        symbol_key="python://src/payment.py#charge",
        symbol_name="charge",
        file_path="src/payment.py",
        start_line=10,
        end_line=20,
    )
    assert span.turn == 1

    # In turn 1 without allow_same_turn, get_emitted returns None
    assert tracker.get_emitted(symbol_key="python://src/payment.py#charge") is None
    # With allow_same_turn, returns span
    assert tracker.get_emitted(symbol_key="python://src/payment.py#charge", allow_same_turn=True) == span

    # Advance turn
    tracker.next_turn()
    assert tracker.current_turn == 2
    # In turn 2, get_emitted returns span from turn 1
    assert tracker.get_emitted(symbol_key="python://src/payment.py#charge") == span
