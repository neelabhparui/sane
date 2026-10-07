"""Python AST language adapter.

Parses Python source files using Python's native `ast` module to extract classes,
functions, methods, decorators, type hints, docstrings, calls, and byte-for-byte
redacted skeletons.
"""

from __future__ import annotations

import ast
import re
from typing import Optional

from sane_nav.core.ids import build_symbol_key
from sane_nav.core.models import (
    ParsedFile,
    ParsedReference,
    ParsedSymbol,
    SourceRange,
    SymbolKind,
)


class PythonAdapter:
    """AST-backed language adapter for Python source files."""

    language = "python"

    def supports(self, path: str) -> bool:
        """Returns True if the path represents a Python source file (.py)."""
        return path.endswith(".py")

    def _get_line_byte_offsets(self, source_bytes: bytes) -> list[int]:
        """Calculates start byte offset for each 1-based line."""
        offsets = [0]
        cur = 0
        for line in source_bytes.splitlines(keepends=True):
            cur += len(line)
            offsets.append(cur)
        return offsets

    def _ast_range(
        self,
        node: ast.AST,
        source_bytes: bytes,
        line_offsets: list[int],
    ) -> SourceRange:
        """Constructs a SourceRange from an AST node's line and column numbers."""
        start_line = getattr(node, "lineno", 1)
        end_line = getattr(node, "end_lineno", start_line)
        col_offset = getattr(node, "col_offset", 0)
        end_col = getattr(node, "end_col_offset", 0)

        start_byte = line_offsets[start_line - 1] + col_offset
        end_byte = line_offsets[end_line - 1] + end_col
        return SourceRange(
            start_byte=start_byte,
            end_byte=end_byte,
            start_line=start_line,
            end_line=end_line,
        )

    def _format_signature(self, node: ast.FunctionDef | ast.AsyncFunctionDef, source_text: str) -> str:
        """Extracts the exact declaration header from 'def' up to the trailing colon."""
        lines = source_text.splitlines()
        start = node.lineno - 1
        def_slice = lines[start:node.body[0].lineno]
        def_text = "\n".join(def_slice)
        match = re.search(r"((async\s+)?def\s+[\s\S]+?):", def_text)
        if match:
            return match.group(1).strip()
        arg_names = [a.arg for a in node.args.args]
        return f"{'async ' if isinstance(node, ast.AsyncFunctionDef) else ''}def {node.name}({', '.join(arg_names)})"

    def parse(self, path: str, source: bytes) -> ParsedFile:
        """Parses Python source into AST and extracts symbols, references, and ranges.

        Args:
            path: Relative path to the file.
            source: Raw file bytes.

        Returns:
            ParsedFile intermediate representation.
        """
        symbols: list[ParsedSymbol] = []
        references: list[ParsedReference] = []
        parse_errors = 0

        try:
            source_text = source.decode("utf-8", errors="replace")
            tree = ast.parse(source_text, filename=path)
        except SyntaxError:
            return ParsedFile(parse_error_count=1)

        line_offsets = self._get_line_byte_offsets(source)

        # Context tracker for enclosing symbols
        class SymbolVisitor(ast.NodeVisitor):
            def __init__(self, adapter: PythonAdapter):
                self.adapter = adapter
                self.scope_stack: list[str] = []
                self.enclosing_symbol_key: Optional[str] = None

            def visit_ClassDef(self, node: ast.ClassDef):
                full_range = self.adapter._ast_range(node, source, line_offsets)
                docstring = ast.get_docstring(node)

                # Body starts after docstring if present, else first statement
                body_first = node.body[1] if (docstring and len(node.body) > 1) else node.body[0]
                body_range = SourceRange(
                    start_byte=line_offsets[body_first.lineno - 1] + body_first.col_offset,
                    end_byte=full_range.end_byte,
                    start_line=body_first.lineno,
                    end_line=full_range.end_line,
                )

                owner = ".".join(self.scope_stack) if self.scope_stack else None
                qualified_name = f"{owner}.{node.name}" if owner else node.name
                symbol_key = build_symbol_key("python", path, owner, node.name, line=node.lineno)

                base_names = []
                for b in node.bases:
                    b_name = None
                    if isinstance(b, ast.Name):
                        b_name = b.id
                    elif isinstance(b, ast.Attribute):
                        b_name = b.attr
                    if b_name:
                        base_names.append(b_name)
                        references.append(
                            ParsedReference(
                                spelling=b_name,
                                role="extends",
                                source_range=full_range,
                                enclosing_symbol_key=symbol_key,
                            )
                        )

                bases_str = f"({', '.join(base_names)})" if base_names else ""
                signature = f"class {node.name}{bases_str}"

                symbols.append(
                    ParsedSymbol(
                        name=node.name,
                        qualified_name=qualified_name,
                        kind=SymbolKind.CLASS.value,
                        signature=signature,
                        docstring=docstring,
                        full_range=full_range,
                        body_range=body_range,
                        parent_key=self.enclosing_symbol_key,
                        symbol_key=symbol_key,
                    )
                )

                old_enc = self.enclosing_symbol_key
                self.enclosing_symbol_key = symbol_key
                self.scope_stack.append(node.name)
                self.generic_visit(node)
                self.scope_stack.pop()
                self.enclosing_symbol_key = old_enc

            def visit_FunctionDef(self, node: ast.FunctionDef):
                self._handle_function(node, is_async=False)

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
                self._handle_function(node, is_async=True)

            def _handle_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, is_async: bool):
                full_range = self.adapter._ast_range(node, source, line_offsets)
                docstring = ast.get_docstring(node)
                signature = self.adapter._format_signature(node, source_text)

                body_first = node.body[1] if (docstring and len(node.body) > 1) else node.body[0]
                body_range = SourceRange(
                    start_byte=line_offsets[body_first.lineno - 1] + body_first.col_offset,
                    end_byte=full_range.end_byte,
                    start_line=body_first.lineno,
                    end_line=full_range.end_line,
                )

                owner = ".".join(self.scope_stack) if self.scope_stack else None
                kind = SymbolKind.METHOD.value if self.scope_stack else SymbolKind.FUNCTION.value
                qualified_name = f"{owner}.{node.name}" if owner else node.name
                symbol_key = build_symbol_key("python", path, owner, node.name, line=node.lineno)

                symbols.append(
                    ParsedSymbol(
                        name=node.name,
                        qualified_name=qualified_name,
                        kind=kind,
                        signature=signature,
                        docstring=docstring,
                        full_range=full_range,
                        body_range=body_range,
                        parent_key=self.enclosing_symbol_key,
                        symbol_key=symbol_key,
                    )
                )

                old_enc = self.enclosing_symbol_key
                self.enclosing_symbol_key = symbol_key
                self.scope_stack.append(node.name)
                self.generic_visit(node)
                self.scope_stack.pop()
                self.enclosing_symbol_key = old_enc

            def visit_Call(self, node: ast.Call):
                spelling = ""
                receiver_text = None
                if isinstance(node.func, ast.Name):
                    spelling = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    spelling = node.func.attr
                    if isinstance(node.func.value, ast.Name):
                        receiver_text = node.func.value.id
                    elif isinstance(node.func.value, ast.Attribute):
                        receiver_text = node.func.value.attr

                if spelling:
                    rng = self.adapter._ast_range(node, source, line_offsets)
                    references.append(
                        ParsedReference(
                            spelling=spelling,
                            role="call",
                            source_range=rng,
                            enclosing_symbol_key=self.enclosing_symbol_key,
                            receiver_text=receiver_text,
                        )
                    )
                self.generic_visit(node)

        visitor = SymbolVisitor(self)
        visitor.visit(tree)

        return ParsedFile(
            symbols=tuple(symbols),
            references=tuple(references),
            docs=(),
            parse_error_count=parse_errors,
        )

    def render_skeleton(self, source: bytes, parsed: ParsedFile) -> str:
        """Redacts implementation bodies from the source byte-for-byte,
        preserving decorators, type hints, docstrings, and imports.
        """
        if not parsed.symbols:
            return source.decode("utf-8", errors="replace")

        # Sort symbols with body ranges by start_byte descending so we replace from end to beginning
        redactable = [
            s for s in parsed.symbols
            if s.body_range and s.kind in (SymbolKind.FUNCTION.value, SymbolKind.METHOD.value)
        ]
        redactable.sort(key=lambda s: s.body_range.start_byte, reverse=True)

        source_text = source.decode("utf-8", errors="replace")
        lines = source_text.splitlines(keepends=True)

        # For clean skeleton display, replace function bodies
        for sym in redactable:
            assert sym.body_range is not None
            b_start = sym.body_range.start_line - 1
            b_end = sym.body_range.end_line

            if b_start < len(lines):
                # Detect indent
                indent = "    "
                if sym.full_range.start_line - 1 < len(lines):
                    first_line = lines[sym.full_range.start_line - 1]
                    matched = re.match(r"^(\s*)", first_line)
                    if matched:
                        indent = matched.group(1) + "    "

                replacement = f"{indent}# ... implementation omitted ...\n"
                if sym.docstring:
                    doc_quoted = f'{indent}"""{sym.docstring}"""\n'
                    replacement = doc_quoted + replacement

                lines[b_start:b_end] = [replacement]

        return "".join(lines)
