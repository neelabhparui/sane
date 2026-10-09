"""SQLite database management with WAL mode and FTS5 search.

Provides transactional persistence for repository metadata, code symbols,
syntactic occurrences, resolved edges, and hierarchical documentation sections.
"""

from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

from sane_nav.core.models import ParsedFile


class Database:
    """Manages transactional SQLite storage for S.A.N.E. index data."""

    def __init__(self, db_path: Path):
        """Initializes database path and applies schema migrations."""
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        """Creates a new SQLite connection configured with WAL and foreign keys."""
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    def _init_db(self) -> None:
        """Executes schema.sql and records schema version metadata."""
        schema_path = Path(__file__).parent / "schema.sql"
        schema_sql = schema_path.read_text(encoding="utf-8")
        with self.get_connection() as conn:
            conn.executescript(schema_sql)
            conn.execute(
                "INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('version', '1.0.0')"
            )
            conn.commit()

    def delete_file_index(self, conn: sqlite3.Connection, file_path: str) -> None:
        """Deletes file record and cascades to symbols, occurrences, edges, docs.

        Args:
            conn: Active SQLite connection inside a transaction.
            file_path: Repository-relative posix path of the file to delete.
        """
        cursor = conn.execute("SELECT id FROM files WHERE path = ?", (file_path,))
        row = cursor.fetchone()
        if row:
            file_id = row["id"]
            sym_ids = [r["id"] for r in conn.execute("SELECT id FROM symbols WHERE file_id = ?", (file_id,))]
            doc_ids = [r["id"] for r in conn.execute("SELECT id FROM docs WHERE file_id = ?", (file_id,))]
            occ_ids = [r["id"] for r in conn.execute("SELECT id FROM occurrences WHERE file_id = ?", (file_id,))]

            if sym_ids:
                placeholders = ",".join("?" for _ in sym_ids)
                conn.execute(
                    f"DELETE FROM search_documents WHERE entity_type = 'symbol' AND entity_id IN ({placeholders})",
                    sym_ids,
                )
            if doc_ids:
                placeholders = ",".join("?" for _ in doc_ids)
                conn.execute(
                    f"DELETE FROM search_documents WHERE entity_type = 'doc' AND entity_id IN ({placeholders})",
                    doc_ids,
                )
            if occ_ids:
                placeholders = ",".join("?" for _ in occ_ids)
                conn.execute(
                    f"DELETE FROM search_documents WHERE entity_type = 'occurrence' AND entity_id IN ({placeholders})",
                    occ_ids,
                )

            conn.execute("DELETE FROM files WHERE id = ?", (file_id,))

    def upsert_file_index(
        self,
        file_path: str,
        language: str,
        content_hash: str,
        size_bytes: int,
        mtime_ns: int,
        parsed: ParsedFile,
    ) -> int:
        """Atomically updates a file's index data, symbols, occurrences, docs, and search documents.

        Args:
            file_path: Repository-relative file path.
            language: Language identifier ('python', 'java', 'kotlin', 'markdown').
            content_hash: SHA-256 hex digest of file bytes.
            size_bytes: File size in bytes.
            mtime_ns: Nanosecond timestamp of file last modification.
            parsed: ParsedFile intermediate representation.

        Returns:
            The integer primary key `id` of the newly created file record.
        """
        with self.get_connection() as conn:
            now_ns = int(time.time_ns())
            self.delete_file_index(conn, file_path)

            cur = conn.execute(
                """
                INSERT INTO files (path, language, content_hash, mtime_ns, size_bytes, indexed_at_ns, parse_error_count)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (file_path, language, content_hash, mtime_ns, size_bytes, now_ns, parsed.parse_error_count),
            )
            file_id = cur.lastrowid

            # Insert symbols
            symbol_key_to_id: dict[str, int] = {}
            for sym in parsed.symbols:
                parent_id = symbol_key_to_id.get(sym.parent_key) if sym.parent_key else None
                s_cur = conn.execute(
                    """
                    INSERT INTO symbols (\n                        file_id, parent_symbol_id, symbol_key, qualified_name, name, kind, visibility,
                        signature, docstring, start_byte, end_byte, start_line, end_line,
                        signature_start_byte, signature_end_byte, body_start_byte, body_end_byte
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        file_id,
                        parent_id,
                        sym.symbol_key or sym.name,
                        sym.qualified_name,
                        sym.name,
                        sym.kind,
                        sym.visibility or "public",
                        sym.signature,
                        sym.docstring,
                        sym.full_range.start_byte,
                        sym.full_range.end_byte,
                        sym.full_range.start_line,
                        sym.full_range.end_line,
                        sym.full_range.start_byte,
                        sym.body_range.start_byte if sym.body_range else sym.full_range.end_byte,
                        sym.body_range.start_byte if sym.body_range else None,
                        sym.body_range.end_byte if sym.body_range else None,
                    ),
                )
                sym_id = s_cur.lastrowid
                if sym.symbol_key:
                    symbol_key_to_id[sym.symbol_key] = sym_id
                symbol_key_to_id[sym.name] = sym_id

                # Index in search_documents
                body_text = f"{sym.signature}\n{sym.docstring or ''}"
                sdoc_cur = conn.execute(
                    """
                    INSERT INTO search_documents (entity_type, entity_id, title, path, body)
                    VALUES ('symbol', ?, ?, ?, ?)
                    """,
                    (sym_id, sym.qualified_name or sym.name, file_path, body_text),
                )
                doc_rowid = sdoc_cur.lastrowid
                conn.execute(
                    "INSERT INTO search_fts (rowid, title, path, body) VALUES (?, ?, ?, ?)",
                    (doc_rowid, sym.qualified_name or sym.name, file_path, body_text),
                )

            # Insert occurrences
            for ref in parsed.references:
                enc_id = symbol_key_to_id.get(ref.enclosing_symbol_key) if ref.enclosing_symbol_key else None
                o_cur = conn.execute(
                    """
                    INSERT INTO occurrences (
                        file_id, enclosing_symbol_id, spelling, role, start_byte, end_byte,
                        start_line, end_line, receiver_text, resolution_kind
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'unresolved')
                    """,
                    (
                        file_id,
                        enc_id,
                        ref.spelling,
                        ref.role,
                        ref.source_range.start_byte,
                        ref.source_range.end_byte,
                        ref.source_range.start_line,
                        ref.source_range.end_line,
                        ref.receiver_text,
                    ),
                )
                occ_id = o_cur.lastrowid

                # Index call-site spelling in search_documents so lexical search can
                # find usages, not just declarations (signature/docstring).
                occ_body = ref.receiver_text or ""
                sdoc_cur = conn.execute(
                    """
                    INSERT INTO search_documents (entity_type, entity_id, title, path, body)
                    VALUES ('occurrence', ?, ?, ?, ?)
                    """,
                    (occ_id, ref.spelling, file_path, occ_body),
                )
                doc_rowid = sdoc_cur.lastrowid
                conn.execute(
                    "INSERT INTO search_fts (rowid, title, path, body) VALUES (?, ?, ?, ?)",
                    (doc_rowid, ref.spelling, file_path, occ_body),
                )

            # Insert documentation sections
            heading_path_to_id: dict[str, int] = {}
            for doc in parsed.docs:
                parent_path = " > ".join(doc.heading_path[:-1]) if len(doc.heading_path) > 1 else ""
                parent_id = heading_path_to_id.get(parent_path)
                curr_path = " > ".join(doc.heading_path)

                d_cur = conn.execute(
                    """
                    INSERT INTO docs (
                        file_id, parent_id, heading_level, heading, heading_path, content,
                        start_byte, end_byte, start_line, end_line
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        file_id,
                        parent_id,
                        doc.level,
                        doc.heading,
                        curr_path,
                        doc.content,
                        doc.source_range.start_byte,
                        doc.source_range.end_byte,
                        doc.source_range.start_line,
                        doc.source_range.end_line,
                    ),
                )
                doc_id = d_cur.lastrowid
                heading_path_to_id[curr_path] = doc_id

                # Index in search_documents
                sdoc_cur = conn.execute(
                    """
                    INSERT INTO search_documents (entity_type, entity_id, title, path, body)
                    VALUES ('doc', ?, ?, ?, ?)
                    """,
                    (doc_id, f"{doc.heading} ({curr_path})", file_path, doc.content),
                )
                doc_rowid = sdoc_cur.lastrowid
                conn.execute(
                    "INSERT INTO search_fts (rowid, title, path, body) VALUES (?, ?, ?, ?)",
                    (doc_rowid, f"{doc.heading} ({curr_path})", file_path, doc.content),
                )

            conn.commit()
            return file_id

    def get_file(self, file_path: str) -> Optional[sqlite3.Row]:
        """Fetches file metadata row by relative path."""
        with self.get_connection() as conn:
            cur = conn.execute("SELECT * FROM files WHERE path = ?", (file_path,))
            return cur.fetchone()

    def search_files_by_name(self, term: str, limit: int = 10) -> list[sqlite3.Row]:
        """Finds indexed files whose path contains the given term (filename glob-style lookup)."""
        with self.get_connection() as conn:
            like_pat = f"%{term}%"
            cur = conn.execute(
                "SELECT * FROM files WHERE path LIKE ? ORDER BY length(path) ASC LIMIT ?",
                (like_pat, limit),
            )
            return cur.fetchall()

    def list_files(self) -> list[sqlite3.Row]:
        """Lists all indexed files in alphabetical order."""
        with self.get_connection() as conn:
            cur = conn.execute("SELECT * FROM files ORDER BY path ASC")
            return cur.fetchall()

    def get_symbol_by_id_or_name(self, query: str) -> list[sqlite3.Row]:
        """Searches symbols by symbol key, qualified name, or short name.

        Tolerates a trailing parameter list (e.g. "Foo.bar(String, int)") and
        a trailing "@L<line>" location suffix by stripping both before
        matching, since a guessed symbol_id's line anchor is often stale by
        the time it's reused. Falls back to a short-name fuzzy match so
        callers get candidates instead of a silent not-found when the
        guessed signature/location doesn't line up with the indexed
        representation.
        """
        normalized = re.sub(r"\([^)]*\)\s*$", "", query).strip()
        normalized = re.sub(r"@L\d+\s*$", "", normalized).strip()

        with self.get_connection() as conn:
            # 1. Exact symbol_key match
            cur = conn.execute(
                "SELECT s.*, f.path as file_path FROM symbols s JOIN files f ON s.file_id = f.id WHERE s.symbol_key = ?",
                (normalized,),
            )
            rows = cur.fetchall()
            if rows:
                return rows

            # 2. Exact qualified_name match
            cur = conn.execute(
                "SELECT s.*, f.path as file_path FROM symbols s JOIN files f ON s.file_id = f.id WHERE s.qualified_name = ?",
                (normalized,),
            )
            rows = cur.fetchall()
            if rows:
                return rows

            # 3. Exact short name match
            cur = conn.execute(
                "SELECT s.*, f.path as file_path FROM symbols s JOIN files f ON s.file_id = f.id WHERE s.name = ?",
                (normalized,),
            )
            rows = cur.fetchall()
            if rows:
                return rows

            # 4. Suffix match (e.g. AuthService.validateToken)
            cur = conn.execute(
                """
                SELECT s.*, f.path as file_path FROM symbols s
                JOIN files f ON s.file_id = f.id
                WHERE s.qualified_name LIKE ? OR s.symbol_key LIKE ?
                """,
                (f"%{normalized}", f"%{normalized}%"),
            )
            rows = cur.fetchall()
            if rows:
                return rows

            # 5. Fuzzy fallback on bare short name (last dotted segment), so a
            # guessed full signature still surfaces candidates rather than
            # failing silently.
            bare_name = normalized.rsplit(".", 1)[-1]
            if bare_name and bare_name != normalized:
                cur = conn.execute(
                    "SELECT s.*, f.path as file_path FROM symbols s JOIN files f ON s.file_id = f.id WHERE s.name = ?",
                    (bare_name,),
                )
                rows = cur.fetchall()
                if rows:
                    return rows

            return []

    def get_file_symbols(self, file_path: str) -> list[sqlite3.Row]:
        """Fetches all symbols declared in a given file ordered by line."""
        with self.get_connection() as conn:
            cur = conn.execute(
                """
                SELECT s.*, f.path as file_path FROM symbols s
                JOIN files f ON s.file_id = f.id
                WHERE f.path = ?
                ORDER BY s.start_line ASC
                """,
                (file_path,),
            )
            return cur.fetchall()

    def get_implementations(self, query: str, transitive: bool = True) -> list[sqlite3.Row]:
        """Finds all direct and indirect implementers / subclasses of a symbol."""
        candidates = self.get_symbol_by_id_or_name(query)
        if not candidates:
            return []

        target_ids = [c["id"] for c in candidates]
        placeholders = ",".join("?" for _ in target_ids)

        with self.get_connection() as conn:
            sql = f"""
            WITH RECURSIVE subtype_graph(sym_id, depth) AS (
                -- Direct implementers / subclasses (depth 1)
                SELECT e.source_symbol_id, 1
                FROM edges e
                WHERE e.target_symbol_id IN ({placeholders}) AND e.kind IN ('implements', 'extends')
                UNION
                -- Transitive implementers / subclasses (depth + 1)
                SELECT e.source_symbol_id, g.depth + 1
                FROM edges e
                JOIN subtype_graph g ON e.target_symbol_id = g.sym_id
                WHERE e.kind IN ('implements', 'extends') AND ? = 1
            )
            SELECT DISTINCT
                s.id, s.symbol_key, s.name, s.qualified_name, s.kind, s.signature,
                s.start_line, s.end_line, f.path as file_path, g.depth
            FROM subtype_graph g
            JOIN symbols s ON g.sym_id = s.id
            JOIN files f ON s.file_id = f.id
            ORDER BY g.depth ASC, s.name ASC;
            """
            params = [*target_ids, 1 if transitive else 0]
            cur = conn.execute(sql, params)
            return cur.fetchall()

    def get_graph_proximity(
        self,
        seed_symbol_ids: list[int],
        max_depth: int = 3,
    ) -> dict[int, int]:
        """Computes shortest-path distance (in edge hops) from any seed symbol
        to every symbol reachable within max_depth, traversing the `edges`
        table (calls/implements/extends) in both directions.

        Used to rerank results by how close they are to a symbol/file the
        caller is already looking at, rather than by name match alone.

        Returns:
            Dict mapping symbol id -> minimum hop distance from any seed (0 for seeds themselves).
        """
        if not seed_symbol_ids:
            return {}

        with self.get_connection() as conn:
            seed_values = ",".join("(?)" for _ in seed_symbol_ids)
            sql = f"""
                WITH RECURSIVE seeds(sym_id) AS (
                    VALUES {seed_values}
                ),
                proximity(sym_id, depth) AS (
                    SELECT sym_id, 0 FROM seeds
                    UNION
                    SELECT
                        CASE WHEN e.source_symbol_id = p.sym_id THEN e.target_symbol_id ELSE e.source_symbol_id END,
                        p.depth + 1
                    FROM edges e
                    JOIN proximity p
                        ON e.source_symbol_id = p.sym_id OR e.target_symbol_id = p.sym_id
                    WHERE p.depth < ?
                )
                SELECT sym_id, MIN(depth) as depth FROM proximity GROUP BY sym_id
            """
            cur = conn.execute(sql, (*seed_symbol_ids, max_depth))
            return {row["sym_id"]: row["depth"] for row in cur.fetchall() if row["sym_id"] is not None}

    def get_stats(self) -> dict[str, Any]:
        """Returns health metrics, counts, and language distribution."""
        with self.get_connection() as conn:
            file_count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            symbol_count = conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
            doc_count = conn.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
            occ_count = conn.execute("SELECT COUNT(*) FROM occurrences").fetchone()[0]
            edge_count = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]

            lang_rows = conn.execute(
                "SELECT language, COUNT(*) as c FROM files WHERE language IS NOT NULL GROUP BY language"
            ).fetchall()
            languages = {r["language"]: r["c"] for r in lang_rows}

            return {
                "state": "ready" if file_count > 0 else "empty",
                "files": file_count,
                "symbols": symbol_count,
                "docs": doc_count,
                "occurrences": occ_count,
                "resolved_edges": edge_count,
                "languages": languages,
                "semantic_mode": "lexical-structural",
            }

    def get_upstream_callers(
        self,
        symbol_ids: int | list[int],
        max_depth: int = 2,
    ) -> list[sqlite3.Row]:
        """Finds all direct and transitive upstream callers of symbol(s) up to max_depth."""
        if isinstance(symbol_ids, int):
            target_ids = [symbol_ids]
        else:
            target_ids = list(symbol_ids)

        if not target_ids:
            return []

        depth_limit = max(1, min(max_depth, 4))
        placeholders = ",".join("?" for _ in target_ids)

        with self.get_connection() as conn:
            sql = f"""
            WITH RECURSIVE upstream_graph(caller_id, callee_id, depth) AS (
                -- Direct callers (depth 1)
                SELECT e.source_symbol_id, e.target_symbol_id, 1
                FROM edges e
                WHERE e.target_symbol_id IN ({placeholders}) AND e.kind = 'calls'
                UNION
                -- Transitive callers (depth + 1)
                SELECT e.source_symbol_id, e.target_symbol_id, g.depth + 1
                FROM edges e
                JOIN upstream_graph g ON e.target_symbol_id = g.caller_id
                WHERE e.kind = 'calls' AND g.depth < ?
            )
            SELECT
                s.id, s.symbol_key, s.name, s.qualified_name, s.kind, s.signature,
                s.docstring, s.start_line, s.end_line, f.path as file_path,
                MIN(g.depth) as depth, g.callee_id
            FROM upstream_graph g
            JOIN symbols s ON g.caller_id = s.id
            JOIN files f ON s.file_id = f.id
            GROUP BY s.id
            ORDER BY depth ASC, s.name ASC;
            """
            params = [*target_ids, depth_limit]
            cur = conn.execute(sql, params)
            return cur.fetchall()

    def get_downstream_callees(
        self,
        symbol_ids: int | list[int],
        max_depth: int = 1,
    ) -> list[sqlite3.Row]:
        """Finds all direct (and optionally transitive) downstream callees invoked by symbol(s)."""
        if isinstance(symbol_ids, int):
            source_ids = [symbol_ids]
        else:
            source_ids = list(symbol_ids)

        if not source_ids:
            return []

        depth_limit = max(1, min(max_depth, 4))
        placeholders = ",".join("?" for _ in source_ids)

        with self.get_connection() as conn:
            sql = f"""
            WITH RECURSIVE downstream_graph(caller_id, callee_id, depth) AS (
                -- Direct callees (depth 1)
                SELECT e.source_symbol_id, e.target_symbol_id, 1
                FROM edges e
                WHERE e.source_symbol_id IN ({placeholders})
                  AND e.target_symbol_id IS NOT NULL
                  AND e.kind = 'calls'
                UNION
                -- Transitive callees (depth + 1)
                SELECT e.source_symbol_id, e.target_symbol_id, g.depth + 1
                FROM edges e
                JOIN downstream_graph g ON e.source_symbol_id = g.callee_id
                WHERE e.target_symbol_id IS NOT NULL
                  AND e.kind = 'calls'
                  AND g.depth < ?
            )
            SELECT
                s.id, s.symbol_key, s.name, s.qualified_name, s.kind, s.signature,
                s.docstring, s.start_line, s.end_line, f.path as file_path,
                MIN(g.depth) as depth, g.caller_id
            FROM downstream_graph g
            JOIN symbols s ON g.callee_id = s.id
            JOIN files f ON s.file_id = f.id
            GROUP BY s.id
            ORDER BY depth ASC, s.name ASC;
            """
            params = [*source_ids, depth_limit]
            cur = conn.execute(sql, params)
            return cur.fetchall()

    def get_affected_tests(
        self,
        symbol_ids: int | list[int],
    ) -> list[sqlite3.Row]:
        """Finds test suite references and occurrences affected by target symbol(s)."""
        if isinstance(symbol_ids, int):
            target_ids = [symbol_ids]
        else:
            target_ids = list(symbol_ids)

        if not target_ids:
            return []

        placeholders = ",".join("?" for _ in target_ids)

        with self.get_connection() as conn:
            sql = f"""
            SELECT DISTINCT
                f.path as file_path,
                o.start_line,
                o.end_line,
                o.spelling,
                o.role,
                o.confidence,
                o.resolution_kind,
                s_target.id as target_symbol_id,
                s_target.name as target_symbol_name,
                s_target.symbol_key as target_symbol_key,
                s_enc.id as enclosing_symbol_id,
                s_enc.name as test_suite_or_method,
                s_enc.kind as enclosing_kind
            FROM occurrences o
            JOIN files f ON o.file_id = f.id
            LEFT JOIN symbols s_target ON o.target_symbol_id = s_target.id
            LEFT JOIN symbols s_enc ON o.enclosing_symbol_id = s_enc.id
            WHERE (
                o.target_symbol_id IN ({placeholders})
                OR (
                    o.target_symbol_id IS NULL
                    AND o.spelling IN (
                        SELECT name FROM symbols WHERE id IN ({placeholders})
                    )
                )
            )
            AND (
                f.path LIKE '%/tests/%'
                OR f.path LIKE '%/test/%'
                OR f.path LIKE 'tests/%'
                OR f.path LIKE 'test/%'
                OR f.path LIKE '%Test.%'
                OR f.path LIKE '%Tests.%'
                OR f.path LIKE '%Spec.%'
                OR f.path LIKE '%_test.%'
                OR f.path LIKE '%test_%'
            )
            ORDER BY f.path ASC, o.start_line ASC;
            """
            params = [*target_ids, *target_ids]
            cur = conn.execute(sql, params)
            return cur.fetchall()

    def get_file_dependents(self, file_path: str) -> list[str]:
        """Finds all indexed files that call or reference symbols declared in file_path."""
        with self.get_connection() as conn:
            sql = """
            SELECT DISTINCT f_caller.path
            FROM edges e
            JOIN symbols s_target ON e.target_symbol_id = s_target.id
            JOIN files f_target ON s_target.file_id = f_target.id
            JOIN symbols s_caller ON e.source_symbol_id = s_caller.id
            JOIN files f_caller ON s_caller.file_id = f_caller.id
            WHERE f_target.path = ? AND f_caller.path != ?
            UNION
            SELECT DISTINCT f_occ.path
            FROM occurrences o
            JOIN symbols s_target ON o.target_symbol_id = s_target.id
            JOIN files f_target ON s_target.file_id = f_target.id
            JOIN files f_occ ON o.file_id = f_occ.id
            WHERE f_target.path = ? AND f_occ.path != ?
            ORDER BY 1 ASC;
            """
            cur = conn.execute(sql, (file_path, file_path, file_path, file_path))
            return [row["path"] for row in cur.fetchall()]

    def get_linked_docs(
        self,
        symbol_names: list[str],
        file_path: Optional[str] = None,
        limit: int = 5,
    ) -> list[sqlite3.Row]:
        """Finds markdown documentation sections matching symbol names or file path."""
        if not symbol_names and not file_path:
            return []

        conditions: list[str] = []
        params: list[Any] = []

        for name in symbol_names:
            if not name:
                continue
            conditions.append("d.heading LIKE ? OR d.content LIKE ?")
            params.extend([f"%{name}%", f"%{name}%"])

        if file_path:
            stem = Path(file_path).stem
            conditions.append("d.heading LIKE ? OR d.content LIKE ?")
            params.extend([f"%{stem}%", f"%{file_path}%"])

        if not conditions:
            return []

        where_clause = " OR ".join(conditions)
        sql = f"""
        SELECT d.*, f.path as file_path
        FROM docs d
        JOIN files f ON d.file_id = f.id
        WHERE ({where_clause})
        ORDER BY d.heading_level ASC, length(d.content) DESC
        LIMIT ?
        """
        params.append(limit)

        with self.get_connection() as conn:
            cur = conn.execute(sql, params)
            return cur.fetchall()
