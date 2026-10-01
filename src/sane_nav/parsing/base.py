from __future__ import annotations

from typing import Protocol

from sane_nav.core.models import ParsedFile


class LanguageAdapter(Protocol):
    language: str

    def supports(self, path: str) -> bool:
        ...

    def parse(self, path: str, source: bytes) -> ParsedFile:
        ...

    def render_skeleton(self, source: bytes, parsed: ParsedFile) -> str:
        ...
