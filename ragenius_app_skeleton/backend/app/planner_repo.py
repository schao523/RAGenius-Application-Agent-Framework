"""Planner output persistence repositories."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class InMemoryPlannerRepo:
    """In-memory planner_outputs storage for tests and local scaffolding."""

    def __init__(self) -> None:
        self._rows: List[Dict[str, Any]] = []

    def reset(self) -> None:
        self._rows.clear()

    def save(self, session_id: str, user_query: str, planner_output: Dict[str, Any]) -> Dict[str, Any]:
        row = {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "user_query": user_query,
            "planner_output": planner_output,
            "confidence": planner_output.get("confidence"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._rows.append(row)
        return row


@dataclass
class PostgresPlannerRepo:
    """PostgreSQL planner_outputs repository."""

    database_url: Optional[str] = None

    def __post_init__(self) -> None:
        self.database_url = self.database_url or os.getenv("DATABASE_URL")
        if not self.database_url:
            raise ValueError("DATABASE_URL is required for PostgresPlannerRepo.")

    def save(self, session_id: str, user_query: str, planner_output: Dict[str, Any]) -> Dict[str, Any]:
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover
            raise ImportError("psycopg is required for PostgresPlannerRepo.") from exc

        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO planner_outputs (session_id, user_query, planner_output, confidence)
                    VALUES (%s::uuid, %s, %s::jsonb, %s)
                    RETURNING id::text, session_id::text, user_query, planner_output, confidence
                    """,
                    (
                        session_id,
                        user_query,
                        json.dumps(planner_output),
                        planner_output.get("confidence"),
                    ),
                )
                row = cur.fetchone()
            conn.commit()

        return {
            "id": row[0],
            "session_id": row[1],
            "user_query": row[2],
            "planner_output": row[3],
            "confidence": row[4],
        }

