from pathlib import Path

import pytest

from sane_nav.mcp.server import McpServer
from sane_nav.mcp.session import SessionDedupTracker
from sane_nav.mcp.tools import McpToolService


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    fixtures_dir = Path(__file__).parent / "fixtures"
    python_dir = tmp_path / "src"
    python_dir.mkdir(parents=True)
    (python_dir / "payment_service.py").write_bytes(
        (fixtures_dir / "python" / "payment_service.py").read_bytes()
    )

    java_dir = tmp_path / "java" / "com" / "acme" / "auth"
    java_dir.mkdir(parents=True)
    (java_dir / "AuthService.java").write_bytes(
        (fixtures_dir / "java" / "AuthService.java").read_bytes()
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


def test_explore_flow_anchor_callees_callers(repo_root: Path):
    service = McpToolService(repo_root)
    service.indexer.index_all()

    # Explore flow for PaymentService.capture
    res = service.explore_flow("PaymentService.capture", max_depth=1)

    assert res["status"] == "success"
    assert res["symbol"] == "capture"
    assert "payment_service.py" in res["file"]

    flow_text = res["flow"]
    assert "# Flow Analysis: `PaymentService.capture`" in flow_text
    assert "def capture" in flow_text
    assert "process_charge" in flow_text or "should_retry" in flow_text

    # Callee check
    callee_names = [c["name"] for c in res["callees"]]
    assert "process_charge" in callee_names or "should_retry" in callee_names

    # Caller check (CheckoutService.submitOrder calls capture)
    caller_names = [c["name"] for c in res["callers"]]
    assert "submitOrder" in caller_names


def test_session_dedup_flow_and_symbol_code(repo_root: Path):
    tracker = SessionDedupTracker()
    service = McpToolService(repo_root, session_tracker=tracker)
    service.indexer.index_all()

    # Turn 1: get_symbol_code
    turn1_res = service.get_symbol_code("PaymentService.capture")
    assert turn1_res["status"] == "success"
    assert turn1_res.get("is_deduplicated") is False
    assert "def capture" in turn1_res["code"]

    # Advance to Turn 2
    tracker.next_turn()

    # Turn 2: get_symbol_code should return back-reference
    turn2_res = service.get_symbol_code("PaymentService.capture")
    assert turn2_res["status"] == "success"
    assert turn2_res.get("is_deduplicated") is True
    assert "[Source for Symbol capture already provided in Turn 1" in turn2_res["code"]
    assert "Omitted to preserve token budget." in turn2_res["code"]

    # Force should bypass deduplication (and re-records in Turn 2)
    force_res = service.get_symbol_code("PaymentService.capture", force=True)
    assert force_res.get("is_deduplicated") is False
    assert "def capture" in force_res["code"]

    # Advance to Turn 3: explore_flow should also deduplicate capture
    tracker.next_turn()
    turn3_res = service.explore_flow("PaymentService.capture")
    assert turn3_res.get("is_deduplicated") is True
    assert "[Source for Symbol capture already provided in Turn 2" in turn3_res["flow"]


def test_skeleton_dedup_back_reference(repo_root: Path):
    tracker = SessionDedupTracker()
    service = McpToolService(repo_root, session_tracker=tracker)
    service.indexer.index_all()

    # Emit should_retry in Turn 1
    sym_res = service.get_symbol_code("PaymentRetryCoordinator.should_retry")
    assert sym_res["status"] == "success"

    # In Turn 2, render skeleton
    tracker.next_turn()
    skel_res = service.get_skeleton("src/payment_service.py")
    skeleton = skel_res["skeleton"]

    assert "[Source for Symbol should_retry already provided in Turn 1" in skeleton
    assert "Omitted to preserve token budget." in skeleton


def test_mcp_server_explore_flow(repo_root: Path):
    service = McpToolService(repo_root)
    service.indexer.index_all()

    server = McpServer(repo_root)

    # Call explore_flow through MCP JSON-RPC
    req = {
        "jsonrpc": "2.0",
        "id": 10,
        "method": "tools/call",
        "params": {
            "name": "explore_flow",
            "arguments": {"symbol": "PaymentService.capture"},
        },
    }
    resp = server.handle_request(req)
    assert resp["result"]["isError"] is False
    content_text = resp["result"]["content"][0]["text"]
    assert "Flow Analysis" in content_text
    assert "capture" in content_text
