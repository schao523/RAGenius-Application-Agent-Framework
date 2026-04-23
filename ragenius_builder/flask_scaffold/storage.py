import json
import uuid
import datetime
import sqlite3
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional


class ValidationSchema:
    def validate(self, payload: Dict[str, Any]) -> Tuple[bool, List[Dict[str, str]]]:
        raise NotImplementedError


class ApplicationSchema(ValidationSchema):
    required_fields = ["name", "slug"]

    def validate(self, payload: Dict[str, Any]):
        errors = []
        for field in self.required_fields:
            if not payload.get(field):
                errors.append({"path": field, "msg": "Required", "code": "required"})
        if "slug" in payload and payload.get("slug"):
            if payload["slug"] != payload["slug"].lower().replace(" ", "-"):
                errors.append({"path": "slug", "msg": "Slug must be lower-kebab-case", "code": "format"})
        return (len(errors) == 0, errors)


class SettingsSchema(ValidationSchema):
    def validate(self, payload: Dict[str, Any]):
        errors = []
        config_settings = payload.get("config_settings", "")
        config_schema = payload.get("config_schema", "")
        for field, value in {"config_settings": config_settings, "config_schema": config_schema}.items():
            if not value:
                errors.append({"path": field, "msg": "Required", "code": "required"})
            else:
                try:
                    json.loads(value)
                except Exception:
                    errors.append({"path": field, "msg": "Must be valid JSON", "code": "json"})
        return (len(errors) == 0, errors)


class InstructionsSchema(ValidationSchema):
    def validate(self, payload: Dict[str, Any]):
        errors = []
        if not payload.get("content"):
            errors.append({"path": "content", "msg": "Required", "code": "required"})
        if not payload.get("uri"):
            errors.append({"path": "uri", "msg": "Required", "code": "required"})
        return (len(errors) == 0, errors)


class DocumentUploadSchema(ValidationSchema):
    def validate(self, payload: Dict[str, Any]):
        errors = []
        if not payload.get("filename"):
            errors.append({"path": "filename", "msg": "Required", "code": "required"})
        if payload.get("size_bytes"):
            try:
                int(payload["size_bytes"])
            except ValueError:
                errors.append({"path": "size_bytes", "msg": "Must be number", "code": "format"})
        return (len(errors) == 0, errors)


class DatabaseStore:
    def __init__(self, db_path: Path | str = "rag_app.db"):
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
        self.seed()

    def _create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS applications (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                description TEXT,
                starter_questions TEXT,
                updated_at TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS instructions (
                app_id TEXT PRIMARY KEY,
                content TEXT,
                uri TEXT,
                version TEXT,
                updated_at TEXT,
                FOREIGN KEY(app_id) REFERENCES applications(id) ON DELETE CASCADE
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                app_id TEXT PRIMARY KEY,
                config_settings TEXT,
                config_schema TEXT,
                updated_at TEXT,
                FOREIGN KEY(app_id) REFERENCES applications(id) ON DELETE CASCADE
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                app_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                mime_type TEXT,
                size_bytes INTEGER,
                language TEXT,
                tags TEXT,
                status TEXT,
                error_message TEXT,
                uploaded_at TEXT,
                FOREIGN KEY(app_id) REFERENCES applications(id) ON DELETE CASCADE
            )
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_documents_app_id ON documents(app_id)")
        self.conn.commit()

    def seed(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM applications")
        if cursor.fetchone()["count"] > 0:
            return

        sample_app_id = str(uuid.uuid4())
        now = datetime.datetime.utcnow().isoformat()
        starter_questions = [
            "What documents are available?",
            "How recent is the content?",
            "What languages are supported?",
            "How do I upload a file?",
        ]
        cursor.execute(
            """
            INSERT INTO applications (id, name, slug, description, starter_questions, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                sample_app_id,
                "Docs Example",
                "docs-example",
                "Starter RAG app",
                json.dumps(starter_questions),
                now,
            ),
        )
        cursor.execute(
            """
            INSERT INTO instructions (app_id, content, uri, version, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                sample_app_id,
                "# Welcome\nProvide answers based on uploaded docs.",
                f"instructions/{sample_app_id}/instructions.md",
                "v1",
                now,
            ),
        )
        cursor.execute(
            """
            INSERT INTO settings (app_id, config_settings, config_schema, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                sample_app_id,
                json.dumps(
                    {
                        "embedding_model": "text-embedding-3-small",
                        "chunk_size": 500,
                        "language": "en",
                    },
                    indent=2,
                ),
                json.dumps(
                    {
                        "type": "object",
                        "properties": {
                            "embedding_model": {
                                "enum": ["text-embedding-3-small", "text-embedding-3-large"]
                            },
                            "chunk_size": {"type": "integer", "minimum": 100, "maximum": 1000},
                            "language": {"enum": ["en", "es", "fr"]},
                        },
                        "required": ["embedding_model", "chunk_size", "language"],
                    },
                    indent=2,
                ),
                now,
            ),
        )
        cursor.execute(
            """
            INSERT INTO documents (id, app_id, filename, mime_type, size_bytes, language, tags, status, error_message, uploaded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                sample_app_id,
                "handbook.pdf",
                "application/pdf",
                120934,
                "en",
                json.dumps(["hr"]),
                "ready",
                None,
                now,
            ),
        )
        self.conn.commit()

    def _app_from_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "slug": row["slug"],
            "description": row["description"] or "",
            "starter_questions": json.loads(row["starter_questions"] or "[]"),
            "updated_at": row["updated_at"],
        }

    def _document_from_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "app_id": row["app_id"],
            "filename": row["filename"],
            "mime_type": row["mime_type"],
            "size_bytes": row["size_bytes"],
            "language": row["language"],
            "tags": json.loads(row["tags"] or "[]"),
            "status": row["status"],
            "error_message": row["error_message"],
            "uploaded_at": row["uploaded_at"],
        }

    def list_applications(self) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM applications ORDER BY updated_at DESC")
        return [self._app_from_row(row) for row in cursor.fetchall()]

    def get_application(self, app_id: str) -> Optional[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM applications WHERE id = ?", (app_id,))
        row = cursor.fetchone()
        return self._app_from_row(row) if row else None

    def get_application_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM applications WHERE lower(name) = lower(?) LIMIT 1",
            (name,),
        )
        row = cursor.fetchone()
        return self._app_from_row(row) if row else None

    def create_application(self, payload: Dict[str, Any]):
        app_id = str(uuid.uuid4())
        now = datetime.datetime.utcnow().isoformat()
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO applications (id, name, slug, description, starter_questions, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    app_id,
                    payload.get("name"),
                    payload.get("slug"),
                    payload.get("description", ""),
                    json.dumps(payload.get("starter_questions", [])),
                    now,
                ),
            )
            cursor.execute(
                """
                INSERT INTO instructions (app_id, content, uri, version, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    app_id,
                    payload.get("instructions", ""),
                    f"instructions/{app_id}/instructions.md",
                    payload.get("version", "v1"),
                    now,
                ),
            )
            cursor.execute(
                """
                INSERT INTO settings (app_id, config_settings, config_schema, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    app_id,
                    json.dumps({}, indent=2),
                    json.dumps({}, indent=2),
                    now,
                ),
            )
            self.conn.commit()
        except sqlite3.IntegrityError:
            return None
        return self.get_application(app_id)

    def update_application(self, app_id: str, payload: Dict[str, Any]):
        cursor = self.conn.cursor()
        payload = payload or {}
        cursor.execute(
            "UPDATE applications SET description = COALESCE(?, description), starter_questions = COALESCE(?, starter_questions), updated_at = ? WHERE id = ?",
            (
                payload.get("description"),
                json.dumps(payload.get("starter_questions")) if payload.get("starter_questions") is not None else None,
                datetime.datetime.utcnow().isoformat(),
                app_id,
            ),
        )
        if cursor.rowcount == 0:
            return None
        self.conn.commit()
        return self.get_application(app_id)

    def get_instructions(self, app_id: str):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM instructions WHERE app_id = ?", (app_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "content": row["content"],
            "uri": row["uri"],
            "version": row["version"],
            "updated_at": row["updated_at"],
        }

    def update_instructions(self, app_id: str, payload: Dict[str, Any]):
        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE instructions
            SET content = COALESCE(?, content), uri = COALESCE(?, uri), version = COALESCE(?, version), updated_at = ?
            WHERE app_id = ?
            """,
            (
                payload.get("content"),
                payload.get("uri"),
                payload.get("version"),
                datetime.datetime.utcnow().isoformat(),
                app_id,
            ),
        )
        if cursor.rowcount == 0:
            return None
        self.conn.commit()
        return self.get_instructions(app_id)

    def get_settings(self, app_id: str):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM settings WHERE app_id = ?", (app_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "config_settings": row["config_settings"],
            "config_schema": row["config_schema"],
            "updated_at": row["updated_at"],
        }

    def update_settings(self, app_id: str, payload: Dict[str, Any]):
        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE settings
            SET config_settings = COALESCE(?, config_settings), config_schema = COALESCE(?, config_schema), updated_at = ?
            WHERE app_id = ?
            """,
            (
                payload.get("config_settings"),
                payload.get("config_schema"),
                datetime.datetime.utcnow().isoformat(),
                app_id,
            ),
        )
        if cursor.rowcount == 0:
            return None
        self.conn.commit()
        return self.get_settings(app_id)

    def queue_document(self, app_id: str, payload: Dict[str, Any]):
        if not self.get_application(app_id):
            return None
        doc_id = str(uuid.uuid4())
        now = datetime.datetime.utcnow().isoformat()
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO documents (id, app_id, filename, mime_type, size_bytes, language, tags, status, error_message, uploaded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc_id,
                app_id,
                payload.get("filename"),
                payload.get("mime_type", "application/octet-stream"),
                int(payload.get("size_bytes") or 0),
                payload.get("language", "en"),
                json.dumps(payload.get("tags", [])),
                "pending",
                None,
                now,
            ),
        )
        self.conn.commit()
        return self.get_document(app_id, doc_id)

    def list_documents(self, app_id: str):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM documents WHERE app_id = ? ORDER BY uploaded_at DESC", (app_id,))
        return [self._document_from_row(row) for row in cursor.fetchall()]

    def get_document(self, app_id: str, doc_id: str):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM documents WHERE app_id = ? AND id = ?", (app_id, doc_id))
        row = cursor.fetchone()
        return self._document_from_row(row) if row else None

    def delete_document(self, app_id: str, doc_id: str):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM documents WHERE app_id = ? AND id = ?", (app_id, doc_id))
        self.conn.commit()
        return cursor.rowcount > 0

    def update_document_status(self, app_id: str, doc_id: str, status: str):
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE documents SET status = ?, uploaded_at = uploaded_at WHERE app_id = ? AND id = ?",
            (status, app_id, doc_id),
        )
        self.conn.commit()
        if cursor.rowcount == 0:
            return None
        return self.get_document(app_id, doc_id)


store = DatabaseStore()
