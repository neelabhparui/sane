from __future__ import annotations

from typing import Optional

from sane_nav.core.models import ResolutionKind
from sane_nav.storage.database import Database


class SymbolResolver:
    def __init__(self, db: Database):
        self.db = db

    def resolve_all_occurrences(self) -> int:
        """Iterates over unresolved occurrences and resolves targets with confidence scores and edges."""
        resolved_count = 0
        with self.db.get_connection() as conn:
            # Fetch occurrences
            cur = conn.execute(
                """
                SELECT o.id, o.file_id, o.enclosing_symbol_id, o.spelling, o.receiver_text, o.role,
                       f.path as file_path
                FROM occurrences o
                JOIN files f ON o.file_id = f.id
                WHERE o.resolution_kind = 'unresolved' OR o.target_symbol_id IS NULL
                """
            )
            occurrences = cur.fetchall()

            for occ in occurrences:
                occ_id = occ["id"]
                spelling = occ["spelling"]
                receiver = occ["receiver_text"]
                role = occ["role"] or "call"
                file_id = occ["file_id"]
                enclosing_id = occ["enclosing_symbol_id"]

                # 1. Look for same-file candidate
                same_file_matches = conn.execute(
                    "SELECT id, symbol_key, qualified_name FROM symbols WHERE file_id = ? AND name = ?",
                    (file_id, spelling),
                ).fetchall()

                target_id: Optional[int] = None
                res_kind = ResolutionKind.UNRESOLVED.value
                confidence = 0.0

                if len(same_file_matches) == 1:
                    target_id = same_file_matches[0]["id"]
                    res_kind = ResolutionKind.CLASS_SCOPED.value
                    confidence = 0.95
                elif receiver:
                    # Look for receiver type or class
                    rec_matches = conn.execute(
                        """
                        SELECT id, symbol_key FROM symbols
                        WHERE (qualified_name LIKE ? OR symbol_key LIKE ?) AND name = ?
                        """,
                        (f"%{receiver}%", f"%{receiver}%", spelling),
                    ).fetchall()
                    if len(rec_matches) == 1:
                        target_id = rec_matches[0]["id"]
                        res_kind = ResolutionKind.IMPORT_SCOPED.value
                        confidence = 0.90

                if not target_id:
                    # Global repository candidate match
                    global_matches = conn.execute(
                        "SELECT id, symbol_key FROM symbols WHERE name = ?",
                        (spelling,),
                    ).fetchall()
                    if len(global_matches) == 1:
                        target_id = global_matches[0]["id"]
                        res_kind = ResolutionKind.PROBABLE.value
                        confidence = 0.80
                    elif len(global_matches) > 1:
                        # Ambiguous match
                        target_id = global_matches[0]["id"]
                        res_kind = ResolutionKind.AMBIGUOUS.value
                        confidence = 0.45

                if target_id:
                    conn.execute(
                        """
                        UPDATE occurrences
                        SET target_symbol_id = ?, resolution_kind = ?, confidence = ?
                        WHERE id = ?
                        """,
                        (target_id, res_kind, confidence, occ_id),
                    )

                    # Create edge if enclosing symbol is known
                    if enclosing_id:
                        edge_kind = role if role in ("implements", "extends") else "calls"
                        conn.execute(
                            """
                            INSERT OR REPLACE INTO edges (
                                source_symbol_id, target_symbol_id, occurrence_id,
                                kind, resolution_kind, confidence
                            ) VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (enclosing_id, target_id, occ_id, edge_kind, res_kind, confidence),
                        )
                    resolved_count += 1

            conn.commit()

        return resolved_count
