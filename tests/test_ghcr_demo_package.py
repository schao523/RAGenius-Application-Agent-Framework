from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_dockerfiles_exist_for_public_demo_images():
    assert (ROOT / "docker" / "builder.Dockerfile").is_file()
    assert (ROOT / "docker" / "app-backend.Dockerfile").is_file()
    assert (ROOT / "docker" / "app-frontend.Dockerfile").is_file()
    assert (ROOT / "docker" / "execution-subsystem.Dockerfile").is_file()


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
    assert "Compress-Archive" in script


def test_github_workflow_builds_and_packages_demo():
    workflow = (ROOT / ".github" / "workflows" / "ghcr-demo-package.yml").read_text(encoding="utf-8")

    assert "ghcr.io" in workflow
    assert "docker/build-push-action" in workflow
    assert "Build-DemoPackage.ps1" in workflow
    assert "RAGenius-Demo-${{ github.ref_name }}-Windows.zip" in workflow
