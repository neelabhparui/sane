from __future__ import annotations

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


class JavaAdapter:
    language = "java"

    def supports(self, path: str) -> bool:
        return path.endswith(".java")

    def _get_line_byte_offsets(self, source_bytes: bytes) -> list[int]:
        offsets = [0]
        cur = 0
        for line in source_bytes.splitlines(keepends=True):
            cur += len(line)
            offsets.append(cur)
        return offsets

    def parse(self, path: str, source: bytes) -> ParsedFile:
        symbols: list[ParsedSymbol] = []
        references: list[ParsedReference] = []
        source_text = source.decode("utf-8", errors="replace")
        line_offsets = self._get_line_byte_offsets(source)
        lines = source_text.splitlines()

        # Find package
        package_name = ""
        pkg_match = re.search(r"package\s+([\w\.]+);", source_text)
        if pkg_match:
            package_name = pkg_match.group(1)

        # Regex for classes, interfaces, records, enums
        class_regex = re.compile(
            r"((?:@\w+(?:\([^)]*\))?\s+)*(?:public|protected|private|static|final|abstract)?\s*(class|interface|record|enum)\s+([A-Za-z0-9_]+)(?:<[^>]+>)?(?:\s+extends\s+[^{]+)?(?:\s+implements\s+[^{]+)?)\s*\{",
            re.MULTILINE,
        )

        # Regex for methods:
        # annotations?, visibility modifiers?, return type, name, (params), throws?
        method_regex = re.compile(
            r"((?:@\w+(?:\([^)]*\))?\s+)*(?:public|protected|private|static|final|synchronized|abstract|default)?\s*([A-Za-z0-9_<>, \.\[\]]+)\s+([A-Za-z0-9_]+)\s*\(([^)]*)\)(?:\s*throws\s+[^{;]+)?)\s*(\{)",
            re.MULTILINE,
        )

        # Find javadoc preceding positions
        def extract_javadoc(byte_pos: int) -> Optional[str]:
            prefix = source_text[:byte_pos].rstrip()
            if prefix.endswith("*/"):
                start_doc = prefix.rfind("/**")
                if start_doc != -1 and (byte_pos - start_doc) < 2000:
                    doc = prefix[start_doc + 3 : -2].strip()
                    # Strip leading asterisks
                    cleaned = "\n".join(re.sub(r"^\s*\*\s?", "", l) for l in doc.splitlines())
                    return cleaned.strip()
            return None

        # Track class enclosures
        current_class: Optional[str] = None
        current_class_key: Optional[str] = None

        # Match classes
        for m in class_regex.finditer(source_text):
            sig = m.group(1).strip()
            c_kind = m.group(2)
            c_name = m.group(3)
            start_pos = m.start()
            start_line = source_text[:start_pos].count("\n") + 1

            # Match closing brace for class
            brace_count = 1
            idx = m.end()
            while idx < len(source_text) and brace_count > 0:
                if source_text[idx] == "{":
                    brace_count += 1
                elif source_text[idx] == "}":
                    brace_count -= 1
                idx += 1
            end_pos = idx
            end_line = source_text[:end_pos].count("\n") + 1

            full_range = SourceRange(start_pos, end_pos, start_line, end_line)
            body_range = SourceRange(m.end(), end_pos, source_text[: m.end()].count("\n") + 1, end_line)

            qualified_name = f"{package_name}.{c_name}" if package_name else c_name
            symbol_key = build_symbol_key("java", path, package_name, c_name, line=start_line)

            docstring = extract_javadoc(start_pos)
            symbols.append(
                ParsedSymbol(
                    name=c_name,
                    qualified_name=qualified_name,
                    kind=c_kind,
                    signature=sig,
                    docstring=docstring,
                    full_range=full_range,
                    body_range=body_range,
                    symbol_key=symbol_key,
                )
            )

            current_class = c_name
            current_class_key = symbol_key

        # Match methods inside classes
        for m in method_regex.finditer(source_text):
            sig = m.group(1).strip()
            ret_type = m.group(2).strip()
            m_name = m.group(3)
            params = m.group(4).strip()
            start_pos = m.start()
            start_line = source_text[:start_pos].count("\n") + 1

            # Filter out control structures
            if m_name in ("if", "for", "while", "switch", "catch"):
                continue

            # Match closing brace for method body
            brace_count = 1
            idx = m.end()
            while idx < len(source_text) and brace_count > 0:
                if source_text[idx] == "{":
                    brace_count += 1
                elif source_text[idx] == "}":
                    brace_count -= 1
                idx += 1
            end_pos = idx
            end_line = source_text[:end_pos].count("\n") + 1

            full_range = SourceRange(start_pos, end_pos, start_line, end_line)
            body_range = SourceRange(m.end() - 1, end_pos, source_text[: m.end() - 1].count("\n") + 1, end_line)

            qualified_name = f"{current_class}.{m_name}" if current_class else m_name
            symbol_key = build_symbol_key(
                "java", path, current_class or package_name, m_name, signature_params=params, line=start_line
            )

            docstring = extract_javadoc(start_pos)
            symbols.append(
                ParsedSymbol(
                    name=m_name,
                    qualified_name=qualified_name,
                    kind=SymbolKind.METHOD.value,
                    signature=sig,
                    docstring=docstring,
                    full_range=full_range,
                    body_range=body_range,
                    parent_key=current_class_key,
                    symbol_key=symbol_key,
                )
            )

        # Match calls e.g. "paymentProcessor.capture(" or "execute("
        call_regex = re.compile(r"(?:([A-Za-z0-9_]+)\.)?([A-Za-z0-9_]+)\s*\(")
        for m in call_regex.finditer(source_text):
            receiver = m.group(1)
            call_name = m.group(2)
            if call_name in ("if", "while", "for", "switch", "catch", "new", "class"):
                continue
            c_pos = m.start()
            c_line = source_text[:c_pos].count("\n") + 1

            # Determine enclosing method
            enc_key = None
            for s in symbols:
                if s.kind == SymbolKind.METHOD.value and s.full_range.start_line <= c_line <= s.full_range.end_line:
                    enc_key = s.symbol_key
                    break

            references.append(
                ParsedReference(
                    spelling=call_name,
                    role="call",
                    source_range=SourceRange(c_pos, m.end(), c_line, c_line),
                    enclosing_symbol_key=enc_key,
                    receiver_text=receiver,
                )
            )

        return ParsedFile(
            symbols=tuple(symbols),
            references=tuple(references),
            docs=(),
            parse_error_count=0,
        )

    def render_skeleton(self, source: bytes, parsed: ParsedFile) -> str:
        source_text = source.decode("utf-8", errors="replace")
        methods = [
            s for s in parsed.symbols
            if s.kind == SymbolKind.METHOD.value and s.body_range
        ]
        methods.sort(key=lambda s: s.body_range.start_byte, reverse=True)

        result = list(source_text)
        for m in methods:
            assert m.body_range is not None
            # Replace interior of method body '{ ... }' with '{\n        // ... implementation omitted ...\n    }'
            sb = m.body_range.start_byte
            eb = m.body_range.end_byte
            replacement = "{\n        // ... implementation omitted ...\n    }"
            result[sb:eb] = list(replacement)

        return "".join(result)
