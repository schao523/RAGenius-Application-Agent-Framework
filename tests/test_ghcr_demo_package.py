from pathlib import Path
import shutil
import subprocess
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def test_dockerfiles_exist_for_public_demo_images():
    assert (ROOT / "docker" / "builder.Dockerfile").is_file()
    assert (ROOT / "docker" / "app-backend.Dockerfile").is_file()
    assert (ROOT / "docker" / "app-frontend.Dockerfile").is_file()
    assert (ROOT / "docker" / "execution-subsystem.Dockerfile").is_file()


def test_python_demo_images_include_shared_package():
    for name in ["builder.Dockerfile", "app-backend.Dockerfile"]:
        dockerfile = (ROOT / "docker" / name).read_text(encoding="utf-8")
        assert "COPY shared ./shared" in dockerfile


def test_demo_compose_uses_public_ghcr_images_and_volumes():
    compose = (ROOT / "packaging" / "demo" / "compose.demo.yml").read_text(encoding="utf-8")

    assert "ghcr.io/${RAGENIUS_GHCR_OWNER:-schao523}/ragenius-builder:${RAGENIUS_IMAGE_TAG:-latest}" in compose
    assert "ghcr.io/${RAGENIUS_GHCR_OWNER:-schao523}/ragenius-app-backend:${RAGENIUS_IMAGE_TAG:-latest}" in compose
    assert "ghcr.io/${RAGENIUS_GHCR_OWNER:-schao523}/ragenius-app-frontend:${RAGENIUS_IMAGE_TAG:-latest}" in compose
    assert "ghcr.io/${RAGENIUS_GHCR_OWNER:-schao523}/ragenius-execution-subsystem:${RAGENIUS_IMAGE_TAG:-latest}" in compose
    assert "ragenius_demo_runtime:" in compose
    assert "./demo-data:/seed/demo-data:ro" in compose


def test_release_package_scripts_exist_and_reference_compose():
    for name in ["Install.ps1", "Start.ps1", "Stop.ps1", "Reset.ps1"]:
        path = ROOT / "packaging" / "demo" / name
        assert path.is_file()
        script = path.read_text(encoding="utf-8")
        assert "compose.demo.yml" in script
        assert "$LASTEXITCODE" in script


def test_build_demo_package_script_copies_seed_and_templates():
    script = (ROOT / "scripts" / "Build-DemoPackage.ps1").read_text(encoding="utf-8")

    assert "RAGenius-Demo-$Version-Windows" in script
    assert "demo-data" in script
    assert ".env.template" in script
    assert "System.IO.Compression.ZipFile" in script


def test_github_workflow_builds_and_packages_demo():
    workflow = (ROOT / ".github" / "workflows" / "ghcr-demo-package.yml").read_text(encoding="utf-8")

    assert "ghcr.io" in workflow
    assert "docker/build-push-action" in workflow
    assert "Build-DemoPackage.ps1" in workflow
    assert "RAGenius-Demo-${{ github.ref_name }}-Windows.zip" in workflow


def test_build_demo_package_includes_seed_documents(scratch_dir):
    output_root = scratch_dir / "dist"
    powershell = shutil.which("powershell") or shutil.which("pwsh") or "powershell"

    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "scripts" / "Build-DemoPackage.ps1"),
            "-Version",
            "zip-test",
            "-OutputRoot",
            str(output_root),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    zip_path = output_root / "RAGenius-Demo-zip-test-Windows.zip"
    assert zip_path.is_file()

    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())

    assert "RAGenius-Demo/.env.template" in names
    assert "RAGenius-Demo/compose.demo.yml" in names
    assert (
        "RAGenius-Demo/demo-data/documents/053eb2ca-54e0-49bf-b7dd-604c9608489e/AI 工具套餐體系.pdf"
        in names
    )
    document_entries = [
        name
        for name in names
        if name.startswith("RAGenius-Demo/demo-data/documents/") and not name.endswith("/")
    ]
    assert len(document_entries) == 37
