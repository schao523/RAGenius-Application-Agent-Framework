# GHCR Demo Package Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a baseline GHCR/Docker public demo package path that builds service images, publishes them through GitHub Actions, and creates a Windows-friendly demo ZIP scaffold.

**Architecture:** Keep the source-checkout runner as the validated developer path. Add Dockerfiles for Builder, app backend, app frontend, and execution subsystem. Add a release package folder containing `compose.demo.yml`, PowerShell wrapper scripts, `.env.template`, and `demo-data/` copied by a packaging script.

**Tech Stack:** Docker, Docker Compose, GitHub Actions, GHCR, PowerShell, Python tests.

**Spec:** `docs/source-checkout-demo-runner-guide.md`

## Global Constraints

- Windows remains the primary documented demo platform.
- Public demo images are pulled from GHCR; users should not build images locally for the public demo path.
- `demo-data/` is immutable release seed data.
- Writable runtime state lives in Docker volumes for the packaged demo.
- LLM calls still require internet and user-provided API keys.
- External interactive integrations remain disabled by default.

---

### Task 1: Static Packaging Contract Tests

**Files:**
- Create: `tests/test_ghcr_demo_package.py`

**Interfaces:**
- Consumes: repository file tree.
- Produces: tests that enforce packaging artifact structure.

- [ ] **Step 1: Write failing tests**

Create tests that assert:

```python
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
        assert "compose.demo.yml" in path.read_text(encoding="utf-8")

def test_github_workflow_builds_and_packages_demo():
    workflow = (ROOT / ".github" / "workflows" / "ghcr-demo-package.yml").read_text(encoding="utf-8")
    assert "ghcr.io" in workflow
    assert "docker/build-push-action" in workflow
    assert "Build-DemoPackage.ps1" in workflow
    assert "RAGenius-Demo-${{ github.ref_name }}-Windows.zip" in workflow
```

- [ ] **Step 2: Verify tests fail**

Run:

```powershell
python -m pytest tests/test_ghcr_demo_package.py -q
```

Expected: fails because artifacts do not exist.

---

### Task 2: Dockerfiles

**Files:**
- Create: `docker/builder.Dockerfile`
- Create: `docker/app-backend.Dockerfile`
- Create: `docker/app-frontend.Dockerfile`
- Create: `docker/execution-subsystem.Dockerfile`

**Interfaces:**
- Consumes: current repo source.
- Produces: image definitions used by GitHub Actions and packaged compose.

- [ ] **Step 1: Add Python Builder Dockerfile**

Use `python:3.12-slim`, install root package plus Builder requirements, copy `rag_subsystem`, `ragenius_builder`, `workflows`, and `scripts/install_demo_seed.py`, expose `8011`, and run Flask on `0.0.0.0`.

- [ ] **Step 2: Add Python app backend Dockerfile**

Use `python:3.12-slim`, install root package plus backend and Builder requirements, copy app backend, Builder Flask scaffold, `rag_subsystem`, `workflows`, and installer script, expose `8000`, and run uvicorn on `0.0.0.0`.

- [ ] **Step 3: Add app frontend Dockerfile**

Build Vite assets with Node 22 and serve with nginx on port `80`. Default `VITE_APP_BASE_URL` to `http://127.0.0.1:8000`.

- [ ] **Step 4: Add execution subsystem Dockerfile**

Use Node 22, run `npm ci`, `npx prisma generate`, `npm run build`, expose `3001`, and run `npx prisma migrate deploy` before `node dist/src/server.js`.

- [ ] **Step 5: Run static tests**

Run:

```powershell
python -m pytest tests/test_ghcr_demo_package.py -q
```

Expected: remaining failures for compose/scripts/workflow.

---

### Task 3: Demo Package Scaffold

**Files:**
- Create: `packaging/demo/compose.demo.yml`
- Create: `packaging/demo/.env.template`
- Create: `packaging/demo/Install.ps1`
- Create: `packaging/demo/Start.ps1`
- Create: `packaging/demo/Stop.ps1`
- Create: `packaging/demo/Reset.ps1`
- Create: `scripts/Build-DemoPackage.ps1`

**Interfaces:**
- Consumes: GHCR images, `demo-data/`, root `.env.template`, Docker Compose.
- Produces: local demo package directory/ZIP under `dist/`.

- [ ] **Step 1: Add compose**

Define services:

- `postgres`
- `seed-init`
- `execution`
- `builder`
- `app-backend`
- `app-frontend`

Use Docker volumes:

- `ragenius_demo_runtime`
- `ragenius_demo_postgres`

- [ ] **Step 2: Add package scripts**

Scripts wrap:

```powershell
docker compose -f compose.demo.yml pull
docker compose -f compose.demo.yml up -d
docker compose -f compose.demo.yml down
docker compose -f compose.demo.yml down -v
```

- [ ] **Step 3: Add packaging script**

`scripts/Build-DemoPackage.ps1` copies `packaging/demo/*`, root `.env.template`, and `demo-data/` into `dist/RAGenius-Demo-<version>-Windows/`, then creates `dist/RAGenius-Demo-<version>-Windows.zip`.

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m pytest tests/test_ghcr_demo_package.py tests/test_demo_seed_installer.py tests/test_demo_lifecycle_scripts.py -q
```

Expected: remaining failures only for workflow.

---

### Task 4: GitHub Actions GHCR Workflow

**Files:**
- Create: `.github/workflows/ghcr-demo-package.yml`

**Interfaces:**
- Consumes: Dockerfiles and packaging script.
- Produces: pushed GHCR images and release ZIP artifact.

- [ ] **Step 1: Add workflow triggers**

Trigger on:

- manual `workflow_dispatch`
- tag push `v*`

- [ ] **Step 2: Add permissions**

Use:

```yaml
permissions:
  contents: write
  packages: write
```

- [ ] **Step 3: Build/push images**

Use `docker/login-action`, `docker/metadata-action`, and `docker/build-push-action`.

- [ ] **Step 4: Build ZIP artifact**

Run:

```powershell
.\scripts\Build-DemoPackage.ps1 -Version $env:GITHUB_REF_NAME
```

- [ ] **Step 5: Upload artifact and attach to release on tag**

Use `actions/upload-artifact` for all runs and GitHub CLI `gh release upload` for tag runs.

- [ ] **Step 6: Run tests**

Run:

```powershell
python -m pytest tests/test_ghcr_demo_package.py tests/test_demo_seed_exporter.py tests/test_demo_seed_installer.py tests/test_demo_lifecycle_scripts.py -q
```

Expected: all pass.

---

## Self-Review

- Spec coverage: The plan covers image definitions, compose-based runtime, immutable seed data, writable volumes, Windows scripts, GitHub Actions, and tests.
- Placeholder scan: No task uses TBD/TODO as a required implementation detail.
- Type consistency: File names and paths are consistent across tests, scripts, and workflow.
