from __future__ import annotations

import os
from pathlib import Path

from sane_nav.core.errors import UnsupportedLanguageError
from sane_nav.parsing.base import LanguageAdapter
from sane_nav.parsing.java import JavaAdapter
from sane_nav.parsing.kotlin import KotlinAdapter
from sane_nav.parsing.markdown import MarkdownAdapter
from sane_nav.parsing.python import PythonAdapter
from sane_nav.parsing.treesitter.engine import TreeSitterAdapter


class ParserRegistry:
    def __init__(self):
        backend = os.getenv("SANE_NAV_PARSER_BACKEND", "treesitter").lower()
        queries_dir = Path(__file__).parent / "treesitter" / "queries"

        if backend == "regex":
            java_adapter: LanguageAdapter = JavaAdapter()
            kotlin_adapter: LanguageAdapter = KotlinAdapter()
        else:
            java_adapter = TreeSitterAdapter(
                language="java",
                extensions=(".java",),
                query_path=queries_dir / "java_tags.scm",
            )
            kotlin_adapter = TreeSitterAdapter(
                language="kotlin",
                extensions=(".kt", ".kts"),
                query_path=queries_dir / "kotlin_tags.scm",
            )

        swift_adapter = TreeSitterAdapter(
            language="swift",
            extensions=(".swift",),
            query_path=queries_dir / "swift_tags.scm",
        )

        self.adapters: list[LanguageAdapter] = [
            PythonAdapter(),
            java_adapter,
            kotlin_adapter,
            swift_adapter,
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
