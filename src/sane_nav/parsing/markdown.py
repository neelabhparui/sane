from __future__ import annotations

import re

from sane_nav.core.models import (
    ParsedDocumentSection,
    ParsedFile,
    SourceRange,
)


class MarkdownAdapter:
    language = "markdown"

    def supports(self, path: str) -> bool:
        return path.endswith(".md") or path.endswith(".markdown")

    def parse(self, path: str, source: bytes) -> ParsedFile:
        source_text = source.decode("utf-8", errors="replace")
        lines = source_text.splitlines()

        # Extract headings and sections
        # Matches #, ##, ###, ####, etc.
        heading_regex = re.compile(r"^(#{1,6})\s+(.+)$")

        @dataclass_heading
        class RawHeading:
            level: int
            title: str
            line_idx: int

        raw_headings: list[RawHeading] = []
        in_code_block = False

        for idx, line in enumerate(lines):
            # Ignore headings inside fenced code blocks ``` ... ```
            if line.strip().startswith("```"):
                in_code_block = not in_code_block
                continue
            if not in_code_block:
                m = heading_regex.match(line)
                if m:
                    level = len(m.group(1))
                    title = m.group(2).strip()
                    raw_headings.append(RawHeading(level, title, idx))

        docs: list[ParsedDocumentSection] = []
        heading_stack: list[tuple[int, str]] = []

        line_offsets = [0]
        cur = 0
        for l in source.splitlines(keepends=True):
            cur += len(l)
            line_offsets.append(cur)

        for i, h in enumerate(raw_headings):
            # Update heading stack
            while heading_stack and heading_stack[-1][0] >= h.level:
                heading_stack.pop()
            heading_stack.append((h.level, h.title))

            heading_path = tuple(t for _, t in heading_stack)

            # Direct body extends to next heading or end of file
            next_line = raw_headings[i + 1].line_idx if (i + 1 < len(raw_headings)) else len(lines)
            content_lines = lines[h.line_idx + 1 : next_line]
            content = "\n".join(content_lines).strip()

            start_line = h.line_idx + 1
            end_line = next_line
            start_byte = line_offsets[h.line_idx]
            end_byte = line_offsets[next_line] if next_line < len(line_offsets) else len(source)

            docs.append(
                ParsedDocumentSection(
                    heading=h.title,
                    heading_path=heading_path,
                    content=content,
                    source_range=SourceRange(start_byte, end_byte, start_line, end_line),
                    level=h.level,
                )
            )

        # If no headings exist, create one section for the whole doc
        if not docs and source_text.strip():
            docs.append(
                ParsedDocumentSection(
                    heading=path.split("/")[-1],
                    heading_path=(path.split("/")[-1],),
                    content=source_text.strip(),
                    source_range=SourceRange(0, len(source), 1, len(lines)),
                    level=1,
                )
            )

        return ParsedFile(
            symbols=(),
            references=(),
            docs=tuple(docs),
            parse_error_count=0,
        )

    def render_skeleton(self, _source: bytes, parsed: ParsedFile) -> str:
        # Outline of Markdown headings
        out: list[str] = []
        for d in parsed.docs:
            indent = "  " * (d.level - 1)
            out.append(f"{indent}# {d.heading} (L{d.source_range.start_line}-L{d.source_range.end_line})")
        return "\n".join(out)


def dataclass_heading(cls):
    def __init__(self, level: int, title: str, line_idx: int):
        self.level = level
        self.title = title
        self.line_idx = line_idx

    cls.__init__ = __init__
    return cls
