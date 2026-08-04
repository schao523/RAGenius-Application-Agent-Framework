# Active Runtime Clarification And Stabilization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the existing directory names, document `ragenius_app_skeleton` as the active integrated runtime and nested `ragenius_app` as legacy/reference, make the instruction-understanding integration test hermetic, verify the complete system, and publish the nested branch before the parent branch.

**Architecture:** No directory or package migration is performed. Runtime ownership remains with `ragenius_app_skeleton`; `ragenius_app` remains an independently runnable legacy/reference submodule. The failing integration test is corrected at the test boundary by disabling the ambient semantic compiler for the parser-only behavior it asserts, leaving production fallback and diagnostic-only behavior unchanged.

**Tech Stack:** Markdown, Python 3.14, FastAPI TestClient, unittest.mock, pytest, Vitest, Vite, TypeScript, Node.js test runner, Git.

## Global Constraints

- Do not rename `ragenius_app` or `ragenius_app_skeleton`.
- Do not move active runtime behavior into the legacy nested app.
- Do not change semantic compilation production behavior.
- Preserve `app_id` and session isolation.
- Keep generated dependencies and runtime state untracked.
- Publish the nested repository commit before publishing the parent commit that references it.

---

### Task 1: Clarify Runtime Ownership

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `ragenius_app/README.md`

**Interfaces:**
- Consumes: Current repository topology and the handover contract in `docs/2026-05-24-ragenius-app-ragenius-app-skeleton-handover.md`.
- Produces: Unambiguous contributor and operator guidance without changing any runtime path.

- [ ] **Step 1: Add the active runtime to the root component list**

Update the component descriptions to state:

```markdown
- `ragenius_app_skeleton/`: active Builder-backed end-user chat and workflow runtime
- `ragenius_app/`: legacy/reference application scaffold and specification source; not used by the integrated runtime
```

- [ ] **Step 2: Update root ownership guidance**

Replace guidance that sends active end-user work to `ragenius_app` with guidance that sends it to `ragenius_app_skeleton`, while reserving `ragenius_app` for legacy/reference maintenance.

- [ ] **Step 3: Add a legacy/reference banner to the nested README**

Place this notice immediately after the title:

```markdown
> **Status: legacy/reference application.** The active integrated Builder-backed runtime is `ragenius_app_skeleton` in the parent repository. This repository remains independently runnable and preserves specifications, prompts, schemas, and original workflow behavior, but new integrated runtime development belongs in `ragenius_app_skeleton`.
```

- [ ] **Step 4: Verify role wording**

Run:

```powershell
rg -n "active.*runtime|legacy/reference|ragenius_app_skeleton" README.md AGENTS.md ragenius_app/README.md
```

Expected: all three files explicitly distinguish the active skeleton runtime from the nested legacy/reference app.

### Task 2: Make The Instruction-Understanding Test Hermetic

**Files:**
- Modify: `ragenius_app_skeleton/tests/test_builder_chat_integration.py`
- Test: `ragenius_app_skeleton/tests/test_builder_chat_integration.py`

**Interfaces:**
- Consumes: `backend.app.main.build_instruction_understanding_compiler(state) -> Optional[Callable]`.
- Produces: A deterministic endpoint integration test that exercises the parser-only compile path without ambient network or LLM configuration.

- [ ] **Step 1: Verify the existing regression is red**

Run:

```powershell
$env:PYTHONPATH='..'
python -m pytest tests\test_builder_chat_integration.py::BuilderChatIntegrationTests::test_instruction_understanding_detail_route_returns_compiled_and_review_payload -q
```

Expected before the test fix: FAIL because `payload["compiled"]` is `None` when an ambient semantic compiler produces a diagnostic-only attempt.

- [ ] **Step 2: Disable the ambient compiler inside this test**

Wrap the recompile and detail requests with:

```python
with mock.patch("backend.app.main.build_instruction_understanding_compiler", return_value=None):
    seeded = self.client.post(
        "/apps/app-1/instruction-understanding/recompile",
        headers={"x-role": "admin"},
    )
    self.assertEqual(seeded.status_code, 200)
    detail = self.client.get(
        "/apps/app-1/instruction-understanding",
        headers={"x-role": "admin"},
    )
```

- [ ] **Step 3: Verify the regression is green**

Run the targeted command from Step 1.

Expected: `1 passed` with no external semantic compiler call.

- [ ] **Step 4: Verify neighboring semantic compilation tests**

Run:

```powershell
$env:PYTHONPATH='..'
python -m pytest tests\test_builder_chat_integration.py -q
```

Expected: all tests in the integration module pass, including explicit valid and invalid semantic compiler cases.

### Task 3: Verify The Complete Repository

**Files:**
- No source changes.

**Interfaces:**
- Consumes: Final documentation and test tree.
- Produces: Fresh evidence for all active applications and the legacy/reference app.

- [ ] **Step 1: Run root and skeleton Python suites**

Run:

```powershell
python -m pytest tests
$env:PYTHONPATH='..'
python -m pytest tests backend\tests
```

Use the repository root for the first command and `ragenius_app_skeleton` for the second.

- [ ] **Step 2: Run skeleton frontend verification**

Run in `ragenius_app_skeleton/frontend`:

```powershell
npm test -- --run
npm run build
```

- [ ] **Step 3: Run execution subsystem verification**

Run in `ragenius_execution_subsystem`:

```powershell
npm test
npm run lint
python -m pytest tests_py
```

- [ ] **Step 4: Run nested legacy/reference verification**

Run the nested Python suite with the parent `rag_subsystem` loaded and the nested `workflows` namespace selected, then run `npm run build` in `ragenius_app/frontend`.

- [ ] **Step 5: Audit Git state**

Run:

```powershell
git status --short --branch --untracked-files=all
git -C ragenius_app status --short --branch --untracked-files=all
```

Expected: only the intended documentation and test changes remain before committing; no generated files are tracked.

### Task 4: Commit And Publish In Dependency Order

**Files:**
- Commit the plan independently.
- Commit the nested README in the nested repository.
- Commit root documentation and the deterministic test in the parent repository.

**Interfaces:**
- Consumes: Verified commits in both repositories.
- Produces: A remotely reachable nested commit before the parent branch references and publishes it.

- [ ] **Step 1: Commit the nested status clarification**

```powershell
git -C ragenius_app add README.md
git -C ragenius_app commit -m "Clarify legacy reference app status"
```

- [ ] **Step 2: Create and push a nested feature branch**

```powershell
git -C ragenius_app switch -c codex/ragenius-app-reference-refresh
git -C ragenius_app push -u origin codex/ragenius-app-reference-refresh
```

- [ ] **Step 3: Update and commit the parent submodule pointer with parent changes**

```powershell
git add README.md AGENTS.md docs/superpowers/plans/2026-08-03-active-runtime-clarification-and-stabilization.md ragenius_app_skeleton/tests/test_builder_chat_integration.py ragenius_app
git commit -m "Clarify active runtime ownership"
```

- [ ] **Step 4: Push the parent feature branch**

```powershell
git push -u origin features/core-ragenius-system-implementation
```

- [ ] **Step 5: Confirm remote publication and clean worktrees**

Run:

```powershell
git status --short --branch
git -C ragenius_app status --short --branch
git log -3 --oneline
git -C ragenius_app log -3 --oneline
```

Expected: both repositories are clean and their current branches track the corresponding remote branches.
