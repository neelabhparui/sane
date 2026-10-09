class SaneError(Exception):
    """Base exception for all S.A.N.E. errors."""


class PathOutsideRepository(SaneError):
    """Raised when an operation requests a path that escapes the repository root."""


class IndexNotFoundError(SaneError):
    """Raised when the S.A.N.E. SQLite index does not exist or has not been initialized."""


class SymbolNotFoundError(SaneError):
    """Raised when a requested symbol cannot be found."""


class AmbiguousSymbolError(SaneError):
    """Raised when a requested symbol matches multiple declarations."""
    def __init__(self, symbol_query: str, candidates: list[dict]):
        super().__init__(f"Ambiguous symbol '{symbol_query}', matched {len(candidates)} candidates.")
        self.candidates = candidates


class UnsupportedLanguageError(SaneError):
    """Raised when a file's language is not supported for structural parsing."""
