"""Symbol identification and identifier normalization utilities.

Provides deterministic canonical symbol keys conforming to URI patterns,
safe parsing of user/agent symbol queries, and camelCase / snake_case tokenization.
"""

from __future__ import annotations

import re
from typing import Optional


def build_symbol_key(
    language: str,
    file_path: str,
    owner_or_class: Optional[str],
    symbol_name: str,
    signature_params: Optional[str] = None,
    line: Optional[int] = None,
) -> str:
    """Builds a deterministic, collision-resistant canonical symbol key.

    Format:
        <language>://<clean_path>::<owner>#<name>(<params>)@L<line>

    Args:
        language: Source language ('python', 'java', 'kotlin').
        file_path: Repository-relative posix file path.
        owner_or_class: Enclosing class, namespace, or module.
        symbol_name: Short identifier of the symbol.
        signature_params: Optional parameter signature to differentiate overloads.
        line: 1-based declaration line.

    Returns:
        Deterministic URI string uniquely identifying the symbol.
    """
    clean_path = file_path.replace("\\", "/").strip("/")
    owner_str = f"::{owner_or_class}" if owner_or_class else ""
    params_str = f"({signature_params})" if signature_params is not None else ""
    loc_str = f"@L{line}" if line else ""

    return f"{language}://{clean_path}{owner_str}#{symbol_name}{params_str}{loc_str}"


def parse_symbol_query(query: str) -> dict[str, Optional[str]]:
    """Parses a query string into component parts.

    Supports:
      - Raw names: 'validateToken', 'rotate_refresh_token'
      - Qualified names: 'AuthService.validateToken', 'com.acme.PaymentProcessor.capture'
      - Full URIs: 'java://com.acme/...#capture'

    Args:
        query: Raw query provided by user or AI agent.

    Returns:
        Dictionary containing extracted 'language', 'path_or_owner', 'name', and 'raw'.
    """
    query = query.strip()
    if "://" in query:
        lang, rest = query.split("://", 1)
        path_and_owner, _, name_and_sig = rest.rpartition("#")
        return {
            "language": lang,
            "path_or_owner": path_and_owner,
            "name": name_and_sig.split("(")[0],
            "raw": query,
        }

    if "." in query:
        parts = query.split(".")
        return {
            "language": None,
            "path_or_owner": ".".join(parts[:-1]),
            "name": parts[-1].split("(")[0],
            "raw": query,
        }

    return {
        "language": None,
        "path_or_owner": None,
        "name": query.split("(")[0],
        "raw": query,
    }


def normalize_identifier_tokens(identifier: str) -> list[str]:
    """Splits identifiers into constituent natural language words.

    Handles camelCase, PascalCase, snake_case, and kebab-case.
    E.g. 'rotateRefreshToken' -> ['rotate', 'refresh', 'token']
         'Payment_retry_coord' -> ['payment', 'retry', 'coord']

    Args:
        identifier: Raw identifier or symbol name.

    Returns:
        List of lowercase token words.
    """
    tokens: list[str] = []
    subparts = re.split(r"[-_]+", identifier)
    for part in subparts:
        words = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\b)|\d+", part)
        if words:
            tokens.extend(w.lower() for w in words)
        elif part:
            tokens.append(part.lower())
    return tokens
