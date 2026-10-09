from pathlib import Path

from sane_nav.config import SaneConfig
from sane_nav.core.errors import (
    AmbiguousSymbolError,
    IndexNotFoundError,
    PathOutsideRepository,
    SaneError,
    SymbolNotFoundError,
    UnsupportedLanguageError,
)
from sane_nav.core.ids import (
    build_symbol_key,
    normalize_identifier_tokens,
    parse_symbol_query,
)
from sane_nav.core.models import (
    OutputBudget,
    ParsedDocumentSection,
    ParsedFile,
    ParsedReference,
    ParsedSymbol,
    ResolutionKind,
    SourceRange,
    SymbolKind,
    UsageItem,
)
from sane_nav.rendering.budget import BudgetManager


def test_ids_build_symbol_key():
    # Full arguments with backslashes normalized
    key1 = build_symbol_key(
        language="python",
        file_path="src\\utils\\helper.py",
        owner_or_class="MyClass",
        symbol_name="do_work",
        signature_params="x: int, y: int",
        line=42,
    )
    assert key1 == "python://src/utils/helper.py::MyClass#do_work(x: int, y: int)@L42"

    # Minimal arguments
    key2 = build_symbol_key(
        language="java",
        file_path="/com/example/Test.java",
        owner_or_class=None,
        symbol_name="main",
    )
    assert key2 == "java://com/example/Test.java#main"


def test_ids_parse_symbol_query():
    # Full URI query
    res_uri = parse_symbol_query("python://src/app.py::Server#start(port)")
    assert res_uri["language"] == "python"
    assert res_uri["path_or_owner"] == "src/app.py::Server"
    assert res_uri["name"] == "start"
    assert res_uri["raw"] == "python://src/app.py::Server#start(port)"

    # Qualified query
    res_qual = parse_symbol_query("com.acme.AuthService.validateToken")
    assert res_qual["language"] is None
    assert res_qual["path_or_owner"] == "com.acme.AuthService"
    assert res_qual["name"] == "validateToken"

    # Simple name query with params
    res_simple = parse_symbol_query("rotateRefreshToken(user_id)")
    assert res_simple["language"] is None
    assert res_simple["path_or_owner"] is None
    assert res_simple["name"] == "rotateRefreshToken"


def test_ids_normalize_identifier_tokens():
    tokens = normalize_identifier_tokens("rotateRefreshToken")
    assert tokens == ["rotate", "refresh", "token"]

    tokens = normalize_identifier_tokens("Payment_retry_coord")
    assert tokens == ["payment", "retry", "coord"]

    tokens = normalize_identifier_tokens("HTTPServer2Handler-v1")
    assert "http" in tokens
    assert "server" in tokens
    assert "2" in tokens
    assert "handler" in tokens
    assert "v" in tokens
    assert "1" in tokens

    # Edge cases
    assert not normalize_identifier_tokens("")
    assert not normalize_identifier_tokens("---")


def test_core_errors():
    err = AmbiguousSymbolError("my_symbol", [{"symbol_id": "1"}, {"symbol_id": "2"}])
    assert issubclass(AmbiguousSymbolError, SaneError)
    assert "my_symbol" in str(err)
    assert len(err.candidates) == 2
    assert issubclass(PathOutsideRepository, SaneError)
    assert issubclass(IndexNotFoundError, SaneError)
    assert issubclass(SymbolNotFoundError, SaneError)
    assert issubclass(UnsupportedLanguageError, SaneError)


def test_core_models_serialization():
    sr = SourceRange(start_byte=10, end_byte=50, start_line=2, end_line=5)
    sr_dict = sr.to_dict()
    assert sr_dict == {
        "start_byte": 10,
        "end_byte": 50,
        "start_line": 2,
        "end_line": 5,
    }

    sym = ParsedSymbol(
        name="test_fn",
        qualified_name="MyClass.test_fn",
        kind=SymbolKind.METHOD.value,
        signature="def test_fn():",
        docstring="Test docstring",
        full_range=sr,
        body_range=SourceRange(start_byte=25, end_byte=50, start_line=3, end_line=5),
        parent_key="python://src/mod.py#MyClass",
        visibility="public",
        symbol_key="python://src/mod.py::MyClass#test_fn",
    )
    sym_dict = sym.to_dict()
    assert sym_dict["name"] == "test_fn"
    assert sym_dict["body_range"]["start_byte"] == 25

    # ParsedSymbol without body_range
    sym_no_body = ParsedSymbol(
        name="test_fn2",
        qualified_name=None,
        kind=SymbolKind.FUNCTION.value,
        signature="def test_fn2(): pass",
        docstring=None,
        full_range=sr,
        body_range=None,
    )
    assert sym_no_body.to_dict()["body_range"] is None

    ref = ParsedReference(
        spelling="test_fn",
        role=ResolutionKind.EXACT.value,
        source_range=sr,
        enclosing_symbol_key="python://src/mod.py#caller",
        receiver_text="self",
    )
    ref_dict = ref.to_dict()
    assert ref_dict["spelling"] == "test_fn"
    assert ref_dict["receiver_text"] == "self"

    doc = ParsedDocumentSection(
        heading="Intro",
        heading_path=("Docs", "Intro"),
        content="Intro text",
        source_range=sr,
        level=2,
    )
    doc_dict = doc.to_dict()
    assert doc_dict["heading"] == "Intro"
    assert doc_dict["heading_path"] == ["Docs", "Intro"]

    parsed_file = ParsedFile(symbols=(sym,), references=(ref,), docs=(doc,), parse_error_count=0)
    assert len(parsed_file.symbols) == 1

    usage = UsageItem(
        file_path="src/main.py",
        enclosing_symbol="run",
        line=10,
        resolution="exact",
        confidence=1.0,
        snippet="res = test_fn()",
    )
    usage_dict = usage.to_dict()
    assert usage_dict["file_path"] == "src/main.py"
    assert usage_dict["confidence"] == 1.0


def test_output_budget():
    budget = OutputBudget(max_chars=20)
    assert budget.has_budget(15) is True
    assert budget.has_budget(25) is False

    t1 = budget.add("Hello ")
    assert t1 == "Hello "
    assert budget.current_chars == 6

    # Adding text exceeding remaining budget
    t2 = budget.add("World! More extra text exceeds 20 characters")
    assert "Output budget limit reached" in t2
    assert budget.current_chars == 20
    assert budget.has_budget(1) is False


def test_budget_manager():
    budget = BudgetManager.create(max_chars=50, max_items=5)
    assert budget.max_chars == 50
    assert budget.max_items == 5

    lines = ["Line 1", "Line 2", "Line 3", "Line 4", "Line 5"]
    truncated = BudgetManager.truncate_lines(lines, max_chars=15, label="rows")
    assert "Showing" in truncated
    assert "rows" in truncated

    not_truncated = BudgetManager.truncate_lines(["A", "B"], max_chars=50)
    assert not_truncated == "A\nB"


def test_config_loading(tmp_path: Path):
    # Non-existent config
    cfg = SaneConfig.load(tmp_path)
    assert cfg.repository.respect_gitignore is True
    assert cfg.index.parse_workers == 4

    # Valid config
    toml_content = """
[repository]
respect_gitignore = false
max_file_bytes = 1000

[index]
parse_workers = 8

[watch]
enabled = false
debounce_ms = 500

[search]
semantic = true
default_limit = 15

[output]
max_chars = 5000
max_usages = 10
"""
    (tmp_path / ".sane.toml").write_text(toml_content, encoding="utf-8")
    cfg2 = SaneConfig.load(tmp_path)
    assert cfg2.repository.respect_gitignore is False
    assert cfg2.repository.max_file_bytes == 1000
    assert cfg2.index.parse_workers == 8
    assert cfg2.watch.enabled is False
    assert cfg2.watch.debounce_ms == 500
    assert cfg2.search.semantic is True
    assert cfg2.search.default_limit == 15
    assert cfg2.output.max_chars == 5000
    assert cfg2.output.max_usages == 10

    # Malformed config -> fallback to defaults
    (tmp_path / ".sane.toml").write_text("invalid [[ toml content", encoding="utf-8")
    cfg3 = SaneConfig.load(tmp_path)
    assert cfg3.index.parse_workers == 4

    # _load_simple fallback directly
    simple = SaneConfig._load_simple(tmp_path / ".sane.toml")
    assert simple.index.parse_workers == 4
