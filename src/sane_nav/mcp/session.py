"""In-memory session deduplication tracker for S.A.N.E. MCP sessions.

Prevents redundant re-emission of previously served code spans across multi-turn
tool interactions, saving token budget for LLM agents.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class EmittedSpan:
    """Represents a code span emitted during a specific conversation turn."""

    turn: int
    file_path: str
    start_line: int
    end_line: int
    symbol_key: str
    symbol_name: str


class SessionDedupTracker:
    """Tracks code spans emitted during an MCP session to prevent redundant token spend."""

    def __init__(self) -> None:
        self.current_turn: int = 1
        self._emitted_by_key: dict[str, EmittedSpan] = {}
        self._emitted_by_range: dict[tuple[str, int, int], EmittedSpan] = {}

    def next_turn(self) -> int:
        """Advances to the next conversation turn."""
        self.current_turn += 1
        return self.current_turn

    def record(
        self,
        symbol_key: str,
        symbol_name: str,
        file_path: str,
        start_line: int,
        end_line: int,
    ) -> EmittedSpan:
        """Records an emitted code span for the current turn."""
        span = EmittedSpan(
            turn=self.current_turn,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            symbol_key=symbol_key,
            symbol_name=symbol_name,
        )
        self._emitted_by_key[symbol_key] = span
        if symbol_name:
            self._emitted_by_key[symbol_name] = span
        self._emitted_by_range[(file_path, start_line, end_line)] = span
        return span

    def get_emitted(
        self,
        symbol_key: Optional[str] = None,
        file_path: Optional[str] = None,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        allow_same_turn: bool = False,
    ) -> Optional[EmittedSpan]:
        """Checks if a symbol or range has already been emitted in an earlier turn."""
        span: Optional[EmittedSpan] = None
        if symbol_key and symbol_key in self._emitted_by_key:
            span = self._emitted_by_key[symbol_key]
        elif file_path and start_line is not None and end_line is not None:
            span = self._emitted_by_range.get((file_path, start_line, end_line))

        if span is not None and (allow_same_turn or span.turn < self.current_turn):
            return span
        return None

    def format_back_reference(self, span: EmittedSpan) -> str:
        """Generates the standardized back-reference string."""
        return (
            f"[Source for Symbol {span.symbol_name} already provided in Turn {span.turn} "
            f"(L{span.start_line}-L{span.end_line}). Omitted to preserve token budget. "
            f"Pass force=True or call read_lines to inspect.]"
        )

    def clear(self) -> None:
        """Clears all session tracking state."""
        self._emitted_by_key.clear()
        self._emitted_by_range.clear()
        self.current_turn = 1
