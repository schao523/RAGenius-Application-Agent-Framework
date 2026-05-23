# Codex-RAGenius-System

RAGenius is a multi-application RAG platform.

## Components

- `rag_subsystem/`: ingestion, retrieval, embeddings, and vector store integrations
- `ragenius_app/`: end-user chat and workflow UX
- `ragenius_builder/`: admin/builder control plane

## Local setup

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ./rag_subsystem
python -m pip install -e ./rag_subsystem[local-embeddings]
```

Run subsystem tests:

```powershell
pytest tests/test_rag_subsystem.py
```

## Notes

- Keep retrieval and ingestion logic in `rag_subsystem`.
- Keep admin workflows in `ragenius_builder`.
- Keep end-user chat flows in `ragenius_app`.
- Enforce per-app isolation (`app_id` scoped retrieval, no cross-app leakage).
