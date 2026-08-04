# RAG Subsystem

Deterministic Python ingestion + retrieval subsystem used by RAGenius.

This README is focused on running the package locally from this repository.

## Local Setup

### Windows (PowerShell)

```powershell
cd C:\Users\User\Documents\GitHub\Codex-RAGenius-System\rag_subsystem
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

### macOS / Linux (bash/zsh)

```bash
cd /path/to/Codex-RAGenius-System/rag_subsystem
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

Optional PostgreSQL support:

```bash
python -m pip install -e .[pgvector]
```

Local embedding inference runtime:

```bash
python -m pip install -e .[local-embeddings]
```

## Default Vector Store Configuration

If you do not pass a `store` object to `process_files(...)` or `retrieve_data(...)`, the subsystem now resolves a default backend from environment variables.

- `RAG_VECTOR_STORE_BACKEND`:
  - `pgvector` (default)
  - `auto`
  - `in_memory`
  - `json`
- `RAG_VECTOR_STORE_DSN`: DSN for pgvector backend
- `RAG_VECTOR_STORE_PATH`: JSON path for `json` backend

Local pgvector DSN default:

```text
postgresql://ragenius:ragenius@localhost:5433/ragenius
```

## Embedding Runtime Configuration

The subsystem now supports real local model inference for embeddings.

- `RAG_EMBEDDING_BACKEND`:
  - `local` (default, real inference via sentence-transformers)
  - `auto` (try local, fallback to deterministic hash)
  - `hash` (deterministic fallback/testing)
- `RAG_EMBEDDING_DEVICE`: `cpu` (default) or `cuda`
- `RAG_EMBEDDING_NORMALIZE`: `true` (default) or `false`
- `RAG_EMBEDDING_DIM`: default `1024`

Current routed local models:

- `e5-large` -> `intfloat/e5-large-v2` (1024 dim)
- `bge-large-zh` -> `BAAI/bge-large-zh-v1.5` (1024 dim)

### Chinese Retrieval Contract (Required)

For reliable Chinese semantic retrieval, do **not** run with hash embeddings.

Required runtime contract:

- Install local embedding deps:
  - `python -m pip install -e .[local-embeddings]`
- Set backend:
  - `RAG_EMBEDDING_BACKEND=local`
- Ensure Chinese model files are resolvable:
  - default: `rag_subsystem/models/bge-large-zh`
  - or set `RAG_EMBEDDING_MODEL_PATH_BGE_LARGE_ZH`
- Keep lexical fallback enabled (built into `retrieve_data`) for robustness when semantic ranking underperforms.

`RAG_EMBEDDING_BACKEND=hash` is intended for deterministic testing only and will reduce Chinese semantic quality.

Quick verification:

```bash
python -c "from rag_subsystem.embedding import embed_text; v=embed_text('細察事實觀察的項目','bge-large-zh'); print(len(v), type(v[0]).__name__)"
```

Expected: `1024 float`

## Verified Local Smoke Test

Run this from the repository root (`Codex-RAGenius-System`) after installing:

```powershell
python -c "from rag_subsystem import process_files, retrieve_data, DEFAULT_PROCESS_CONFIG, DEFAULT_RETRIEVAL_CONFIG; from rag_subsystem.vector_store.in_memory_store import InMemoryVectorStore; store=InMemoryVectorStore(); text='RAG systems combine retrieval and generation to answer questions with grounded evidence. This local smoke test paragraph includes enough words to pass the minimum chunk threshold and validate ingestion, vector upsert, and retrieval behavior in the in memory store.'; docs=[{'doc_id':'doc1','blocks':[{'type':'text','text':text,'metadata':{'version':'1.0.0'}}]}]; ingest=process_files(docs, DEFAULT_PROCESS_CONFIG, store); r=retrieve_data('grounded evidence retrieval', top_k=3, config=DEFAULT_RETRIEVAL_CONFIG, store=store); print(len(ingest), ingest[0].inserted if ingest else -1, len(r.results))"
```

Expected output:

```text
1 1 1
```

If you get `0` inserted chunks, your text is likely below the default `min_chunk_length` of 30 tokens.

## Minimal Usage

```python
from rag_subsystem import process_files, retrieve_data, DEFAULT_PROCESS_CONFIG, DEFAULT_RETRIEVAL_CONFIG
from rag_subsystem.vector_store.in_memory_store import InMemoryVectorStore

store = InMemoryVectorStore()

documents = [
    {
        "doc_id": "doc1",
        "blocks": [
            {
                "type": "text",
                "text": "This example block should contain at least thirty tokens so it survives quality filtering before retrieval.",
                "metadata": {"version": "1.0.0"},
            }
        ],
    }
]

ingest_results = process_files(documents, DEFAULT_PROCESS_CONFIG, store)
result = retrieve_data("quality filtering retrieval", top_k=5, filters={}, config=DEFAULT_RETRIEVAL_CONFIG, store=store)

for candidate in result.results:
    print(candidate.chunk.text, candidate.score)
```

## Tests

```bash
python -m pip install -e .[dev]
pytest
```

## pgvector Schema

`rag_subsystem/vector_store/pgvector_store.py` contains `SQL_SCHEMA`. Apply it to your PostgreSQL database before using the pgvector store.
