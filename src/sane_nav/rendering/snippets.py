from __future__ import annotations

from pathlib import Path
from typing import Optional


def render_code_snippet(
    file_path: Path,
    target_line: int,
    start_line_bound: Optional[int] = None,
    end_line_bound: Optional[int] = None,
    context_lines: int = 2,
) -> str:
    """Renders a clean, formatted code snippet centered around target_line with '>' indicator.
    Bounds can constrain it to enclosing function/class boundaries.
    """
    if not file_path.exists():
        return f"[File not found: {file_path}]"

    try:
        lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as e:
        return f"[Error reading file: {e}]"

    total = len(lines)
    if total == 0:
        return ""

    # 1-indexed to 0-indexed
    target_idx = max(0, min(target_line - 1, total - 1))

    low = max(0, target_idx - context_lines)
    high = min(total - 1, target_idx + context_lines)

    if start_line_bound is not None:
        low = max(low, start_line_bound - 1)
    if end_line_bound is not None:
        high = min(high, end_line_bound - 1)

    output: list[str] = []
    for idx in range(low, high + 1):
        ln = idx + 1
        prefix = ">" if ln == target_line else " "
        line_content = lines[idx]
        output.append(f"{prefix} {ln:4d} | {line_content}")

    return "\n".join(output)


def render_symbol_body(
    file_path: Path,
    start_line: int,
    end_line: int,
    context_lines: int = 0,
) -> str:
    """Extracts exact lines for a symbol with line numbers."""
    if not file_path.exists():
        return f"[File not found: {file_path}]"

    try:
        lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as e:
        return f"[Error reading file: {e}]"

    total = len(lines)
    low = max(0, start_line - 1 - context_lines)
    high = min(total - 1, end_line - 1 + context_lines)

    output: list[str] = []
    for idx in range(low, high + 1):
        ln = idx + 1
        output.append(f"{ln:4d} | {lines[idx]}")

    return "\n".join(output)
