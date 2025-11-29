"""pgvector-backed vector store."""
from __future__ import annotations
import json
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
CREATE INDEX IF NOT EXISTS idx_rag_chunks_namespace ON rag_chunks(namespace);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_doc ON rag_chunks(doc_id);
-- Upsert operations rely on ON CONFLICT(chunk_id) in application code
"""


class PgVectorStore(VectorStore):
    def __init__(self, dsn: str):
        self.dsn = dsn

    def _conn(self):  # pragma: no cover - requires postgres
        if psycopg2 is None:
            raise RuntimeError("psycopg2 not installed")
        return psycopg2.connect(self.dsn)

    def upsert(self, chunks: Sequence[Chunk]) -> None:  # pragma: no cover - requires postgres
        with self._conn() as conn:
            with conn.cursor() as cur:
                for chunk in chunks:
                    cur.execute(
                        """
                        INSERT INTO rag_chunks(doc_id, chunk_id, namespace, text, section_path, ordering, embedding, metadata, hash, language, embedding_model)
                        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT(chunk_id) DO UPDATE SET
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
                            chunk.namespace,
                            chunk.text,
                            chunk.section_path,
                            chunk.order,
                            chunk.embedding,
                            Json(chunk.metadata),
                            chunk.hash,
                            chunk.language,
                            chunk.embedding_model,
                        ),
                    )
            conn.commit()

    def semantic_search(self, query_embedding: List[float], namespace: str, top_k: int) -> List[Tuple[Chunk, float]]:  # pragma: no cover
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT doc_id, chunk_id, text, section_path, ordering, embedding, metadata, hash, language, embedding_model,
                1 - (embedding <=> %s::vector) as score FROM rag_chunks WHERE namespace=%s ORDER BY embedding <=> %s::vector LIMIT %s""",
                (query_embedding, namespace, query_embedding, top_k),
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

    def metadata_search(self, filters: Dict[str, Any], namespace: str, top_k: int) -> List[Tuple[Chunk, float]]:  # pragma: no cover
        where_clauses = ["namespace=%s"]
        params = [namespace]
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

    def delete_by_doc_id(self, doc_id: str) -> None:  # pragma: no cover
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM rag_chunks WHERE doc_id=%s", (doc_id,))
            conn.commit()
