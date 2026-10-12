from __future__ import annotations

import re
from typing import TYPE_CHECKING, Optional

from sane_nav.parsing.registry import ParserRegistry
from sane_nav.paths import RepoPaths
from sane_nav.storage.database import Database

if TYPE_CHECKING:
    from sane_nav.mcp.session import SessionDedupTracker


def collapse_imports(skeleton: str, rel_path: str) -> str:
    """Collapses verbose top-level import blocks into a single clean comment to save agent tokens.

    Preserves module docstrings, package declarations, and comments outside import blocks.
    Emits '# [imports omitted]' for Python or '// [imports omitted]' for other languages.
    If no imports are present, returns the skeleton unmodified.
    """
    lines = skeleton.splitlines()
    if not lines:
        return skeleton

    is_py = rel_path.endswith((".py", ".pyi"))
    comment = "# [imports omitted]" if is_py else "// [imports omitted]"

    import_ranges: list[tuple[int, int]] = []
    in_import = False
    paren_depth = 0
    brace_depth = 0
    start_idx: Optional[int] = None

    for i, line in enumerate(lines):
        if not in_import:
            starts_import = False
            if is_py:
                # Top-level python imports only (no leading indentation)
                if re.match(r"^(?:from\s+[a-zA-Z0-9_.]+\s+import|import\s+[a-zA-Z0-9_.]+)", line):
                    starts_import = True
            else:
                # Java, Kotlin, Swift, TS, JS, Go, Rust
                if (
                    re.match(r"^\s*import\s+", line)
                    or re.match(r"^\s*(?:@\w+\s+)?import\s+\w+", line)
                    or re.match(r"^\s*(?:const|let|var)\s+.*?=\s*require\(", line)
                    or re.match(r"^\s*(?:pub\s+)?use\s+[a-zA-Z0-9_:]+", line)
                ):
                    starts_import = True

            if starts_import:
                in_import = True
                start_idx = i
                paren_depth = line.count("(") - line.count(")")
                brace_depth = line.count("{") - line.count("}")

                # Check if single line statement ended
                if is_py:
                    if paren_depth <= 0 and not line.rstrip().endswith("\\"):
                        in_import = False
                        import_ranges.append((start_idx, i))
                        start_idx = None
                else:
                    stripped = line.strip()
                    if (
                        paren_depth <= 0
                        and brace_depth <= 0
                        and (
                            line.rstrip().endswith(";")
                            or line.rstrip().endswith('"')
                            or line.rstrip().endswith("'")
                            or not ("(" in line or "{" in line)
                        )
                    ):
                        in_import = False
                        import_ranges.append((start_idx, i))
                        start_idx = None
        else:
            paren_depth += line.count("(") - line.count(")")
            brace_depth += line.count("{") - line.count("}")
            if is_py:
                if paren_depth <= 0 and not line.rstrip().endswith("\\"):
                    in_import = False
                    assert start_idx is not None
                    import_ranges.append((start_idx, i))
                    start_idx = None
            else:
                stripped = line.strip()
                if paren_depth <= 0 and brace_depth <= 0 and (
                    line.rstrip().endswith(";")
                    or line.rstrip().endswith('"')
                    or line.rstrip().endswith("'")
                    or stripped == ")"
                    or stripped == "}"
                ):
                    in_import = False
                    assert start_idx is not None
                    import_ranges.append((start_idx, i))
                    start_idx = None

    if in_import and start_idx is not None:
        import_ranges.append((start_idx, len(lines) - 1))

    # Merge nearby import ranges separated only by blank lines or comments
    merged: list[tuple[int, int]] = []
    comment_prefix = "#" if is_py else "//"
    for r in import_ranges:
        if not merged:
            merged.append(r)
        else:
            prev_start, prev_end = merged[-1]
            between_lines = lines[prev_end + 1 : r[0]]
            if all(
                not l.strip()
                or l.strip().startswith(comment_prefix)
                or (not is_py and (l.strip().startswith("/*") or l.strip().startswith("*")))
                for l in between_lines
            ):
                merged[-1] = (prev_start, r[1])
            else:
                merged.append(r)

    if not merged:
        return skeleton

    new_lines: list[str] = []
    last_end = 0
    for start, end in merged:
        new_lines.extend(lines[last_end:start])
        new_lines.append(comment)
        last_end = end + 1
    new_lines.extend(lines[last_end:])
    return "\n".join(new_lines)


class SkeletonRenderer:
    def __init__(self, repo_paths: RepoPaths, db: Database, registry: ParserRegistry):
        self.repo_paths = repo_paths
        self.db = db
        self.registry = registry

    def render_file_skeleton(
        self,
        rel_path: str,
        max_chars: int = 12000,
        session_tracker: Optional[SessionDedupTracker] = None,
    ) -> str:
        abs_p = self.repo_paths.resolve_user_path(rel_path)
        if not abs_p.exists():
            return f"[Error: File '{rel_path}' does not exist]"

        source_bytes = abs_p.read_bytes()
        adapter = self.registry.for_path(rel_path)
        parsed = adapter.parse(rel_path, source_bytes)
        skeleton = adapter.render_skeleton(source_bytes, parsed)

        # Collapse verbose import statements to minimize token bloat
        skeleton = collapse_imports(skeleton, rel_path)

        if session_tracker:
            comment_char = "#" if rel_path.endswith(".py") else "//"
            for sym in parsed.symbols:
                emitted = session_tracker.get_emitted(
                    symbol_key=sym.symbol_key,
                    file_path=rel_path,
                    start_line=sym.full_range.start_line,
                    end_line=sym.full_range.end_line,
                )
                if emitted:
                    back_ref = session_tracker.format_back_reference(emitted)
                    sig_anchor = sym.signature.splitlines()[0].strip() if sym.signature else sym.name
                    pat = rf"({re.escape(sig_anchor)}[\s\S]*?\n\s*{re.escape(comment_char)}\s*)\.\.\. implementation omitted \.\.\."
                    new_skeleton, num_subs = re.subn(pat, rf"\g<1>{back_ref}", skeleton, count=1)
                    if num_subs > 0:
                        skeleton = new_skeleton
                    else:
                        pat_fallback = rf"({re.escape(sym.name)}[\s\S]*?\n\s*{re.escape(comment_char)}\s*)\.\.\. implementation omitted \.\.\."
                        skeleton = re.sub(pat_fallback, rf"\g<1>{back_ref}", skeleton, count=1)

        if len(skeleton) > max_chars:
            return skeleton[:max_chars] + f"\n\n... [Skeleton truncated at {max_chars} chars. Request specific symbols directly]"

        return skeleton
