"""Durable repositories for chat/session/planner/retrieval artifacts."""

from __future__ import annotations

import os
import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _default_state_db() -> Path:
    return Path(__file__).resolve().parents[1] / ".state" / "runtime_state.db"


def _default_uploads_dir() -> Path:
    return Path(__file__).resolve().parents[1] / ".state" / "session_uploads"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_runtime_state(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "workflow_progress": {},
            "session_execution_state": {},
            "intermediate_outputs": [],
            "assembly_state": {},
        }
    if any(key in payload for key in ("workflow_progress", "session_execution_state", "intermediate_outputs", "assembly_state")):
        workflow_progress = payload.get("workflow_progress", {})
        session_execution_state = payload.get("session_execution_state", {})
        intermediate_outputs = payload.get("intermediate_outputs", [])
        assembly_state = payload.get("assembly_state", {})
    else:
        workflow_progress = payload
        session_execution_state = {}
        intermediate_outputs = []
        assembly_state = {}
    return {
        "workflow_progress": workflow_progress if isinstance(workflow_progress, dict) else {},
        "session_execution_state": session_execution_state if isinstance(session_execution_state, dict) else {},
        "intermediate_outputs": intermediate_outputs if isinstance(intermediate_outputs, list) else [],
        "assembly_state": assembly_state if isinstance(assembly_state, dict) else {},
    }


_MEMORY_STORES: dict[str, dict[str, Any]] = {}
_MEMORY_LOCK = threading.Lock()


def _store_key(db_path: str | Path | None) -> str:
    requested = Path(db_path or os.getenv("RAGENIUS_APP_STATE_DB") or _default_state_db()).resolve()
    return str(requested)


def _blank_store() -> dict[str, Any]:
    return {
        "sessions": {},
        "messages": [],
        "uploads": {},
        "compiled": [],
        "reviews": [],
        "approvals": [],
        "revisions": [],
    }


class _RuntimeStateMemory:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self._key = _store_key(db_path)
        self.db_path = Path(db_path or os.getenv("RAGENIUS_APP_STATE_DB") or _default_state_db()).resolve()
        self.uploads_dir = Path(os.getenv("RAGENIUS_APP_UPLOADS_DIR") or _default_uploads_dir()).resolve()
        self._lock = _MEMORY_LOCK
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_sqlite_schema()
        with self._lock:
            _MEMORY_STORES.setdefault(self._key, _blank_store())

    @property
    def _store(self) -> dict[str, Any]:
        return _MEMORY_STORES[self._key]

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _managed_connection(self):
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _ensure_sqlite_schema(self) -> None:
        with self._managed_connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    collection_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    title TEXT,
                    pinned INTEGER NOT NULL DEFAULT 0,
                    archived INTEGER NOT NULL DEFAULT 0,
                    runtime_state_json TEXT NOT NULL,
                    workflow_progress_json TEXT NOT NULL,
                    config_version INTEGER NOT NULL,
                    adapter_version INTEGER NOT NULL,
                    template_version INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    citations_json TEXT NOT NULL,
                    missing_info_types_json TEXT NOT NULL,
                    retrieval_summary_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_messages_session_created
                    ON messages(session_id, created_at, id);
                CREATE TABLE IF NOT EXISTS uploads (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    mime_type TEXT,
                    size_bytes INTEGER NOT NULL,
                    file_path TEXT NOT NULL,
                    text_content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_uploads_session_created
                    ON uploads(session_id, created_at, id);
                """
            )
            session_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(sessions)").fetchall()
            }
            if "runtime_state_json" not in session_columns:
                connection.execute("ALTER TABLE sessions ADD COLUMN runtime_state_json TEXT NOT NULL DEFAULT '{}'")
            if "workflow_progress_json" not in session_columns:
                connection.execute("ALTER TABLE sessions ADD COLUMN workflow_progress_json TEXT NOT NULL DEFAULT '{}'")
            if "archived" not in session_columns:
                connection.execute("ALTER TABLE sessions ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")
            if "pinned" not in session_columns:
                connection.execute("ALTER TABLE sessions ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0")

            message_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(messages)").fetchall()
            }
            if "citations_json" not in message_columns:
                connection.execute("ALTER TABLE messages ADD COLUMN citations_json TEXT NOT NULL DEFAULT '[]'")
            if "missing_info_types_json" not in message_columns:
                connection.execute("ALTER TABLE messages ADD COLUMN missing_info_types_json TEXT NOT NULL DEFAULT '[]'")
            if "retrieval_summary_json" not in message_columns:
                connection.execute("ALTER TABLE messages ADD COLUMN retrieval_summary_json TEXT NOT NULL DEFAULT '{}'")

            upload_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(uploads)").fetchall()
            }
            if "text_content" not in upload_columns:
                connection.execute("ALTER TABLE uploads ADD COLUMN text_content TEXT NOT NULL DEFAULT ''")

    def _row_to_session(self, row: sqlite3.Row | None) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        runtime_state = _normalize_runtime_state(json.loads(str(row["runtime_state_json"] or "{}")))
        return {
            "id": row["id"],
            "collection_id": row["collection_id"],
            "user_id": row["user_id"],
            "title": row["title"],
            "pinned": bool(row["pinned"]),
            "archived": bool(row["archived"]),
            "runtime_state": runtime_state,
            "workflow_progress": runtime_state.get("workflow_progress", {}),
            "config_version": int(row["config_version"]),
            "adapter_version": int(row["adapter_version"]),
            "template_version": int(row["template_version"]),
            "created_at": row["created_at"],
        }

    def reset_sessions(self) -> None:
        with self._managed_connection() as connection:
            connection.execute("DELETE FROM messages")
            connection.execute("DELETE FROM uploads")
            connection.execute("DELETE FROM sessions")
        if self.uploads_dir.exists():
            for path in sorted(self.uploads_dir.glob("**/*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()

    def reset_messages(self) -> None:
        with self._managed_connection() as connection:
            connection.execute("DELETE FROM messages")

    def reset_instruction_understanding(self) -> None:
        with self._lock:
            self._store["compiled"] = []
            self._store["reviews"] = []
            self._store["approvals"] = []
            self._store["revisions"] = []

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._managed_connection() as connection:
            row = connection.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        payload = self._row_to_session(row)
        return deepcopy(payload) if isinstance(payload, dict) else None

    def list_sessions(self, collection_id: str, user_id: str, *, include_archived: bool = False) -> List[Dict[str, Any]]:
        query = "SELECT * FROM sessions WHERE collection_id = ? AND user_id = ?"
        params: list[Any] = [collection_id, user_id]
        if not include_archived:
            query += " AND archived = 0"
        with self._managed_connection() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
            sessions = []
            for row in rows:
                item = self._row_to_session(row) or {}
                last_message = connection.execute(
                    "SELECT role, content, created_at FROM messages WHERE session_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
                    (item["id"],),
                ).fetchone()
                item["last_message_at"] = last_message["created_at"] if last_message else None
                item["last_message_role"] = last_message["role"] if last_message else None
                item["last_message_preview"] = last_message["content"] if last_message else None
                sessions.append(item)
        sessions.sort(
            key=lambda item: (
                0 if item.get("pinned") else 1,
                item.get("last_message_at") or item.get("created_at") or "",
                item.get("created_at") or "",
            ),
            reverse=False,
        )
        return sessions

    def insert_session(
        self,
        session_id: str,
        *,
        collection_id: str,
        user_id: str,
        title: str | None,
        pinned: bool,
        archived: bool,
        config_version: int,
        adapter_version: int,
        template_version: int,
    ) -> Dict[str, Any]:
        row = {
            "id": session_id,
            "collection_id": collection_id,
            "user_id": user_id,
            "title": title,
            "pinned": bool(pinned),
            "archived": bool(archived),
            "runtime_state": _normalize_runtime_state({}),
            "workflow_progress": {},
            "config_version": config_version,
            "adapter_version": adapter_version,
            "template_version": template_version,
            "created_at": _utcnow(),
        }
        with self._managed_connection() as connection:
            connection.execute(
                """
                INSERT INTO sessions (
                    id, collection_id, user_id, title, pinned, archived,
                    runtime_state_json, workflow_progress_json,
                    config_version, adapter_version, template_version, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row["collection_id"],
                    row["user_id"],
                    row["title"],
                    1 if row["pinned"] else 0,
                    1 if row["archived"] else 0,
                    json.dumps(row["runtime_state"], ensure_ascii=False),
                    json.dumps(row["workflow_progress"], ensure_ascii=False),
                    row["config_version"],
                    row["adapter_version"],
                    row["template_version"],
                    row["created_at"],
                ),
            )
        return deepcopy(row)

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        citations: Optional[List[Dict[str, Any]]] = None,
        missing_info_types: Optional[List[str]] = None,
        retrieval_summary: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        row = {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "role": role,
            "content": content,
            "citations": deepcopy(list(citations or [])),
            "missing_infoTypes": list(missing_info_types or []),
            "retrievalSummary": deepcopy(dict(retrieval_summary or {})),
            "created_at": _utcnow(),
        }
        with self._managed_connection() as connection:
            connection.execute(
                """
                INSERT INTO messages (
                    id, session_id, role, content, citations_json,
                    missing_info_types_json, retrieval_summary_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row["session_id"],
                    row["role"],
                    row["content"],
                    json.dumps(row["citations"], ensure_ascii=False),
                    json.dumps(row["missing_infoTypes"], ensure_ascii=False),
                    json.dumps(row["retrievalSummary"], ensure_ascii=False),
                    row["created_at"],
                ),
            )
        return row

    def history(self, session_id: str) -> List[Dict[str, Any]]:
        with self._managed_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC, id ASC",
                (session_id,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "session_id": row["session_id"],
                "role": row["role"],
                "content": row["content"],
                "citations": deepcopy(json.loads(str(row["citations_json"] or "[]"))),
                "missing_infoTypes": list(json.loads(str(row["missing_info_types_json"] or "[]"))),
                "retrievalSummary": deepcopy(json.loads(str(row["retrieval_summary_json"] or "{}"))),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def update_session_title(self, session_id: str, title: str) -> Optional[Dict[str, Any]]:
        with self._managed_connection() as connection:
            connection.execute("UPDATE sessions SET title = ? WHERE id = ?", (title.strip() or None, session_id))
        return self.get_session(session_id)

    def update_session_flags(self, session_id: str, *, pinned: bool | None = None, archived: bool | None = None) -> Optional[Dict[str, Any]]:
        assignments: list[str] = []
        params: list[Any] = []
        if pinned is not None:
            assignments.append("pinned = ?")
            params.append(1 if pinned else 0)
        if archived is not None:
            assignments.append("archived = ?")
            params.append(1 if archived else 0)
        if assignments:
            params.append(session_id)
            with self._managed_connection() as connection:
                connection.execute(f"UPDATE sessions SET {', '.join(assignments)} WHERE id = ?", tuple(params))
        return self.get_session(session_id)

    def delete_session(self, session_id: str) -> bool:
        uploads = self.list_session_uploads(session_id)
        with self._managed_connection() as connection:
            existed = connection.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,)).fetchone() is not None
            connection.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            connection.execute("DELETE FROM uploads WHERE session_id = ?", (session_id,))
            connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        for upload in uploads:
            file_path = Path(str(upload.get("file_path") or ""))
            if file_path.exists():
                file_path.unlink()
        upload_dir = self.uploads_dir / session_id
        if upload_dir.exists() and upload_dir.is_dir():
            for path in sorted(upload_dir.glob("**/*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            upload_dir.rmdir()
        return existed

    def update_session_workflow_state(self, session_id: str, workflow_progress: Dict[str, Any] | None) -> Optional[Dict[str, Any]]:
        session = self.get_session(session_id)
        if not isinstance(session, dict):
            return None
        state = _normalize_runtime_state(session.get("runtime_state") or {})
        state["workflow_progress"] = workflow_progress if isinstance(workflow_progress, dict) else {}
        with self._managed_connection() as connection:
            connection.execute(
                "UPDATE sessions SET runtime_state_json = ?, workflow_progress_json = ? WHERE id = ?",
                (
                    json.dumps(state, ensure_ascii=False),
                    json.dumps(state["workflow_progress"], ensure_ascii=False),
                    session_id,
                ),
            )
        return self.get_session(session_id)

    def update_session_runtime_state(self, session_id: str, runtime_state: Dict[str, Any] | None) -> Optional[Dict[str, Any]]:
        state = _normalize_runtime_state(runtime_state or {})
        with self._managed_connection() as connection:
            connection.execute(
                "UPDATE sessions SET runtime_state_json = ?, workflow_progress_json = ? WHERE id = ?",
                (
                    json.dumps(state, ensure_ascii=False),
                    json.dumps(state.get("workflow_progress", {}), ensure_ascii=False),
                    session_id,
                ),
            )
        return self.get_session(session_id)

    def save_session_upload(
        self,
        session_id: str,
        *,
        filename: str,
        mime_type: str | None,
        content: bytes,
        text_content: str,
    ) -> Dict[str, Any]:
        file_path = self.uploads_dir / session_id / f"{uuid.uuid4()}_{Path(filename).name}"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(content)
        row = {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "filename": Path(filename).name,
            "mime_type": mime_type,
            "size_bytes": len(content),
            "file_path": str(file_path),
            "text_content": text_content,
            "created_at": _utcnow(),
        }
        with self._managed_connection() as connection:
            connection.execute(
                """
                INSERT INTO uploads (
                    id, session_id, filename, mime_type, size_bytes, file_path, text_content, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row["session_id"],
                    row["filename"],
                    row["mime_type"],
                    row["size_bytes"],
                    row["file_path"],
                    row["text_content"],
                    row["created_at"],
                ),
            )
        return row

    def list_session_uploads(self, session_id: str) -> List[Dict[str, Any]]:
        with self._managed_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM uploads WHERE session_id = ? ORDER BY created_at ASC, id ASC",
                (session_id,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "session_id": row["session_id"],
                "filename": row["filename"],
                "mime_type": row["mime_type"],
                "size_bytes": int(row["size_bytes"]),
                "file_path": row["file_path"],
                "text_content": row["text_content"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def save_compiled_instruction_understanding(
        self,
        *,
        app_id: str,
        instruction_source_hash: str,
        instruction_source_version: int | None,
        instruction_uri: str | None,
        parser_contract_version: str,
        binding_logic_version: str,
        resource_catalog_hash: str,
        compiled_status: str,
        compile_duration_ms: int,
        compile_errors: List[str] | None,
        compiled_contract: Dict[str, Any],
        metadata: Dict[str, Any] | None = None,
        is_active: bool = True,
    ) -> Dict[str, Any]:
        row = {
            "id": str(uuid.uuid4()),
            "app_id": app_id,
            "instruction_source_hash": instruction_source_hash,
            "instruction_source_version": instruction_source_version,
            "instruction_uri": instruction_uri,
            "parser_contract_version": parser_contract_version,
            "binding_logic_version": binding_logic_version,
            "resource_catalog_hash": resource_catalog_hash,
            "compiled_status": compiled_status,
            "compiled_at": _utcnow(),
            "compile_duration_ms": int(compile_duration_ms or 0),
            "compile_errors": list(compile_errors or []),
            "compiled_contract": deepcopy(dict(compiled_contract or {})),
            "metadata": deepcopy(dict(metadata or {})),
            "is_active": bool(is_active),
        }
        with self._lock:
            if bool(is_active):
                for item in self._store["compiled"]:
                    if item["app_id"] == app_id:
                        item["is_active"] = False
                for item in self._store["reviews"]:
                    if item["app_id"] == app_id:
                        item["is_active"] = False
            self._store["compiled"].append(deepcopy(row))
        return row

    def restore_compiled_instruction_understanding(self, record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        row = deepcopy(record) if isinstance(record, dict) else None
        if not isinstance(row, dict):
            return None
        app_id = str(row.get("app_id") or "").strip()
        record_id = str(row.get("id") or "").strip()
        if not app_id or not record_id:
            return None
        row["compile_errors"] = list(row.get("compile_errors") or [])
        row["compiled_contract"] = deepcopy(dict(row.get("compiled_contract") or {}))
        row["metadata"] = deepcopy(dict(row.get("metadata") or {}))
        row["is_active"] = bool(row.get("is_active", True))
        row["compile_duration_ms"] = int(row.get("compile_duration_ms") or 0)
        with self._lock:
            if bool(row["is_active"]):
                for item in self._store["compiled"]:
                    if item["app_id"] == app_id:
                        item["is_active"] = False
                for item in self._store["reviews"]:
                    if item["app_id"] == app_id:
                        item["is_active"] = False
            existing_index = None
            for index, item in enumerate(self._store["compiled"]):
                if str(item.get("id") or "").strip() == record_id:
                    existing_index = index
                    break
            if existing_index is not None:
                self._store["compiled"][existing_index] = deepcopy(row)
            else:
                self._store["compiled"].append(deepcopy(row))
        return deepcopy(row)

    def _select_latest(self, rows: list[dict[str, Any]], *, app_id: str, active_only: bool = False, order_key: str = "compiled_at") -> Optional[Dict[str, Any]]:
        candidates = [row for row in rows if row.get("app_id") == app_id and (not active_only or bool(row.get("is_active")))]
        if not candidates:
            return None
        candidates.sort(key=lambda row: (str(row.get(order_key) or ""), str(row.get("id") or "")), reverse=True)
        return deepcopy(candidates[0])

    def get_active_compiled_instruction_understanding(self, app_id: str) -> Optional[Dict[str, Any]]:
        return self._select_latest(self._store["compiled"], app_id=app_id, active_only=True, order_key="compiled_at")

    def get_latest_compiled_instruction_understanding(self, app_id: str) -> Optional[Dict[str, Any]]:
        return self._select_latest(self._store["compiled"], app_id=app_id, active_only=False, order_key="compiled_at")

    def publish_compiled_instruction_understanding(self, app_id: str, compiled_record_id: str) -> Optional[Dict[str, Any]]:
        target_id = str(compiled_record_id or "").strip()
        if not target_id:
            return None
        with self._lock:
            found = None
            for row in self._store["compiled"]:
                if row["app_id"] == app_id:
                    row["is_active"] = False
                if row["app_id"] == app_id and row["id"] == target_id:
                    found = row
            if isinstance(found, dict):
                found["is_active"] = True
                return deepcopy(found)
            return None

    def save_instruction_understanding_review(
        self,
        *,
        app_id: str,
        instruction_source_hash: str,
        parser_contract_version: str,
        review_model: str | None,
        review_prompt_version: str,
        review_status: str,
        review_confidence: float | None,
        review_findings: Dict[str, Any] | None,
        review_summary_md: str,
        review_recommendations: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        row = {
            "id": str(uuid.uuid4()),
            "app_id": app_id,
            "instruction_source_hash": instruction_source_hash,
            "parser_contract_version": parser_contract_version,
            "review_model": review_model,
            "review_prompt_version": review_prompt_version,
            "review_status": review_status,
            "reviewed_at": _utcnow(),
            "review_confidence": review_confidence,
            "review_findings": deepcopy(dict(review_findings or {})),
            "review_summary_md": review_summary_md or "",
            "review_recommendations": deepcopy(dict(review_recommendations or {})),
            "is_active": True,
        }
        with self._lock:
            for item in self._store["reviews"]:
                if item["app_id"] == app_id:
                    item["is_active"] = False
            self._store["reviews"].append(deepcopy(row))
        return row

    def get_active_instruction_understanding_review(self, app_id: str) -> Optional[Dict[str, Any]]:
        return self._select_latest(self._store["reviews"], app_id=app_id, active_only=True, order_key="reviewed_at")

    def save_instruction_understanding_approval(
        self,
        *,
        app_id: str,
        compiled_record_id: str,
        review_record_id: str,
        approved_findings: List[Dict[str, Any]] | None,
        approver: str | None,
    ) -> Dict[str, Any]:
        row = {
            "id": str(uuid.uuid4()),
            "app_id": app_id,
            "compiled_record_id": compiled_record_id,
            "review_record_id": review_record_id,
            "approved_findings": deepcopy(list(approved_findings or [])),
            "approver": approver,
            "approved_at": _utcnow(),
            "is_active": True,
        }
        with self._lock:
            for item in self._store["approvals"]:
                if item["app_id"] == app_id:
                    item["is_active"] = False
            self._store["approvals"].append(deepcopy(row))
        return row

    def get_active_instruction_understanding_approval(self, app_id: str) -> Optional[Dict[str, Any]]:
        return self._select_latest(self._store["approvals"], app_id=app_id, active_only=True, order_key="approved_at")

    def save_instruction_understanding_revision(
        self,
        *,
        app_id: str,
        compiled_record_id: str,
        review_record_id: str | None,
        approval_record_id: str | None,
        instruction_source_hash: str,
        parser_contract_version: str,
        revision_prompt_version: str,
        revision_status: str,
        revised_contract: Dict[str, Any] | None,
        revision_notes: List[str] | None,
        preserved_ids: List[str] | None,
        changed_ids: List[str] | None,
        revision_confidence: float | None,
    ) -> Dict[str, Any]:
        row = {
            "id": str(uuid.uuid4()),
            "app_id": app_id,
            "compiled_record_id": compiled_record_id,
            "review_record_id": review_record_id,
            "approval_record_id": approval_record_id,
            "instruction_source_hash": instruction_source_hash,
            "parser_contract_version": parser_contract_version,
            "revision_prompt_version": revision_prompt_version,
            "revision_status": revision_status,
            "revised_contract": deepcopy(dict(revised_contract or {})),
            "revision_notes": list(revision_notes or []),
            "preserved_ids": list(preserved_ids or []),
            "changed_ids": list(changed_ids or []),
            "revision_confidence": revision_confidence,
            "revised_at": _utcnow(),
            "is_active": True,
        }
        with self._lock:
            for item in self._store["revisions"]:
                if item["app_id"] == app_id:
                    item["is_active"] = False
            self._store["revisions"].append(deepcopy(row))
        return row

    def get_active_instruction_understanding_revision(self, app_id: str) -> Optional[Dict[str, Any]]:
        return self._select_latest(self._store["revisions"], app_id=app_id, active_only=True, order_key="revised_at")


class SessionRepo:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db = _RuntimeStateMemory(db_path)

    def reset(self) -> None:
        self._db.reset_sessions()

    def get_or_create(
        self,
        session_id: str,
        *,
        collection_id: str,
        user_id: str,
        title: str | None = None,
        pinned: bool = False,
        archived: bool = False,
        config_version: int,
        adapter_version: int,
        template_version: int,
    ) -> Dict[str, Any]:
        existing = self._db.get_session(session_id)
        if existing is not None:
            if existing["collection_id"] != collection_id or existing["user_id"] != user_id:
                raise ValueError("Session identity mismatch.")
            return existing
        return self._db.insert_session(
            session_id,
            collection_id=collection_id,
            user_id=user_id,
            title=title,
            pinned=pinned,
            archived=archived,
            config_version=config_version,
            adapter_version=adapter_version,
            template_version=template_version,
        )

    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self._db.get_session(session_id)

    def list_for_app_user(self, collection_id: str, user_id: str, *, include_archived: bool = False) -> List[Dict[str, Any]]:
        return self._db.list_sessions(collection_id, user_id, include_archived=include_archived)

    def set_title(self, session_id: str, title: str) -> Optional[Dict[str, Any]]:
        return self._db.update_session_title(session_id, title)

    def set_flags(self, session_id: str, *, pinned: bool | None = None, archived: bool | None = None) -> Optional[Dict[str, Any]]:
        return self._db.update_session_flags(session_id, pinned=pinned, archived=archived)

    def delete(self, session_id: str) -> bool:
        return self._db.delete_session(session_id)

    def set_workflow_progress(self, session_id: str, workflow_progress: Dict[str, Any] | None) -> Optional[Dict[str, Any]]:
        return self._db.update_session_workflow_state(session_id, workflow_progress)

    def get_runtime_state(self, session_id: str) -> Dict[str, Any]:
        session = self._db.get_session(session_id)
        if session is None:
            return _normalize_runtime_state({})
        return _normalize_runtime_state(session.get("runtime_state") or {})

    def set_runtime_state(self, session_id: str, runtime_state: Dict[str, Any] | None) -> Optional[Dict[str, Any]]:
        return self._db.update_session_runtime_state(session_id, runtime_state)

    def add_upload(
        self,
        session_id: str,
        *,
        filename: str,
        mime_type: str | None,
        content: bytes,
        text_content: str,
    ) -> Dict[str, Any]:
        return self._db.save_session_upload(
            session_id,
            filename=filename,
            mime_type=mime_type,
            content=content,
            text_content=text_content,
        )

    def list_uploads(self, session_id: str) -> List[Dict[str, Any]]:
        return self._db.list_session_uploads(session_id)


class ChatRepo:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db = _RuntimeStateMemory(db_path)

    def reset(self) -> None:
        self._db.reset_messages()

    def append(
        self,
        session_id: str,
        role: str,
        content: str,
        citations: Optional[List[Dict[str, Any]]] = None,
        missing_info_types: Optional[List[str]] = None,
        retrieval_summary: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self._db.append_message(
            session_id,
            role,
            content,
            citations=citations,
            missing_info_types=missing_info_types,
            retrieval_summary=retrieval_summary,
        )

    def history(self, session_id: str) -> List[Dict[str, Any]]:
        return self._db.history(session_id)


class InstructionUnderstandingRepo:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db = _RuntimeStateMemory(db_path)

    def reset(self) -> None:
        self._db.reset_instruction_understanding()

    def get_active_compiled(self, app_id: str) -> Optional[Dict[str, Any]]:
        return self._db.get_active_compiled_instruction_understanding(app_id)

    def get_latest_compiled(self, app_id: str) -> Optional[Dict[str, Any]]:
        return self._db.get_latest_compiled_instruction_understanding(app_id)

    def save_compiled(
        self,
        *,
        app_id: str,
        instruction_source_hash: str,
        instruction_source_version: int | None,
        instruction_uri: str | None,
        parser_contract_version: str,
        binding_logic_version: str,
        resource_catalog_hash: str,
        compiled_status: str,
        compile_duration_ms: int,
        compile_errors: List[str] | None,
        compiled_contract: Dict[str, Any],
        metadata: Dict[str, Any] | None = None,
        is_active: bool = True,
    ) -> Dict[str, Any]:
        return self._db.save_compiled_instruction_understanding(
            app_id=app_id,
            instruction_source_hash=instruction_source_hash,
            instruction_source_version=instruction_source_version,
            instruction_uri=instruction_uri,
            parser_contract_version=parser_contract_version,
            binding_logic_version=binding_logic_version,
            resource_catalog_hash=resource_catalog_hash,
            compiled_status=compiled_status,
            compile_duration_ms=compile_duration_ms,
            compile_errors=compile_errors,
            compiled_contract=compiled_contract,
            metadata=metadata,
            is_active=is_active,
        )

    def restore_compiled(self, record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self._db.restore_compiled_instruction_understanding(record)

    def publish_compiled(self, app_id: str, compiled_record_id: str) -> Optional[Dict[str, Any]]:
        return self._db.publish_compiled_instruction_understanding(app_id, compiled_record_id)

    def get_active_review(self, app_id: str) -> Optional[Dict[str, Any]]:
        return self._db.get_active_instruction_understanding_review(app_id)

    def save_review(
        self,
        *,
        app_id: str,
        instruction_source_hash: str,
        parser_contract_version: str,
        review_model: str | None,
        review_prompt_version: str,
        review_status: str,
        review_confidence: float | None,
        review_findings: Dict[str, Any] | None,
        review_summary_md: str,
        review_recommendations: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        return self._db.save_instruction_understanding_review(
            app_id=app_id,
            instruction_source_hash=instruction_source_hash,
            parser_contract_version=parser_contract_version,
            review_model=review_model,
            review_prompt_version=review_prompt_version,
            review_status=review_status,
            review_confidence=review_confidence,
            review_findings=review_findings,
            review_summary_md=review_summary_md,
            review_recommendations=review_recommendations,
        )

    def get_active_approval(self, app_id: str) -> Optional[Dict[str, Any]]:
        return self._db.get_active_instruction_understanding_approval(app_id)

    def save_approval(
        self,
        *,
        app_id: str,
        compiled_record_id: str,
        review_record_id: str,
        approved_findings: List[Dict[str, Any]] | None,
        approver: str | None = None,
    ) -> Dict[str, Any]:
        return self._db.save_instruction_understanding_approval(
            app_id=app_id,
            compiled_record_id=compiled_record_id,
            review_record_id=review_record_id,
            approved_findings=approved_findings,
            approver=approver,
        )

    def get_active_revision(self, app_id: str) -> Optional[Dict[str, Any]]:
        return self._db.get_active_instruction_understanding_revision(app_id)

    def save_revision(
        self,
        *,
        app_id: str,
        compiled_record_id: str,
        review_record_id: str | None,
        approval_record_id: str | None,
        instruction_source_hash: str,
        parser_contract_version: str,
        revision_prompt_version: str,
        revision_status: str,
        revised_contract: Dict[str, Any] | None,
        revision_notes: List[str] | None,
        preserved_ids: List[str] | None,
        changed_ids: List[str] | None,
        revision_confidence: float | None,
    ) -> Dict[str, Any]:
        return self._db.save_instruction_understanding_revision(
            app_id=app_id,
            compiled_record_id=compiled_record_id,
            review_record_id=review_record_id,
            approval_record_id=approval_record_id,
            instruction_source_hash=instruction_source_hash,
            parser_contract_version=parser_contract_version,
            revision_prompt_version=revision_prompt_version,
            revision_status=revision_status,
            revised_contract=revised_contract,
            revision_notes=revision_notes,
            preserved_ids=preserved_ids,
            changed_ids=changed_ids,
            revision_confidence=revision_confidence,
        )


class RetrievalRepo:
    def __init__(self) -> None:
        self._rows: List[Dict[str, Any]] = []

    def reset(self) -> None:
        self._rows.clear()

    def save(self, planner_output_id: str, retrieval_plan: Dict[str, Any], result_count: int, debug_trace: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        row = {
            "id": str(uuid.uuid4()),
            "planner_output_id": planner_output_id,
            "retrieval_plan": retrieval_plan,
            "result_count": result_count,
            "debug_trace": debug_trace,
            "created_at": _utcnow(),
        }
        self._rows.append(row)
        return row
