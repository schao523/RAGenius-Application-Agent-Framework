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


def test_python_demo_images_include_local_embedding_runtime_dependencies():
    for name in ["builder.Dockerfile", "app-backend.Dockerfile"]:
        dockerfile = (ROOT / "docker" / name).read_text(encoding="utf-8")
        assert "local-embeddings" in dockerfile


def test_python_demo_images_include_shared_package():
    for name in ["builder.Dockerfile", "app-backend.Dockerfile"]:
        dockerfile = (ROOT / "docker" / name).read_text(encoding="utf-8")
        assert "COPY shared ./shared" in dockerfile


def test_app_backend_image_includes_runtime_schema_contracts():
    dockerfile = (ROOT / "docker" / "app-backend.Dockerfile").read_text(encoding="utf-8")

    assert "COPY ragenius_app_skeleton/schemas ./ragenius_app_skeleton/schemas" in dockerfile


def test_demo_compose_uses_public_ghcr_images_and_volumes():
    compose = (ROOT / "packaging" / "demo" / "compose.demo.yml").read_text(encoding="utf-8")

    assert "ghcr.io/${RAGENIUS_GHCR_OWNER:-schao523}/ragenius-builder:${RAGENIUS_IMAGE_TAG:-latest}" in compose
    assert "ghcr.io/${RAGENIUS_GHCR_OWNER:-schao523}/ragenius-app-backend:${RAGENIUS_IMAGE_TAG:-latest}" in compose
    assert "ghcr.io/${RAGENIUS_GHCR_OWNER:-schao523}/ragenius-app-frontend:${RAGENIUS_IMAGE_TAG:-latest}" in compose
    assert "ghcr.io/${RAGENIUS_GHCR_OWNER:-schao523}/ragenius-execution-subsystem:${RAGENIUS_IMAGE_TAG:-latest}" in compose
    assert "ragenius_demo_runtime:" in compose
    assert "./demo-data:/seed/demo-data:ro" in compose
    assert "./models:/models:ro" in compose
    assert "RAG_EMBEDDING_BACKEND: ${RAG_EMBEDDING_BACKEND:-local}" in compose
    assert "RAG_EMBEDDING_MODEL_PATH_BGE_LARGE_ZH: ${RAG_EMBEDDING_MODEL_PATH_BGE_LARGE_ZH:-/models/bge-large-zh}" in compose
    assert "RAG_EMBEDDING_MODEL_PATH_E5_LARGE: ${RAG_EMBEDDING_MODEL_PATH_E5_LARGE:-/models/e5-large}" in compose


def test_demo_env_template_does_not_use_hash_embeddings_by_default():
    template = (ROOT / "packaging" / "demo" / ".env.template").read_text(encoding="utf-8")

    assert "RAG_EMBEDDING_BACKEND=local" in template
    assert "RAG_EMBEDDING_BACKEND=hash" not in template
    assert "RAG_EMBEDDING_MODEL_PATH_BGE_LARGE_ZH=/models/bge-large-zh" in template
    assert "RAG_EMBEDDING_MODEL_PATH_E5_LARGE=/models/e5-large" in template


def test_demo_package_defaults_ghcr_images_to_amd64_for_windows_arm_hosts():
    compose = (ROOT / "packaging" / "demo" / "compose.demo.yml").read_text(encoding="utf-8")
    template = (ROOT / "packaging" / "demo" / ".env.template").read_text(encoding="utf-8")

    assert "RAGENIUS_DOCKER_PLATFORM=linux/amd64" in template
    assert compose.count("platform: ${RAGENIUS_DOCKER_PLATFORM:-linux/amd64}") >= 5


def test_demo_package_uses_non_conflicting_postgres_host_port_by_default():
    compose = (ROOT / "packaging" / "demo" / "compose.demo.yml").read_text(encoding="utf-8")
    template = (ROOT / "packaging" / "demo" / ".env.template").read_text(encoding="utf-8")

    assert "RAGENIUS_POSTGRES_PORT=55433" in template
    assert "${RAGENIUS_POSTGRES_PORT:-55433}:5432" in compose


def test_source_checkout_embedding_setup_script_contract():
    script = (ROOT / "scripts" / "Setup-Embeddings.ps1").read_text(encoding="utf-8")
    downloader = (ROOT / "scripts" / "download_embeddings.py").read_text(encoding="utf-8")
    env_template = (ROOT / ".env.template").read_text(encoding="utf-8")

    assert ".[local-embeddings]" in script
    assert "download_embeddings.py" in script
    assert "rag_subsystem" in script
    assert "models" in script
    assert "BAAI/bge-large-zh-v1.5" in downloader
    assert "intfloat/e5-large-v2" in downloader
    assert "RAG_EMBEDDING_BACKEND=local" in env_template


def test_docker_demo_embedding_setup_script_contract():
    script = (ROOT / "packaging" / "demo" / "Setup-Embeddings.ps1").read_text(encoding="utf-8")

    assert "python:3.12-slim" in script
    assert "download_embeddings.py" in script
    assert "BAAI/bge-large-zh-v1.5" in script
    assert "intfloat/e5-large-v2" in script
    assert "$LASTEXITCODE" in script


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
    assert "download_embeddings.py" in script
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
        env_template = archive.read("RAGenius-Demo/.env.template").decode("utf-8")

    assert "RAGenius-Demo/.env.template" in names
    assert "RAGenius-Demo/compose.demo.yml" in names
    assert "RAGenius-Demo/Setup-Embeddings.ps1" in names
    assert "RAGenius-Demo/download_embeddings.py" in names
    assert "RAGENIUS_IMAGE_TAG=zip-test" in env_template
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
