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


class KotlinAdapter:
    language = "kotlin"

    def supports(self, path: str) -> bool:
        return path.endswith(".kt") or path.endswith(".kts")

    def parse(self, path: str, source: bytes) -> ParsedFile:
        symbols: list[ParsedSymbol] = []
        references: list[ParsedReference] = []
        source_text = source.decode("utf-8", errors="replace")

        # Find package
        package_name = ""
        pkg_match = re.search(r"package\s+([\w\.]+)", source_text)
        if pkg_match:
            package_name = pkg_match.group(1)

        # Regex for Kotlin classes/interfaces/objects:
        # e.g. "data class User(val id: String)", "sealed interface State", "companion object", "class AuthService"
        class_regex = re.compile(
            r"((?:@\w+(?:\([^)]*\))?\s+)*(?:public|protected|private|internal|open|abstract|sealed|data|value)?\s*(class|interface|object|enum\s+class)\s+([A-Za-z0-9_]+)(?:<[^>]+>)?(?:\s*\([^)]*\))?(?:\s*:\s*[^{]+)?)\s*(\{)?",
            re.MULTILINE,
        )

        # Regex for Kotlin functions:
        # e.g. "@Transactional suspend fun capture(intent: PaymentIntent, amount: Money): CaptureResult"
        fun_regex = re.compile(
            r"((?:@\w+(?:\([^)]*\))?\s+)*(?:public|protected|private|internal|override|suspend|inline|open|abstract)?\s*fun\s+(?:<[^>]+>\s+)?(?:([A-Za-z0-9_]+)\.)?([A-Za-z0-9_]+)\s*\(([^)]*)\)(?:\s*:\s*([A-Za-z0-9_<>, \?\.\[\]]+))?)\s*(\{|=)",
            re.MULTILINE,
        )

        def extract_kdoc(byte_pos: int) -> Optional[str]:
            prefix = source_text[:byte_pos].rstrip()
            if prefix.endswith("*/"):
                start_doc = prefix.rfind("/**")
                if start_doc != -1 and (byte_pos - start_doc) < 2000:
                    doc = prefix[start_doc + 3 : -2].strip()
                    cleaned = "\n".join(re.sub(r"^\s*\*\s?", "", l) for l in doc.splitlines())
                    return cleaned.strip()
            return None

        current_class: Optional[str] = None
        current_class_key: Optional[str] = None

        for m in class_regex.finditer(source_text):
            sig = m.group(1).strip()
            c_kind = m.group(2).strip()
            c_name = m.group(3)
            has_brace = m.group(4) == "{"
            start_pos = m.start()
            start_line = source_text[:start_pos].count("\n") + 1

            if has_brace:
                brace_count = 1
                idx = m.end()
                while idx < len(source_text) and brace_count > 0:
                    if source_text[idx] == "{":
                        brace_count += 1
                    elif source_text[idx] == "}":
                        brace_count -= 1
                    idx += 1
                end_pos = idx
            else:
                end_pos = m.end()

            end_line = source_text[:end_pos].count("\n") + 1
            full_range = SourceRange(start_pos, end_pos, start_line, end_line)
            body_range = SourceRange(m.end() - 1, end_pos, source_text[: m.end()].count("\n") + 1, end_line) if has_brace else None

            qualified_name = f"{package_name}.{c_name}" if package_name else c_name
            symbol_key = build_symbol_key("kotlin", path, package_name, c_name, line=start_line)

            docstring = extract_kdoc(start_pos)
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

        for m in fun_regex.finditer(source_text):
            sig = m.group(1).strip()
            receiver_type = m.group(2)
            f_name = m.group(3)
            params = m.group(4).strip()
            body_opener = m.group(6)  # "{" or "="
            start_pos = m.start()
            start_line = source_text[:start_pos].count("\n") + 1

            if body_opener == "{":
                brace_count = 1
                idx = m.end()
                while idx < len(source_text) and brace_count > 0:
                    if source_text[idx] == "{":
                        brace_count += 1
                    elif source_text[idx] == "}":
                        brace_count -= 1
                    idx += 1
                end_pos = idx
                body_start = m.end() - 1
            else:
                # Expression body (= ...)
                # Read until next statement or newline with lower indent
                line_end = source_text.find("\n", m.end())
                end_pos = line_end if line_end != -1 else len(source_text)
                body_start = m.end() - 1

            end_line = source_text[:end_pos].count("\n") + 1
            full_range = SourceRange(start_pos, end_pos, start_line, end_line)
            body_range = SourceRange(body_start, end_pos, source_text[:body_start].count("\n") + 1, end_line)

            owner = receiver_type or current_class
            qualified_name = f"{owner}.{f_name}" if owner else f_name
            symbol_key = build_symbol_key(
                "kotlin", path, owner or package_name, f_name, signature_params=params, line=start_line
            )

            docstring = extract_kdoc(start_pos)
            symbols.append(
                ParsedSymbol(
                    name=f_name,
                    qualified_name=qualified_name,
                    kind=SymbolKind.METHOD.value if owner else SymbolKind.FUNCTION.value,
                    signature=sig,
                    docstring=docstring,
                    full_range=full_range,
                    body_range=body_range,
                    parent_key=current_class_key if not receiver_type else None,
                    symbol_key=symbol_key,
                )
            )

        # Match calls
        call_regex = re.compile(r"(?:([A-Za-z0-9_]+)\.)?([A-Za-z0-9_]+)\s*\(")
        for m in call_regex.finditer(source_text):
            receiver = m.group(1)
            call_name = m.group(2)
            if call_name in ("if", "while", "for", "when", "catch", "fun", "class", "val", "var"):
                continue
            c_pos = m.start()
            c_line = source_text[:c_pos].count("\n") + 1

            enc_key = None
            for s in symbols:
                if s.full_range.start_line <= c_line <= s.full_range.end_line and s.kind in (
                    SymbolKind.METHOD.value,
                    SymbolKind.FUNCTION.value,
                ):
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
        functions = [
            s for s in parsed.symbols
            if s.kind in (SymbolKind.FUNCTION.value, SymbolKind.METHOD.value) and s.body_range
        ]
        functions.sort(key=lambda s: s.body_range.start_byte, reverse=True)

        result = list(source_text)
        for f in functions:
            assert f.body_range is not None
            sb = f.body_range.start_byte
            eb = f.body_range.end_byte
            replacement = "{\n        // … implementation omitted …\n    }"
            result[sb:eb] = list(replacement)

        return "".join(result)
