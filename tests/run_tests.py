#!/usr/bin/env python3
import sys
import tempfile
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sane_nav.mcp.server import McpServer
from sane_nav.mcp.tools import McpToolService
from sane_nav.parsing.markdown import MarkdownAdapter
from sane_nav.parsing.python import PythonAdapter
from sane_nav.parsing.registry import ParserRegistry


def create_sample_repo(tmp_path: Path):
    fixtures_dir = Path(__file__).parent / "fixtures"
    python_dir = tmp_path / "src"
    python_dir.mkdir(parents=True, exist_ok=True)
    (python_dir / "payment_service.py").write_bytes(
        (fixtures_dir / "python" / "payment_service.py").read_bytes()
    )

    java_dir = tmp_path / "java" / "com" / "acme" / "auth"
    java_dir.mkdir(parents=True, exist_ok=True)
    (java_dir / "AuthService.java").write_bytes(
        (fixtures_dir / "java" / "AuthService.java").read_bytes()
    )

    kt_dir = tmp_path / "kotlin" / "com" / "acme" / "checkout"
    kt_dir.mkdir(parents=True, exist_ok=True)
    (kt_dir / "CheckoutService.kt").write_bytes(
        (fixtures_dir / "kotlin" / "CheckoutService.kt").read_bytes()
    )

    swift_dir = tmp_path / "swift"
    swift_dir.mkdir(parents=True, exist_ok=True)
    (swift_dir / "AuthService.swift").write_bytes(
        (fixtures_dir / "swift" / "AuthService.swift").read_bytes()
    )

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "architecture.md").write_bytes(
        (fixtures_dir / "markdown" / "architecture.md").read_bytes()
    )


def test_python_adapter(repo_root: Path):
    adapter = PythonAdapter()
    py_file = repo_root / "src" / "payment_service.py"
    source = py_file.read_bytes()
    parsed = adapter.parse("src/payment_service.py", source)

    names = [s.name for s in parsed.symbols]
    assert "PaymentToken" in names, "PaymentToken missing"
    assert "PaymentGateway" in names, "PaymentGateway missing"
    assert "PaymentRetryCoordinator" in names, "PaymentRetryCoordinator missing"
    assert "should_retry" in names, "should_retry missing"
    assert "schedule_retry" in names, "schedule_retry missing"
    assert "capture" in names, "capture missing"

    skeleton = adapter.render_skeleton(source, parsed)
    assert "# ... implementation omitted ..." in skeleton, "Skeleton redaction marker missing"
    assert "def should_retry" in skeleton, "Signature missing in skeleton"
    print("✓ test_python_adapter passed")


def test_java_adapter(repo_root: Path):
    registry = ParserRegistry()
    adapter = registry.for_path("AuthService.java")
    j_file = repo_root / "java" / "com" / "acme" / "auth" / "AuthService.java"
    source = j_file.read_bytes()
    parsed = adapter.parse("AuthService.java", source)

    names = [s.name for s in parsed.symbols]
    assert "AuthService" in names, "AuthService missing"
    assert "validateToken" in names, "validateToken missing"
    assert "rotateRefreshToken" in names, "rotateRefreshToken missing"

    skeleton = adapter.render_skeleton(source, parsed)
    assert "// ... implementation omitted ..." in skeleton, "Java skeleton marker missing"
    assert "public String rotateRefreshToken" in skeleton, "Java signature missing"
    print("✓ test_java_adapter passed")


def test_kotlin_adapter(repo_root: Path):
    registry = ParserRegistry()
    adapter = registry.for_path("CheckoutService.kt")
    kt_file = repo_root / "kotlin" / "com" / "acme" / "checkout" / "CheckoutService.kt"
    source = kt_file.read_bytes()
    parsed = adapter.parse("CheckoutService.kt", source)

    names = [s.name for s in parsed.symbols]
    assert "CheckoutService" in names, "CheckoutService missing"
    assert "submitOrder" in names, "submitOrder missing"

    refs = [r.spelling for r in parsed.references]
    assert "capture" in refs, "capture call reference missing"
    print("✓ test_kotlin_adapter passed")


def test_swift_adapter(repo_root: Path):
    registry = ParserRegistry()
    adapter = registry.for_path("AuthService.swift")
    s_file = repo_root / "swift" / "AuthService.swift"
    source = s_file.read_bytes()
    parsed = adapter.parse("AuthService.swift", source)

    names = [s.name for s in parsed.symbols]
    assert "AuthService" in names, "AuthService missing"
    assert "validateToken" in names, "validateToken missing"
    assert "rotateRefreshToken" in names, "rotateRefreshToken missing"

    refs = [r.spelling for r in parsed.references]
    assert "findUserId" in refs, "findUserId missing"
    assert "invalidate" in refs, "invalidate missing"

    skeleton = adapter.render_skeleton(source, parsed)
    assert "// ... implementation omitted ..." in skeleton, "Swift skeleton marker missing"
    assert "public func rotateRefreshToken" in skeleton, "Swift signature missing"
    print("✓ test_swift_adapter passed")


def test_markdown_adapter(repo_root: Path):
    adapter = MarkdownAdapter()
    md_file = repo_root / "docs" / "architecture.md"
    source = md_file.read_bytes()
    parsed = adapter.parse("docs/architecture.md", source)

    headings = [d.heading for d in parsed.docs]
    assert "System Architecture" in headings, "System Architecture missing"
    assert "Authentication" in headings, "Authentication missing"
    assert "Refresh tokens" in headings, "Refresh tokens missing"
    assert "Retry Policy" in headings, "Retry Policy missing"

    retry_doc = [d for d in parsed.docs if d.heading == "Retry Policy"][0]
    assert retry_doc.heading_path == ("System Architecture", "Payments and Billing", "Retry Policy"), (
        f"Incorrect heading path: {retry_doc.heading_path}"
    )
    print("✓ test_markdown_adapter passed")


def test_indexing_and_mcp_tools(repo_root: Path):
    service = McpToolService(repo_root)

    # 1. Index everything
    stats = service.indexer.index_all()
    assert stats["total_files"] == 5, f"Expected 5 files, got {stats['total_files']}"
    assert stats["indexed_files"] == 5, f"Expected 5 indexed files, got {stats['indexed_files']}"

    # 2. Check index_status
    status = service.index_status()
    assert status["files"] == 5, f"Expected 5 files, got {status['files']}"
    assert status["symbols"] > 0, "No symbols indexed"
    assert status["docs"] > 0, "No docs indexed"

    # 3. Search semantic
    search_res = service.search_semantic("refresh token")
    assert search_res["count"] > 0, "Semantic search returned 0 results"
    found_names = [r.get("name") or r.get("title") for r in search_res["results"]]
    assert any("rotateRefreshToken" in str(n) or "Refresh tokens" in str(n) for n in found_names), (
        f"Could not find token refresh in {found_names}"
    )

    # 4. Get skeleton
    skel_res = service.get_skeleton("src/payment_service.py")
    assert "PaymentService" in skel_res["skeleton"], "PaymentService missing from skeleton"
    assert "implementation omitted" in skel_res["skeleton"], "Skeleton not redacted"

    # 5. Get symbol code
    sym_res = service.get_symbol_code("PaymentRetryCoordinator.should_retry")
    assert sym_res["status"] == "success", f"Failed to get symbol code: {sym_res}"
    assert "TIMEOUT" in sym_res["code"], "Method code content incorrect"

    # 6. Find usages
    usage_res = service.find_usages("capture")
    assert usage_res["total_found"] > 0, "Failed to find usages for capture"

    # 7. Get context for feature
    ctx_res = service.get_context("Retry Policy")
    assert "PaymentRetryCoordinator" in ctx_res["content"], "Context stitching missing coordinator"
    assert "[Documentation]" in ctx_res["content"], "Context stitching missing documentation block"
    print("✓ test_indexing_and_mcp_tools passed")


def test_mcp_server_jsonrpc(repo_root: Path):
    service = McpToolService(repo_root)
    service.indexer.index_all()
    server = McpServer(repo_root)

    # Test initialize
    init_resp = server.handle_request({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {},
    })
    assert init_resp["result"]["serverInfo"]["name"] == "sane-nav", "Server name mismatch"

    # Test tools/list
    list_resp = server.handle_request({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
    })
    tool_names = [t["name"] for t in list_resp["result"]["tools"]]
    assert "search_semantic" in tool_names
    assert "get_skeleton" in tool_names
    assert "get_symbol_code" in tool_names
    assert "find_usages" in tool_names
    assert "get_context" in tool_names

    # Test tools/call
    call_resp = server.handle_request({
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "search_semantic",
            "arguments": {"query": "PaymentService"},
        },
    })
    assert call_resp["result"]["isError"] is False
    assert "PaymentService" in call_resp["result"]["content"][0]["text"]
    print("✓ test_mcp_server_jsonrpc passed")


def main():
    print("=" * 60)
    print("Running S.A.N.E. Test Suite")
    print("=" * 60)
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        create_sample_repo(tmp_path)

        test_python_adapter(tmp_path)
        test_java_adapter(tmp_path)
        test_kotlin_adapter(tmp_path)
        test_swift_adapter(tmp_path)
        test_markdown_adapter(tmp_path)
        test_indexing_and_mcp_tools(tmp_path)
        test_mcp_server_jsonrpc(tmp_path)

    print("=" * 60)
    print("ALL TESTS PASSED SUCCESSFULLY! (7/7 test groups passed)")
    print("=" * 60)


if __name__ == "__main__":
    main()
