from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


APP_CHURCH_MINISTRY = "053eb2ca-54e0-49bf-b7dd-604c9608489e"
APP_BIBLE_TUTOR = "2302c77b-3d82-4650-bd15-e0ff9c0faab7"
APP_GPT_DESIGN = "dd494ba5-face-4eaf-95d1-a55cb9f80c78"

APP_EXPORT_ORDER = [APP_CHURCH_MINISTRY, APP_BIBLE_TUTOR, APP_GPT_DESIGN]

APP_PURPOSE = {
    APP_CHURCH_MINISTRY: "Prompt design workflow demo for church ministry content and structured prompt generation.",
    APP_BIBLE_TUTOR: "RAG and guided Bible-study workflow demo with app-scoped resources.",
    APP_GPT_DESIGN: "GPT application design workflow demo for Builder-authored application design support.",
}


@dataclass(frozen=True)
class SourcePaths:
    repo_root: Path
    builder_root: Path
    builder_db: Path
    instruction_root: Path
    upload_root: Path
    snapshot_root: Path


def export_demo_seed(repo_root: Path, output_dir: Path, force: bool = False) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    output_dir = output_dir.resolve()
    paths = _source_paths(repo_root)
    _validate_sources(paths)
    _prepare_output_dir(output_dir, force=force)

    apps: list[dict[str, Any]] = []
    document_manifest: list[dict[str, Any]] = []

    with _connect_readonly(paths.builder_db) as con:
        con.row_factory = sqlite3.Row
        for app_id in APP_EXPORT_ORDER:
            app = _required_row(con, "SELECT * FROM applications WHERE id = ?", (app_id,))
            instruction = _required_row(
                con,
                "SELECT * FROM instructions WHERE app_id = ?",
                (app_id,),
            )
            settings = _required_row(con, "SELECT * FROM settings WHERE app_id = ?", (app_id,))
            documents = con.execute(
                "SELECT * FROM documents WHERE app_id = ? AND status = 'ready' ORDER BY filename, id",
                (app_id,),
            ).fetchall()

            instruction_seed_path, instruction_hash = _copy_instruction(paths, output_dir, app_id)
            snapshot_seed_path, snapshot_summary = _copy_snapshot(
                paths,
                output_dir,
                app_id,
                expected_instruction_hash=instruction_hash,
            )
            exported_documents = [
                _copy_document(output_dir, app_id, dict(document)) for document in documents
            ]
            document_manifest.extend(exported_documents)

            apps.append(
                {
                    "id": app["id"],
                    "name": app["name"],
                    "slug": app["slug"],
                    "description": app["description"],
                    "starter_questions": _loads_json(app["starter_questions"], []),
                    "purpose": APP_PURPOSE[app_id],
                    "instructions": {
                        "uri": instruction["uri"],
                        "version": instruction["version"],
                        "seed_path": instruction_seed_path,
                        "sha256": instruction_hash,
                    },
                    "settings": {
                        "config_settings": _loads_json(settings["config_settings"], {}),
                        "config_schema": _loads_json(settings["config_schema"], {}),
                    },
                    "snapshot": {
                        "seed_path": snapshot_seed_path,
                        **snapshot_summary,
                    },
                    "documents": [
                        {
                            "id": document["document_id"],
                            "filename": document["filename"],
                            "seed_path": document["seed_path"],
                            "sha256": document["sha256"],
                            "size_bytes": document["size_bytes"],
                            "mime_type": document["mime_type"],
                            "language": document["language"],
                            "tags": document["tags"],
                        }
                        for document in exported_documents
                    ],
                }
            )

    apps_payload = {
        "schema_version": 1,
        "source": {
            "builder_db": _repo_relative(paths.builder_db, repo_root),
            "instruction_root": _repo_relative(paths.instruction_root, repo_root),
            "snapshot_root": _repo_relative(paths.snapshot_root, repo_root),
            "upload_root": _repo_relative(paths.upload_root, repo_root),
        },
        "apps": apps,
    }
    documents_payload = {
        "schema_version": 1,
        "documents": document_manifest,
    }
    allowlist_payload = {
        "schema_version": 1,
        "apps": [
            {
                "app_id": app_id,
                "name": next(app["name"] for app in apps if app["id"] == app_id),
                "include_ready_documents": True,
                "purpose": APP_PURPOSE[app_id],
            }
            for app_id in APP_EXPORT_ORDER
        ],
        "snapshot_source": "ragenius_app_skeleton/backend/.state/instruction_understanding_snapshots",
        "notes": [
            "This allowlist intentionally excludes the Christian Parenting Coach app from the public demo seed.",
            "Documents are copied from ready document records only.",
        ],
    }

    _write_json(output_dir / "apps.json", apps_payload)
    _write_json(output_dir / "documents.manifest.json", documents_payload)
    _write_json(output_dir / "source-allowlist.json", allowlist_payload)
    _write_manifest_md(output_dir / "MANIFEST.md", apps, document_manifest)

    return {
        "app_count": len(apps),
        "document_count": len(document_manifest),
        "output_dir": str(output_dir),
    }


def _source_paths(repo_root: Path) -> SourcePaths:
    builder_root = repo_root / "ragenius_builder" / "flask_scaffold"
    return SourcePaths(
        repo_root=repo_root,
        builder_root=builder_root,
        builder_db=builder_root / "rag_app.db",
        instruction_root=builder_root / "instructions",
        upload_root=builder_root / "storage" / "uploads",
        snapshot_root=repo_root
        / "ragenius_app_skeleton"
        / "backend"
        / ".state"
        / "instruction_understanding_snapshots",
    )


def _validate_sources(paths: SourcePaths) -> None:
    if not paths.builder_db.is_file():
        raise FileNotFoundError(f"Builder runtime DB not found: {paths.builder_db}")
    if not paths.instruction_root.is_dir():
        raise FileNotFoundError(f"Instruction root not found: {paths.instruction_root}")
    if not paths.snapshot_root.is_dir():
        raise FileNotFoundError(f"Snapshot root not found: {paths.snapshot_root}")


def _prepare_output_dir(output_dir: Path, force: bool) -> None:
    if output_dir.exists():
        if not force:
            raise FileExistsError(f"Output directory already exists: {output_dir}")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path.as_posix()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def _required_row(
    con: sqlite3.Connection,
    query: str,
    params: tuple[Any, ...],
) -> sqlite3.Row:
    row = con.execute(query, params).fetchone()
    if row is None:
        raise ValueError(f"Required runtime row missing for query: {query} {params}")
    return row


def _copy_instruction(paths: SourcePaths, output_dir: Path, app_id: str) -> tuple[str, str]:
    source = paths.instruction_root / app_id / "instructions.md"
    if not source.is_file():
        raise FileNotFoundError(f"Instruction file not found for {app_id}: {source}")
    destination = output_dir / "instructions" / app_id / "instructions.md"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    content = destination.read_text(encoding="utf-8")
    return _seed_relative(destination, output_dir), _sha256_text(content)


def _copy_snapshot(
    paths: SourcePaths,
    output_dir: Path,
    app_id: str,
    expected_instruction_hash: str,
) -> tuple[str, dict[str, Any]]:
    source = paths.snapshot_root / app_id / "understanding.json"
    if not source.is_file():
        raise FileNotFoundError(f"Instruction-understanding snapshot not found for {app_id}: {source}")
    snapshot = json.loads(source.read_text(encoding="utf-8"))
    snapshot_hash = snapshot.get("instruction_source_hash")
    if snapshot_hash != expected_instruction_hash:
        raise ValueError(
            "stale instruction snapshot for "
            f"{app_id}: snapshot hash {snapshot_hash!r} != instruction hash {expected_instruction_hash!r}"
        )
    destination = output_dir / "snapshots" / app_id / "understanding.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    _write_json(destination, snapshot)
    return (
        _seed_relative(destination, output_dir),
        {
            "id": snapshot.get("id"),
            "compiled_status": snapshot.get("compiled_status"),
            "compiled_at": snapshot.get("compiled_at"),
            "instruction_source_hash": snapshot_hash,
            "resource_catalog_hash": snapshot.get("resource_catalog_hash"),
            "freshness": "fresh",
            "metadata": snapshot.get("metadata") or {},
        },
    )


def _copy_document(output_dir: Path, app_id: str, document: dict[str, Any]) -> dict[str, Any]:
    source_path_value = (document.get("file_path") or "").strip()
    if not source_path_value:
        raise FileNotFoundError(
            f"Ready document {document.get('id')} for {app_id} has no source file_path"
        )
    source = Path(source_path_value)
    if not source.is_file():
        raise FileNotFoundError(f"Document source file not found: {source}")

    filename = document["filename"]
    destination = output_dir / "documents" / app_id / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination = output_dir / "documents" / app_id / f"{document['id']}_{filename}"
    shutil.copy2(source, destination)

    license_info = _document_license(app_id, filename)
    return {
        "document_id": document["id"],
        "app_id": app_id,
        "filename": filename,
        "seed_path": _seed_relative(destination, output_dir),
        "source_type": license_info["source_type"],
        "license": license_info["license"],
        "copyright_holder": license_info["copyright_holder"],
        "redistribution": "approved",
        "contains_secrets": False,
        "contains_personal_data": False,
        "sha256": _sha256_file(destination),
        "size_bytes": destination.stat().st_size,
        "mime_type": document["mime_type"],
        "language": document["language"],
        "tags": _loads_json(document.get("tags"), []),
        "status": document["status"],
    }


def _document_license(app_id: str, filename: str) -> dict[str, str | None]:
    if app_id == APP_BIBLE_TUTOR and filename.startswith("Bible "):
        return {
            "source_type": "public-domain",
            "license": "public-domain",
            "copyright_holder": None,
        }
    return {
        "source_type": "project-authored",
        "license": "project-license",
        "copyright_holder": "schao523",
    }


def _loads_json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_manifest_md(
    path: Path,
    apps: list[dict[str, Any]],
    documents: list[dict[str, Any]],
) -> None:
    lines = [
        "# RAGenius Demo Data Manifest",
        "",
        "This folder contains immutable seed data for the public RAGenius demo.",
        "Demo startup scripts should copy this data into writable runtime folders and regenerate machine-local paths.",
        "",
        "## Included demo applications",
        "",
        "| Application | App ID | Documents | Snapshot status | Purpose |",
        "|---|---:|---:|---|---|",
    ]
    for app in apps:
        lines.append(
            "| "
            + " | ".join(
                [
                    app["name"],
                    f"`{app['id']}`",
                    str(len(app["documents"])),
                    str(app["snapshot"].get("compiled_status")),
                    app["purpose"],
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Provenance",
            "",
            "- Bible PDFs are marked `public-domain`.",
            "- Project-authored markdown and PDF resources are marked `project-authored`.",
            "- No credentials, private user data, generated logs, mutable runtime DBs, or vector indexes are intentionally included.",
            "",
            "## Document inventory",
            "",
            "| Application ID | Filename | License | Redistribution | Seed path |",
            "|---|---|---|---|---|",
        ]
    )
    for document in documents:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{document['app_id']}`",
                    document["filename"],
                    document["license"],
                    document["redistribution"],
                    f"`{document['seed_path']}`",
                ]
            )
            + " |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _seed_relative(path: Path, output_dir: Path) -> str:
    return path.resolve().relative_to(output_dir.resolve()).as_posix()


def _repo_relative(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def main() -> int:
    parser = argparse.ArgumentParser(description="Export portable RAGenius public demo seed data.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, default=Path("demo-data"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    result = export_demo_seed(
        repo_root=args.repo_root,
        output_dir=args.output_dir,
        force=args.force,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
