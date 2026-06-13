import json
import uuid
import datetime
import sqlite3
import hashlib
import tempfile
import os
import atexit
import re
import shutil
import zipfile
import yaml
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

SKILL_LIFECYCLE_STATES = {
    "draft",
    "review",
    "published",
    "active",
    "deprecated",
    "disabled",
    "archived",
}

ALLOWED_SKILL_RESOURCE_DIRS = {"assets", "references", "workflows", "prompts", "schemas"}


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
    def __init__(
        self,
        db_path: Path | str = "rag_app.db",
        *,
        storage_root: Path | str | None = None,
        seed_data: bool = True,
    ):
        self.db_path_value = str(db_path)
        self.db_path = None if self.db_path_value == ":memory:" else Path(db_path).resolve()
        self.base_dir = (
            Path(storage_root).resolve()
            if storage_root is not None
            else (self.db_path.parent if self.db_path else Path.cwd())
        )
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.instructions_root = self.base_dir / "instructions"
        self.skills_root = self.base_dir / "skills"
        self.instructions_root.mkdir(parents=True, exist_ok=True)
        self.skills_root.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path_value, check_same_thread=False)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
        if seed_data:
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
        abs_path = self.base_dir / rel
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        return abs_path

    def _skill_version_rel_root(self, scope: str, skill_id: str, version: str) -> str:
        return f"skills/{scope}/{skill_id}/{version}"

    def _skill_version_abs_root(self, scope: str, skill_id: str, version: str) -> Path:
        root = self.base_dir / self._skill_version_rel_root(scope, skill_id, version)
        root.mkdir(parents=True, exist_ok=True)
        return root

    @staticmethod
    def _slugify(value: str) -> str:
        text = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower())
        return text.strip("-")

    @staticmethod
    def _parse_skill_manifest(markdown: str) -> Dict[str, Any]:
        text = str(markdown or "").replace("\r\n", "\n").replace("\r", "\n")
        if not text.startswith("---\n"):
            raise ValueError("SKILL.md must begin with frontmatter delimited by ---")
        parts = text.split("\n---\n", 1)
        if len(parts) != 2:
            raise ValueError("SKILL.md frontmatter is not properly terminated")
        header_text = parts[0][4:]
        try:
            parsed = yaml.safe_load(header_text) or {}
        except yaml.YAMLError as exc:
            raise ValueError("SKILL.md frontmatter is not valid YAML") from exc
        if not isinstance(parsed, dict):
            raise ValueError("SKILL.md frontmatter must be a YAML object")
        return parsed

    @classmethod
    def _normalize_skill_manifest(cls, manifest: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(manifest or {})
        skill_name = str(normalized.get("name", "")).strip()
        skill_id = str(normalized.get("id", "")).strip()
        version = str(normalized.get("version", "")).strip()

        def merged_list(*keys: str) -> list[str]:
            values: list[str] = []
            for key in keys:
                value = normalized.get(key)
                if isinstance(value, list):
                    values.extend(
                        str(item).strip() for item in value if str(item).strip()
                    )
                elif isinstance(value, str) and value.strip():
                    values.append(value.strip())
            deduped: list[str] = []
            for value in values:
                if value not in deduped:
                    deduped.append(value)
            return deduped

        if skill_name and not skill_id:
            normalized["id"] = cls._slugify(skill_name).replace("-", "_")
        if version:
            normalized["version"] = version
        else:
            normalized["version"] = "1.0.0"
        normalized["required_tools"] = merged_list("required_tools", "tools")
        normalized["required_permissions"] = merged_list(
            "required_permissions", "permissions"
        )
        if "permission_class" in normalized:
            normalized["permission_class"] = str(
                normalized.get("permission_class", "")
            ).strip()
        return normalized

    @staticmethod
    def _validate_archive_member(name: str) -> Path:
        path = Path(name)
        if path.is_absolute() or any(part == ".." for part in path.parts):
            raise ValueError(f"Unsafe archive path: {name}")
        return path

    def _extract_skill_archive(self, archive_path: Path, destination: Path) -> None:
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                rel_path = self._validate_archive_member(member.filename)
                if not member.filename or member.is_dir():
                    continue
                target = destination / rel_path
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member, "r") as source, open(target, "wb") as output:
                    shutil.copyfileobj(source, output)

    @staticmethod
    def _validate_skill_structure(extracted_root: Path, manifest: Dict[str, Any]) -> None:
        skill_md_path = extracted_root / "SKILL.md"
        if not skill_md_path.is_file():
            raise ValueError("Imported skill archive must contain SKILL.md at the root")
        for required_field in ("id", "name", "version"):
            if not str(manifest.get(required_field, "")).strip():
                raise ValueError(f"SKILL.md is missing required field: {required_field}")
        for resource_dir in extracted_root.iterdir():
            if resource_dir.name == "SKILL.md":
                continue
            if resource_dir.is_dir() and resource_dir.name not in ALLOWED_SKILL_RESOURCE_DIRS:
                raise ValueError(f"Unsupported skill resource directory: {resource_dir.name}")
        for ref_field in ("workflow_ref", "input_schema_ref"):
            ref = str(manifest.get(ref_field, "")).strip()
            if ref and not (extracted_root / ref).is_file():
                raise ValueError(f"Missing referenced skill resource: {ref}")
        schema_ref = str(manifest.get("input_schema_ref", "")).strip()
        if schema_ref and schema_ref.lower().endswith(".json"):
            try:
                json.loads((extracted_root / schema_ref).read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON schema file: {schema_ref}") from exc

    def _skill_from_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "slug": row["slug"],
            "name": row["name"],
            "scope": row["scope"],
            "owner_app_id": row["owner_app_id"],
            "status_summary": row["status_summary"],
            "current_active_version_id": row["current_active_version_id"],
            "current_published_version_id": row["current_published_version_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _skill_version_from_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        metadata = json.loads(row["metadata_json"] or "{}")
        return {
            "id": row["id"],
            "skill_id": row["skill_id"],
            "version": row["version"],
            "state": row["state"],
            "manifest_format": row["manifest_format"],
            "skill_md_rel_path": row["skill_md_rel_path"],
            "storage_root_rel_path": row["storage_root_rel_path"],
            "checksum": row["checksum"],
            "import_source": row["import_source"],
            "validation_status": row["validation_status"],
            "metadata": metadata,
            "published_at": row["published_at"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

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
        try:
            tmp_path.replace(target)
        except PermissionError:
            target.write_text(content or "", encoding="utf-8")
            try:
                tmp_path.unlink(missing_ok=True)
            except PermissionError:
                pass
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
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS skills (
                id TEXT PRIMARY KEY,
                slug TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                scope TEXT NOT NULL,
                owner_app_id TEXT,
                status_summary TEXT NOT NULL,
                current_active_version_id TEXT,
                current_published_version_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS skill_versions (
                id TEXT PRIMARY KEY,
                skill_id TEXT NOT NULL,
                version TEXT NOT NULL,
                state TEXT NOT NULL,
                manifest_format TEXT NOT NULL,
                skill_md_rel_path TEXT NOT NULL,
                storage_root_rel_path TEXT NOT NULL,
                checksum TEXT NOT NULL,
                import_source TEXT NOT NULL,
                validation_status TEXT NOT NULL,
                metadata_json TEXT,
                published_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(skill_id) REFERENCES skills(id) ON DELETE CASCADE,
                UNIQUE(skill_id, version)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS app_skill_bindings (
                id TEXT PRIMARY KEY,
                app_id TEXT NOT NULL,
                skill_id TEXT NOT NULL,
                skill_version TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                permission_mode TEXT NOT NULL,
                execution_policy TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(app_id) REFERENCES applications(id) ON DELETE CASCADE,
                FOREIGN KEY(skill_id) REFERENCES skills(id) ON DELETE CASCADE
            )
            """
        )
        try:
            cursor.execute("ALTER TABLE documents ADD COLUMN file_path TEXT")
        except sqlite3.OperationalError:
            # Column already exists in existing local DBs.
            pass
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_documents_app_id ON documents(app_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_skill_versions_skill_id ON skill_versions(skill_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_app_skill_bindings_app_id ON app_skill_bindings(app_id)")
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

    def get_skill(self, skill_id: str) -> Optional[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM skills WHERE id = ?", (skill_id,))
        row = cursor.fetchone()
        return self._skill_from_row(row) if row else None

    def list_skills(self) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM skills ORDER BY updated_at DESC")
        return [self._skill_from_row(row) for row in cursor.fetchall()]

    def get_skill_version(self, version_id: str) -> Optional[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM skill_versions WHERE id = ?", (version_id,))
        row = cursor.fetchone()
        return self._skill_version_from_row(row) if row else None

    def get_skill_version_by_number(self, skill_id: str, version: str) -> Optional[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM skill_versions WHERE skill_id = ? AND version = ?",
            (skill_id, version),
        )
        row = cursor.fetchone()
        return self._skill_version_from_row(row) if row else None

    def list_skill_versions(self, skill_id: str) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM skill_versions WHERE skill_id = ? ORDER BY created_at DESC",
            (skill_id,),
        )
        return [self._skill_version_from_row(row) for row in cursor.fetchall()]

    def _cleanup_skill_storage(self, version_rows: List[Dict[str, Any]]) -> None:
        for version in version_rows:
            storage_rel = str(version.get("storage_root_rel_path", "")).strip()
            if not storage_rel:
                continue
            storage_root = (self.base_dir / storage_rel).resolve()
            if not storage_root.exists():
                continue
            for child in sorted(storage_root.rglob("*"), key=lambda path: len(path.parts), reverse=True):
                try:
                    if child.is_file():
                        child.unlink()
                    elif child.is_dir():
                        child.rmdir()
                except OSError:
                    # Windows local ACLs/locks may block cleanup; keep delete best-effort.
                    continue
            try:
                storage_root.rmdir()
            except OSError:
                continue
            parent = storage_root.parent
            while parent.exists():
                try:
                    parent.rmdir()
                except OSError:
                    break
                if parent == self.base_dir:
                    break
                parent = parent.parent

    def delete_skill(self, skill_id: str) -> bool:
        skill = self.get_skill(skill_id)
        if not skill:
            return False

        version_rows = self.list_skill_versions(skill_id)
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM skills WHERE id = ?", (skill_id,))
        self.conn.commit()
        self._cleanup_skill_storage(version_rows)
        return True

    def publish_skill_version(self, version_id: str) -> Optional[Dict[str, Any]]:
        version = self.get_skill_version(version_id)
        if not version:
            return None
        if version["validation_status"] != "passed":
            raise ValueError("Only validated skill versions can be published")
        if version["state"] not in {"draft", "review", "published", "active"}:
            raise ValueError("Skill version is not in a publishable state")
        now = datetime.datetime.utcnow().isoformat()
        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE skill_versions
            SET state = ?, published_at = ?, updated_at = ?
            WHERE id = ?
            """,
            ("published", now, now, version_id),
        )
        cursor.execute(
            """
            UPDATE skills
            SET current_published_version_id = ?, status_summary = ?, updated_at = ?
            WHERE id = ?
            """,
            (version_id, "published", now, version["skill_id"]),
        )
        self.conn.commit()
        return self.get_skill_version(version_id)

    def _binding_from_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
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

    def create_app_skill_binding(
        self,
        *,
        app_id: str,
        skill_id: str,
        skill_version: str,
        permission_mode: str,
        execution_policy: Optional[Dict[str, Any]] = None,
        enabled: bool = True,
    ) -> Dict[str, Any]:
        if not self.get_application(app_id):
            raise ValueError("Application not found")
        version = self.get_skill_version_by_number(skill_id, skill_version)
        if not version:
            raise ValueError("Skill version not found")
        if version["state"] not in {"published", "active"}:
            raise ValueError("Only published or active skill versions can be bound")
        if permission_mode not in {"auto_allow", "restricted", "require_confirmation", "blocked"}:
            raise ValueError("Unsupported permission mode")
        now = datetime.datetime.utcnow().isoformat()
        binding_id = str(uuid.uuid4())
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO app_skill_bindings (
                id, app_id, skill_id, skill_version, enabled,
                permission_mode, execution_policy, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                binding_id,
                app_id,
                skill_id,
                skill_version,
                1 if enabled else 0,
                permission_mode,
                json.dumps(execution_policy or {}, ensure_ascii=False),
                now,
                now,
            ),
        )
        self.conn.commit()
        cursor.execute("SELECT * FROM app_skill_bindings WHERE id = ?", (binding_id,))
        return self._binding_from_row(cursor.fetchone())

    def list_app_skill_bindings(self, app_id: str) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM app_skill_bindings WHERE app_id = ? ORDER BY created_at DESC",
            (app_id,),
        )
        return [self._binding_from_row(row) for row in cursor.fetchall()]

    def get_published_skill_definition(self, *, skill_id: str, version: str | None = None) -> Optional[Dict[str, Any]]:
        skill = self.get_skill(skill_id)
        if not skill:
            return None
        version_row = (
            self.get_skill_version_by_number(skill_id, version)
            if version
            else (
                self.get_skill_version(skill["current_active_version_id"])
                if skill.get("current_active_version_id")
                else self.get_skill_version(skill["current_published_version_id"])
            )
        )
        if not version_row:
            return None
        if version_row["state"] not in {"published", "active"}:
            raise ValueError("Requested skill version is not published")
        metadata = dict(version_row["metadata"] or {})
        storage_root = self.base_dir / version_row["storage_root_rel_path"]
        skill_md_path = self.base_dir / version_row["skill_md_rel_path"]
        manifest = {}
        if skill_md_path.is_file():
            try:
                manifest = self._normalize_skill_manifest(
                    self._parse_skill_manifest(skill_md_path.read_text(encoding="utf-8"))
                )
            except ValueError:
                manifest = {}

        def merged_text(key: str) -> str:
            meta_value = str(metadata.get(key, "")).strip()
            if meta_value:
                return meta_value
            return str(manifest.get(key, "")).strip()

        def merged_list(key: str) -> List[str]:
            meta_value = metadata.get(key, [])
            if isinstance(meta_value, list) and meta_value:
                return [str(item).strip() for item in meta_value if str(item).strip()]
            manifest_value = manifest.get(key, [])
            if isinstance(manifest_value, list):
                return [str(item).strip() for item in manifest_value if str(item).strip()]
            return []

        input_schema_ref = merged_text("input_schema_ref")
        output_schema_ref = merged_text("output_schema_ref")
        workflow_ref = merged_text("workflow_ref")
        input_schema = metadata.get("input_schema", {}) or {}
        output_schema = metadata.get("output_schema", {}) or {}
        workflow_definition = metadata.get("workflow_definition", {}) or {}
        if not input_schema:
            input_schema = (
                json.loads((storage_root / input_schema_ref).read_text(encoding="utf-8"))
                if input_schema_ref
                else {"type": "object", "properties": {}}
            )
        if not output_schema:
            output_schema = (
                json.loads((storage_root / output_schema_ref).read_text(encoding="utf-8"))
                if output_schema_ref
                else {"type": "object", "properties": {}}
            )
        if not workflow_definition:
            workflow_definition = (
                json.loads((storage_root / workflow_ref).read_text(encoding="utf-8"))
                if workflow_ref
                else {"steps": []}
            )
        return {
            "skill_id": skill["id"],
            "name": skill["name"],
            "version": version_row["version"],
            "description": merged_text("description"),
            "enabled": version_row["state"] in {"published", "active"},
            "required_tools": merged_list("required_tools"),
            "required_permissions": merged_list("required_permissions"),
            "input_schema": input_schema,
            "output_schema": output_schema,
            "workflow_definition": workflow_definition,
            "storage_root": str(storage_root),
            "skill_md_path": str(skill_md_path),
            "checksum": version_row["checksum"],
            "state": version_row["state"],
            "metadata": metadata,
        }

    def import_skill_package(
        self,
        *,
        archive_path: Path | str,
        storage_root: Path | str | None = None,
        scope: str,
        import_source: str,
    ) -> Dict[str, Any]:
        scope_value = str(scope or "").strip().lower()
        if scope_value not in {"managed", "workspace", "bundled"}:
            raise ValueError(f"Unsupported skill scope: {scope}")
        archive_file = Path(archive_path)
        if not archive_file.is_file():
            raise ValueError(f"Skill archive not found: {archive_file}")
        destination_root = Path(storage_root).resolve() if storage_root is not None else self.skills_root
        destination_root.mkdir(parents=True, exist_ok=True)
        temp_root = destination_root.parent / "_skill_import_staging" / uuid.uuid4().hex
        temp_root.mkdir(parents=True, exist_ok=True)
        try:
            extracted_root = temp_root
            self._extract_skill_archive(archive_file, extracted_root)
            skill_md_path = extracted_root / "SKILL.md"
            if not skill_md_path.is_file():
                raise ValueError("Imported skill archive must contain SKILL.md at the root")
            manifest_text = skill_md_path.read_text(encoding="utf-8")
            manifest = self._normalize_skill_manifest(self._parse_skill_manifest(manifest_text))
            from skill_normalization import normalize_skill_markdown

            normalized_contract = normalize_skill_markdown(manifest_text)
            self._validate_skill_structure(extracted_root, manifest)

            skill_id = str(manifest["id"]).strip()
            skill_name = str(manifest["name"]).strip()
            version = str(manifest["version"]).strip()
            slug = self._slugify(skill_name) or self._slugify(skill_id)
            if not slug:
                raise ValueError("Unable to derive a skill slug from manifest metadata")
            now = datetime.datetime.utcnow().isoformat()
            skill_row = self.get_skill(skill_id)
            cursor = self.conn.cursor()
            if not skill_row:
                cursor.execute(
                    """
                    INSERT INTO skills (
                        id, slug, name, scope, owner_app_id, status_summary,
                        current_active_version_id, current_published_version_id,
                        created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        skill_id,
                        slug,
                        skill_name,
                        scope_value,
                        None,
                        "draft",
                        None,
                        None,
                        now,
                        now,
                    ),
                )
            scoped_rel_root = Path(scope_value) / skill_id / version
            target_root = destination_root / scoped_rel_root
            if target_root.exists():
                raise ValueError(f"Skill version already exists: {skill_id}@{version}")
            target_root.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(extracted_root, target_root)
            storage_rel_root = os.path.relpath(target_root, self.base_dir).replace("\\", "/")
            checksum = hashlib.sha256(manifest_text.encode("utf-8")).hexdigest()
            version_id = str(uuid.uuid4())
            metadata = {
                "description": str(manifest.get("description", "")).strip(),
                "required_tools": normalized_contract.get(
                    "required_tools", manifest.get("required_tools", [])
                ),
                "required_permissions": normalized_contract.get(
                    "required_permissions",
                    manifest.get("required_permissions", []),
                ),
                "workflow_ref": str(manifest.get("workflow_ref", "")).strip(),
                "input_schema_ref": str(manifest.get("input_schema_ref", "")).strip(),
                "output_schema_ref": str(manifest.get("output_schema_ref", "")).strip(),
                "workflow_definition": normalized_contract.get("workflow_definition", {}),
                "input_schema": normalized_contract.get("input_schema", {}),
                "output_schema": normalized_contract.get("output_schema", {}),
                "policy_class": normalized_contract.get("policy_class", "unsupported"),
                "template_family": normalized_contract.get("template_family", "unsupported"),
                "auto_finalize": bool(normalized_contract.get("auto_finalize", False)),
            }
            explicit_required_tools = manifest.get("required_tools", [])
            version_state = "draft"
            if metadata["policy_class"] == "review_required":
                version_state = "review"
            elif (
                not metadata["auto_finalize"]
                and not metadata["required_tools"]
                and not explicit_required_tools
            ):
                version_state = "review"
            cursor.execute(
                """
                INSERT INTO skill_versions (
                    id, skill_id, version, state, manifest_format, skill_md_rel_path,
                    storage_root_rel_path, checksum, import_source, validation_status,
                    metadata_json, published_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    version_id,
                    skill_id,
                    version,
                    version_state,
                    "skill_md_frontmatter",
                    f"{storage_rel_root}/SKILL.md",
                    storage_rel_root,
                    checksum,
                    import_source,
                    "passed",
                    json.dumps(metadata, ensure_ascii=False),
                    None,
                    now,
                    now,
                ),
            )
            cursor.execute(
                "UPDATE skills SET updated_at = ?, status_summary = ? WHERE id = ?",
                (now, version_state, skill_id),
            )
            self.conn.commit()
            imported_skill = self.get_skill(skill_id)
            imported_version = self.get_skill_version(version_id)
            return {
                "skill": imported_skill,
                "version": imported_version,
            }
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

    def preview_skill_package(
        self,
        *,
        archive_path: Path | str,
        scope: str,
    ) -> Dict[str, Any]:
        scope_value = str(scope or "").strip().lower()
        if scope_value not in {"managed", "workspace", "bundled"}:
            raise ValueError(f"Unsupported skill scope: {scope}")
        archive_file = Path(archive_path)
        if not archive_file.is_file():
            raise ValueError(f"Skill archive not found: {archive_file}")
        temp_root = self.skills_root.parent / "_skill_preview_staging" / uuid.uuid4().hex
        temp_root.mkdir(parents=True, exist_ok=True)
        try:
            extracted_root = temp_root
            self._extract_skill_archive(archive_file, extracted_root)
            skill_md_path = extracted_root / "SKILL.md"
            if not skill_md_path.is_file():
                raise ValueError("Imported skill archive must contain SKILL.md at the root")
            manifest_text = skill_md_path.read_text(encoding="utf-8")
            manifest = self._normalize_skill_manifest(self._parse_skill_manifest(manifest_text))
            from skill_normalization import normalize_skill_markdown

            normalized_contract = normalize_skill_markdown(manifest_text)
            self._validate_skill_structure(extracted_root, manifest)

            explicit_required_tools = manifest.get("required_tools", [])
            version_state = "draft"
            if normalized_contract.get("policy_class") == "review_required":
                version_state = "review"
            elif (
                not normalized_contract.get("auto_finalize", False)
                and not normalized_contract.get("required_tools", [])
                and not explicit_required_tools
            ):
                version_state = "review"

            metadata = {
                "description": str(manifest.get("description", "")).strip(),
                "required_tools": normalized_contract.get(
                    "required_tools", manifest.get("required_tools", [])
                ),
                "required_permissions": normalized_contract.get(
                    "required_permissions",
                    manifest.get("required_permissions", []),
                ),
                "workflow_ref": str(manifest.get("workflow_ref", "")).strip(),
                "input_schema_ref": str(manifest.get("input_schema_ref", "")).strip(),
                "output_schema_ref": str(manifest.get("output_schema_ref", "")).strip(),
                "workflow_definition": normalized_contract.get("workflow_definition", {}),
                "input_schema": normalized_contract.get("input_schema", {}),
                "output_schema": normalized_contract.get("output_schema", {}),
                "policy_class": normalized_contract.get("policy_class", "unsupported"),
                "template_family": normalized_contract.get("template_family", "unsupported"),
                "auto_finalize": bool(normalized_contract.get("auto_finalize", False)),
            }

            return {
                "skill": {
                    "id": str(manifest["id"]).strip(),
                    "name": str(manifest["name"]).strip(),
                    "scope": scope_value,
                    "description": str(manifest.get("description", "")).strip(),
                },
                "version": {
                    "id": "preview",
                    "skill_id": str(manifest["id"]).strip(),
                    "version": str(manifest["version"]).strip(),
                    "state": version_state,
                    "manifest_format": "skill_md_frontmatter",
                    "skill_md_rel_path": "",
                    "storage_root_rel_path": "",
                    "checksum": hashlib.sha256(manifest_text.encode("utf-8")).hexdigest(),
                    "import_source": "preview",
                    "validation_status": "passed",
                    "metadata": metadata,
                    "published_at": None,
                    "created_at": None,
                    "updated_at": None,
                    "manifest_text": manifest_text,
                },
            }
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)


_BASE_DIR = Path(__file__).resolve().parent
_DEFAULT_DB_PATH_ENV = os.environ.get("RAGENIUS_BUILDER_DB", str(_BASE_DIR / "rag_app.db"))
_DEFAULT_DB_PATH = (
    ":memory:"
    if _DEFAULT_DB_PATH_ENV == ":memory:"
    else Path(_DEFAULT_DB_PATH_ENV).resolve()
)
_DEFAULT_STORAGE_ROOT_ENV = os.environ.get("RAGENIUS_BUILDER_STORAGE_ROOT")
_DEFAULT_STORAGE_ROOT = (
    Path(_DEFAULT_STORAGE_ROOT_ENV).resolve()
    if _DEFAULT_STORAGE_ROOT_ENV
    else None
)
store = None
if os.environ.get("RAGENIUS_BUILDER_DISABLE_GLOBAL_STORE") != "1":
    store = DatabaseStore(_DEFAULT_DB_PATH, storage_root=_DEFAULT_STORAGE_ROOT)
    atexit.register(store.close)
