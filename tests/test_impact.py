from pathlib import Path
import pytest

from sane_nav.mcp.server import McpServer
from sane_nav.mcp.tools import McpToolService


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
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

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True)
    test_code = """
import unittest
from src.payment_service import PaymentService, PaymentToken

class TestPayment(unittest.TestCase):
    def test_capture_success(self):
        token = PaymentToken(token_id="tok_123", amount=100.0)
        # Call capture
        service = PaymentService(None, None)
        service.capture(token)
"""
    (tests_dir / "test_payment.py").write_text(test_code, encoding="utf-8")

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True)
    (docs_dir / "architecture.md").write_bytes(
        (fixtures_dir / "markdown" / "architecture.md").read_bytes()
    )

    return tmp_path


def test_analyze_impact_callers_and_tests(repo_root: Path):
    service = McpToolService(repo_root)
    service.indexer.index_all()

    # Analyze impact for PaymentService.capture
    res = service.analyze_impact("PaymentService.capture", depth=2, include_tests=True)

    assert res["status"] == "success"
    assert res["symbol"] == "capture"

    # Upstream callers should include submitOrder from CheckoutService
    caller_names = [c["name"] for c in res["upstream_callers"]]
    assert "submitOrder" in caller_names

    # Affected tests should include test_payment.py
    assert res["summary"]["affected_test_files"] >= 1
    test_paths = [t["file"] for t in res["affected_tests"]]
    assert any("test_payment.py" in p for p in test_paths)

    # Report text formatting
    report = res["report"]
    assert "# Impact Analysis: `PaymentService.capture`" in report
    assert "Upstream Callers" in report
    assert "Affected Test Suites" in report
    assert "test_payment.py" in report


def test_read_file_structural(repo_root: Path):
    service = McpToolService(repo_root)
    service.indexer.index_all()

    res = service.read_file_structural("src/payment_service.py", start=1, end=35)

    assert "file" in res
    assert res["file"] == "src/payment_service.py"
    assert res["start"] == 1
    assert res["end"] == 35

    # Check symbols declared
    sym_names = [s["name"] for s in res["symbols"]]
    assert "PaymentToken" in sym_names
    assert "PaymentGateway" in sym_names
    assert "PaymentRetryCoordinator" in sym_names

    # Check upstream dependents (CheckoutService calls into payment_service.py)
    assert any("CheckoutService.kt" in dep for dep in res["upstream_dependents"])

    # Check structural header in content
    content = res["content"]
    assert "=== Structural Context: src/payment_service.py ===" in content
    assert "Declared Symbols" in content
    assert "Upstream Dependents" in content
    assert "   1 | " in content or "1 | " in content


def test_mcp_server_impact_and_read_structural(repo_root: Path):
    service = McpToolService(repo_root)
    service.indexer.index_all()

    server = McpServer(repo_root)

    # MCP analyze_impact
    impact_resp = server.handle_request({
        "jsonrpc": "2.0",
        "id": 20,
        "method": "tools/call",
        "params": {
            "name": "analyze_impact",
            "arguments": {"symbol": "PaymentService.capture", "depth": 2},
        },
    })
    assert impact_resp["result"]["isError"] is False
    assert "Impact Analysis" in impact_resp["result"]["content"][0]["text"]

    # MCP read_file_structural
    read_resp = server.handle_request({
        "jsonrpc": "2.0",
        "id": 21,
        "method": "tools/call",
        "params": {
            "name": "read_file_structural",
            "arguments": {"file_path": "src/payment_service.py", "start": 1, "end": 20},
        },
    })
    assert read_resp["result"]["isError"] is False
    assert "Structural Context" in read_resp["result"]["content"][0]["text"]
