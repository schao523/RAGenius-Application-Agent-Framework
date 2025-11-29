# RAG Subsystem

This repository implements a deterministic Python RAG subsystem per the Design Specification v1.3.2. It provides end-to-end ingestion and retrieval with normalization, chunking, quality filtering, embedding routing, vector storage, and hybrid retrieval fusion.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

The repository ships a `pyproject.toml`, so it can be installed directly from the source tree or a Git URL:

```bash
pip install "git+https://example.com/rag-subsystem/repo.git"
```

For PostgreSQL-backed vector storage, install the optional dependency group:

```bash
pip install -e .[pgvector]
```

Running tests:

```bash
pytest
```

## pgvector setup

The pgvector-backed store uses the schema in `rag_subsystem/vector_store/pgvector_store.py` via `SQL_SCHEMA`. Execute it after connecting to your PostgreSQL database:

```sql
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
```

## Usage

### Ingestion

```python
from rag_subsystem import process_files, DEFAULT_PROCESS_CONFIG
from rag_subsystem.vector_store.in_memory_store import InMemoryVectorStore

store = InMemoryVectorStore()
documents = [
    {"doc_id": "doc1", "blocks": [{"type": "text", "text": "Hello world", "metadata": {"version": "1.0.0"}}]},
]
ingest_results = process_files(documents, DEFAULT_PROCESS_CONFIG, store)
```

### Retrieval

```python
from rag_subsystem import retrieve_data, DEFAULT_RETRIEVAL_CONFIG

result = retrieve_data("hello", top_k=5, filters={}, config=DEFAULT_RETRIEVAL_CONFIG, store=store)
for candidate in result.results:
    print(candidate.chunk.text, candidate.score)
```

The retrieval debug payload includes timing, routing, candidate lists, and fusion scores for observability.
