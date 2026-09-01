# Demo Seed Exporter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a repeatable exporter that promotes the three approved real RAGenius runtime applications into portable, tracked public demo seed data.

**Architecture:** The exporter reads the ignored local Builder runtime database and filesystem runtime snapshots, copies allowlisted app metadata/instructions/documents/snapshots into `demo-data/`, and rewrites machine-specific absolute document paths into portable relative seed paths. The source runtime remains untouched; `demo-data/` becomes the immutable public seed input for later install/start/reset scripts.

**Tech Stack:** Python standard library, SQLite, PowerShell wrapper, pytest.

**Spec:** Conversation-approved demo packaging direction: use Church Ministry Prompt Designer, Bible Tutor 4.0, and GPT Application Design Assistant; copy current runtime data into portable `demo-data/`; use newer App Skeleton filesystem instruction snapshots; require manifest-based provenance.

## Global Constraints

- Windows-only demo target.
- Do not mutate ignored runtime DBs, uploads, or snapshots.
- Do not preserve local absolute paths in seed metadata.
- Use only the three approved app IDs:
  - `053eb2ca-54e0-49bf-b7dd-604c9608489e`
  - `2302c77b-3d82-4650-bd15-e0ff9c0faab7`
  - `dd494ba5-face-4eaf-95d1-a55cb9f80c78`
- Use `ragenius_app_skeleton/backend/.state/instruction_understanding_snapshots` as the canonical snapshot source.
- Use `ragenius_builder/flask_scaffold/rag_app.db` as the current real Builder metadata source.
- Keep `demo-data/` portable and reviewable.
- Do not include API keys, tokens, secrets, generated logs, vector indexes, or mutable runtime DBs.

---

### Task 1: Demo Seed Exporter Tests

**Files:**
- Create: `tests/test_demo_seed_exporter.py`

**Interfaces:**
- Consumes: `scripts.export_demo_seed.export_demo_seed(...)`
- Produces: regression coverage for path normalization, app filtering, snapshot freshness, manifest generation, and document copying.

- [ ] **Step 1: Write failing tests**

Create tests that build a temporary source runtime with:

- SQLite tables `applications`, `instructions`, `settings`, `documents`
- one approved app and one excluded app
- one document with an absolute source `file_path`
- one matching `understanding.json` snapshot

Assert that export creates:

- `apps.json`
- `documents.manifest.json`
- `MANIFEST.md`
- copied instruction
- copied document
- copied snapshot
- relative `seed_path`
- no source `file_path` in public seed metadata
- no excluded app

- [ ] **Step 2: Run test to verify failure**

Run: `python -m pytest tests/test_demo_seed_exporter.py -q`

Expected: import failure because `scripts.export_demo_seed` does not exist yet.

---

### Task 2: Demo Seed Exporter Implementation

**Files:**
- Create: `scripts/export_demo_seed.py`
- Create: `scripts/Export-DemoSeed.ps1`

**Interfaces:**
- Produces:
  - `export_demo_seed(repo_root: Path, output_dir: Path, force: bool = False) -> dict`
  - CLI arguments `--repo-root`, `--output-dir`, `--force`

- [ ] **Step 1: Implement exporter**

Exporter behavior:

- Read `ragenius_builder/flask_scaffold/rag_app.db` in read-only mode.
- Export exactly the three approved apps.
- Copy current tracked Builder instructions from `ragenius_builder/flask_scaffold/instructions/{app_id}/instructions.md`.
- Copy allowlisted documents referenced by DB records from their local runtime absolute paths.
- Copy snapshots from `ragenius_app_skeleton/backend/.state/instruction_understanding_snapshots/{app_id}/understanding.json`.
- Verify snapshot `instruction_source_hash` equals SHA-256 of copied instruction text.
- Generate `demo-data/apps.json`.
- Generate `demo-data/documents.manifest.json`.
- Generate `demo-data/MANIFEST.md`.
- Refuse to overwrite existing `demo-data/` unless `--force` is passed.

- [ ] **Step 2: Add PowerShell wrapper**

The wrapper should run the Python module from the repo root:

```powershell
python .\scripts\export_demo_seed.py --repo-root . --output-dir .\demo-data --force
```

---

### Task 3: Export Current Demo Data

**Files:**
- Create: `demo-data/`

**Interfaces:**
- Consumes: current local ignored runtime data.
- Produces: portable immutable seed data.

- [ ] **Step 1: Run exporter**

Run: `python scripts/export_demo_seed.py --repo-root . --output-dir demo-data --force`

- [ ] **Step 2: Inspect generated seed**

Run:

```powershell
Get-ChildItem -Recurse demo-data | Select-Object FullName,Length
python -m json.tool demo-data/apps.json > $null
python -m json.tool demo-data/documents.manifest.json > $null
```

---

### Task 4: Verification

**Files:**
- Validate generated outputs only.

**Interfaces:**
- Confirms exporter correctness and public-data hygiene.

- [ ] **Step 1: Run tests**

Run: `python -m pytest tests/test_demo_seed_exporter.py -q`

- [ ] **Step 2: Run secret-pattern scan**

Run:

```powershell
rg -n --hidden "(API[_-]?KEY|SECRET|TOKEN|PASSWORD|BEGIN (RSA|OPENSSH|PRIVATE) KEY|sk-[A-Za-z0-9]|DEEPSEEK_API_KEY|OPENAI_API_KEY)" demo-data scripts tests
```

Expected: no matches, except benign documentation references if intentionally added.

- [ ] **Step 3: Confirm no absolute local paths in seed JSON**

Run:

```powershell
rg -n "D:\\\\GitHub|C:\\\\Users|file_path" demo-data/*.json
```

Expected: no matches.
