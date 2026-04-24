CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS rag_chunks (
    doc_id TEXT NOT NULL,
    chunk_id TEXT PRIMARY KEY,
    app_id TEXT NOT NULL,
    namespace TEXT NOT NULL,
    text TEXT NOT NULL,
    section_path TEXT,
    ordering INTEGER,
    embedding vector(1024),
    metadata JSONB,
    hash TEXT,
    language TEXT,
    embedding_model TEXT,
    updated_at TIMESTAMP DEFAULT NOW()
);
ALTER TABLE rag_chunks ADD COLUMN IF NOT EXISTS app_id TEXT;
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname='public'
          AND c.relname='rag_chunks'
          AND a.attname='embedding'
          AND a.atttypid = 'vector'::regtype
          AND a.atttypmod <> 1024
    ) THEN
        ALTER TABLE rag_chunks DROP COLUMN embedding;
        ALTER TABLE rag_chunks ADD COLUMN embedding vector(1024);
    END IF;
END $$;
UPDATE rag_chunks SET app_id = COALESCE(NULLIF(metadata->>'app_id', ''), 'unknown') WHERE app_id IS NULL OR app_id = '';
ALTER TABLE rag_chunks ALTER COLUMN app_id SET DEFAULT '';
CREATE INDEX IF NOT EXISTS idx_rag_chunks_namespace ON rag_chunks(namespace);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_app ON rag_chunks(app_id);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_app_namespace ON rag_chunks(app_id, namespace);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_doc ON rag_chunks(doc_id);
