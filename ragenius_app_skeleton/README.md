# RAGenius App

Builder-backed RAGenius runtime with:
- FastAPI chat and ingestion APIs
- LangGraph user-query pipeline
- React user-facing control surface
- Builder instructions/settings derived into runtime config
- `rag_subsystem` ingestion and retrieval

## Run Locally
1. Copy env file:
   - `cp .env.example .env` (Linux/macOS)
   - `Copy-Item .env.example .env` (PowerShell)
2. Start stack:
   - `docker-compose up --build`
3. Open:
   - Backend: `http://localhost:8000`
   - Frontend: `http://localhost:5173`

## Apply DB Migration
Run `backend/db/migrations.sql` against PostgreSQL before production use.

## Test
- `python -m unittest discover -s tests -p "test_*.py"`

## Runtime Model
- `ragenius_builder` is the source of truth for:
  - app metadata
  - `instructions/{app_id}/instructions.md`
  - per-app settings
  - uploaded document records and file paths
- `ragenius_app_skeleton` is a builder-only runtime:
  - no local Config PDF flow
  - no local adapter approval flow
  - no app-local document upload storage

## Key Endpoints
- `GET /apps/{app_id}`
- `GET /apps/{app_id}/instructions` (admin)
- `GET /apps/{app_id}/documents` (admin)
- `POST /apps/{app_id}/documents/ingest` (admin)
- `GET /apps/{app_id}/ingestion_runs/{run_id}` (admin)
- `POST /sessions/{id}/chat`
