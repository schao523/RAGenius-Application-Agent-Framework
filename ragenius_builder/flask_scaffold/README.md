# RAG Web Application (Builder Flask Scaffold)

This folder is the primary builder/admin application for `ragenius_builder`.

The older FastAPI prototype has been quarantined under `../archived_fastapi_prototype/` and should not be used as a runtime target.

## Getting started

```bash
pip install flask rag_subsystem
FLASK_APP=app.py flask run --reload
```

The server seeds a sample application and document in `rag_app.db` (created in this folder) so you can explore pages at `/apps`, configure instructions/settings, upload placeholder documents, and try search.

Builder skill-management MVP pages are also available:

- `/skills`
- `/skills/import`
- `/skills/<skill_id>`
- `/skills/<skill_id>/test`

## Notes
- RAG processing and retrieval are delegated to `rag_stub.py`; ensure `rag_subsystem` is installed.
- Data is stored in `rag_app.db` using SQLite via `storage.py`.
- Forms include labels and error descriptions for accessibility.
- `/api/apps/by-name/{name}` uses a local in-process rate limit of 60 requests/min/client IP.
- Search retrieval enforces a 3-second timeout and returns HTTP 503 on timeout.
- Builder-owned skill metadata, published skill contracts, and app-skill bindings are persisted in SQLite plus builder-managed skill folders.
- Skill test execution calls `ragenius_execution_subsystem`; builder does not execute skills locally.
