"""Literal-aware brace matching for regex-based C-family parsers.

Naive `{`/`}` counting over raw source text breaks whenever a brace
character appears inside a string/char literal or a comment (e.g.
`val s = "}"` or `// }`), truncating the enclosing block early and
corrupting every symbol range computed from it. This scans character by
character, tracking literal/comment state, so such braces are ignored.
"""

from __future__ import annotations


def find_matching_brace(source_text: str, open_brace_pos: int) -> int:
    """Finds the index just past the `}` matching the `{` at open_brace_pos.

    Args:
        source_text: Full source text.
        open_brace_pos: Index of the opening '{' (counted as already consumed).

    Returns:
        Index just past the matching closing '}', or len(source_text) if
        the block is unterminated.
    """
    n = len(source_text)
    depth = 1
    idx = open_brace_pos
    in_string: str | None = None  # '"' or "'" while inside a literal
    in_line_comment = False
    in_block_comment = False

    while idx < n and depth > 0:
        ch = source_text[idx]
        nxt = source_text[idx + 1] if idx + 1 < n else ""

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            idx += 1
            continue
        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                idx += 2
                continue
            idx += 1
            continue
        if in_string:
            if ch == "\\":
                idx += 2
                continue
            if ch == in_string:
                in_string = None
            idx += 1
            continue

        if ch == "/" and nxt == "/":
            in_line_comment = True
            idx += 2
            continue
        if ch == "/" and nxt == "*":
            in_block_comment = True
            idx += 2
            continue
        if ch in ("\"", "'"):
            in_string = ch
            idx += 1
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        idx += 1

    return idx
