# Bible Tutor Module Ownership And Support Binding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve module ownership for stepwise procedures in Bible Tutor so `查經互動模組` remains the executable service block, `歸納釋經法` remains its internal procedure, and support modules never become accidental default entry targets.

**Architecture:** Fix the compiled-understanding boundary before touching planner fallback behavior. The compiler must preserve authored parent ownership (`模組` owns steps) and project one canonical executable identity through routing, service blocks, procedures, and steps. Planner/runtime then bind only to those canonical primary targets and treat support modules as on-demand only.

**Tech Stack:** Python, `unittest`, FastAPI backend runtime model, planner node

---

### Task 1: Lock ownership and support-binding failures in tests

**Files:**
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_instruction_understanding_service.py`
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_planner_node.py`

- [ ] **Step 1: Add a failing compile regression for module-owned stepwise procedures**
  - Assert Bible Tutor-shaped input produces:
    - `support_module:查經互動模組`
    - `procedure:support_module_查經互動模組`
    - no separate `workflow:歸納釋經法`

- [ ] **Step 2: Add a failing compile regression for Bible Study route binding**
  - Assert `route:bible_study` and `logic:bible_study_mode` bind to the executable module id for `查經互動模組`, not a synthetic workflow id and not a missing route-only id.

- [ ] **Step 3: Add a failing compile regression for Life Application support behavior**
  - Assert `logic:life_application_mode` keeps exegesis support in on-demand metadata only and does not get a primary executable target of `釋經支援模組`.

- [ ] **Step 4: Add a failing planner regression for starter-turn activation**
  - Assert the Bible Study starter turn activates:
    - primary service block `查經互動模組`
    - first step `細察事實`
  - Assert the Life Application starter turn does not auto-activate exegesis support as primary service block.

- [ ] **Step 5: Run targeted tests and confirm RED**
  - Run:
    - `python -m unittest ragenius_app_skeleton.tests.test_instruction_understanding_service`
    - `python -m unittest ragenius_app_skeleton.tests.test_planner_node`
  - Expected: new tests fail for ownership/binding reasons

### Task 2: Preserve parent ownership in compiled-understanding normalization

**Files:**
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\instruction_understanding_service.py`

- [ ] **Step 1: Add ownership-preserving normalization for stepwise `模組` sections**
  - If deterministic/semantic content shows ordered steps under a module section, project:
    - executable module service block
    - module-owned procedure
    - module-owned steps
  - Do not synthesize a sibling workflow from the same step sequence.

- [ ] **Step 2: Unify executable identity through one canonical block id**
  - Ensure route targets, logic targets, procedure owners, and steps all reuse the module block id when the authored parent is a module.

- [ ] **Step 3: Keep support modules separate from primary module ownership**
  - Exegesis and lexical modules remain support modules.
  - They must not replace the primary Bible Study module during compile projection.

- [ ] **Step 4: Run targeted compile tests and confirm GREEN**
  - Run:
    - `python -m unittest ragenius_app_skeleton.tests.test_instruction_understanding_service`

### Task 3: Tighten planner binding to primary vs support executable targets

**Files:**
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\planner.py`

- [ ] **Step 1: Prefer explicit primary executable target over support modules**
  - When a logic block names a primary subordinate target, planner must bind to it before any on-demand support module.

- [ ] **Step 2: Treat support modules as additive only**
  - `support_modules_on_demand`, `optional_support_modules`, and similar fields may enrich resource loading or later activation, but must not become primary active module on starter entry.

- [ ] **Step 3: Keep Bible Study starter on first procedure step**
  - If primary target owns a procedure with ordered steps, starter activation should land on step 1.

- [ ] **Step 4: Run targeted planner tests and confirm GREEN**
  - Run:
    - `python -m unittest ragenius_app_skeleton.tests.test_planner_node`

### Task 4: Protect unaffected applications

**Files:**
- Modify as needed: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_instruction_understanding_service.py`
- Modify as needed: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_planner_node.py`

- [ ] **Step 1: Add or preserve non-regression assertions for Church Ministry and GPT Application Design Assistant**
  - Existing support-module ids remain valid.
  - No blanket rewrite from support modules to workflows.

- [ ] **Step 2: Run non-regression slices**
  - Run:
    - targeted `unittest` cases covering support-module behavior in unaffected apps

### Task 5: Full verification and live-shape confirmation

**Files:**
- Verify only:
  - `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\.state\instruction_understanding_snapshots\2302c77b-3d82-4650-bd15-e0ff9c0faab7\understanding.json`
  - `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\.state\instruction_understanding_snapshots\0ea6ac80-c96d-4a65-b7e7-645f3ee848e9\understanding.json`

- [ ] **Step 1: Run full backend verification**
  - Run:
    - `python -m unittest ragenius_app_skeleton.tests.test_instruction_understanding_service`
    - `python -m unittest ragenius_app_skeleton.tests.test_planner_node`
    - `python -m unittest ragenius_app_skeleton.tests.test_builder_chat_integration`
    - `python -m unittest ragenius_app_skeleton.tests.test_llm_runtime_compat`

- [ ] **Step 2: Re-inspect persisted active snapshots after user recompiles**
  - Bible Tutor must show:
    - `module:查經互動模組` or `support_module:查經互動模組` as the executable primary block
    - no sibling `workflow:歸納釋經法` service block if the flow is module-owned
    - exegesis support still present as separate support module
  - `與孩子一起成長` must not regress.

- [ ] **Step 3: Confirm runtime expectations**
  - Bible Study starter binds to `查經互動模組` then `細察事實`
  - Life Application starter remains in life-application mode without auto-binding exegesis support
