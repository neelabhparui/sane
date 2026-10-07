"""SQLite database management with WAL mode and FTS5 search.

Provides transactional persistence for repository metadata, code symbols,
syntactic occurrences, resolved edges, and hierarchical documentation sections.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any, Iterator, Optional

from sane_nav.core.models import (
    ParsedDocumentSection,
    ParsedFile,
    ParsedReference,
    ParsedSymbol,
    SourceRange,
)


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
                conn.execute(
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

    def list_files(self) -> list[sqlite3.Row]:
        """Lists all indexed files in alphabetical order."""
        with self.get_connection() as conn:
            cur = conn.execute("SELECT * FROM files ORDER BY path ASC")
            return cur.fetchall()

    def get_symbol_by_id_or_name(self, query: str) -> list[sqlite3.Row]:
        """Searches symbols by symbol key, qualified name, or short name."""
        with self.get_connection() as conn:
            # 1. Exact symbol_key match
            cur = conn.execute(
                "SELECT s.*, f.path as file_path FROM symbols s JOIN files f ON s.file_id = f.id WHERE s.symbol_key = ?",
                (query,),
            )
            rows = cur.fetchall()
            if rows:
                return rows

            # 2. Exact qualified_name match
            cur = conn.execute(
                "SELECT s.*, f.path as file_path FROM symbols s JOIN files f ON s.file_id = f.id WHERE s.qualified_name = ?",
                (query,),
            )
            rows = cur.fetchall()
            if rows:
                return rows

            # 3. Exact short name match
            cur = conn.execute(
                "SELECT s.*, f.path as file_path FROM symbols s JOIN files f ON s.file_id = f.id WHERE s.name = ?",
                (query,),
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
                (f"%{query}", f"%{query}%"),
            )
            return cur.fetchall()

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
