# Builder Review/Governance UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a minimal review/governance panel to the existing Builder skill detail page so operators can inspect the inferred executable contract before publishing a skill version.

**Architecture:** Builder already persists normalized skill contract metadata in version records. This slice adds route-level shaping in `app.py` and a display panel in `skill_detail.html`, without adding new workflow states, storage redesign, or execution-subsystem changes.

**Tech Stack:** Flask/Python (`ragenius_builder`), Jinja templates, existing Builder `DatabaseStore`, current skill import/publish/bind/test routes.

---

## File Structure

### Builder backend

- Modify: `ragenius_builder/flask_scaffold/app.py`
  - prepare a review-ready contract view model for skill versions on the skill detail route

### Builder template

- Modify: `ragenius_builder/flask_scaffold/templates/skill_detail.html`
  - render the contract review/governance panel

### Tests

- Modify: `ragenius_builder/flask_scaffold/tests/test_skill_management.py`
  - add route-level coverage for safe, review-required, and unsupported review states

---

## Task 1: Add route-level contract review view model shaping

**Files:**
- Modify: `ragenius_builder/flask_scaffold/app.py`

- [ ] **Step 1: Inspect current version metadata usage on the skill detail route**

Confirm the detail route currently passes raw versions and bindings directly to the template.

- [ ] **Step 2: Add a contract review view helper**

Add a small helper that accepts a skill version row and returns a review-ready view model containing:

- `version_id`
- `version`
- `state`
- `policy_class`
- `risk_label`
- `auto_finalize`
- `template_family`
- `required_tools`
- `required_permissions`
- `input_schema_pretty`
- `output_schema_pretty`
- `workflow_pretty`
- `has_contract`
- `review_note`

Recommended risk mapping:

- `safe_read` -> `Safe Read`
- `review_required` -> `Review Required`
- `unsupported` -> `Unsupported`

- [ ] **Step 3: Pass review view models into `skill_detail.html`**

Update the `skill_detail` route to include:

- review data for each version, or
- a `versions_with_review` list where each version row is enriched with review fields

Avoid making the template parse raw JSON strings.

- [ ] **Step 4: Keep the route backward-compatible**

Existing template fields for:

- `skill`
- `versions`
- `bindings`
- `apps`

must continue to work after the review view model is added.

---

## Task 2: Add the minimal review/governance panel to the skill detail template

**Files:**
- Modify: `ragenius_builder/flask_scaffold/templates/skill_detail.html`

- [ ] **Step 1: Add a contract review section near version/publish controls**

The panel should display, for each version or the selected version:

- risk badge / label
- policy class
- auto-finalize flag
- template family
- required tools
- required permissions
- input schema preview
- output schema preview
- workflow preview

- [ ] **Step 2: Add review guidance text by risk level**

Recommended behavior:

- `safe_read`
  - low-risk informational note
- `review_required`
  - warning note explaining publish creates an executable contract and runtime confirmation may still be required for write-capable flows
- `unsupported`
  - explicit unsupported/descriptive-only note

- [ ] **Step 3: Add empty-state handling**

If a version has no normalized executable contract metadata:

- show `No normalized executable contract available`

If the version is unsupported:

- render a clear unsupported block instead of empty JSON previews

- [ ] **Step 4: Keep styling minimal**

Use simple HTML structure:

- summary rows
- flat lists
- `<pre>` blocks for pretty JSON

Do not add a complex new CSS system for this slice.

---

## Task 3: Add Builder route/template tests for review/governance UX

**Files:**
- Modify: `ragenius_builder/flask_scaffold/tests/test_skill_management.py`

- [ ] **Step 1: Add a safe-read review panel test**

Cover:

- import a safe-read normalized skill
- load the skill detail page
- assert the response contains:
  - `Safe Read`
  - expected required tool
  - expected required permission

- [ ] **Step 2: Add a review-required panel test**

Cover:

- import a review-required skill such as:
  - mutation skill, or
  - Gmail direct-send skill
- load the skill detail page
- assert the response contains:
  - `Review Required`
  - expected tool id
  - expected permission
  - workflow preview marker such as the MCP service/tool id

- [ ] **Step 3: Add an unsupported panel test**

Cover:

- import an unsupported descriptive skill
- load the skill detail page
- assert the response contains:
  - `Unsupported`
  - `No normalized executable contract available` or equivalent unsupported message

- [ ] **Step 4: Verify publish/bind/test pages are unaffected**

Keep existing tests passing for:

- publish
- bind
- skill test page

No regression should be introduced by the route/template shaping changes.

---

## Task 4: Final verification

- [ ] **Step 1: Run Builder skill management tests**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System
python -m unittest ragenius_builder.flask_scaffold.tests.test_skill_management
```

Expected:

```text
OK
```

- [ ] **Step 2: Manually sanity-check the rendered detail page**

Open or inspect one safe skill and one risky skill detail page and confirm:

- safe skill shows `Safe Read`
- Gmail or mutation skill shows `Review Required`
- tools, permissions, schemas, and workflow are visible

- [ ] **Step 3: Sanity-check residual scope**

Verify:

- no new approval workflow states were added
- no edit-in-place contract UI was added
- no execution-subsystem changes were required

---

## Completion Criteria

The implementation is complete when:

- the skill detail page displays the normalized contract review panel
- `safe_read`, `review_required`, and `unsupported` are visually distinguishable
- operators can inspect tools, permissions, schemas, and workflow before publish
- existing publish/bind/test flows still work
- Builder test suite passes
