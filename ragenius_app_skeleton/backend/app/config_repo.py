"""Config instruction persistence repositories."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


class InMemoryConfigRepo:
    """In-memory config_instructions store for local runs/tests."""

    def __init__(self, persistence_file: str | None = None) -> None:
        self._persistence_file = Path(persistence_file) if persistence_file else None
        self._configs: Dict[str, Dict[int, Dict[str, Any]]] = {}
        self._latest_version: Dict[str, int] = {}
        self._load()

    def _load(self) -> None:
        if self._persistence_file is None or not self._persistence_file.exists():
            return
        raw = json.loads(self._persistence_file.read_text(encoding="utf-8"))
        self._configs = {
            cid: {int(ver): row for ver, row in versions.items()}
            for cid, versions in raw.get("configs", {}).items()
        }
        self._latest_version = {cid: int(ver) for cid, ver in raw.get("latest_version", {}).items()}

    def _save(self) -> None:
        if self._persistence_file is None:
            return
        self._persistence_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "configs": {
                cid: {str(ver): row for ver, row in versions.items()}
                for cid, versions in self._configs.items()
            },
            "latest_version": self._latest_version,
        }
        self._persistence_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def reset(self) -> None:
        self._configs.clear()
        self._latest_version.clear()
        self._save()

    def save(
        self,
        collection_id: str,
        config_json: Dict[str, Any],
        extracted_text: str,
        *,
        source_pdf_name: str | None = None,
    ) -> Dict[str, Any]:
        version = self._latest_version.get(collection_id, 0) + 1
        row = {
            "id": str(uuid.uuid4()),
            "collection_id": collection_id,
            "version": version,
            "source_pdf_name": source_pdf_name,
            "config_json": config_json,
            "extracted_text": extracted_text,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._configs.setdefault(collection_id, {})[version] = row
        self._latest_version[collection_id] = version
        self._save()
        return row

    def latest(self, collection_id: str) -> Dict[str, Any] | None:
        version = self._latest_version.get(collection_id)
        if version is None:
            return None
        return self._configs.get(collection_id, {}).get(version)


@dataclass
class PostgresConfigRepo:
    """Repository for versioned config_instructions persistence."""

    database_url: str | None = None

    def __post_init__(self) -> None:
        self.database_url = self.database_url or os.getenv("DATABASE_URL")
        if not self.database_url:
            raise ValueError("DATABASE_URL is required for PostgresConfigRepo.")

    def save(
        self,
        collection_id: str,
        config_json: Dict[str, Any],
        extracted_text: str,
        *,
        source_pdf_name: str | None = None,
    ) -> Dict[str, Any]:
        """Persist a new config version for a collection.

        TODO: Move SQL into migration-managed query helpers when DAL is introduced.
        """
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover
            raise ImportError("psycopg is required for DB persistence.") from exc

        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COALESCE(MAX(version), 0) + 1
                    FROM config_instructions
                    WHERE collection_id = %s::uuid
                    """,
                    (collection_id,),
                )
                next_version = int(cur.fetchone()[0])

                cur.execute(
                    """
                    INSERT INTO config_instructions
                        (collection_id, version, source_pdf_name, config_json, extracted_text)
                    VALUES
                        (%s::uuid, %s, %s, %s::jsonb, %s)
                    RETURNING id::text, collection_id::text, version, source_pdf_name, config_json, extracted_text
                    """,
                    (
                        collection_id,
                        next_version,
                        source_pdf_name,
                        json.dumps(config_json),
                        extracted_text,
                    ),
                )
                row = cur.fetchone()
            conn.commit()

        return {
            "id": row[0],
            "collection_id": row[1],
            "version": row[2],
            "source_pdf_name": row[3],
            "config_json": row[4],
            "extracted_text": row[5],
        }
