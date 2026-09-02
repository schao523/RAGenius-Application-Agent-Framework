from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any


def install_demo_seed(demo_data_dir: Path, runtime_root: Path, force: bool = False) -> dict[str, Any]:
    demo_data_dir = demo_data_dir.resolve()
    runtime_root = runtime_root.resolve()
    _validate_demo_data(demo_data_dir)
    _prepare_runtime_root(runtime_root, force=force)

    apps_payload = _read_json(demo_data_dir / "apps.json")
    documents_payload = _read_json(demo_data_dir / "documents.manifest.json")
    documents_by_id = _approved_documents_by_id(documents_payload)

    builder_root = runtime_root / "builder"
    app_state_root = runtime_root / "app" / ".state"
    upload_root = builder_root / "storage" / "uploads"
    instruction_root = builder_root / "instructions"
    snapshot_root = builder_root / "instruction_understanding"
    app_state_snapshot_root = app_state_root / "instruction_understanding_snapshots"
    builder_db = builder_root / "rag_app.db"

    builder_root.mkdir(parents=True, exist_ok=True)
    upload_root.mkdir(parents=True, exist_ok=True)
    instruction_root.mkdir(parents=True, exist_ok=True)
    snapshot_root.mkdir(parents=True, exist_ok=True)
    app_state_snapshot_root.mkdir(parents=True, exist_ok=True)

    now = dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()
    apps = apps_payload.get("apps") or []
    installed_document_count = 0

    with sqlite3.connect(builder_db) as con:
        _create_schema(con)
        for app in apps:
            app_id = app["id"]
            _copy_seed_file(
                demo_data_dir / app["instructions"]["seed_path"],
                instruction_root / app_id / "instructions.md",
            )
            _copy_seed_file(
                demo_data_dir / app["snapshot"]["seed_path"],
                snapshot_root / app_id / "understanding.json",
            )
            _copy_seed_file(
                demo_data_dir / app["snapshot"]["seed_path"],
                app_state_snapshot_root / app_id / "understanding.json",
            )

            con.execute(
                """
                INSERT INTO applications (id, name, slug, description, starter_questions, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    app_id,
                    app["name"],
                    app["slug"],
                    app.get("description", ""),
                    json.dumps(app.get("starter_questions", []), ensure_ascii=False),
                    now,
                ),
            )
            con.execute(
                """
                INSERT INTO instructions (app_id, content, uri, version, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    app_id,
                    (instruction_root / app_id / "instructions.md").read_text(encoding="utf-8"),
                    f"instructions/{app_id}/instructions.md",
                    app["instructions"].get("version", "v1"),
                    now,
                ),
            )
            con.execute(
                """
                INSERT INTO settings (app_id, config_settings, config_schema, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    app_id,
                    json.dumps(app["settings"].get("config_settings", {}), ensure_ascii=False, indent=2),
                    json.dumps(app["settings"].get("config_schema", {}), ensure_ascii=False, indent=2),
                    now,
                ),
            )

            for app_document in app.get("documents", []):
                document_id = app_document["id"]
                manifest_document = documents_by_id.get(document_id)
                if manifest_document is None:
                    raise ValueError(f"Document {document_id} is missing from documents.manifest.json")
                source = demo_data_dir / manifest_document["seed_path"]
                destination = upload_root / app_id / f"{document_id}_{manifest_document['filename']}"
                _copy_seed_file(source, destination)
                con.execute(
                    """
                    INSERT INTO documents (
                        id, app_id, filename, mime_type, size_bytes, language,
                        tags, file_path, status, error_message, uploaded_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        document_id,
                        app_id,
                        manifest_document["filename"],
                        manifest_document.get("mime_type", "application/octet-stream"),
                        int(manifest_document.get("size_bytes") or destination.stat().st_size),
                        manifest_document.get("language"),
                        json.dumps(manifest_document.get("tags", []), ensure_ascii=False),
                        str(destination.resolve()),
                        "pending",
                        None,
                        now,
                    ),
                )
                installed_document_count += 1
        con.commit()

    return {
        "app_count": len(apps),
        "document_count": installed_document_count,
        "runtime_root": str(runtime_root),
        "builder_db": str(builder_db),
        "snapshot_root": str(snapshot_root),
        "app_state_snapshot_root": str(app_state_snapshot_root),
    }


def _validate_demo_data(demo_data_dir: Path) -> None:
    for filename in ["apps.json", "documents.manifest.json"]:
        path = demo_data_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f"Required demo seed file not found: {path}")


def _prepare_runtime_root(runtime_root: Path, force: bool) -> None:
    if runtime_root.exists():
        if not force:
            raise FileExistsError(f"Runtime root already exists: {runtime_root}")
        shutil.rmtree(runtime_root)
    runtime_root.mkdir(parents=True, exist_ok=True)


def _approved_documents_by_id(documents_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for document in documents_payload.get("documents") or []:
        if document.get("redistribution") != "approved":
            raise ValueError(
                f"Document {document.get('document_id')} is not approved for redistribution"
            )
        if document.get("contains_secrets") is not False:
            raise ValueError(f"Document {document.get('document_id')} is not approved: secret flag")
        if document.get("contains_personal_data") is not False:
            raise ValueError(
                f"Document {document.get('document_id')} is not approved: personal data flag"
            )
        result[document["document_id"]] = document
    return result


def _create_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS applications (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            description TEXT,
            starter_questions TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS instructions (
            app_id TEXT PRIMARY KEY,
            content TEXT,
            uri TEXT,
            version TEXT,
            updated_at TEXT,
            FOREIGN KEY(app_id) REFERENCES applications(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS settings (
            app_id TEXT PRIMARY KEY,
            config_settings TEXT,
            config_schema TEXT,
            updated_at TEXT,
            FOREIGN KEY(app_id) REFERENCES applications(id) ON DELETE CASCADE
        );

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
        );
        """
    )


def _copy_seed_file(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"Demo seed source file not found: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Install RAGenius demo seed data into writable runtime state.")
    parser.add_argument("--demo-data-dir", type=Path, default=Path("demo-data"))
    parser.add_argument("--runtime-root", type=Path, default=Path("runtime/demo"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    result = install_demo_seed(
        demo_data_dir=args.demo_data_dir,
        runtime_root=args.runtime_root,
        force=args.force,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
