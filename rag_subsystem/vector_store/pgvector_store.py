"""pgvector-backed vector store."""
from __future__ import annotations
from typing import Any, Dict, List, Sequence, Tuple
try:
    import psycopg2
    from psycopg2.extras import Json
except ImportError:  # pragma: no cover - optional dependency
    psycopg2 = None
    Json = None
from .base import VectorStore
from ..schemas import Chunk


SQL_SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS rag_chunks (
    doc_id TEXT NOT NULL,
    chunk_id TEXT PRIMARY KEY,
    app_id TEXT NOT NULL,
    namespace TEXT NOT NULL,
    text TEXT NOT NULL,
    section_path TEXT,
    ordering INTEGER,
    embedding vector(8),
    metadata JSONB,
    hash TEXT,
    language TEXT,
    embedding_model TEXT,
    updated_at TIMESTAMP DEFAULT NOW()
);
ALTER TABLE rag_chunks ADD COLUMN IF NOT EXISTS app_id TEXT;
UPDATE rag_chunks SET app_id = COALESCE(NULLIF(metadata->>'app_id', ''), app_id, '') WHERE app_id IS NULL OR app_id = '';
ALTER TABLE rag_chunks ALTER COLUMN app_id SET DEFAULT '';
CREATE INDEX IF NOT EXISTS idx_rag_chunks_namespace ON rag_chunks(namespace);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_app ON rag_chunks(app_id);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_app_namespace ON rag_chunks(app_id, namespace);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_doc ON rag_chunks(doc_id);
-- Upsert operations rely on ON CONFLICT(chunk_id) in application code
"""


class PgVectorStore(VectorStore):
    def __init__(self, dsn: str, bootstrap_schema: bool = True):
        self.dsn = dsn
        self.bootstrap_schema = bootstrap_schema
        self.ensure_ready()

    def _conn(self):  # pragma: no cover - requires postgres
        if psycopg2 is None:
            raise RuntimeError("psycopg2 not installed")
        return psycopg2.connect(self.dsn)

    @staticmethod
    def _to_vector_literal(values: List[float]) -> str:
        return "[" + ",".join(str(float(v)) for v in values) + "]"

    def _schema_is_ready(self) -> bool:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_extension WHERE extname='vector'")
            has_vector = cur.fetchone() is not None
            cur.execute("SELECT to_regclass('public.rag_chunks')")
            has_table = cur.fetchone()[0] is not None
            if not has_vector or not has_table:
                return False
            cur.execute(
                "SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='rag_chunks' AND column_name='app_id'"
            )
            return cur.fetchone() is not None

    def ensure_ready(self) -> None:
        if self.bootstrap_schema:
            with self._conn() as conn, conn.cursor() as cur:
                cur.execute(SQL_SCHEMA)
                conn.commit()
        if not self._schema_is_ready():
            raise RuntimeError(
                "pgvector preflight failed: missing extension/table/columns. "
                "Enable bootstrap or run rag_subsystem/sql/init_pgvector.sql."
            )

    def upsert(self, chunks: Sequence[Chunk]) -> None:  # pragma: no cover - requires postgres
        with self._conn() as conn:
            with conn.cursor() as cur:
                for chunk in chunks:
                    app_id = str(chunk.metadata.get("app_id", "")).strip()
                    if not app_id:
                        raise ValueError("chunk.metadata.app_id is required for pgvector upsert")
                    cur.execute(
                        """
                        INSERT INTO rag_chunks(doc_id, chunk_id, app_id, namespace, text, section_path, ordering, embedding, metadata, hash, language, embedding_model)
                        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT(chunk_id) DO UPDATE SET
                            app_id=EXCLUDED.app_id,
                            text=EXCLUDED.text,
                            section_path=EXCLUDED.section_path,
                            ordering=EXCLUDED.ordering,
                            embedding=EXCLUDED.embedding,
                            metadata=EXCLUDED.metadata,
                            hash=EXCLUDED.hash,
                            language=EXCLUDED.language,
                            embedding_model=EXCLUDED.embedding_model,
                            updated_at=NOW();
                        """,
                        (
                            chunk.doc_id,
                            chunk.chunk_id,
                            app_id,
                            chunk.namespace,
                            chunk.text,
                            chunk.section_path,
                            chunk.order,
                            self._to_vector_literal(chunk.embedding),
                            Json(chunk.metadata),
                            chunk.hash,
                            chunk.language,
                            chunk.embedding_model,
                        ),
                    )
            conn.commit()

    def semantic_search(
        self, query_embedding: List[float], namespace: str, top_k: int, app_id: str | None = None
    ) -> List[Tuple[Chunk, float]]:  # pragma: no cover
        if not app_id:
            raise ValueError("app_id is required for semantic_search")
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT doc_id, chunk_id, text, section_path, ordering, embedding, metadata, hash, language, embedding_model,
                1 - (embedding <=> %s::vector) as score FROM rag_chunks WHERE app_id=%s AND namespace=%s ORDER BY embedding <=> %s::vector LIMIT %s""",
                (
                    self._to_vector_literal(query_embedding),
                    app_id,
                    namespace,
                    self._to_vector_literal(query_embedding),
                    top_k,
                ),
            )
            rows = cur.fetchall()
            return [
                (
                    Chunk(
                        doc_id=row[0],
                        chunk_id=row[1],
                        text=row[2],
                        section_path=row[3],
                        order=row[4],
                        embedding=row[5],
                        metadata=row[6] or {},
                        hash=row[7],
                        language=row[8],
                        embedding_model=row[9],
                        namespace=namespace,
                    ),
                    float(row[10]),
                )
                for row in rows
            ]

    def metadata_search(
        self, filters: Dict[str, Any], namespace: str, top_k: int, app_id: str | None = None
    ) -> List[Tuple[Chunk, float]]:  # pragma: no cover
        if not app_id:
            raise ValueError("app_id is required for metadata_search")
        where_clauses = ["app_id=%s", "namespace=%s"]
        params = [app_id, namespace]
        for key, value in filters.items():
            where_clauses.append(f"metadata->>%s = %s")
            params.extend([key, value])
        where_sql = " AND ".join(where_clauses)
        sql = f"SELECT doc_id, chunk_id, text, section_path, ordering, embedding, metadata, hash, language, embedding_model FROM rag_chunks WHERE {where_sql} LIMIT %s"
        params.append(top_k)
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
            return [
                (
                    Chunk(
                        doc_id=row[0],
                        chunk_id=row[1],
                        text=row[2],
                        section_path=row[3],
                        order=row[4],
                        embedding=row[5],
                        metadata=row[6] or {},
                        hash=row[7],
                        language=row[8],
                        embedding_model=row[9],
                        namespace=namespace,
                    ),
                    1.0,
                )
                for row in rows
            ]

    def delete_by_doc_id(self, doc_id: str, app_id: str | None = None) -> None:  # pragma: no cover
        if not app_id:
            raise ValueError("app_id is required for delete_by_doc_id")
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM rag_chunks WHERE doc_id=%s AND app_id=%s", (doc_id, app_id))
            conn.commit()
