from __future__ import annotations

import re
from typing import Any, Optional

from sane_nav.core.ids import normalize_identifier_tokens
from sane_nav.storage.database import Database


class LexicalRetriever:
    def __init__(self, db: Database):
        self.db = db

    def search_exact(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        rows = self.db.get_symbol_by_id_or_name(query)
        results = []
        for r in rows[:limit]:
            results.append({
                "entity_type": "symbol",
                "entity_id": r["id"],
                "symbol_key": r["symbol_key"],
                "name": r["name"],
                "qualified_name": r["qualified_name"],
                "kind": r["kind"],
                "signature": r["signature"],
                "docstring": r["docstring"],
                "file_path": r["file_path"],
                "start_line": r["start_line"],
                "end_line": r["end_line"],
                "match_reason": "exact_name",
                "score": 1.0,
            })
        return results

    def search_fts(self, query: str, path_prefix: Optional[str] = None, limit: int = 15) -> list[dict[str, Any]]:
        # Normalize and prepare FTS query string
        tokens = normalize_identifier_tokens(query)
        if not tokens:
            tokens = [re.sub(r"[^\w]", "", query)]

        # SQLite FTS5 query: prefix tokens e.g. "rotate* OR refresh*"
        fts_query = " OR ".join(f'"{t}"*' for t in tokens if t)
        if not fts_query:
            fts_query = query

        with self.db.get_connection() as conn:
            try:
                sql = """
                SELECT sd.entity_type, sd.entity_id, sd.title, sd.path, sd.body,
                       rank
                FROM search_fts
                JOIN search_documents sd ON search_fts.rowid = sd.id
                WHERE search_fts MATCH ?
                """
                params: list[Any] = [fts_query]
                if path_prefix:
                    sql += " AND sd.path LIKE ?"
                    params.append(f"{path_prefix}%")

                sql += " ORDER BY rank LIMIT ?"
                params.append(limit)

                cursor = conn.execute(sql, params)
                rows = cursor.fetchall()
            except Exception:
                # Fallback to simple LIKE if FTS expression has syntax quirks
                like_pat = f"%{query}%"
                cursor = conn.execute(
                    """
                    SELECT entity_type, entity_id, title, path, body, 1.0 as rank
                    FROM search_documents
                    WHERE title LIKE ? OR body LIKE ? OR path LIKE ?
                    LIMIT ?
                    """,
                    (like_pat, like_pat, like_pat, limit),
                )
                rows = cursor.fetchall()

            results = []
            for r in rows:
                item: dict[str, Any] = {
                    "entity_type": r["entity_type"],
                    "entity_id": r["entity_id"],
                    "title": r["title"],
                    "file_path": r["path"],
                    "body": r["body"],
                    "rank": r["rank"],
                    "match_reason": "fts_text",
                }

                # If symbol, populate symbol metadata
                if r["entity_type"] == "symbol":
                    srow = conn.execute(
                        "SELECT * FROM symbols WHERE id = ?", (r["entity_id"],)
                    ).fetchone()
                    if srow:
                        item.update({
                            "symbol_key": srow["symbol_key"],
                            "name": srow["name"],
                            "qualified_name": srow["qualified_name"],
                            "kind": srow["kind"],
                            "signature": srow["signature"],
                            "docstring": srow["docstring"],
                            "start_line": srow["start_line"],
                            "end_line": srow["end_line"],
                        })
                elif r["entity_type"] == "doc":
                    drow = conn.execute(
                        "SELECT * FROM docs WHERE id = ?", (r["entity_id"],)
                    ).fetchone()
                    if drow:
                        item.update({
                            "heading": drow["heading"],
                            "heading_path": drow["heading_path"],
                            "start_line": drow["start_line"],
                            "end_line": drow["end_line"],
                        })

                results.append(item)

            return results
