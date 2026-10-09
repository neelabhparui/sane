from pathlib import Path

import pytest

from sane_nav.mcp.server import McpServer
from sane_nav.mcp.tools import McpToolService
from sane_nav.parsing.java import JavaAdapter
from sane_nav.parsing.kotlin import KotlinAdapter
from sane_nav.parsing.markdown import MarkdownAdapter
from sane_nav.parsing.python import PythonAdapter
from sane_nav.parsing.registry import ParserRegistry
from sane_nav.parsing.treesitter.engine import TreeSitterAdapter


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    # Set up sample repo in tmp_path
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

    swift_dir = tmp_path / "swift"
    swift_dir.mkdir(parents=True)
    (swift_dir / "AuthService.swift").write_bytes(
        (fixtures_dir / "swift" / "AuthService.swift").read_bytes()
    )

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True)
    (docs_dir / "architecture.md").write_bytes(
        (fixtures_dir / "markdown" / "architecture.md").read_bytes()
    )

    return tmp_path


def test_python_adapter(repo_root: Path):
    adapter = PythonAdapter()
    py_file = repo_root / "src" / "payment_service.py"
    source = py_file.read_bytes()
    parsed = adapter.parse("src/payment_service.py", source)

    names = [s.name for s in parsed.symbols]
    assert "PaymentToken" in names
    assert "PaymentGateway" in names
    assert "PaymentRetryCoordinator" in names
    assert "should_retry" in names
    assert "schedule_retry" in names
    assert "capture" in names

    # Test skeleton redaction
    skeleton = adapter.render_skeleton(source, parsed)
    assert "# ... implementation omitted ..." in skeleton
    assert "def should_retry" in skeleton
    assert "Determines if a failure is retriable" in skeleton  # docstring preserved!


def test_java_adapter(repo_root: Path):
    registry = ParserRegistry()
    adapter = registry.for_path("AuthService.java")
    j_file = repo_root / "java" / "com" / "acme" / "auth" / "AuthService.java"
    source = j_file.read_bytes()
    parsed = adapter.parse("AuthService.java", source)

    names = [s.name for s in parsed.symbols]
    assert "AuthService" in names
    assert "validateToken" in names
    assert "rotateRefreshToken" in names

    skeleton = adapter.render_skeleton(source, parsed)
    assert "// ... implementation omitted ..." in skeleton
    assert "public String rotateRefreshToken" in skeleton


def test_kotlin_adapter(repo_root: Path):
    registry = ParserRegistry()
    adapter = registry.for_path("CheckoutService.kt")
    kt_file = repo_root / "kotlin" / "com" / "acme" / "checkout" / "CheckoutService.kt"
    source = kt_file.read_bytes()
    parsed = adapter.parse("CheckoutService.kt", source)

    names = [s.name for s in parsed.symbols]
    assert "CheckoutService" in names
    assert "submitOrder" in names

    # References
    refs = [r.spelling for r in parsed.references]
    assert "capture" in refs


def test_swift_adapter(repo_root: Path):
    registry = ParserRegistry()
    adapter = registry.for_path("AuthService.swift")
    s_file = repo_root / "swift" / "AuthService.swift"
    source = s_file.read_bytes()
    parsed = adapter.parse("AuthService.swift", source)

    names = [s.name for s in parsed.symbols]
    assert "AuthService" in names
    assert "validateToken" in names
    assert "rotateRefreshToken" in names

    refs = [r.spelling for r in parsed.references]
    assert "findUserId" in refs
    assert "invalidate" in refs

    skeleton = adapter.render_skeleton(source, parsed)
    assert "// ... implementation omitted ..." in skeleton
    assert "public func rotateRefreshToken" in skeleton


def test_parser_backend_toggle(monkeypatch):
    # Default should be treesitter
    monkeypatch.delenv("SANE_NAV_PARSER_BACKEND", raising=False)
    reg_default = ParserRegistry()
    java_def = reg_default.for_path("Test.java")
    kt_def = reg_default.for_path("Test.kt")
    assert isinstance(java_def, TreeSitterAdapter)
    assert isinstance(kt_def, TreeSitterAdapter)

    # When set to regex, should use regex adapters
    monkeypatch.setenv("SANE_NAV_PARSER_BACKEND", "regex")
    reg_regex = ParserRegistry()
    java_reg = reg_regex.for_path("Test.java")
    kt_reg = reg_regex.for_path("Test.kt")
    assert isinstance(java_reg, JavaAdapter)
    assert isinstance(kt_reg, KotlinAdapter)


def test_markdown_adapter(repo_root: Path):
    adapter = MarkdownAdapter()
    md_file = repo_root / "docs" / "architecture.md"
    source = md_file.read_bytes()
    parsed = adapter.parse("docs/architecture.md", source)

    headings = [d.heading for d in parsed.docs]
    assert "System Architecture" in headings
    assert "Authentication" in headings
    assert "Refresh tokens" in headings
    assert "Retry Policy" in headings

    # Heading hierarchy check
    retry_doc = [d for d in parsed.docs if d.heading == "Retry Policy"][0]
    assert retry_doc.heading_path == ("System Architecture", "Payments and Billing", "Retry Policy")


def test_indexing_and_mcp_tools(repo_root: Path):
    service = McpToolService(repo_root)

    # 1. Index everything
    stats = service.indexer.index_all()
    assert stats["total_files"] == 5
    assert stats["indexed_files"] == 5

    # 2. Check index_status
    status = service.index_status()
    assert status["files"] == 5
    assert status["symbols"] > 0
    assert status["docs"] > 0

    # 3. Search semantic
    search_res = service.search_semantic("refresh token")
    assert search_res["count"] > 0
    found_names = [r.get("name") or r.get("title") for r in search_res["results"]]
    assert any("rotateRefreshToken" in str(n) or "Refresh tokens" in str(n) for n in found_names)

    # 4. Get skeleton
    skel_res = service.get_skeleton("src/payment_service.py")
    assert "PaymentService" in skel_res["skeleton"]
    assert "implementation omitted" in skel_res["skeleton"]

    # 5. Get symbol code
    sym_res = service.get_symbol_code("PaymentRetryCoordinator.should_retry")
    assert sym_res["status"] == "success"
    assert "TIMEOUT" in sym_res["code"]

    # 6. Find usages
    usage_res = service.find_usages("capture")
    assert usage_res["total_found"] > 0
    assert any(
        "CheckoutService.kt" in f["file"] for f in usage_res["usages_by_file"]
    )

    # 7. Get context for feature
    ctx_res = service.get_context("Retry Policy")
    assert "PaymentRetryCoordinator" in ctx_res["content"]
    assert "[Documentation]" in ctx_res["content"]


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
    assert init_resp["result"]["serverInfo"]["name"] == "sane-nav"

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
    content_raw = call_resp["result"]["content"][0]["text"]
    assert "PaymentService" in content_raw


def test_search_semantic_empty_proximity_rerank(repo_root: Path):
    service = McpToolService(repo_root)
    service.indexer.index_all()

    # Query with non-matching term but valid context_symbol must not raise ValueError
    res = service.search_semantic("nonexistent_random_term_xyz", context_symbol="AuthService")
    assert res["count"] == 0
    assert res["results"] == []


def test_search_semantic_kinds_filter_excludes_files(repo_root: Path):
    service = McpToolService(repo_root)
    service.indexer.index_all()

    # Query for a filename-shaped query with kinds=["class"] must not include kind: "file"
    res = service.search_semantic("AuthService", kinds=["class"], limit=5)
    for r in res["results"]:
        assert r.get("kind") != "file"
    assert res["count"] <= 5


def test_find_usages_include_probable_false(repo_root: Path):
    service = McpToolService(repo_root)
    service.indexer.index_all()

    res = service.find_usages("capture", include_probable=False)
    assert res["total_found"] == res["exact_count"]
    assert res["probable_count"] == 0
    for f in res["usages_by_file"]:
        for u in f["usages"]:
            assert u["confidence"] >= 0.9


def test_session_dedup_actionable_backref(repo_root: Path):
    service = McpToolService(repo_root)
    service.indexer.index_all()

    turn1 = service.get_symbol_code("PaymentService.capture")
    assert turn1["status"] == "success"

    service.session_tracker.next_turn()
    turn2 = service.get_symbol_code("PaymentService.capture")
    assert turn2["status"] == "success"
    assert turn2["is_deduplicated"] is True
    assert "Pass force=True or call read_lines to inspect" in turn2["code"]
