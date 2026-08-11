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
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_skill_sources (
                id TEXT PRIMARY KEY,
                backend TEXT NOT NULL,
                source_kind TEXT NOT NULL,
                display_name TEXT NOT NULL,
                runtime_target_id TEXT NOT NULL,
                protected_locator_ref TEXT NOT NULL,
                precedence INTEGER NOT NULL DEFAULT 100,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(backend, runtime_target_id, protected_locator_ref)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_skill_catalog (
                id TEXT PRIMARY KEY,
                backend TEXT NOT NULL,
                runtime_target_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                provider_skill_name TEXT NOT NULL,
                provider_skill_reference TEXT NOT NULL,
                display_name TEXT NOT NULL,
                description TEXT NOT NULL,
                content_fingerprint TEXT NOT NULL,
                discovery_status TEXT NOT NULL,
                model_visible INTEGER NOT NULL,
                user_invocable INTEGER NOT NULL,
                direct_tool_dispatch INTEGER NOT NULL,
                missing_requirements_json TEXT NOT NULL,
                provider_metadata_json TEXT NOT NULL,
                discovered_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(source_id) REFERENCES agent_skill_sources(id) ON DELETE CASCADE,
                UNIQUE(backend, runtime_target_id, source_id, provider_skill_reference)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_skill_approvals (
                id TEXT PRIMARY KEY,
                agent_skill_id TEXT NOT NULL,
                approved_fingerprint TEXT NOT NULL,
                state TEXT NOT NULL,
                review_notes TEXT,
                approved_by TEXT NOT NULL,
                approved_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(agent_skill_id) REFERENCES agent_skill_catalog(id) ON DELETE CASCADE
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS app_agent_skill_bindings (
                id TEXT PRIMARY KEY,
                app_id TEXT NOT NULL,
                agent_skill_id TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(app_id) REFERENCES applications(id) ON DELETE CASCADE,
                FOREIGN KEY(agent_skill_id) REFERENCES agent_skill_catalog(id) ON DELETE CASCADE,
                UNIQUE(app_id, agent_skill_id)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_skill_audit_events (
                id TEXT PRIMARY KEY,
                occurred_at TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                action TEXT NOT NULL,
                source_id TEXT,
                agent_skill_id TEXT,
                approval_id TEXT,
                binding_id TEXT,
                app_id TEXT,
                before_json TEXT,
                after_json TEXT,
                correlation_id TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_skill_projection_state (
                singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1),
                builder_instance_id TEXT,
                local_revision INTEGER NOT NULL DEFAULT 0,
                published_revision INTEGER,
                published_digest TEXT,
                published_snapshot_json TEXT,
                sync_status TEXT NOT NULL DEFAULT 'synchronized',
                last_attempt_at TEXT,
                last_success_at TEXT,
                last_error_code TEXT,
                last_error_message TEXT
            )
            """
        )
        cursor.execute(
            """
            INSERT OR IGNORE INTO agent_skill_projection_state (
                singleton_id, local_revision, sync_status
            ) VALUES (1, 0, 'synchronized')
            """
        )
        self.conn.commit()
        self._migrate_agent_skill_catalog_reference()
        cursor = self.conn.cursor()
        try:
            cursor.execute("ALTER TABLE documents ADD COLUMN file_path TEXT")
        except sqlite3.OperationalError:
            # Column already exists in existing local DBs.
            pass
        try:
            cursor.execute(
                "ALTER TABLE agent_skill_projection_state "
                "ADD COLUMN published_snapshot_json TEXT"
            )
        except sqlite3.OperationalError:
            # Column already exists in current local DBs.
            pass
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_documents_app_id ON documents(app_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_skill_versions_skill_id ON skill_versions(skill_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_app_skill_bindings_app_id ON app_skill_bindings(app_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_agent_skill_catalog_source_id ON agent_skill_catalog(source_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_agent_skill_approvals_skill_id ON agent_skill_approvals(agent_skill_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_app_agent_skill_bindings_app_id ON app_agent_skill_bindings(app_id)")
        self.conn.commit()

    def _migrate_agent_skill_catalog_reference(self):
        columns = {
            row["name"]
            for row in self.conn.execute(
                "PRAGMA table_info(agent_skill_catalog)"
            ).fetchall()
        }
        if "provider_skill_reference" in columns:
            return
        self.conn.execute("PRAGMA foreign_keys = OFF")
        try:
            self.conn.executescript(
                """
                BEGIN IMMEDIATE;
                DROP TABLE IF EXISTS agent_skill_catalog_new;
                CREATE TABLE agent_skill_catalog_new (
                    id TEXT PRIMARY KEY,
                    backend TEXT NOT NULL,
                    runtime_target_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    provider_skill_name TEXT NOT NULL,
                    provider_skill_reference TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    content_fingerprint TEXT NOT NULL,
                    discovery_status TEXT NOT NULL,
                    model_visible INTEGER NOT NULL,
                    user_invocable INTEGER NOT NULL,
                    direct_tool_dispatch INTEGER NOT NULL,
                    missing_requirements_json TEXT NOT NULL,
                    provider_metadata_json TEXT NOT NULL,
                    discovered_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(source_id) REFERENCES agent_skill_sources(id) ON DELETE CASCADE,
                    UNIQUE(backend, runtime_target_id, source_id, provider_skill_reference)
                );
                INSERT INTO agent_skill_catalog_new (
                    id, backend, runtime_target_id, source_id,
                    provider_skill_name, provider_skill_reference, display_name,
                    description, content_fingerprint, discovery_status,
                    model_visible, user_invocable, direct_tool_dispatch,
                    missing_requirements_json, provider_metadata_json,
                    discovered_at, last_seen_at, updated_at
                )
                SELECT
                    id, backend, runtime_target_id, source_id,
                    provider_skill_name, provider_skill_name, display_name,
                    description, content_fingerprint, discovery_status,
                    model_visible, user_invocable, direct_tool_dispatch,
                    missing_requirements_json, provider_metadata_json,
                    discovered_at, last_seen_at, updated_at
                FROM agent_skill_catalog;
                DROP TABLE agent_skill_catalog;
                ALTER TABLE agent_skill_catalog_new RENAME TO agent_skill_catalog;
                COMMIT;
                """
            )
        except Exception:
            if self.conn.in_transaction:
                self.conn.rollback()
            raise
        finally:
            self.conn.execute("PRAGMA foreign_keys = ON")

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

    @staticmethod
    def _agent_skill_now() -> str:
        return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    @staticmethod
    def _agent_skill_json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def _record_agent_skill_audit(
        self,
        cursor: sqlite3.Cursor,
        *,
        actor_id: str,
        action: str,
        source_id: str | None = None,
        agent_skill_id: str | None = None,
        approval_id: str | None = None,
        binding_id: str | None = None,
        app_id: str | None = None,
        before: Any = None,
        after: Any = None,
        correlation_id: str | None = None,
    ) -> None:
        cursor.execute(
            """
            INSERT INTO agent_skill_audit_events (
                id, occurred_at, actor_id, action, source_id, agent_skill_id,
                approval_id, binding_id, app_id, before_json, after_json,
                correlation_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                self._agent_skill_now(),
                actor_id,
                action,
                source_id,
                agent_skill_id,
                approval_id,
                binding_id,
                app_id,
                self._agent_skill_json(before)[:16384] if before is not None else None,
                self._agent_skill_json(after)[:16384] if after is not None else None,
                correlation_id,
            ),
        )

    def _mark_agent_skill_projection_pending(self, cursor: sqlite3.Cursor) -> int:
        row = cursor.execute(
            "SELECT local_revision FROM agent_skill_projection_state WHERE singleton_id = 1"
        ).fetchone()
        previous = int(row["local_revision"] if row else 0)
        epoch_ms = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)
        revision = max(previous + 1, epoch_ms)
        cursor.execute(
            """
            UPDATE agent_skill_projection_state
            SET local_revision = ?, sync_status = 'pending',
                last_error_code = NULL, last_error_message = NULL
            WHERE singleton_id = 1
            """,
            (revision,),
        )
        return revision

    @staticmethod
    def _agent_skill_source_from_row(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "backend": row["backend"],
            "source_kind": row["source_kind"],
            "display_name": row["display_name"],
            "runtime_target_id": row["runtime_target_id"],
            "protected_locator_ref": row["protected_locator_ref"],
            "precedence": row["precedence"],
            "enabled": bool(row["enabled"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def create_agent_skill_source(
        self,
        *,
        backend: str,
        source_kind: str,
        display_name: str,
        runtime_target_id: str,
        protected_locator_ref: str,
        actor_id: str,
        precedence: int = 100,
        enabled: bool = True,
        correlation_id: str | None = None,
    ) -> Dict[str, Any]:
        valid_pairs = {
            ("codex_cli", "codex_directory"),
            ("codex_cli", "codex_plugin_inventory"),
            ("openclaw_cli", "openclaw_agent_inventory"),
        }
        if (backend, source_kind) not in valid_pairs:
            raise ValueError("Unsupported Agent skill backend/source kind")
        source_id = str(uuid.uuid4())
        now = self._agent_skill_now()
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT INTO agent_skill_sources (
                    id, backend, source_kind, display_name, runtime_target_id,
                    protected_locator_ref, precedence, enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    backend,
                    source_kind,
                    display_name.strip(),
                    runtime_target_id.strip(),
                    protected_locator_ref.strip(),
                    int(precedence),
                    1 if enabled else 0,
                    now,
                    now,
                ),
            )
            self._mark_agent_skill_projection_pending(cursor)
            self._record_agent_skill_audit(
                cursor,
                actor_id=actor_id,
                action="agent_skill_source.created",
                source_id=source_id,
                after={"backend": backend, "enabled": enabled, "display_name": display_name},
                correlation_id=correlation_id,
            )
        return self.get_agent_skill_source(source_id)

    def get_agent_skill_source(self, source_id: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            "SELECT * FROM agent_skill_sources WHERE id = ?", (source_id,)
        ).fetchone()
        return self._agent_skill_source_from_row(row) if row else None

    def list_agent_skill_sources(self) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM agent_skill_sources ORDER BY precedence, display_name, id"
        ).fetchall()
        return [self._agent_skill_source_from_row(row) for row in rows]

    def update_agent_skill_source(
        self,
        source_id: str,
        *,
        actor_id: str,
        display_name: str | None = None,
        precedence: int | None = None,
        enabled: bool | None = None,
        correlation_id: str | None = None,
        expected_local_revision: int | None = None,
    ) -> Dict[str, Any]:
        before = self.get_agent_skill_source(source_id)
        if not before:
            raise ValueError("Agent skill source not found")
        if expected_local_revision is not None:
            current_revision = int(self.get_agent_skill_projection_state()["local_revision"])
            if int(expected_local_revision) != current_revision:
                raise ValueError("AGENT_SKILL_LOCAL_REVISION_STALE")
        after = {
            **before,
            "display_name": display_name.strip() if display_name is not None else before["display_name"],
            "precedence": int(precedence) if precedence is not None else before["precedence"],
            "enabled": bool(enabled) if enabled is not None else before["enabled"],
            "updated_at": self._agent_skill_now(),
        }
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                UPDATE agent_skill_sources
                SET display_name = ?, precedence = ?, enabled = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    after["display_name"],
                    after["precedence"],
                    1 if after["enabled"] else 0,
                    after["updated_at"],
                    source_id,
                ),
            )
            if any(after[key] != before[key] for key in ("display_name", "precedence", "enabled")):
                self._mark_agent_skill_projection_pending(cursor)
            self._record_agent_skill_audit(
                cursor,
                actor_id=actor_id,
                action="agent_skill_source.updated",
                source_id=source_id,
                before={key: before[key] for key in ("display_name", "precedence", "enabled")},
                after={key: after[key] for key in ("display_name", "precedence", "enabled")},
                correlation_id=correlation_id,
            )
        return self.get_agent_skill_source(source_id)

    def _latest_agent_skill_approval(self, agent_skill_id: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            """
            SELECT * FROM agent_skill_approvals
            WHERE agent_skill_id = ?
            ORDER BY approved_at DESC, rowid DESC LIMIT 1
            """,
            (agent_skill_id,),
        ).fetchone()
        if not row:
            return None
        return dict(row)

    def _agent_skill_catalog_from_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        item = {
            "id": row["id"],
            "agent_skill_id": row["id"],
            "backend": row["backend"],
            "runtime_target_id": row["runtime_target_id"],
            "source_id": row["source_id"],
            "provider_skill_name": row["provider_skill_name"],
            "provider_skill_reference": row["provider_skill_reference"],
            "display_name": row["display_name"],
            "description": row["description"],
            "content_fingerprint": row["content_fingerprint"],
            "discovery_status": row["discovery_status"],
            "model_visible": bool(row["model_visible"]),
            "user_invocable": bool(row["user_invocable"]),
            "direct_tool_dispatch": bool(row["direct_tool_dispatch"]),
            "missing_requirements": json.loads(row["missing_requirements_json"] or "{}"),
            "provider_metadata": json.loads(row["provider_metadata_json"] or "{}"),
            "discovered_at": row["discovered_at"],
            "last_seen_at": row["last_seen_at"],
            "updated_at": row["updated_at"],
        }
        source = self.get_agent_skill_source(item["source_id"])
        approval = self._latest_agent_skill_approval(item["id"])
        if source and not source["enabled"]:
            governance_state = "source_disabled"
        elif item["discovery_status"] != "available":
            governance_state = "unavailable"
        elif not approval:
            governance_state = "pending_review"
        elif approval["state"] == "revoked":
            governance_state = "revoked"
        elif approval["state"] == "approved" and approval["approved_fingerprint"] == item["content_fingerprint"]:
            governance_state = "approved"
        else:
            governance_state = "changed_pending_review"
        item["governance_state"] = governance_state
        item["approval"] = approval
        item["source"] = {
            "id": source["id"],
            "backend": source["backend"],
            "display_name": source["display_name"],
            "enabled": source["enabled"],
        } if source else None
        return item

    def get_agent_skill_catalog_item(self, agent_skill_id: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            "SELECT * FROM agent_skill_catalog WHERE id = ?", (agent_skill_id,)
        ).fetchone()
        return self._agent_skill_catalog_from_row(row) if row else None

    def list_agent_skill_catalog(self, source_id: str | None = None) -> List[Dict[str, Any]]:
        if source_id:
            rows = self.conn.execute(
                "SELECT * FROM agent_skill_catalog WHERE source_id = ? ORDER BY display_name, id",
                (source_id,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM agent_skill_catalog ORDER BY display_name, id"
            ).fetchall()
        return [self._agent_skill_catalog_from_row(row) for row in rows]

    def list_agent_skill_catalog_view(
        self, *, view: str, source_id: str | None = None,
    ) -> List[Dict[str, Any]]:
        normalized_view = str(view or "active").strip().lower()
        if normalized_view not in {"active", "source", "disabled"}:
            raise ValueError("Unsupported Agent skill catalog view")
        if normalized_view == "source" and not source_id:
            raise ValueError("Agent skill source is required")
        items = self.list_agent_skill_catalog(source_id if normalized_view == "source" else None)
        if normalized_view == "active":
            items = [item for item in items if item.get("source", {}).get("enabled")]
        elif normalized_view == "disabled":
            items = [item for item in items if not item.get("source", {}).get("enabled")]
        return sorted(
            items,
            key=lambda item: (
                str(item.get("backend") or "").casefold(),
                str(item.get("display_name") or "").casefold(),
                str(item.get("provider_skill_reference") or "").casefold(),
                str(item.get("id") or ""),
            ),
        )

    def get_agent_skill_source_impact(self, source_id: str) -> Dict[str, Any]:
        source = self.get_agent_skill_source(source_id)
        if not source:
            raise ValueError("Agent skill source not found")
        skills = self.list_agent_skill_catalog(source_id)
        current_approved = sum(
            1
            for skill in skills
            if skill.get("approval", {}).get("state") == "approved"
            and skill.get("approval", {}).get("approved_fingerprint") == skill.get("content_fingerprint")
        )
        skill_ids = [str(skill["id"]) for skill in skills]
        bindings: list[sqlite3.Row] = []
        if skill_ids:
            placeholders = ",".join("?" for _ in skill_ids)
            bindings = self.conn.execute(
                f"""
                SELECT b.*, a.name AS app_name
                FROM app_agent_skill_bindings b
                JOIN applications a ON a.id = b.app_id
                WHERE b.agent_skill_id IN ({placeholders}) AND b.enabled = 1
                """,
                tuple(skill_ids),
            ).fetchall()
        affected = {
            (str(binding["app_id"]), str(binding["app_name"]))
            for binding in bindings
        }
        return {
            "source_id": source_id,
            "discovered_skill_count": len(skills),
            "approved_current_fingerprint_count": current_approved,
            "enabled_binding_count": len(bindings),
            "affected_apps": [
                {"id": app_id, "name": name}
                for app_id, name in sorted(affected, key=lambda item: (item[1].casefold(), item[0]))
            ],
        }

    def refresh_agent_skill_catalog(
        self,
        *,
        source_id: str,
        candidates: List[Dict[str, Any]],
        actor_id: str,
        correlation_id: str | None = None,
    ) -> List[Dict[str, Any]]:
        source = self.get_agent_skill_source(source_id)
        if not source:
            raise ValueError("Agent skill source not found")
        now = self._agent_skill_now()
        seen_references: set[str] = set()
        changed = False
        with self.conn:
            cursor = self.conn.cursor()
            for candidate in candidates:
                if candidate.get("backend") != source["backend"]:
                    raise ValueError("Discovered Agent skill backend does not match source")
                if candidate.get("runtime_target_id") != source["runtime_target_id"]:
                    raise ValueError("Discovered Agent skill runtime target does not match source")
                provider_name = str(candidate.get("provider_skill_name", "")).strip()
                provider_reference = str(
                    candidate.get("provider_skill_reference") or provider_name
                ).strip()
                if not provider_name:
                    raise ValueError("Discovered Agent skill name is required")
                if not provider_reference:
                    raise ValueError("Discovered Agent skill reference is required")
                seen_references.add(provider_reference)
                existing = cursor.execute(
                    """
                    SELECT * FROM agent_skill_catalog
                    WHERE backend = ? AND runtime_target_id = ? AND source_id = ?
                      AND provider_skill_reference = ?
                    """,
                    (source["backend"], source["runtime_target_id"], source_id, provider_reference),
                ).fetchone()
                item_id = existing["id"] if existing else str(candidate.get("agent_skill_id") or uuid.uuid4())
                if not existing and cursor.execute(
                    "SELECT 1 FROM agent_skill_catalog WHERE id = ?", (item_id,)
                ).fetchone():
                    item_id = str(uuid.uuid4())
                values = (
                    source["backend"],
                    source["runtime_target_id"],
                    source_id,
                    provider_name,
                    provider_reference,
                    str(candidate.get("display_name") or provider_name),
                    str(candidate.get("description") or ""),
                    str(candidate.get("content_fingerprint") or ""),
                    str(candidate.get("discovery_status") or "invalid"),
                    1 if candidate.get("model_visible") else 0,
                    1 if candidate.get("user_invocable") else 0,
                    1 if candidate.get("direct_tool_dispatch") else 0,
                    self._agent_skill_json(candidate.get("missing_requirements") or {}),
                    self._agent_skill_json(candidate.get("provider_metadata") or {}),
                    str(candidate.get("discovered_at") or now),
                    str(candidate.get("last_seen_at") or now),
                    now,
                )
                if existing:
                    old_values = tuple(existing[key] for key in (
                        "backend", "runtime_target_id", "source_id", "provider_skill_name",
                        "provider_skill_reference",
                        "display_name", "description", "content_fingerprint", "discovery_status",
                        "model_visible", "user_invocable", "direct_tool_dispatch",
                        "missing_requirements_json", "provider_metadata_json", "discovered_at",
                        "last_seen_at", "updated_at",
                    ))
                    changed = changed or old_values[:-1] != values[:-1]
                    cursor.execute(
                        """
                        UPDATE agent_skill_catalog SET
                            backend=?, runtime_target_id=?, source_id=?, provider_skill_name=?,
                            provider_skill_reference=?,
                            display_name=?, description=?, content_fingerprint=?, discovery_status=?,
                            model_visible=?, user_invocable=?, direct_tool_dispatch=?,
                            missing_requirements_json=?, provider_metadata_json=?, discovered_at=?,
                            last_seen_at=?, updated_at=? WHERE id=?
                        """,
                        (*values, item_id),
                    )
                else:
                    changed = True
                    cursor.execute(
                        """
                        INSERT INTO agent_skill_catalog (
                            id, backend, runtime_target_id, source_id, provider_skill_name,
                            provider_skill_reference,
                            display_name, description, content_fingerprint, discovery_status,
                            model_visible, user_invocable, direct_tool_dispatch,
                            missing_requirements_json, provider_metadata_json, discovered_at,
                            last_seen_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (item_id, *values),
                    )
            existing_rows = cursor.execute(
                "SELECT id, provider_skill_reference, discovery_status FROM agent_skill_catalog WHERE source_id = ?",
                (source_id,),
            ).fetchall()
            for row in existing_rows:
                if row["provider_skill_reference"] not in seen_references and row["discovery_status"] != "missing":
                    changed = True
                    cursor.execute(
                        "UPDATE agent_skill_catalog SET discovery_status = 'missing', updated_at = ? WHERE id = ?",
                        (now, row["id"]),
                    )
            if changed:
                self._mark_agent_skill_projection_pending(cursor)
            self._record_agent_skill_audit(
                cursor,
                actor_id=actor_id,
                action="agent_skill_catalog.refreshed",
                source_id=source_id,
                after={"candidate_count": len(candidates), "changed": changed},
                correlation_id=correlation_id,
            )
        return self.list_agent_skill_catalog(source_id)

    def approve_agent_skill(
        self,
        *,
        agent_skill_id: str,
        expected_fingerprint: str,
        approved_by: str,
        review_notes: str = "",
        correlation_id: str | None = None,
    ) -> Dict[str, Any]:
        skill = self.get_agent_skill_catalog_item(agent_skill_id)
        if not skill:
            raise ValueError("Agent skill not found")
        if skill["content_fingerprint"] != expected_fingerprint:
            raise ValueError("AGENT_SKILL_FINGERPRINT_CHANGED")
        if skill["governance_state"] == "source_disabled":
            raise ValueError("Agent skill source is disabled")
        if skill["discovery_status"] != "available":
            raise ValueError("Agent skill is not available")
        approval_id = str(uuid.uuid4())
        now = self._agent_skill_now()
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                UPDATE agent_skill_approvals SET state = 'superseded', updated_at = ?
                WHERE agent_skill_id = ? AND state = 'approved'
                """,
                (now, agent_skill_id),
            )
            cursor.execute(
                """
                INSERT INTO agent_skill_approvals (
                    id, agent_skill_id, approved_fingerprint, state, review_notes,
                    approved_by, approved_at, updated_at
                ) VALUES (?, ?, ?, 'approved', ?, ?, ?, ?)
                """,
                (approval_id, agent_skill_id, expected_fingerprint, review_notes, approved_by, now, now),
            )
            self._mark_agent_skill_projection_pending(cursor)
            self._record_agent_skill_audit(
                cursor,
                actor_id=approved_by,
                action="agent_skill.approved",
                agent_skill_id=agent_skill_id,
                approval_id=approval_id,
                after={"approved_fingerprint": expected_fingerprint, "state": "approved"},
                correlation_id=correlation_id,
            )
        return dict(self.conn.execute(
            "SELECT * FROM agent_skill_approvals WHERE id = ?", (approval_id,)
        ).fetchone())

    def revoke_agent_skill(
        self,
        *,
        agent_skill_id: str,
        actor_id: str,
        review_notes: str = "",
        correlation_id: str | None = None,
    ) -> Dict[str, Any]:
        skill = self.get_agent_skill_catalog_item(agent_skill_id)
        if not skill:
            raise ValueError("Agent skill not found")
        approval_id = str(uuid.uuid4())
        now = self._agent_skill_now()
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute(
                "UPDATE agent_skill_approvals SET state = 'superseded', updated_at = ? WHERE agent_skill_id = ? AND state = 'approved'",
                (now, agent_skill_id),
            )
            cursor.execute(
                """
                INSERT INTO agent_skill_approvals (
                    id, agent_skill_id, approved_fingerprint, state, review_notes,
                    approved_by, approved_at, updated_at
                ) VALUES (?, ?, ?, 'revoked', ?, ?, ?, ?)
                """,
                (approval_id, agent_skill_id, skill["content_fingerprint"], review_notes, actor_id, now, now),
            )
            self._mark_agent_skill_projection_pending(cursor)
            self._record_agent_skill_audit(
                cursor,
                actor_id=actor_id,
                action="agent_skill.revoked",
                agent_skill_id=agent_skill_id,
                approval_id=approval_id,
                after={"state": "revoked"},
                correlation_id=correlation_id,
            )
        return dict(self.conn.execute(
            "SELECT * FROM agent_skill_approvals WHERE id = ?", (approval_id,)
        ).fetchone())

    @staticmethod
    def _app_agent_skill_binding_from_row(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "app_id": row["app_id"],
            "agent_skill_id": row["agent_skill_id"],
            "enabled": bool(row["enabled"]),
            "created_by": row["created_by"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def create_app_agent_skill_binding(
        self,
        *,
        app_id: str,
        agent_skill_id: str,
        created_by: str,
        enabled: bool = True,
        correlation_id: str | None = None,
    ) -> Dict[str, Any]:
        if not self.get_application(app_id):
            raise ValueError("Application not found")
        skill = self.get_agent_skill_catalog_item(agent_skill_id)
        if not skill or skill["governance_state"] != "approved":
            raise ValueError("Agent skill must have a current approval before binding")
        existing = self.conn.execute(
            "SELECT * FROM app_agent_skill_bindings WHERE app_id = ? AND agent_skill_id = ?",
            (app_id, agent_skill_id),
        ).fetchone()
        if existing:
            return self._app_agent_skill_binding_from_row(existing)
        binding_id = str(uuid.uuid4())
        now = self._agent_skill_now()
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT INTO app_agent_skill_bindings (
                    id, app_id, agent_skill_id, enabled, created_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (binding_id, app_id, agent_skill_id, 1 if enabled else 0, created_by, now, now),
            )
            self._mark_agent_skill_projection_pending(cursor)
            self._record_agent_skill_audit(
                cursor,
                actor_id=created_by,
                action="app_agent_skill_binding.created",
                agent_skill_id=agent_skill_id,
                binding_id=binding_id,
                app_id=app_id,
                after={"enabled": enabled},
                correlation_id=correlation_id,
            )
        return self.get_app_agent_skill_binding(binding_id)

    def get_app_agent_skill_binding(self, binding_id: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            "SELECT * FROM app_agent_skill_bindings WHERE id = ?", (binding_id,)
        ).fetchone()
        return self._app_agent_skill_binding_from_row(row) if row else None

    def list_app_agent_skill_bindings(self, app_id: str) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM app_agent_skill_bindings WHERE app_id = ? ORDER BY created_at, id",
            (app_id,),
        ).fetchall()
        return [self._app_agent_skill_binding_from_row(row) for row in rows]

    def update_app_agent_skill_binding(
        self,
        binding_id: str,
        *,
        enabled: bool,
        actor_id: str,
        correlation_id: str | None = None,
    ) -> Dict[str, Any]:
        before = self.get_app_agent_skill_binding(binding_id)
        if not before:
            raise ValueError("Agent skill binding not found")
        if enabled:
            skill = self.get_agent_skill_catalog_item(before["agent_skill_id"])
            if not skill or skill["governance_state"] != "approved":
                raise ValueError("Agent skill source is disabled or approval is not current")
        now = self._agent_skill_now()
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute(
                "UPDATE app_agent_skill_bindings SET enabled = ?, updated_at = ? WHERE id = ?",
                (1 if enabled else 0, now, binding_id),
            )
            if before["enabled"] != enabled:
                self._mark_agent_skill_projection_pending(cursor)
            self._record_agent_skill_audit(
                cursor,
                actor_id=actor_id,
                action="app_agent_skill_binding.updated",
                agent_skill_id=before["agent_skill_id"],
                binding_id=binding_id,
                app_id=before["app_id"],
                before={"enabled": before["enabled"]},
                after={"enabled": enabled},
                correlation_id=correlation_id,
            )
        return self.get_app_agent_skill_binding(binding_id)

    def delete_app_agent_skill_binding(
        self,
        binding_id: str,
        *,
        actor_id: str,
        correlation_id: str | None = None,
    ) -> bool:
        before = self.get_app_agent_skill_binding(binding_id)
        if not before:
            return False
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM app_agent_skill_bindings WHERE id = ?", (binding_id,))
            self._mark_agent_skill_projection_pending(cursor)
            self._record_agent_skill_audit(
                cursor,
                actor_id=actor_id,
                action="app_agent_skill_binding.deleted",
                agent_skill_id=before["agent_skill_id"],
                binding_id=binding_id,
                app_id=before["app_id"],
                before={"enabled": before["enabled"]},
                correlation_id=correlation_id,
            )
        return True

    def list_agent_skill_audit_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM agent_skill_audit_events ORDER BY occurred_at DESC, rowid DESC LIMIT ?",
            (max(1, min(int(limit), 500)),),
        ).fetchall()
        return [
            {
                **dict(row),
                "before": json.loads(row["before_json"]) if row["before_json"] else None,
                "after": json.loads(row["after_json"]) if row["after_json"] else None,
            }
            for row in rows
        ]

    def record_agent_skill_publication_event(
        self,
        *,
        action: str,
        actor_id: str,
        details: Dict[str, Any],
        correlation_id: str,
    ) -> None:
        if action not in {
            "agent_skill.publication_attempted",
            "agent_skill.publication_succeeded",
            "agent_skill.publication_failed",
        }:
            raise ValueError("Unsupported Agent skill publication audit action")
        with self.conn:
            self._record_agent_skill_audit(
                self.conn.cursor(),
                actor_id=actor_id,
                action=action,
                after=details,
                correlation_id=correlation_id,
            )

    def configure_agent_skill_projection(self, builder_instance_id: str) -> Dict[str, Any]:
        state = self.get_agent_skill_projection_state()
        current = state.get("builder_instance_id")
        if current and current != builder_instance_id and state.get("published_revision") is not None:
            raise ValueError("Builder instance identity cannot change after publication")
        if current != builder_instance_id or int(state["local_revision"]) == 0:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute(
                    "UPDATE agent_skill_projection_state SET builder_instance_id = ? WHERE singleton_id = 1",
                    (builder_instance_id,),
                )
                if int(state["local_revision"]) == 0:
                    self._mark_agent_skill_projection_pending(cursor)
        return self.get_agent_skill_projection_state()

    def get_agent_skill_projection_state(self) -> Dict[str, Any]:
        row = self.conn.execute(
            "SELECT * FROM agent_skill_projection_state WHERE singleton_id = 1"
        ).fetchone()
        return dict(row)

    def list_agent_skill_projection_items(self) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT b.app_id, b.enabled AS binding_enabled,
                   c.*, s.enabled AS source_enabled,
                   a.approved_fingerprint, a.state AS approval_state
            FROM app_agent_skill_bindings b
            JOIN agent_skill_catalog c ON c.id = b.agent_skill_id
            JOIN agent_skill_sources s ON s.id = c.source_id
            JOIN agent_skill_approvals a ON a.id = (
                SELECT a2.id FROM agent_skill_approvals a2
                WHERE a2.agent_skill_id = c.id
                ORDER BY a2.approved_at DESC, a2.rowid DESC LIMIT 1
            )
            ORDER BY b.app_id, c.backend, c.runtime_target_id, c.source_id,
                     c.provider_skill_name, c.id
            """
        ).fetchall()
        return [
            {
                "app_id": row["app_id"],
                "agent_skill_id": row["id"],
                "backend": row["backend"],
                "runtime_target_id": row["runtime_target_id"],
                "source_id": row["source_id"],
                "protected_locator_ref": self.get_agent_skill_source(row["source_id"])["protected_locator_ref"],
                "provider_skill_name": row["provider_skill_name"],
                "provider_skill_reference": row["provider_skill_reference"],
                "display_name": row["display_name"],
                "description": row["description"],
                "current_fingerprint": row["content_fingerprint"],
                "approved_fingerprint": row["approved_fingerprint"],
                "source_enabled": bool(row["source_enabled"]) and row["discovery_status"] == "available",
                "approval_state": row["approval_state"],
                "binding_enabled": bool(row["binding_enabled"]),
                "model_visible": bool(row["model_visible"]),
                "user_invocable": bool(row["user_invocable"]),
                "direct_tool_dispatch": bool(row["direct_tool_dispatch"]),
            }
            for row in rows
        ]

    def mark_agent_skill_projection_attempt(self) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE agent_skill_projection_state SET last_attempt_at = ? WHERE singleton_id = 1",
                (self._agent_skill_now(),),
            )

    @staticmethod
    def _normalize_published_agent_skill_snapshot(
        snapshot: Dict[str, Any],
    ) -> Dict[str, Any]:
        invalid = ValueError("PUBLISHED_SNAPSHOT_INVALID")
        if not isinstance(snapshot, dict) or set(snapshot) != {
            "sources",
            "skills",
            "bindings",
        }:
            raise invalid

        schemas = {
            "sources": {
                "source_id": str,
                "enabled": bool,
            },
            "skills": {
                "agent_skill_id": str,
                "source_id": str,
                "provider_skill_reference": str,
                "current_fingerprint": str,
                "approved_fingerprint": (str, type(None)),
                "approval_state": str,
            },
            "bindings": {
                "app_id": str,
                "agent_skill_id": str,
                "enabled": bool,
            },
        }
        normalized: Dict[str, Any] = {}
        for collection, schema in schemas.items():
            records = snapshot.get(collection)
            if not isinstance(records, list):
                raise invalid
            checked = []
            for record in records:
                if not isinstance(record, dict) or set(record) != set(schema):
                    raise invalid
                for field, expected_type in schema.items():
                    value = record[field]
                    if not isinstance(value, expected_type):
                        raise invalid
                    if isinstance(value, str) and not value:
                        raise invalid
                checked.append(dict(record))
            normalized[collection] = sorted(
                checked,
                key=lambda value: json.dumps(
                    value,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
        return normalized

    def get_published_agent_skill_snapshot(self) -> Optional[Dict[str, Any]]:
        state = self.get_agent_skill_projection_state()
        serialized = state.get("published_snapshot_json")
        if serialized is None:
            return None
        try:
            snapshot = json.loads(serialized)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("PUBLISHED_SNAPSHOT_INVALID") from exc
        return self._normalize_published_agent_skill_snapshot(snapshot)

    def mark_agent_skill_projection_published(
        self,
        *,
        builder_instance_id: str,
        revision: int,
        digest: str,
        redacted_snapshot: Dict[str, Any],
    ) -> Dict[str, Any]:
        snapshot = self._normalize_published_agent_skill_snapshot(redacted_snapshot)
        state = self.get_agent_skill_projection_state()
        if (
            state["builder_instance_id"] != builder_instance_id
            or state["local_revision"] != revision
        ):
            raise ValueError("Projection acknowledgment does not match current Builder state")
        serialized = json.dumps(
            snapshot,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        now = self._agent_skill_now()
        with self.conn:
            self.conn.execute(
                """
                UPDATE agent_skill_projection_state
                SET published_revision = ?, published_digest = ?,
                    published_snapshot_json = ?, sync_status = 'synchronized',
                    last_success_at = ?, last_error_code = NULL, last_error_message = NULL
                WHERE singleton_id = 1
                """,
                (revision, digest, serialized, now),
            )
        return self.get_agent_skill_projection_state()

    def _current_redacted_agent_skill_snapshot(self) -> Dict[str, Any]:
        items = self.list_agent_skill_projection_items()
        sources = {
            item["source_id"]: {
                "source_id": item["source_id"],
                "enabled": bool(item["source_enabled"]),
            }
            for item in items
        }
        skills = {
            item["agent_skill_id"]: {
                "agent_skill_id": item["agent_skill_id"],
                "source_id": item["source_id"],
                "provider_skill_reference": item["provider_skill_reference"],
                "current_fingerprint": item["current_fingerprint"],
                "approved_fingerprint": item["approved_fingerprint"],
                "approval_state": item["approval_state"],
            }
            for item in items
        }
        bindings = [
            {
                "app_id": item["app_id"],
                "agent_skill_id": item["agent_skill_id"],
                "enabled": bool(item["binding_enabled"]),
            }
            for item in items
        ]
        return self._normalize_published_agent_skill_snapshot(
            {
                "sources": list(sources.values()),
                "skills": list(skills.values()),
                "bindings": bindings,
            }
        )

    def mark_agent_skill_projection_synchronized(
        self, *, builder_instance_id: str, revision: int, digest: str
    ) -> Dict[str, Any]:
        return self.mark_agent_skill_projection_published(
            builder_instance_id=builder_instance_id,
            revision=revision,
            digest=digest,
            redacted_snapshot=self._current_redacted_agent_skill_snapshot(),
        )

    def mark_agent_skill_projection_failed(self, *, code: str, message: str) -> Dict[str, Any]:
        with self.conn:
            self.conn.execute(
                """
                UPDATE agent_skill_projection_state
                SET sync_status = 'failed', last_error_code = ?, last_error_message = ?
                WHERE singleton_id = 1
                """,
                (str(code)[:128], str(message)[:1024]),
            )
        return self.get_agent_skill_projection_state()


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
