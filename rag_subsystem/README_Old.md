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
