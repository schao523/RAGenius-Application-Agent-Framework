import json
import uuid
import datetime
import sqlite3
import hashlib
import tempfile
import os
import atexit
import re
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional

DEFAULT_APP_CONFIG_SETTINGS = {
    "llm": {
        "provider": "deepseek",
        "models": {
            "planner": "deepseek-v4-pro",
            "answer_generation": "deepseek-v4-flash",
            "adapter_generation": "deepseek-v4-pro",
            "evidence_analysis": "deepseek-v4-flash",
            "config_extraction_fallback": "deepseek-v4-flash",
            "instruction_understanding_compile": "deepseek-v4-pro",
            "instruction_understanding_review": "deepseek-v4-pro",
            "instruction_understanding_revision": "deepseek-v4-pro",
        },
        "temperature": {
            "planner": 0.1,
            "answer_generation": 0.2,
            "adapter_generation": 0.0,
            "evidence_analysis": 0.1,
            "instruction_understanding_compile": 0.2,
            "instruction_understanding_review": 0.2,
            "instruction_understanding_revision": 0.2,
        },
    }
}

DEFAULT_APP_CONFIG_SCHEMA = {
    "type": "object",
    "properties": {
        "llm": {
            "type": "object",
            "properties": {
                "provider": {"type": "string", "default": "deepseek"},
                "models": {
                    "type": "object",
                    "properties": {
                        "planner": {"type": "string", "default": "deepseek-v4-pro"},
                        "answer_generation": {"type": "string", "default": "deepseek-v4-flash"},
                        "adapter_generation": {"type": "string", "default": "deepseek-v4-pro"},
                        "evidence_analysis": {"type": "string", "default": "deepseek-v4-flash"},
                        "config_extraction_fallback": {"type": "string", "default": "deepseek-v4-flash"},
                        "instruction_understanding_compile": {"type": "string", "default": "deepseek-v4-pro"},
                        "instruction_understanding_review": {"type": "string", "default": "deepseek-v4-pro"},
                        "instruction_understanding_revision": {"type": "string", "default": "deepseek-v4-pro"},
                    },
                },
                "temperature": {
                    "type": "object",
                    "properties": {
                        "planner": {"type": "number", "default": 0.1},
                        "answer_generation": {"type": "number", "default": 0.2},
                        "adapter_generation": {"type": "number", "default": 0.0},
                        "evidence_analysis": {"type": "number", "default": 0.1},
                        "instruction_understanding_compile": {"type": "number", "default": 0.2},
                        "instruction_understanding_review": {"type": "number", "default": 0.2},
                        "instruction_understanding_revision": {"type": "number", "default": 0.2},
                    },
                },
            },
        }
    },
}


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
    @staticmethod
    def _is_number(value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    @staticmethod
    def _validate_against_schema(instance: Any, schema: Dict[str, Any], path: str, errors: List[Dict[str, str]]) -> None:
        expected_type = schema.get("type")
        enum_values = schema.get("enum")

        def add_error(msg: str, code: str = "schema"):
            errors.append({"path": path, "msg": msg, "code": code})

        if enum_values is not None and instance not in enum_values:
            add_error(f"Value must be one of {enum_values}", "enum")

        if expected_type == "object":
            if not isinstance(instance, dict):
                add_error("Must be an object", "type")
                return
            properties = schema.get("properties", {}) or {}
            required = schema.get("required", []) or []
            for key in required:
                if key not in instance:
                    errors.append({"path": f"{path}.{key}", "msg": "Required", "code": "required"})
            additional_allowed = schema.get("additionalProperties", True)
            if additional_allowed is False:
                for key in instance.keys():
                    if key not in properties:
                        errors.append(
                            {
                                "path": f"{path}.{key}",
                                "msg": "Unknown property not allowed by schema",
                                "code": "additional_properties",
                            }
                        )
            for key, child_schema in properties.items():
                if key in instance:
                    SettingsSchema._validate_against_schema(instance[key], child_schema or {}, f"{path}.{key}", errors)
            return

        if expected_type == "array":
            if not isinstance(instance, list):
                add_error("Must be an array", "type")
                return
            min_items = schema.get("minItems")
            max_items = schema.get("maxItems")
            if isinstance(min_items, int) and len(instance) < min_items:
                add_error(f"Must contain at least {min_items} item(s)", "min_items")
            if isinstance(max_items, int) and len(instance) > max_items:
                add_error(f"Must contain at most {max_items} item(s)", "max_items")
            item_schema = schema.get("items")
            if isinstance(item_schema, dict):
                for idx, item in enumerate(instance):
                    SettingsSchema._validate_against_schema(item, item_schema, f"{path}[{idx}]", errors)
            return

        if expected_type == "string":
            if not isinstance(instance, str):
                add_error("Must be a string", "type")
                return
            min_length = schema.get("minLength")
            max_length = schema.get("maxLength")
            if isinstance(min_length, int) and len(instance) < min_length:
                add_error(f"Must have at least {min_length} characters", "min_length")
            if isinstance(max_length, int) and len(instance) > max_length:
                add_error(f"Must have at most {max_length} characters", "max_length")
            pattern = schema.get("pattern")
            if isinstance(pattern, str):
                try:
                    if re.search(pattern, instance) is None:
                        add_error("Value does not match required pattern", "pattern")
                except re.error:
                    add_error("Schema pattern is invalid", "schema_pattern")
            return

        if expected_type == "boolean":
            if not isinstance(instance, bool):
                add_error("Must be a boolean", "type")
            return

        if expected_type == "integer":
            if not isinstance(instance, int) or isinstance(instance, bool):
                add_error("Must be an integer", "type")
                return
            minimum = schema.get("minimum")
            maximum = schema.get("maximum")
            if SettingsSchema._is_number(minimum) and instance < minimum:
                add_error(f"Must be >= {minimum}", "minimum")
            if SettingsSchema._is_number(maximum) and instance > maximum:
                add_error(f"Must be <= {maximum}", "maximum")
            return

        if expected_type == "number":
            if not SettingsSchema._is_number(instance):
                add_error("Must be a number", "type")
                return
            minimum = schema.get("minimum")
            maximum = schema.get("maximum")
            if SettingsSchema._is_number(minimum) and instance < minimum:
                add_error(f"Must be >= {minimum}", "minimum")
            if SettingsSchema._is_number(maximum) and instance > maximum:
                add_error(f"Must be <= {maximum}", "maximum")
            return

        if expected_type == "null":
            if instance is not None:
                add_error("Must be null", "type")
            return

    def validate(self, payload: Dict[str, Any]):
        errors = []
        config_settings = payload.get("config_settings", "")
        config_schema = payload.get("config_schema", "")
        parsed_settings = None
        parsed_schema = None
        for field, value in {"config_settings": config_settings, "config_schema": config_schema}.items():
            if not value:
                errors.append({"path": field, "msg": "Required", "code": "required"})
            else:
                try:
                    parsed = json.loads(value)
                    if field == "config_settings":
                        parsed_settings = parsed
                    else:
                        parsed_schema = parsed
                except Exception:
                    errors.append({"path": field, "msg": "Must be valid JSON", "code": "json"})

        if parsed_schema is not None and not isinstance(parsed_schema, dict):
            errors.append({"path": "config_schema", "msg": "Schema must be a JSON object", "code": "schema"})

        if parsed_settings is not None and parsed_schema is not None and isinstance(parsed_schema, dict):
            root_type = parsed_schema.get("type")
            if root_type and root_type != "object":
                errors.append(
                    {
                        "path": "config_schema.type",
                        "msg": "Top-level schema type should be 'object' for config settings",
                        "code": "schema",
                    }
                )
            self._validate_against_schema(parsed_settings, parsed_schema, "config_settings", errors)
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
        self.instructions_root = self.db_path.parent / "instructions"
        self.instructions_root.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
        self.seed()

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass

    def _instructions_rel_uri(self, app_id: str) -> str:
        return f"instructions/{app_id}/instructions.md"

    def _instructions_abs_path(self, app_id: str) -> Path:
        rel = Path(self._instructions_rel_uri(app_id))
        abs_path = self.db_path.parent / rel
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        return abs_path

    def _write_instructions_file(self, app_id: str, content: str) -> str:
        target = self._instructions_abs_path(app_id)
        with tempfile.NamedTemporaryFile(
            "w",
            delete=False,
            encoding="utf-8",
            dir=str(target.parent),
            suffix=".tmp",
        ) as tmp:
            tmp.write(content or "")
            tmp_path = Path(tmp.name)
        tmp_path.replace(target)
        return self._instructions_rel_uri(app_id)

    def _read_instructions_file(self, app_id: str) -> Optional[str]:
        path = self._instructions_abs_path(app_id)
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

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
                file_path TEXT,
                status TEXT,
                error_message TEXT,
                uploaded_at TEXT,
                FOREIGN KEY(app_id) REFERENCES applications(id) ON DELETE CASCADE
            )
            """
        )
        try:
            cursor.execute("ALTER TABLE documents ADD COLUMN file_path TEXT")
        except sqlite3.OperationalError:
            # Column already exists in existing local DBs.
            pass
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
                self._write_instructions_file(
                    sample_app_id,
                    "# Welcome\nProvide answers based on uploaded docs.",
                ),
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
                json.dumps(DEFAULT_APP_CONFIG_SETTINGS, indent=2),
                json.dumps(DEFAULT_APP_CONFIG_SCHEMA, indent=2),
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
            "file_path": row["file_path"],
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
                    self._write_instructions_file(app_id, payload.get("instructions", "")),
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
                    json.dumps(DEFAULT_APP_CONFIG_SETTINGS, indent=2),
                    json.dumps(DEFAULT_APP_CONFIG_SCHEMA, indent=2),
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

    def delete_application(self, app_id: str) -> bool:
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM applications WHERE id = ?", (app_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def get_instructions(self, app_id: str):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM instructions WHERE app_id = ?", (app_id,))
        row = cursor.fetchone()
        if not row:
            return None
        content = self._read_instructions_file(app_id)
        if content is None:
            content = row["content"] or ""
            self._write_instructions_file(app_id, content)
        return {
            "content": content,
            "uri": row["uri"] or self._instructions_rel_uri(app_id),
            "version": row["version"],
            "checksum": hashlib.sha256((content or "").encode("utf-8")).hexdigest(),
            "updated_at": row["updated_at"],
        }

    def update_instructions(self, app_id: str, payload: Dict[str, Any]):
        content = payload.get("content")
        if content is None:
            existing = self.get_instructions(app_id)
            content = existing.get("content", "") if existing else ""
        uri = self._write_instructions_file(app_id, content)

        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE instructions
            SET content = COALESCE(?, content), uri = COALESCE(?, uri), version = COALESCE(?, version), updated_at = ?
            WHERE app_id = ?
            """,
            (
                content,
                uri,
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
            INSERT INTO documents (id, app_id, filename, mime_type, size_bytes, language, tags, file_path, status, error_message, uploaded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc_id,
                app_id,
                payload.get("filename"),
                payload.get("mime_type", "application/octet-stream"),
                int(payload.get("size_bytes") or 0),
                payload.get("language", "en"),
                json.dumps(payload.get("tags", [])),
                payload.get("file_path"),
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

    def update_document_file_path(self, app_id: str, doc_id: str, file_path: str):
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE documents SET file_path = ? WHERE app_id = ? AND id = ?",
            (file_path, app_id, doc_id),
        )
        self.conn.commit()
        if cursor.rowcount == 0:
            return None
        return self.get_document(app_id, doc_id)

    def update_document_status(self, app_id: str, doc_id: str, status: str, error_message: str | None = None):
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE documents SET status = ?, error_message = ?, uploaded_at = uploaded_at WHERE app_id = ? AND id = ?",
            (status, error_message, app_id, doc_id),
        )
        self.conn.commit()
        if cursor.rowcount == 0:
            return None
        return self.get_document(app_id, doc_id)

    def update_document_language(self, app_id: str, doc_id: str, language: str):
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE documents SET language = ? WHERE app_id = ? AND id = ?",
            (language, app_id, doc_id),
        )
        self.conn.commit()
        if cursor.rowcount == 0:
            return None
        return self.get_document(app_id, doc_id)


_BASE_DIR = Path(__file__).resolve().parent
_DEFAULT_DB_PATH = Path(os.environ.get("RAGENIUS_BUILDER_DB", str(_BASE_DIR / "rag_app.db"))).resolve()
store = DatabaseStore(_DEFAULT_DB_PATH)
atexit.register(store.close)
