import hashlib
import json
import sqlite3
from pathlib import Path

import pytest


APP_CHURCH_MINISTRY = "053eb2ca-54e0-49bf-b7dd-604c9608489e"
APP_BIBLE_TUTOR = "2302c77b-3d82-4650-bd15-e0ff9c0faab7"
APP_GPT_DESIGN = "dd494ba5-face-4eaf-95d1-a55cb9f80c78"
APP_EXCLUDED = "0ea6ac80-c96d-4a65-b7e7-645f3ee848e9"


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_source_runtime(repo_root: Path) -> None:
    builder_root = repo_root / "ragenius_builder" / "flask_scaffold"
    instruction_root = builder_root / "instructions"
    upload_root = builder_root / "storage" / "uploads"
    snapshot_root = (
        repo_root
        / "ragenius_app_skeleton"
        / "backend"
        / ".state"
        / "instruction_understanding_snapshots"
    )

    db_path = builder_root / "rag_app.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.executescript(
        """
        CREATE TABLE applications (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            slug TEXT NOT NULL,
            description TEXT NOT NULL,
            starter_questions TEXT NOT NULL,
            updated_at TEXT
        );
        CREATE TABLE instructions (
            app_id TEXT PRIMARY KEY,
            content TEXT,
            uri TEXT NOT NULL,
            version TEXT,
            updated_at TEXT
        );
        CREATE TABLE settings (
            app_id TEXT PRIMARY KEY,
            config_settings TEXT NOT NULL,
            config_schema TEXT NOT NULL,
            updated_at TEXT
        );
        CREATE TABLE documents (
            id TEXT PRIMARY KEY,
            app_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            mime_type TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            language TEXT,
            tags TEXT,
            status TEXT NOT NULL,
            error_message TEXT,
            uploaded_at TEXT,
            file_path TEXT
        );
        """
    )

    selected_apps = [
        (APP_CHURCH_MINISTRY, "Church Ministry Prompt Designer", "church-ministry"),
        (APP_BIBLE_TUTOR, "Bible Tutor 4.0", "bible-tutor"),
        (APP_GPT_DESIGN, "GPT Application Design Assistant", "gpt-design"),
    ]
    all_apps = selected_apps + [(APP_EXCLUDED, "Christian Parenting Coach", "parenting")]
    for app_id, name, slug in all_apps:
        instructions = f"# {name}\n\nCurrent instructions for {app_id}."
        instruction_path = instruction_root / app_id / "instructions.md"
        _write_text(instruction_path, instructions)
        instruction_hash = hashlib.sha256(instructions.encode("utf-8")).hexdigest()
        snapshot = {
            "id": f"snapshot-{app_id}",
            "app_id": app_id,
            "compiled_status": "ready",
            "is_active": True,
            "compiled_at": "2026-08-31T00:00:00+00:00",
            "instruction_uri": f"instructions/{app_id}/instructions.md",
            "instruction_source_version": "v1",
            "instruction_source_hash": instruction_hash,
            "resource_catalog_hash": f"resources-{app_id}",
            "metadata": {"semantic_compile_valid": True},
            "compiled_contract": {
                "full_instruction_text": instructions,
                "resource_reference_catalog": [],
            },
        }
        _write_text(snapshot_root / app_id / "understanding.json", json.dumps(snapshot))

        con.execute(
            "INSERT INTO applications VALUES (?, ?, ?, ?, ?, ?)",
            (
                app_id,
                name,
                slug,
                f"Description for {name}",
                json.dumps([f"Question {index}" for index in range(1, 5)]),
                "2026-08-31T00:00:00",
            ),
        )
        con.execute(
            "INSERT INTO instructions VALUES (?, ?, ?, ?, ?)",
            (
                app_id,
                instructions,
                f"instructions/{app_id}/instructions.md",
                "v1",
                "2026-08-31T00:00:00",
            ),
        )
        con.execute(
            "INSERT INTO settings VALUES (?, ?, ?, ?)",
            (
                app_id,
                json.dumps(
                    {
                        "llm": {"provider": "deepseek"},
                        "planner_mode": "hybrid_active",
                        "instruction_understanding_mode": "hybrid_active",
                    }
                ),
                json.dumps({"type": "object"}),
                "2026-08-31T00:00:00",
            ),
        )
        source_doc = upload_root / app_id / f"doc-{app_id}.md"
        _write_text(source_doc, f"# Runtime document for {name}\n")
        con.execute(
            "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"doc-{app_id}",
                app_id,
                f"{slug}.md",
                "text/markdown",
                source_doc.stat().st_size,
                "zh",
                json.dumps(["demo"]),
                "ready",
                None,
                "2026-08-31T00:00:00",
                str(source_doc.resolve()),
            ),
        )

    con.commit()
    con.close()


def test_export_demo_seed_copies_only_selected_apps_and_normalizes_paths(scratch_dir: Path):
    from scripts.export_demo_seed import export_demo_seed

    repo_root = scratch_dir / "repo"
    _make_source_runtime(repo_root)
    output_dir = repo_root / "demo-data"

    result = export_demo_seed(repo_root=repo_root, output_dir=output_dir, force=False)

    assert result["app_count"] == 3
    assert result["document_count"] == 3
    assert (output_dir / "MANIFEST.md").is_file()

    apps_payload = json.loads((output_dir / "apps.json").read_text(encoding="utf-8"))
    exported_ids = {app["id"] for app in apps_payload["apps"]}
    assert exported_ids == {APP_CHURCH_MINISTRY, APP_BIBLE_TUTOR, APP_GPT_DESIGN}
    assert APP_EXCLUDED not in exported_ids

    for app in apps_payload["apps"]:
        assert "file_path" not in json.dumps(app)
        assert app["instructions"]["seed_path"] == f"instructions/{app['id']}/instructions.md"
        assert app["snapshot"]["seed_path"] == f"snapshots/{app['id']}/understanding.json"
        assert (output_dir / app["instructions"]["seed_path"]).is_file()
        assert (output_dir / app["snapshot"]["seed_path"]).is_file()
        assert app["snapshot"]["freshness"] == "fresh"

    documents_payload = json.loads(
        (output_dir / "documents.manifest.json").read_text(encoding="utf-8")
    )
    assert len(documents_payload["documents"]) == 3
    for document in documents_payload["documents"]:
        assert document["app_id"] in exported_ids
        assert document["redistribution"] == "approved"
        assert document["contains_secrets"] is False
        assert document["contains_personal_data"] is False
        assert "D:\\" not in json.dumps(document)
        assert "C:\\" not in json.dumps(document)
        assert "file_path" not in document
        assert (output_dir / document["seed_path"]).is_file()


def test_export_demo_seed_refuses_stale_snapshot(scratch_dir: Path):
    from scripts.export_demo_seed import export_demo_seed

    repo_root = scratch_dir / "repo"
    _make_source_runtime(repo_root)
    snapshot_path = (
        repo_root
        / "ragenius_app_skeleton"
        / "backend"
        / ".state"
        / "instruction_understanding_snapshots"
        / APP_BIBLE_TUTOR
        / "understanding.json"
    )
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    snapshot["instruction_source_hash"] = "stale"
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")

    with pytest.raises(ValueError, match="stale instruction snapshot"):
        export_demo_seed(repo_root=repo_root, output_dir=repo_root / "demo-data")


def test_export_demo_seed_refuses_to_overwrite_without_force(scratch_dir: Path):
    from scripts.export_demo_seed import export_demo_seed

    repo_root = scratch_dir / "repo"
    _make_source_runtime(repo_root)
    output_dir = repo_root / "demo-data"
    output_dir.mkdir(parents=True)
    (output_dir / "existing.txt").write_text("keep me", encoding="utf-8")

    with pytest.raises(FileExistsError, match="already exists"):
        export_demo_seed(repo_root=repo_root, output_dir=output_dir, force=False)
