import json
import sqlite3
from pathlib import Path

import pytest


APP_ID = "053eb2ca-54e0-49bf-b7dd-604c9608489e"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_demo_data(root: Path) -> Path:
    demo_data = root / "demo-data"
    _write_text(
        demo_data / "instructions" / APP_ID / "instructions.md",
        "# Demo Instructions\n",
    )
    _write_text(
        demo_data / "documents" / APP_ID / "guide.md",
        "# Demo Guide\n",
    )
    _write_json(
        demo_data / "snapshots" / APP_ID / "understanding.json",
        {
            "id": "snapshot-1",
            "app_id": APP_ID,
            "compiled_status": "ready",
            "is_active": True,
            "instruction_source_hash": "hash",
        },
    )
    app_payload = {
        "schema_version": 1,
        "apps": [
            {
                "id": APP_ID,
                "name": "Church Ministry Prompt Designer",
                "slug": "church-ministry",
                "description": "Demo app",
                "starter_questions": ["one", "two", "three", "four"],
                "instructions": {
                    "uri": f"instructions/{APP_ID}/instructions.md",
                    "version": "v1",
                    "seed_path": f"instructions/{APP_ID}/instructions.md",
                    "sha256": "unused",
                },
                "settings": {
                    "config_settings": {
                        "llm": {"provider": "deepseek"},
                        "planner_mode": "hybrid_active",
                    },
                    "config_schema": {"type": "object"},
                },
                "snapshot": {
                    "seed_path": f"snapshots/{APP_ID}/understanding.json",
                    "compiled_status": "ready",
                    "freshness": "fresh",
                },
                "documents": [
                    {
                        "id": "doc-1",
                        "filename": "guide.md",
                        "seed_path": f"documents/{APP_ID}/guide.md",
                        "size_bytes": 13,
                        "mime_type": "text/markdown",
                        "language": "zh",
                        "tags": ["demo"],
                    }
                ],
            }
        ],
    }
    documents_payload = {
        "schema_version": 1,
        "documents": [
            {
                "document_id": "doc-1",
                "app_id": APP_ID,
                "filename": "guide.md",
                "seed_path": f"documents/{APP_ID}/guide.md",
                "license": "project-license",
                "redistribution": "approved",
                "contains_secrets": False,
                "contains_personal_data": False,
                "size_bytes": 13,
                "mime_type": "text/markdown",
                "language": "zh",
                "tags": ["demo"],
                "status": "ready",
            }
        ],
    }
    _write_json(demo_data / "apps.json", app_payload)
    _write_json(demo_data / "documents.manifest.json", documents_payload)
    return demo_data


def test_install_demo_seed_creates_builder_db_runtime_files_and_snapshots(scratch_dir: Path):
    from scripts.install_demo_seed import install_demo_seed

    demo_data = _make_demo_data(scratch_dir)
    runtime_root = scratch_dir / "runtime"

    result = install_demo_seed(demo_data_dir=demo_data, runtime_root=runtime_root, force=False)

    assert result["app_count"] == 1
    assert result["document_count"] == 1
    builder_db = runtime_root / "builder" / "rag_app.db"
    assert builder_db.is_file()
    assert (
        runtime_root / "builder" / "instructions" / APP_ID / "instructions.md"
    ).read_text(encoding="utf-8") == "# Demo Instructions\n"
    assert (
        runtime_root
        / "app"
        / ".state"
        / "instruction_understanding_snapshots"
        / APP_ID
        / "understanding.json"
    ).is_file()
    installed_doc = runtime_root / "builder" / "storage" / "uploads" / APP_ID / "doc-1_guide.md"
    assert installed_doc.read_text(encoding="utf-8") == "# Demo Guide\n"

    con = sqlite3.connect(builder_db)
    con.row_factory = sqlite3.Row
    app = dict(con.execute("SELECT * FROM applications WHERE id = ?", (APP_ID,)).fetchone())
    assert app["name"] == "Church Ministry Prompt Designer"
    assert json.loads(app["starter_questions"]) == ["one", "two", "three", "four"]
    settings = dict(con.execute("SELECT * FROM settings WHERE app_id = ?", (APP_ID,)).fetchone())
    assert json.loads(settings["config_settings"])["llm"]["provider"] == "deepseek"
    document = dict(con.execute("SELECT * FROM documents WHERE id = 'doc-1'").fetchone())
    assert document["status"] == "ready"
    assert Path(document["file_path"]).resolve() == installed_doc.resolve()
    assert str(runtime_root.resolve()) in document["file_path"]
    assert "demo-data" not in document["file_path"]
    con.close()


def test_install_demo_seed_refuses_to_overwrite_without_force(scratch_dir: Path):
    from scripts.install_demo_seed import install_demo_seed

    demo_data = _make_demo_data(scratch_dir)
    runtime_root = scratch_dir / "runtime"
    runtime_root.mkdir()
    (runtime_root / "existing.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError, match="already exists"):
        install_demo_seed(demo_data_dir=demo_data, runtime_root=runtime_root, force=False)


def test_install_demo_seed_refuses_unapproved_document(scratch_dir: Path):
    from scripts.install_demo_seed import install_demo_seed

    demo_data = _make_demo_data(scratch_dir)
    manifest_path = demo_data / "documents.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["documents"][0]["redistribution"] = "needs_review"
    _write_json(manifest_path, manifest)

    with pytest.raises(ValueError, match="not approved"):
        install_demo_seed(demo_data_dir=demo_data, runtime_root=scratch_dir / "runtime")
