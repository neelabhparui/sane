from pathlib import Path

from sane_nav.parsing.brace_matching import find_matching_brace
from sane_nav.parsing.java import JavaAdapter
from sane_nav.parsing.kotlin import KotlinAdapter, _parse_kotlin_supertypes


def test_brace_matching():
    # Simple brace
    code = "{ return 1; }"
    idx = find_matching_brace(code, 0)
    assert idx == len(code)

    # Nested braces
    code2 = "{ if (true) { return 1; } return 0; }"
    idx2 = find_matching_brace(code2, 0)
    assert idx2 == len(code2)

    # Braces inside string literals and escaped quotes
    code3 = r'{ String s = "{\"hello\": \"}\"}"; char c = \'}\'; return s; }'
    idx3 = find_matching_brace(code3, 0)
    assert idx3 == len(code3)

    # Braces inside line comments and block comments
    code4 = """{
        // Line comment with } brace
        /* Block comment
           with { and } braces
        */
        return 42;
    }"""
    idx4 = find_matching_brace(code4, 0)
    assert idx4 == len(code4)

    # Unterminated block
    code5 = "{ return 1;"
    idx5 = find_matching_brace(code5, 0)
    assert idx5 == len(code5)


def test_kotlin_supertypes_parser():
    raw = "BaseClass(1), InterfaceA, InterfaceB<String>, Delegate by impl"
    parsed = _parse_kotlin_supertypes(raw)
    assert ("BaseClass", "extends") in parsed
    assert ("InterfaceA", "implements") in parsed
    assert ("InterfaceB", "implements") in parsed
    assert ("Delegate", "implements") in parsed

    # Empty and filtered types (Any, Unit, Nothing)
    assert not _parse_kotlin_supertypes("Any, Unit, Nothing")
    assert not _parse_kotlin_supertypes("")


def test_java_adapter_regex():
    adapter = JavaAdapter()
    assert adapter.supports("Foo.java") is True
    assert adapter.supports("Foo.kt") is False

    java_code = """
package com.example.test;

/**
 * Service for account management.
 */
public class AccountService extends BaseService implements IAccountService {
    private String name;

    /**
     * Finds account by ID.
     */
    public Account findAccount(String id) throws Exception {
        validate(id);
        return new Account(id);
    }

    protected void validate(String id) {
        if (id == null) {
            throw new IllegalArgumentException();
        }
    }
}

public interface IAccountService {
    Account findAccount(String id);
}

public record Account(String id) {}

public enum Status {
    ACTIVE, INACTIVE
}
"""
    source_bytes = java_code.encode("utf-8")
    parsed = adapter.parse("com/example/test/AccountService.java", source_bytes)

    sym_names = [s.name for s in parsed.symbols]
    assert "AccountService" in sym_names
    assert "findAccount" in sym_names
    assert "validate" in sym_names
    assert "IAccountService" in sym_names
    assert "Account" in sym_names
    assert "Status" in sym_names

    # Check Javadoc was parsed
    account_service_sym = next(s for s in parsed.symbols if s.name == "AccountService")
    assert account_service_sym.docstring is not None
    assert "Service for account management" in account_service_sym.docstring

    # Check references
    ref_spellings = [r.spelling for r in parsed.references]
    assert "BaseService" in ref_spellings
    assert "IAccountService" in ref_spellings
    assert "validate" in ref_spellings

    # Check skeleton rendering
    skeleton = adapter.render_skeleton(source_bytes, parsed)
    assert "public class AccountService" in skeleton
    assert "implementation omitted" in skeleton
    assert "findAccount" in skeleton


def test_kotlin_adapter_regex():
    adapter = KotlinAdapter()
    assert adapter.supports("Foo.kt") is True
    assert adapter.supports("Foo.kts") is True
    assert adapter.supports("Foo.java") is False

    kt_code = """
package com.example.test

/**
 * User repository interface.
 */
interface UserRepository {
    fun findById(id: String): User?
}

data class User(val id: String, val name: String) : BaseEntity()

class UserService(private val repo: UserRepository) : BaseService(), IService {
    /**
     * Retrieves active user.
     */
    fun getUser(id: String): User {
        val user = repo.findById(id) ?: error("Not found")
        process(user)
        return user
    }

    private fun process(user: User) {
        println(user.name)
    }
}

object AppConfig {
    fun getVersion(): String = "1.0"
}
"""
    source_bytes = kt_code.encode("utf-8")
    parsed = adapter.parse("com/example/test/UserService.kt", source_bytes)

    sym_names = [s.name for s in parsed.symbols]
    assert "UserRepository" in sym_names
    assert "User" in sym_names
    assert "UserService" in sym_names
    assert "getUser" in sym_names
    assert "process" in sym_names
    assert "AppConfig" in sym_names

    # Check supertypes and references
    refs = [r.spelling for r in parsed.references]
    assert "BaseEntity" in refs
    assert "BaseService" in refs
    assert "IService" in refs
    assert "findById" in refs

    # Check skeleton
    skeleton = adapter.render_skeleton(source_bytes, parsed)
    assert "class UserService" in skeleton
    assert "implementation omitted" in skeleton
    assert "fun getUser" in skeleton


def test_adapters_with_fixtures():
    fixtures_dir = Path(__file__).parent / "fixtures"

    # Java fixture
    j_adapter = JavaAdapter()
    j_path = fixtures_dir / "java" / "AuthService.java"
    j_bytes = j_path.read_bytes()
    j_parsed = j_adapter.parse("AuthService.java", j_bytes)
    assert any(s.name == "validateToken" for s in j_parsed.symbols)
    j_skel = j_adapter.render_skeleton(j_bytes, j_parsed)
    assert "implementation omitted" in j_skel

    # Kotlin fixture
    kt_adapter = KotlinAdapter()
    kt_path = fixtures_dir / "kotlin" / "CheckoutService.kt"
    kt_bytes = kt_path.read_bytes()
    kt_parsed = kt_adapter.parse("CheckoutService.kt", kt_bytes)
    assert any(s.name == "submitOrder" for s in kt_parsed.symbols)
    kt_skel = kt_adapter.render_skeleton(kt_bytes, kt_parsed)
    assert "implementation omitted" in kt_skel
