PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS files (
    id                INTEGER PRIMARY KEY,
    path              TEXT NOT NULL UNIQUE,
    language          TEXT,
    content_hash      TEXT NOT NULL,
    mtime_ns          INTEGER,
    size_bytes        INTEGER NOT NULL,
    indexed_at_ns     INTEGER NOT NULL,
    parse_error_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS symbols (
    id                   INTEGER PRIMARY KEY,
    file_id              INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    parent_symbol_id     INTEGER REFERENCES symbols(id) ON DELETE CASCADE,
    symbol_key           TEXT NOT NULL UNIQUE,
    qualified_name       TEXT,
    name                 TEXT NOT NULL,
    kind                 TEXT NOT NULL,
    visibility           TEXT DEFAULT 'public',
    signature            TEXT,
    docstring            TEXT,
    start_byte           INTEGER NOT NULL,
    end_byte             INTEGER NOT NULL,
    start_line           INTEGER NOT NULL,
    end_line             INTEGER NOT NULL,
    signature_start_byte INTEGER,
    signature_end_byte   INTEGER,
    body_start_byte      INTEGER,
    body_end_byte        INTEGER
);

CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
CREATE INDEX IF NOT EXISTS idx_symbols_qualified_name ON symbols(qualified_name);
CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_id);

CREATE TABLE IF NOT EXISTS occurrences (
    id                   INTEGER PRIMARY KEY,
    file_id              INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    enclosing_symbol_id  INTEGER REFERENCES symbols(id) ON DELETE CASCADE,
    spelling             TEXT NOT NULL,
    role                 TEXT NOT NULL,
    start_byte           INTEGER NOT NULL,
    end_byte             INTEGER NOT NULL,
    start_line           INTEGER NOT NULL,
    end_line             INTEGER NOT NULL,
    target_symbol_id     INTEGER REFERENCES symbols(id) ON DELETE SET NULL,
    receiver_text        TEXT,
    resolution_kind      TEXT NOT NULL DEFAULT 'unresolved',
    confidence           REAL
);

CREATE INDEX IF NOT EXISTS idx_occurrence_spelling ON occurrences(spelling);
CREATE INDEX IF NOT EXISTS idx_occurrence_target ON occurrences(target_symbol_id);

CREATE TABLE IF NOT EXISTS edges (
    id                INTEGER PRIMARY KEY,
    source_symbol_id  INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    target_symbol_id  INTEGER REFERENCES symbols(id) ON DELETE CASCADE,
    occurrence_id     INTEGER REFERENCES occurrences(id) ON DELETE CASCADE,
    target_text       TEXT,
    kind              TEXT NOT NULL,
    resolution_kind   TEXT NOT NULL,
    confidence        REAL
);

CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_symbol_id);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_symbol_id);

CREATE TABLE IF NOT EXISTS docs (
    id             INTEGER PRIMARY KEY,
    file_id        INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    parent_id      INTEGER REFERENCES docs(id) ON DELETE CASCADE,
    heading_level  INTEGER NOT NULL,
    heading        TEXT NOT NULL,
    heading_path   TEXT NOT NULL,
    content        TEXT NOT NULL,
    start_byte     INTEGER NOT NULL,
    end_byte       INTEGER NOT NULL,
    start_line     INTEGER NOT NULL,
    end_line       INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS search_documents (
    id          INTEGER PRIMARY KEY,
    entity_type TEXT NOT NULL,     -- symbol | doc
    entity_id   INTEGER NOT NULL,
    title       TEXT NOT NULL,
    path        TEXT NOT NULL,
    body        TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(
    title,
    path,
    body,
    content='search_documents',
    content_rowid='id',
    tokenize='unicode61'
);
