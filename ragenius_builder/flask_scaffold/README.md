# RAG Web Application (Builder Flask Scaffold)

This folder contains a minimal Flask + Tailwind prototype generated for builder/admin workflows.

## Getting started

```bash
pip install flask rag_subsystem
FLASK_APP=app.py flask run --reload
```

The server seeds a sample application and document in `rag_app.db` (created in this folder) so you can explore pages at `/apps`, configure instructions/settings, upload placeholder documents, and try search.

## Notes
- RAG processing and retrieval are delegated to `rag_stub.py`; ensure `rag_subsystem` is installed.
- Data is stored in `rag_app.db` using SQLite via `storage.py`.
- Forms include labels and error descriptions for accessibility.
- `/api/apps/by-name/{name}` uses a local in-process rate limit of 60 requests/min/client IP.
- Search retrieval enforces a 3-second timeout and returns HTTP 503 on timeout.