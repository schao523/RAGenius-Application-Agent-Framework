# App-Local Canonical Route Target Normalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stabilize `intent_routed_multi_workflow` compilation by normalizing unresolved semantic route workflow ids into app-local canonical executable targets derived from the deterministic contract.

**Architecture:** Add a narrow fallback normalization layer inside semantic grounding in `ragenius_app_skeleton/backend/app/instruction_understanding_service.py`. The normalizer builds an app-local canonical route target registry from deterministic instruction artifacts, rewrites only unresolved child workflow route ids, and preserves orchestration policy as interaction logic rather than executable workflow blocks.

**Tech Stack:** Python, `unittest`, existing instruction-understanding compiler/validator in `ragenius_app_skeleton`

---

### Task 1: Add failing tests for app-local canonical target normalization

**Files:**
- Modify: `ragenius_app_skeleton/tests/test_instruction_understanding_service.py`

- [ ] **Step 1: Write a failing test for unresolved aliases mapping into app-local canonical route ids**
- [ ] **Step 2: Write a failing test for partner-specific subtype mapping**
- [ ] **Step 3: Write a failing test for orchestration-policy preservation**
- [ ] **Step 4: Run targeted tests to verify failure or drift against current behavior**
- [ ] **Step 5: Commit**

### Task 2: Build the app-local canonical route target registry

**Files:**
- Modify: `ragenius_app_skeleton/backend/app/instruction_understanding_service.py`
- Test: `ragenius_app_skeleton/tests/test_instruction_understanding_service.py`

- [ ] **Step 1: Add a helper to collect canonical route target candidates from deterministic artifacts**
- [ ] **Step 2: Add a narrow canonical id helper**
- [ ] **Step 3: Run the targeted tests**
- [ ] **Step 4: Commit**

### Task 3: Wire fallback normalization into semantic grounding

**Files:**
- Modify: `ragenius_app_skeleton/backend/app/instruction_understanding_service.py`
- Test: `ragenius_app_skeleton/tests/test_instruction_understanding_service.py`

- [ ] **Step 1: Add a helper that resolves unresolved route ids to canonical ids**
- [ ] **Step 2: Apply canonicalization only for unresolved routed child workflows**
- [ ] **Step 3: Synthesize executable records from canonical ids**
- [ ] **Step 4: Run the new targeted regressions**
- [ ] **Step 5: Commit**

### Task 4: Preserve orchestration policy as logic-only

**Files:**
- Modify: `ragenius_app_skeleton/backend/app/instruction_understanding_service.py`
- Test: `ragenius_app_skeleton/tests/test_instruction_understanding_service.py`

- [ ] **Step 1: Keep orchestration-policy routes out of executable block synthesis**
- [ ] **Step 2: If needed, add minimal `module_orchestration` synthesis**
- [ ] **Step 3: Run orchestration-specific regression**
- [ ] **Step 4: Commit**

### Task 5: Tighten validator expectations around canonicalized targets

**Files:**
- Modify: `ragenius_app_skeleton/backend/app/instruction_understanding_service.py`
- Test: `ragenius_app_skeleton/tests/test_instruction_understanding_service.py`

- [ ] **Step 1: Keep validator strict, but only against canonicalized outputs**
- [ ] **Step 2: Confirm ambiguous routes still fail clearly**
- [ ] **Step 3: Run targeted validator ambiguity test**
- [ ] **Step 4: Commit**

### Task 6: Full backend verification and live acceptance

**Files:**
- Test: `ragenius_app_skeleton/tests/test_instruction_understanding_service.py`
- Optional verify: `ragenius_app_skeleton/tests/test_builder_chat_integration.py`

- [ ] **Step 1: Run full instruction-understanding suite**
- [ ] **Step 2: Run integration slice if touched**
- [ ] **Step 3: Manual live verification**
- [ ] **Step 4: Commit**
