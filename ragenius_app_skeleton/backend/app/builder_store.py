"""Read-only integration helpers for ragenius_builder/flask_scaffold storage."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Dict, Optional


DEFAULT_BUILDER_DB = (
    Path(__file__).resolve().parents[3] / "ragenius_builder" / "flask_scaffold" / "rag_app.db"
)


class BuilderStore:
    """Read builder-owned application metadata and file-backed instructions."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path or os.getenv("RAGENIUS_BUILDER_DB") or DEFAULT_BUILDER_DB).resolve()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def list_applications(self) -> list[Dict[str, Any]]:
        if not self.db_path.exists():
            return []
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT * FROM applications ORDER BY updated_at DESC, name ASC").fetchall()
        apps: list[Dict[str, Any]] = []
        for row in rows:
            apps.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "slug": row["slug"],
                    "description": row["description"] or "",
                    "starter_questions": json.loads(row["starter_questions"] or "[]"),
                    "updated_at": row["updated_at"],
                }
            )
        return apps

    def get_application(self, app_id: str) -> Optional[Dict[str, Any]]:
        if not self.db_path.exists():
            return None
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "name": row["name"],
            "slug": row["slug"],
            "description": row["description"] or "",
            "starter_questions": json.loads(row["starter_questions"] or "[]"),
            "updated_at": row["updated_at"],
        }

    def get_application_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        if not self.db_path.exists():
            return None
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM applications WHERE lower(name) = lower(?) LIMIT 1",
                (name,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "name": row["name"],
            "slug": row["slug"],
            "description": row["description"] or "",
            "starter_questions": json.loads(row["starter_questions"] or "[]"),
            "updated_at": row["updated_at"],
        }

    def get_settings(self, app_id: str) -> Optional[Dict[str, Any]]:
        if not self.db_path.exists():
            return None
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM settings WHERE app_id = ?", (app_id,)).fetchone()
        if row is None:
            return None
        try:
            config_settings = json.loads(row["config_settings"] or "{}")
        except Exception:
            config_settings = {}
        try:
            config_schema = json.loads(row["config_schema"] or "{}")
        except Exception:
            config_schema = {}
        return {
            "config_settings": config_settings,
            "config_schema": config_schema,
            "updated_at": row["updated_at"],
        }

    def get_instructions(self, app_id: str) -> Optional[Dict[str, Any]]:
        if not self.db_path.exists():
            return None
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM instructions WHERE app_id = ?", (app_id,)).fetchone()
        if row is None:
            return None

        uri = row["uri"] or f"instructions/{app_id}/instructions.md"
        path = (self.db_path.parent / uri).resolve()
        content = row["content"] or ""
        if path.exists():
            content = path.read_text(encoding="utf-8", errors="ignore")
        return {
            "content": content,
            "uri": uri,
            "version": row["version"],
            "updated_at": row["updated_at"],
        }

    def list_documents(self, app_id: str) -> list[Dict[str, Any]]:
        if not self.db_path.exists():
            return []
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM documents WHERE app_id = ? ORDER BY uploaded_at DESC",
                (app_id,),
            ).fetchall()
        documents: list[Dict[str, Any]] = []
        for row in rows:
            documents.append(
                {
                    "id": row["id"],
                    "app_id": row["app_id"],
                    "filename": row["filename"],
                    "mime_type": row["mime_type"],
                    "size_bytes": row["size_bytes"],
                    "language": row["language"],
                    "tags": json.loads(row["tags"] or "[]"),
                    "file_path": row["file_path"],
                    "status": row["status"],
                    "error_message": row["error_message"],
                    "uploaded_at": row["uploaded_at"],
                }
            )
        return documents

    def get_document(self, app_id: str, doc_id: str) -> Optional[Dict[str, Any]]:
        if not self.db_path.exists():
            return None
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE app_id = ? AND id = ?",
                (app_id, doc_id),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "app_id": row["app_id"],
            "filename": row["filename"],
            "mime_type": row["mime_type"],
            "size_bytes": row["size_bytes"],
            "language": row["language"],
            "tags": json.loads(row["tags"] or "[]"),
            "file_path": row["file_path"],
            "status": row["status"],
            "error_message": row["error_message"],
            "uploaded_at": row["uploaded_at"],
        }

    def list_app_skill_bindings(self, app_id: str) -> list[Dict[str, Any]]:
        if not self.db_path.exists():
            return []
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT id, app_id, skill_id, skill_version, enabled, permission_mode, execution_policy,
                       created_at, updated_at
                FROM app_skill_bindings
                WHERE app_id = ?
                ORDER BY created_at DESC
                """,
                (app_id,),
            ).fetchall()
        bindings: list[Dict[str, Any]] = []
        for row in rows:
            bindings.append(
                {
                    "id": row["id"],
                    "app_id": row["app_id"],
                    "skill_id": row["skill_id"],
                    "skill_version": row["skill_version"],
                    "enabled": bool(row["enabled"]),
                    "permission_mode": row["permission_mode"],
                    "execution_policy": json.loads(row["execution_policy"] or "{}"),
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            )
        return bindings

    def get_published_skill_definition(
        self, *, skill_id: str, version: str | None = None
    ) -> Optional[Dict[str, Any]]:
        if not self.db_path.exists():
            return None
        try:
            from ragenius_builder.flask_scaffold.storage import store

            return store.get_published_skill_definition(skill_id=skill_id, version=version)
        except Exception:
            return None


def get_builder_store() -> BuilderStore:
    return BuilderStore()
