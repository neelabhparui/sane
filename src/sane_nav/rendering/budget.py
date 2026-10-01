from __future__ import annotations

from sane_nav.core.models import OutputBudget


class BudgetManager:
    @staticmethod
    def create(max_chars: int = 12000, max_items: int = 10) -> OutputBudget:
        return OutputBudget(max_chars=max_chars, max_items=max_items)

    @staticmethod
    def truncate_lines(lines: list[str], max_chars: int, label: str = "items") -> str:
        out: list[str] = []
        curr = 0
        truncated = False
        for i, line in enumerate(lines):
            line_len = len(line) + 1
            if curr + line_len > max_chars:
                out.append(f"\n... [Showing {i} of {len(lines)} {label}. Refine query or request sub-range]")
                truncated = True
                break
            out.append(line)
            curr += line_len
        return "\n".join(out)
