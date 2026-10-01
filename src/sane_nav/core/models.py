"""Core data models and representations for S.A.N.E.

This module defines the foundational intermediate representation (IR) objects
used throughout the engine, including source byte ranges, parsed symbols,
occurrences/references, documentation sections, output budgets, and usage items.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


@dataclass(frozen=True)
class SourceRange:
    """Represents a contiguous span within a source file.

    Attributes:
        start_byte: 0-indexed byte offset of the beginning of the range.
        end_byte: 0-indexed byte offset of the end of the range.
        start_line: 1-indexed starting line number (presentation friendly).
        end_line: 1-indexed ending line number.
    """
    start_byte: int
    end_byte: int
    start_line: int  # 1-indexed for external presentation, stored as 1-based in SQLite for humans
    end_line: int

    def to_dict(self) -> dict[str, int]:
        """Serializes the range to a JSON-compatible dictionary."""
        return {
            "start_byte": self.start_byte,
            "end_byte": self.end_byte,
            "start_line": self.start_line,
            "end_line": self.end_line,
        }


class SymbolKind(str, Enum):
    """Categorization of code symbol types."""
    MODULE = "module"
    CLASS = "class"
    INTERFACE = "interface"
    RECORD = "record"
    FUNCTION = "function"
    METHOD = "method"
    PROPERTY = "property"
    CONSTRUCTOR = "constructor"
    VARIABLE = "variable"
    CONSTANT = "constant"


class ResolutionKind(str, Enum):
    """Classification of how an occurrence was resolved to a target symbol."""
    EXACT = "exact"
    IMPORT_SCOPED = "import-scoped"
    CLASS_SCOPED = "class-scoped"
    PROBABLE = "probable"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class ParsedSymbol:
    """Represents a code symbol extracted from an AST.

    Attributes:
        name: Short identifier name (e.g. 'capture', 'AuthService').
        qualified_name: Optional namespace-qualified name (e.g. 'PaymentService.capture').
        kind: SymbolKind classification.
        signature: Full signature line or declaration header.
        docstring: Associated docstring or documentation comments.
        full_range: SourceRange covering the complete declaration and body.
        body_range: SourceRange covering only the implementation body (for redaction).
        parent_key: Canonical symbol key of the enclosing class or module.
        visibility: Access modifier ('public', 'private', 'protected', 'internal').
        symbol_key: Unique deterministic symbol URI across the repository.
    """
    name: str
    qualified_name: Optional[str]
    kind: str
    signature: str
    docstring: Optional[str]
    full_range: SourceRange
    body_range: Optional[SourceRange]
    parent_key: Optional[str] = None
    visibility: Optional[str] = "public"
    symbol_key: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Serializes the symbol to a JSON-compatible dictionary."""
        return {
            "name": self.name,
            "qualified_name": self.qualified_name,
            "kind": self.kind,
            "signature": self.signature,
            "docstring": self.docstring,
            "full_range": self.full_range.to_dict(),
            "body_range": self.body_range.to_dict() if self.body_range else None,
            "parent_key": self.parent_key,
            "visibility": self.visibility,
            "symbol_key": self.symbol_key,
        }


@dataclass(frozen=True)
class ParsedReference:
    """Represents a syntactic call site or identifier occurrence in code.

    Attributes:
        spelling: The literal identifier text (e.g. 'capture', 'reserve').
        role: Syntactic role ('call', 'import', 'type', 'instantiation').
        source_range: Exact position of the occurrence.
        enclosing_symbol_key: Symbol key of the containing method or function.
        receiver_text: Optional variable name or expression preceding the call.
    """
    spelling: str
    role: str  # call, type, import, instantiation, read
    source_range: SourceRange
    enclosing_symbol_key: Optional[str]
    receiver_text: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Serializes the reference to a JSON-compatible dictionary."""
        return {
            "spelling": self.spelling,
            "role": self.role,
            "source_range": self.source_range.to_dict(),
            "enclosing_symbol_key": self.enclosing_symbol_key,
            "receiver_text": self.receiver_text,
        }


@dataclass(frozen=True)
class ParsedDocumentSection:
    """Represents a section in a Markdown documentation file.

    Attributes:
        heading: Title of this section heading.
        heading_path: Tuple of ancestor heading titles (e.g. ('Architecture', 'Auth')).
        content: Direct markdown content between this heading and the next.
        source_range: Byte and line offsets of this section.
        level: Heading depth (1 for #, 2 for ##, 3 for ###).
    """
    heading: str
    heading_path: tuple[str, ...]
    content: str
    source_range: SourceRange
    level: int = 1

    def to_dict(self) -> dict[str, Any]:
        """Serializes the document section to a dictionary."""
        return {
            "heading": self.heading,
            "heading_path": list(self.heading_path),
            "content": self.content,
            "source_range": self.source_range.to_dict(),
            "level": self.level,
        }


@dataclass(frozen=True)
class ParsedFile:
    """Encapsulates all extracted data from parsing a single source file.

    Attributes:
        symbols: Extracted code symbols.
        references: Extracted call sites and occurrences.
        docs: Extracted documentation sections.
        parse_error_count: Number of syntax or parsing errors encountered.
    """
    symbols: tuple[ParsedSymbol, ...] = ()
    references: tuple[ParsedReference, ...] = ()
    docs: tuple[ParsedDocumentSection, ...] = ()
    parse_error_count: int = 0


@dataclass
class OutputBudget:
    """Enforces strict character and item limits on tool responses.

    Attributes:
        max_chars: Maximum characters allowed in response.
        max_items: Maximum items (usages, search candidates) to include.
        max_snippet_lines: Maximum lines allowed per code snippet.
        current_chars: Accumulator of consumed characters.
    """
    max_chars: int = 12000
    max_items: int = 10
    max_snippet_lines: int = 12
    current_chars: int = 0

    def has_budget(self, additional_chars: int = 0) -> bool:
        """Returns True if additional_chars can fit within the remaining budget."""
        return (self.current_chars + additional_chars) <= self.max_chars

    def add(self, text: str) -> str:
        """Appends text to the budget, safely truncating with a warning if exceeded."""
        remaining = max(0, self.max_chars - self.current_chars)
        if len(text) > remaining:
            truncated = text[:remaining] + "\n... [Output budget limit reached. Refine search or request sub-range]"
            self.current_chars = self.max_chars
            return truncated
        self.current_chars += len(text)
        return text


@dataclass
class UsageItem:
    """Represents a single formatted call site usage for agent consumption."""
    file_path: str
    enclosing_symbol: Optional[str]
    line: int
    resolution: str
    confidence: float
    snippet: str

    def to_dict(self) -> dict[str, Any]:
        """Serializes the usage item to a dictionary."""
        return {
            "file_path": self.file_path,
            "enclosing_symbol": self.enclosing_symbol,
            "line": self.line,
            "resolution": self.resolution,
            "confidence": self.confidence,
            "snippet": self.snippet,
        }
