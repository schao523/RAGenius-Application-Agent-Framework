"""In-memory ingestion_runs repository."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class IngestionRepo:
    def __init__(self) -> None:
        self._runs: Dict[str, Dict[str, Any]] = {}

    def reset(self) -> None:
        self._runs.clear()

    def create_run(self, collection_id: str, document_count: int) -> Dict[str, Any]:
        run_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        row = {
            "id": run_id,
            "collection_id": collection_id,
            "document_count": document_count,
            "status": "queued",
            "debug_trace": None,
            "created_at": now,
            "updated_at": now,
        }
        self._runs[run_id] = row
        return row

    def update_status(self, run_id: str, status: str, *, debug_trace: Optional[Dict[str, Any]] = None, document_count: Optional[int] = None) -> Dict[str, Any]:
        row = self._runs.get(run_id)
        if row is None:
            raise KeyError(f"Ingestion run not found: {run_id}")
        row["status"] = status
        if debug_trace is not None:
            row["debug_trace"] = debug_trace
        if document_count is not None:
            row["document_count"] = document_count
        row["updated_at"] = datetime.now(timezone.utc).isoformat()
        return row

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        return self._runs.get(run_id)

