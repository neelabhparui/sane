from __future__ import annotations

from pathlib import Path
import re
from typing import Optional

import tree_sitter
import tree_sitter_language_pack as tslp

from sane_nav.core.ids import build_symbol_key
from sane_nav.core.models import (
    ParsedFile,
    ParsedReference,
    ParsedSymbol,
    SourceRange,
    SymbolKind,
)


class TreeSitterAdapter:
    """Generic language adapter driven by Tree-sitter AST queries."""

    def __init__(
        self,
        language: str,
        extensions: tuple[str, ...],
        query_path: str | Path,
    ) -> None:
        self.language = language
        self.extensions = extensions
        self.query_path = Path(query_path)
        self._lang = tslp.get_language(self.language)
        self._parser = tslp.get_parser(self.language)
        query_scm = self.query_path.read_text(encoding="utf-8")
        self._query = tree_sitter.Query(self._lang, query_scm)

    def supports(self, path: str) -> bool:
        return any(path.endswith(ext) for ext in self.extensions)

    def _count_errors(self, node: tree_sitter.Node) -> int:
        if not node.has_error:
            return 0
        cnt = 1 if (node.is_error or node.is_missing) else 0
        for child in node.children:
            if child.has_error:
                cnt += self._count_errors(child)
        return cnt

    def _extract_docstring(self, node: tree_sitter.Node) -> Optional[str]:
        curr = node.prev_sibling
        comments: list[tree_sitter.Node] = []
        while curr and curr.type in ("comment", "line_comment", "block_comment", "multiline_comment"):
            comments.append(curr)
            curr = curr.prev_sibling
        if not comments:
            return None
        comments.reverse()
        raw = "\n".join(c.text.decode("utf-8", errors="replace") for c in comments).strip()
        if raw.startswith("/*") and raw.endswith("*/"):
            content = raw[2:-2]
            lines = [re.sub(r"^\s*\*\s?", "", l) for l in content.splitlines()]
            cleaned = "\n".join(lines).strip()
            return cleaned or None
        lines = [re.sub(r"^\s*///?\s?", "", l) for l in raw.splitlines()]
        cleaned = "\n".join(lines).strip()
        return cleaned or None

    def parse(self, path: str, source: bytes) -> ParsedFile:
        tree = self._parser.parse(source)
        error_count = self._count_errors(tree.root_node)

        cursor = tree_sitter.QueryCursor(self._query)
        matches = cursor.matches(tree.root_node)

        # 1. Package / namespace
        package_name = ""
        for _, caps in matches:
            if "package" in caps:
                package_name = caps["package"][0].text.decode("utf-8", errors="replace").strip()
                break

        # 2. Collect definition and reference matches
        defs: list[tuple[tree_sitter.Node, str, dict[str, list[tree_sitter.Node]]]] = []
        refs: list[tuple[tree_sitter.Node, str, dict[str, list[tree_sitter.Node]]]] = []

        for _, caps in matches:
            def_key = next((k for k in caps if k.startswith("definition.")), None)
            if def_key:
                defs.append((caps[def_key][0], def_key, caps))
            ref_key = next((k for k in caps if k.startswith("reference.")), None)
            if ref_key:
                refs.append((caps[ref_key][0], ref_key, caps))

        # Sort definitions in pre-order: outer before inner
        defs.sort(key=lambda item: (item[0].start_byte, -item[0].end_byte))

        symbols: list[ParsedSymbol] = []
        symbol_by_node_id: dict[int, ParsedSymbol] = {}

        for def_node, def_key, caps in defs:
            raw_kind = def_key.split(".", 1)[1]
            name_node = caps.get("name", [None])[0]
            if name_node:
                name = name_node.text.decode("utf-8", errors="replace")
            elif raw_kind in ("companion", "companion_object"):
                name = "Companion"
            elif raw_kind == "constructor":
                name = "init" if self.language == "swift" else "constructor"
            else:
                name = def_node.type

            body_node = caps.get("body", [None])[0]
            param_node = caps.get("parameters", [None])[0]
            sig_params = None
            if param_node:
                p_text = param_node.text.decode("utf-8", errors="replace").strip()
                if p_text.startswith("(") and p_text.endswith(")"):
                    p_text = p_text[1:-1].strip()
                sig_params = p_text

            # Resolve enclosing parent symbol
            curr = def_node.parent
            parent_sym: Optional[ParsedSymbol] = None
            while curr:
                if curr.id in symbol_by_node_id:
                    parent_sym = symbol_by_node_id[curr.id]
                    break
                curr = curr.parent

            # Determine normalized SymbolKind
            if raw_kind in ("class", "struct", "enum", "object", "companion"):
                kind = SymbolKind.CLASS.value
            elif raw_kind in ("interface", "protocol"):
                kind = SymbolKind.INTERFACE.value
            elif raw_kind == "record":
                kind = SymbolKind.RECORD.value
            elif raw_kind == "constructor":
                kind = SymbolKind.METHOD.value if parent_sym else SymbolKind.CONSTRUCTOR.value
            elif raw_kind in ("method", "function"):
                kind = SymbolKind.METHOD.value if parent_sym else SymbolKind.FUNCTION.value
            else:
                kind = raw_kind

            start_line = def_node.start_point[0] + 1
            end_line = def_node.end_point[0] + 1
            full_range = SourceRange(def_node.start_byte, def_node.end_byte, start_line, end_line)

            if body_node:
                body_range = SourceRange(
                    body_node.start_byte,
                    body_node.end_byte,
                    body_node.start_point[0] + 1,
                    body_node.end_point[0] + 1,
                )
                sig_bytes = source[def_node.start_byte : body_node.start_byte]
                signature = sig_bytes.decode("utf-8", errors="replace").strip()
            else:
                body_range = None
                sig_bytes = source[def_node.start_byte : def_node.end_byte]
                signature = sig_bytes.decode("utf-8", errors="replace").rstrip(";").strip()

            if parent_sym:
                parent_key = parent_sym.symbol_key
                owner_name = parent_sym.name
                qualified_name = f"{parent_sym.name}.{name}"
            else:
                parent_key = None
                owner_name = package_name
                qualified_name = f"{package_name}.{name}" if package_name else name

            symbol_key = build_symbol_key(
                self.language,
                path,
                owner_name,
                name,
                signature_params=sig_params,
                line=start_line,
            )

            docstring = self._extract_docstring(def_node)

            sym = ParsedSymbol(
                name=name,
                qualified_name=qualified_name,
                kind=kind,
                signature=signature,
                docstring=docstring,
                full_range=full_range,
                body_range=body_range,
                parent_key=parent_key,
                symbol_key=symbol_key,
            )
            symbols.append(sym)
            symbol_by_node_id[def_node.id] = sym

        # 3. References
        references: list[ParsedReference] = []
        for ref_node, ref_key, caps in refs:
            role = ref_key.split(".", 1)[1]
            if role == "type":
                role = "implements"
            name_node = caps.get("name", [ref_node])[0]
            spelling = name_node.text.decode("utf-8", errors="replace").strip()

            # Ignore language primitives/keywords
            if spelling in (
                "if", "while", "for", "switch", "when", "catch", "new",
                "class", "super", "this", "self", "Object", "Any", "Unit", "Nothing"
            ):
                continue

            receiver_node = caps.get("receiver", [None])[0]
            receiver_text = (
                receiver_node.text.decode("utf-8", errors="replace").strip()
                if receiver_node
                else None
            )

            # Find enclosing symbol
            curr = ref_node.parent
            enc_sym: Optional[ParsedSymbol] = None
            while curr:
                if curr.id in symbol_by_node_id:
                    cand = symbol_by_node_id[curr.id]
                    if role in ("extends", "implements"):
                        enc_sym = cand
                        break
                    if cand.kind in (SymbolKind.METHOD.value, SymbolKind.FUNCTION.value, SymbolKind.CONSTRUCTOR.value):
                        enc_sym = cand
                        break
                    if enc_sym is None:
                        enc_sym = cand
                curr = curr.parent

            enc_key = enc_sym.symbol_key if enc_sym else None
            start_line = ref_node.start_point[0] + 1
            end_line = ref_node.end_point[0] + 1
            source_range = SourceRange(
                ref_node.start_byte,
                ref_node.end_byte,
                start_line,
                end_line,
            )

            references.append(
                ParsedReference(
                    spelling=spelling,
                    role=role,
                    source_range=source_range,
                    enclosing_symbol_key=enc_key,
                    receiver_text=receiver_text,
                )
            )

        return ParsedFile(
            symbols=tuple(symbols),
            references=tuple(references),
            docs=(),
            parse_error_count=error_count,
        )

    def render_skeleton(self, source: bytes, parsed: ParsedFile) -> str:
        source_text = source.decode("utf-8", errors="replace")
        redactable = [
            s for s in parsed.symbols
            if s.body_range and s.kind in (
                SymbolKind.METHOD.value,
                SymbolKind.FUNCTION.value,
                SymbolKind.CONSTRUCTOR.value,
            )
        ]
        redactable.sort(key=lambda s: s.body_range.start_byte, reverse=True)

        result = list(source_text)
        for s in redactable:
            assert s.body_range is not None
            sb = s.body_range.start_byte
            eb = s.body_range.end_byte
            body_snippet = source_text[sb:eb].strip()
            if body_snippet.startswith("{"):
                replacement = "{\n        // ... implementation omitted ...\n    }"
            else:
                replacement = "= ..."
            result[sb:eb] = list(replacement)

        return "".join(result)
