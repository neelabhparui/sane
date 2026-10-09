from __future__ import annotations

import re
from typing import Optional
from sane_nav.rendering.budget import BudgetManager
from sane_nav.retrieval.lexical import LexicalRetriever
from sane_nav.storage.database import Database


class ContextStitcher:
    def __init__(self, db: Database, lexical: LexicalRetriever):
        self.db = db
        self.lexical = lexical

    def get_feature_context(
        self,
        feature: str,
        path_prefix: Optional[str] = None,
        max_chars: int = 10000,
    ) -> str:
        budget = BudgetManager.create(max_chars=max_chars)
        output_sections: list[str] = []

        # 1. Search for documentation sections
        doc_matches = self.lexical.search_fts(feature, path_prefix=path_prefix, limit=3)
        relevant_docs = [d for d in doc_matches if d.get("entity_type") == "doc"]

        # 2. Search for symbols matching feature
        symbol_matches = self.lexical.search_fts(feature, path_prefix=path_prefix, limit=5)
        relevant_symbols = [s for s in symbol_matches if s.get("entity_type") == "symbol"]

        # Extract mentions of code symbols from doc bodies
        doc_text_combined = " ".join(d.get("body", "") for d in relevant_docs)
        potential_mentions = set(re.findall(r"\b([A-Z][a-zA-Z0-9_]+)\b", doc_text_combined))

        with self.db.get_connection() as conn:
            for mention in potential_mentions:
                rows = conn.execute(
                    "SELECT s.*, f.path as file_path FROM symbols s JOIN files f ON s.file_id = f.id WHERE s.name = ?",
                    (mention,),
                ).fetchall()
                for r in rows:
                    if not any(s.get("symbol_key") == r["symbol_key"] for s in relevant_symbols):
                        relevant_symbols.append({
                            "entity_type": "symbol",
                            "symbol_key": r["symbol_key"],
                            "name": r["name"],
                            "qualified_name": r["qualified_name"],
                            "kind": r["kind"],
                            "signature": r["signature"],
                            "docstring": r["docstring"],
                            "file_path": r["file_path"],
                            "start_line": r["start_line"],
                            "end_line": r["end_line"],
                            "match_reason": "doc_mention",
                        })

        # Assemble [Documentation] block
        if relevant_docs:
            doc_lines = ["[Documentation]"]
            for d in relevant_docs:
                doc_lines.append(f"--- {d['file_path']} > {d.get('heading_path', d.get('title'))} (L{d.get('start_line', 1)}-L{d.get('end_line', 1)}) ---")
                doc_lines.append(d.get("body", "").strip())
                doc_lines.append("")
            output_sections.append("\n".join(doc_lines))

        # Assemble [Core Symbols & Signatures] block
        if relevant_symbols:
            sym_lines = ["[Core symbols & signatures]"]
            for s in relevant_symbols[:6]:
                sym_lines.append(
                    f"* {s.get('qualified_name', s.get('name'))} [{s.get('kind')}] at {s.get('file_path')}:{s.get('start_line')}"
                )
                sig = s.get("signature")
                if sig:
                    sym_lines.append(f"  {sig}")
                doc = s.get("docstring")
                if doc:
                    first_doc = doc.strip().split("\n")[0]
                    sym_lines.append(f"  // Doc: {first_doc}")
                sym_lines.append("")
            output_sections.append("\n".join(sym_lines))

        if not output_sections:
            return f"No specific documentation or symbols found for feature '{feature}'."

        full_context = "\n\n".join(output_sections)
        return budget.add(full_context)
