from __future__ import annotations

from pathlib import Path
from typing import Optional

from sane_nav.core.errors import UnsupportedLanguageError
from sane_nav.parsing.base import LanguageAdapter
from sane_nav.parsing.java import JavaAdapter
from sane_nav.parsing.kotlin import KotlinAdapter
from sane_nav.parsing.markdown import MarkdownAdapter
from sane_nav.parsing.python import PythonAdapter


class ParserRegistry:
    def __init__(self):
        self.adapters: list[LanguageAdapter] = [
            PythonAdapter(),
            JavaAdapter(),
            KotlinAdapter(),
            MarkdownAdapter(),
        ]

    def for_path(self, path: str | Path) -> LanguageAdapter:
        p_str = str(path)
        for adapter in self.adapters:
            if adapter.supports(p_str):
                return adapter
        raise UnsupportedLanguageError(f"No language adapter registered for file '{path}'")

    def is_supported(self, path: str | Path) -> bool:
        p_str = str(path)
        return any(a.supports(p_str) for a in self.adapters)
