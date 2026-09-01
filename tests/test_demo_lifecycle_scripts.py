import json
import shutil
import sqlite3
import subprocess
from pathlib import Path

from tests.test_demo_seed_installer import APP_ID, _make_demo_data


REPO_ROOT = Path(__file__).resolve().parents[1]


def _powershell() -> str:
    return shutil.which("powershell") or shutil.which("pwsh") or "powershell"


def _run_script(script_name: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            _powershell(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(REPO_ROOT / "scripts" / script_name),
            *args,
        ],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_reset_demo_rebuilds_writable_runtime_from_seed_data(scratch_dir: Path):
    demo_data = _make_demo_data(scratch_dir)
    runtime_root = scratch_dir / "runtime" / "demo"
    runtime_root.mkdir(parents=True)
    (runtime_root / "stale.txt").write_text("old", encoding="utf-8")

    result = _run_script(
        "Reset-Demo.ps1",
        "-DemoDataDir",
        str(demo_data),
        "-RuntimeRoot",
        str(runtime_root),
    )

    assert result.returncode == 0, result.stderr
    assert not (runtime_root / "stale.txt").exists()
    builder_db = runtime_root / "builder" / "rag_app.db"
    assert builder_db.is_file()

    with sqlite3.connect(builder_db) as con:
        document_path = con.execute("SELECT file_path FROM documents WHERE id = 'doc-1'").fetchone()[0]

    assert Path(document_path).resolve().is_file()
    assert str(runtime_root.resolve()) in document_path
    assert "demo-data" not in document_path


def test_start_demo_prepare_only_installs_seed_data_and_writes_runtime_environment(scratch_dir: Path):
    demo_data = _make_demo_data(scratch_dir)
    runtime_root = scratch_dir / "runtime" / "demo"

    result = _run_script(
        "Start-Demo.ps1",
        "-DemoDataDir",
        str(demo_data),
        "-RuntimeRoot",
        str(runtime_root),
        "-PrepareOnly",
    )

    assert result.returncode == 0, result.stderr
    assert (runtime_root / "builder" / "rag_app.db").is_file()
    env_path = runtime_root / "demo-runtime.env.json"
    assert env_path.is_file()
    env = json.loads(env_path.read_text(encoding="utf-8"))
    assert Path(env["RAGENIUS_BUILDER_DB"]).resolve() == (
        runtime_root / "builder" / "rag_app.db"
    ).resolve()
    assert Path(env["RAGENIUS_APP_STATE_DB"]).resolve() == (
        runtime_root / "app" / ".state" / "runtime_state.db"
    ).resolve()
    assert env["RAGENIUS_EXECUTION_SUBSYSTEM_URL"] == "http://127.0.0.1:3001/v1"
    assert "Prepare-only mode" in result.stdout


def test_stop_demo_ignores_missing_process_file(scratch_dir: Path):
    result = _run_script(
        "Stop-Demo.ps1",
        "-RuntimeRoot",
        str(scratch_dir / "runtime" / "demo"),
    )

    assert result.returncode == 0, result.stderr
    assert "No demo process file found" in result.stdout
