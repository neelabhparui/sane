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


def _parse_kotlin_supertypes(raw: str) -> list[tuple[str, str]]:
    """Splits Kotlin supertypes by comma, returning list of (spelling, role)."""
    items: list[str] = []
    current: list[str] = []
    p_depth = 0
    a_depth = 0
    for ch in raw:
        if ch == "(":
            p_depth += 1
            current.append(ch)
        elif ch == ")":
            p_depth = max(0, p_depth - 1)
            current.append(ch)
        elif ch == "<":
            a_depth += 1
            current.append(ch)
        elif ch == ">":
            a_depth = max(0, a_depth - 1)
            current.append(ch)
        elif ch == "," and p_depth == 0 and a_depth == 0:
            items.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        items.append("".join(current).strip())

    results: list[tuple[str, str]] = []
    for item in items:
        if not item:
            continue
        had_parens = "(" in item
        # Remove delegate: "Foo by bar" -> "Foo"
        clean = re.sub(r"\s+by\s+.*$", "", item)
        # Remove constructor call parens: "RenderView(context)" -> "RenderView"
        clean = re.sub(r"\(.*?\)", "", clean)
        # Remove type arguments: "List<String>" -> "List"
        clean = re.sub(r"<.*?>", "", clean).strip()
        # Extract simple identifier name (in case of package prefix or whitespace)
        match = re.search(r"([A-Za-z0-9_]+)$", clean)
        if match:
            spelling = match.group(1)
            if spelling not in ("Any", "Unit", "Nothing"):
                role = "extends" if had_parens else "implements"
                results.append((spelling, role))
    return results


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

        # Regex for matching Kotlin class/interface/object header
        class_head_regex = re.compile(
            r"((?:@\w+(?:\([^)]*\))?\s+)*(?:(?:public|protected|private|internal|open|abstract|sealed|data|value|inner|annotation)\s+)*(class|interface|object|companion\s+object|enum\s+class|annotation\s+class)\s+([A-Za-z0-9_]+)?(?:<[^>]+>)?)",
            re.MULTILINE,
        )

        fun_regex = re.compile(
            r"(?:@\w+(?:\([^)]*\))?\s+)*(?:public|protected|private|internal|override|suspend|inline|open|abstract)?\s*fun\s+(?:<[^>]+>\s+)?(?:([A-Za-z0-9_]+)\.)?([A-Za-z0-9_]+)\s*\(",
            re.MULTILINE,
        )
        fun_tail_regex = re.compile(
            r"\s*(?::\s*([A-Za-z0-9_<>, \?\.\/\[\]]+))?\s*(\{|=\s*)"
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

        class_symbols: list[ParsedSymbol] = []

        for m in class_head_regex.finditer(source_text):
            c_kind = m.group(2).strip()
            c_name = m.group(3)
            if not c_name:
                if "companion" in c_kind:
                    c_name = "Companion"
                else:
                    continue

            start_pos = m.start()
            start_line = source_text[:start_pos].count("\n") + 1

            idx = m.end()

            # Skip whitespace
            while idx < len(source_text) and source_text[idx].isspace():
                idx += 1

            # Check for primary constructor: optional 'constructor' keyword then (...)
            if source_text[idx:].startswith("constructor"):
                idx += len("constructor")
                while idx < len(source_text) and source_text[idx].isspace():
                    idx += 1

            if idx < len(source_text) and source_text[idx] == "(":
                paren_count = 1
                idx += 1
                while idx < len(source_text) and paren_count > 0:
                    if source_text[idx] == "(":
                        paren_count += 1
                    elif source_text[idx] == ")":
                        paren_count -= 1
                    idx += 1

            # Skip whitespace
            while idx < len(source_text) and source_text[idx].isspace():
                idx += 1

            # Check for supertypes: ':'
            supertypes_raw = ""
            if idx < len(source_text) and source_text[idx] == ":":
                supertypes_start = idx + 1
                idx = supertypes_start
                p_depth = 0
                a_depth = 0
                while idx < len(source_text):
                    ch = source_text[idx]
                    if ch == "(":
                        p_depth += 1
                    elif ch == ")":
                        p_depth = max(0, p_depth - 1)
                    elif ch == "<":
                        a_depth += 1
                    elif ch == ">":
                        a_depth = max(0, a_depth - 1)
                    elif ch == "{" and p_depth == 0 and a_depth == 0:
                        break
                    elif ch == "\n" and p_depth == 0 and a_depth == 0:
                        rest = source_text[idx + 1:].lstrip()
                        if not rest:
                            break
                        if rest[0] in ("{", ","):
                            idx += 1
                            continue
                        if re.match(r"(class|interface|object|fun|val|var|override|private|public|internal)\b", rest):
                            break
                    idx += 1
                supertypes_raw = source_text[supertypes_start:idx].strip()

            header_end = idx
            while idx < len(source_text) and source_text[idx].isspace():
                idx += 1

            has_brace = idx < len(source_text) and source_text[idx] == "{"
            if has_brace:
                brace_count = 1
                idx += 1
                while idx < len(source_text) and brace_count > 0:
                    if source_text[idx] == "{":
                        brace_count += 1
                    elif source_text[idx] == "}":
                        brace_count -= 1
                    idx += 1
                end_pos = idx
            else:
                end_pos = header_end

            end_line = source_text[:end_pos].count("\n") + 1
            full_range = SourceRange(start_pos, end_pos, start_line, end_line)
            body_range = SourceRange(header_end, end_pos, source_text[:header_end].count("\n") + 1, end_line) if has_brace else None

            qualified_name = f"{package_name}.{c_name}" if package_name else c_name
            symbol_key = build_symbol_key("kotlin", path, package_name, c_name, line=start_line)
            sig = source_text[start_pos:header_end].strip()

            docstring = extract_kdoc(start_pos)
            class_symbol = ParsedSymbol(
                name=c_name,
                qualified_name=qualified_name,
                kind=c_kind,
                signature=sig,
                docstring=docstring,
                full_range=full_range,
                body_range=body_range,
                symbol_key=symbol_key,
            )
            symbols.append(class_symbol)
            class_symbols.append(class_symbol)

            # Extract supertypes as references
            if supertypes_raw:
                for super_name, role in _parse_kotlin_supertypes(supertypes_raw):
                    references.append(
                        ParsedReference(
                            spelling=super_name,
                            role=role,
                            source_range=full_range,
                            enclosing_symbol_key=symbol_key,
                        )
                    )

        for m in fun_regex.finditer(source_text):
            receiver_type = m.group(1)
            f_name = m.group(2)
            params_open_pos = m.end() - 1

            paren_count = 1
            idx = params_open_pos + 1
            while idx < len(source_text) and paren_count > 0:
                if source_text[idx] == "(":
                    paren_count += 1
                elif source_text[idx] == ")":
                    paren_count -= 1
                idx += 1
            if paren_count != 0:
                continue
            params_close_pos = idx
            params = source_text[params_open_pos + 1 : params_close_pos - 1].strip()

            tail_match = fun_tail_regex.match(source_text, params_close_pos)
            if not tail_match:
                continue
            body_opener = tail_match.group(2).strip()

            start_pos = m.start()
            start_line = source_text[:start_pos].count("\n") + 1
            sig = source_text[start_pos : tail_match.end() - (1 if body_opener == "{" else 0)].strip()

            header_end = tail_match.end()
            if body_opener == "{":
                brace_count = 1
                idx = header_end
                while idx < len(source_text) and brace_count > 0:
                    if source_text[idx] == "{":
                        brace_count += 1
                    elif source_text[idx] == "}":
                        brace_count -= 1
                    idx += 1
                end_pos = idx
                body_start = header_end - 1
            else:
                line_end = source_text.find("\n", header_end)
                end_pos = line_end if line_end != -1 else len(source_text)
                body_start = header_end - 1

            end_line = source_text[:end_pos].count("\n") + 1
            full_range = SourceRange(start_pos, end_pos, start_line, end_line)
            body_range = SourceRange(body_start, end_pos, source_text[:body_start].count("\n") + 1, end_line)

            enclosing_class = None
            for cs in class_symbols:
                if cs.full_range.start_line <= start_line <= cs.full_range.end_line:
                    if enclosing_class is None or (
                        cs.full_range.end_line - cs.full_range.start_line
                        < enclosing_class.full_range.end_line - enclosing_class.full_range.start_line
                    ):
                        enclosing_class = cs

            owner = receiver_type or (enclosing_class.name if enclosing_class else None)
            owner_key = enclosing_class.symbol_key if enclosing_class and not receiver_type else None
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
                    parent_key=owner_key,
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
