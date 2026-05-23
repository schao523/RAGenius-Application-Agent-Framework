# Church Ministry and Bible Tutor Runtime Contract Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix recurring workflow-state and resource-scoping defects in Church Ministry Prompt Designer and Bible Tutor without regressing `???????`.

**Architecture:** Strengthen the compile contract first so active snapshots project executable steps, follow-up modules, and step-owned resource refs consistently. Then tighten planner precedence so persisted runtime state and GUI payload follow the canonical step/module path instead of broad phase bindings.

**Tech Stack:** Python, FastAPI, planner/runtime state model, hybrid instruction-understanding compiler, unittest/pytest integration suites.

---

### Task 1: Lock Bible Tutor and Church Ministry compile-contract regressions

**Files:**
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_instruction_understanding_service.py`
- Reference: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\instruction_understanding_service.py`

- [ ] **Step 1: Add failing Bible Tutor step-resource projection test**

```python
def test_compile_instruction_understanding_bible_tutor_projects_step_resource_refs(self):
    record = compile_instruction_understanding(
        app_id="app-1",
        instruction_text=self._bible_tutor_markdown(),
        instruction_uri="instructions/app-1/instructions.md",
    )

    contract = record.compiled_contract["hybrid_instruction_runtime_model"]
    step_rows = {
        item["step_id"]: item
        for item in contract["procedure_steps"]
        if isinstance(item, dict)
    }

    self.assertEqual(step_rows["step:observation"]["resource_refs"], ["observation_guide.md"])
    self.assertEqual(
        step_rows["step:identify_relationships"]["resource_refs"],
        ["identify_relationships_guide.md"],
    )
```

- [ ] **Step 2: Add failing Church Ministry follow-up executable projection test**

```python
def test_compile_instruction_understanding_church_ministry_projects_optimization_followup_as_runtime_block(self):
    record = compile_instruction_understanding(
        app_id="app-1",
        instruction_text=self._church_ministry_markdown(),
        instruction_uri="instructions/app-1/instructions.md",
    )

    contract = record.compiled_contract["hybrid_instruction_runtime_model"]
    block_ids = {
        item["block_id"]
        for item in contract["instruction_service_blocks"]
        if isinstance(item, dict)
    }

    self.assertIn("followup_module:optimization_module", block_ids)
```

- [ ] **Step 3: Add failing compatibility-projection non-regression test for `???????`**

```python
def test_compile_instruction_understanding_parenting_app_preserves_existing_runtime_bindings(self):
    record = compile_instruction_understanding(
        app_id="app-1",
        instruction_text=self._parenting_markdown(),
        instruction_uri="instructions/app-1/instructions.md",
    )

    contract = record.compiled_contract["hybrid_instruction_runtime_model"]
    block_ids = {
        item["block_id"]
        for item in contract["instruction_service_blocks"]
        if isinstance(item, dict)
    }

    self.assertIn("support_module:??????", block_ids)
    self.assertIn("workflow:3x1?????", block_ids)
```

- [ ] **Step 4: Run compile-contract tests to verify failure**

Run:
```powershell
python -m pytest ragenius_app_skeleton/tests/test_instruction_understanding_service.py -k "bible_tutor_projects_step_resource_refs or church_ministry_projects_optimization_followup_as_runtime_block or parenting_app_preserves_existing_runtime_bindings" -q
```

Expected: FAIL on missing step `resource_refs` and missing follow-up runtime block.

### Task 2: Lock planner/runtime persistence regressions

**Files:**
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_planner_node.py`
- Reference: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\planner.py`

- [ ] **Step 1: Add failing Bible Tutor narrow-resource persistence test**

```python
def test_bible_tutor_active_step_scope_suppresses_module_phase_resource_expansion(self):
    state = self.state.copy()
    state["planner_mode"] = "hybrid_active"
    state["user_query"] = "Move to next step"
    state["template_registry"] = {
        "compiled_instruction_understanding": {
            "hybrid_instruction_runtime_model": {
                "primary_service_mode": "intent_routed_interaction_logic",
                "instruction_service_blocks": [
                    {"block_id": "support_module:bible_study", "block_type": "support_module", "title": "??????"}
                ],
                "instruction_procedures": [
                    {"procedure_id": "procedure:support_module_bible_study", "service_block_id": "support_module:bible_study", "title": "??????"}
                ],
                "procedure_steps": [
                    {"step_id": "step:observation", "procedure_id": "procedure:support_module_bible_study", "order": 1, "title": "????", "execution_mode": "interactive", "resource_refs": ["observation_guide.md"]},
                    {"step_id": "step:identify_relationships", "procedure_id": "procedure:support_module_bible_study", "order": 2, "title": "????", "execution_mode": "interactive", "resource_refs": ["identify_relationships_guide.md"]},
                ],
            }
        }
    }
    state["session_execution_state"] = {
        "active_service_block_id": "support_module:bible_study",
        "active_step_scope_id": "step:identify_relationships",
        "active_binding_ids": ["phase:??????"],
    }

    out = planner.run(state, llm_planner=self.llm)
    self.assertEqual(
        out["turn_execution_plan"]["selected_resource_filenames"],
        ["identify_relationships_guide.md"],
    )
```

- [ ] **Step 2: Add failing Church Ministry progression persistence test**

```python
def test_church_ministry_core_and_optimization_turns_persist_runtime_state(self):
    state = self.state.copy()
    state["planner_mode"] = "hybrid_active"
    state["user_query"] = "???? Prompt"
    state["session_execution_state"] = {
        "active_workflow": "Interaction Logic & Execution Flow",
        "active_step_scope_id": "step:core_workflow_execution",
        "active_module_queue": ["followup_module:optimization_module"],
        "bundled_execution_completed": True,
    }
    state["template_registry"] = {
        "compiled_instruction_understanding": {
            "hybrid_instruction_runtime_model": {
                "primary_service_mode": "single_default_workflow",
                "instruction_service_blocks": [
                    {"block_id": "workflow:church-ministry", "block_type": "primary_workflow", "title": "Interaction Logic & Execution Flow", "is_default": True},
                    {"block_id": "followup_module:optimization_module", "block_type": "followup_module", "title": "Optimization Module"},
                ],
                "instruction_procedures": [],
                "procedure_steps": [],
            }
        }
    }

    out = planner.run(state, llm_planner=self.llm)
    self.assertEqual(out["session_execution_state"]["active_service_block_id"], "followup_module:optimization_module")
    self.assertEqual(out["session_execution_state"]["primary_support_module_title"], "Optimization Module")
```

- [ ] **Step 3: Add failing parenting non-regression test**

```python
def test_parenting_role_routing_keeps_existing_runtime_binding_after_resource_precedence_changes(self):
    state = self._parenting_role_bound_state()
    out = planner.run(state, llm_planner=self.llm)
    self.assertEqual(out["session_execution_state"]["active_workflow"], "3x1 ??????")
    self.assertEqual(out["session_execution_state"]["active_service_block_id"], "workflow:3x1?????")
```

- [ ] **Step 4: Run planner tests to verify failure**

Run:
```powershell
python -m pytest ragenius_app_skeleton/tests/test_planner_node.py -k "suppresses_module_phase_resource_expansion or core_and_optimization_turns_persist_runtime_state or parenting_role_routing_keeps_existing_runtime_binding" -q
```

Expected: FAIL on broad resource expansion and missing follow-up persistence.

### Task 3: Lock GUI payload regressions

**Files:**
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_builder_chat_integration.py`
- Reference: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\main.py`

- [ ] **Step 1: Add failing Church Ministry GUI workflow-status test**

```python
def test_session_messages_workflow_status_shows_core_workflow_then_optimization_module(self):
    db_path, _ = _create_builder_db(str(self.tmp_root))

    with mock.patch.dict(os.environ, {"RAGENIUS_BUILDER_DB": db_path}, clear=False):
        session_repo.get_or_create(
            "s-church-runtime",
            collection_id="app-1",
            user_id="u1",
            title="Church runtime session",
            config_version=1,
            adapter_version=1,
            template_version=1,
        )
        chat_repo.append(
            "s-church-runtime",
            "assistant",
            "Optimization turn",
            retrieval_summary={
                "session_execution_state": {
                    "active_workflow": "Interaction Logic & Execution Flow",
                    "active_service_block_type": "followup_module",
                    "active_service_block_id": "followup_module:optimization_module",
                    "active_service_block_title": "Optimization Module",
                    "active_step_title": "????(Workflow Execution)",
                    "active_step_scope_id": "step:core_workflow_execution",
                    "execution_status": "guiding",
                    "workflow_progress": {"workflow_id": "interaction_logic_execution_flow", "workflow_title": "Interaction Logic & Execution Flow", "step_order": 2, "step_title": "????(Workflow Execution)"},
                }
            },
        )

        response = self.client.get("/sessions/s-church-runtime/messages?app_id=app-1&user_id=u1")

    workflow_status = response.json()["workflow_status"]
    self.assertEqual(workflow_status["current_step"]["title"], "????(Workflow Execution)")
    self.assertEqual(workflow_status["active_service_block_title"], "Optimization Module")
```

- [ ] **Step 2: Add failing Bible Tutor narrow-resource GUI payload test**

```python
def test_session_messages_workflow_status_prefers_step_scoped_bible_tutor_resources(self):
    db_path, _ = _create_builder_db(str(self.tmp_root))

    with mock.patch.dict(os.environ, {"RAGENIUS_BUILDER_DB": db_path}, clear=False):
        session_repo.get_or_create(
            "s-bible-runtime",
            collection_id="app-1",
            user_id="u1",
            title="Bible runtime session",
            config_version=1,
            adapter_version=1,
            template_version=1,
        )
        chat_repo.append(
            "s-bible-runtime",
            "assistant",
            "Step 2",
            retrieval_summary={
                "selected_resource_filenames": ["identify_relationships_guide.md"],
                "session_execution_state": {
                    "active_step_title": "???? (Identify Relationships)",
                    "active_step_scope_id": "step:identify_relationships",
                    "active_service_block_id": "support_module:??????",
                },
            },
        )

        response = self.client.get("/sessions/s-bible-runtime/messages?app_id=app-1&user_id=u1")

    payload = response.json()
    self.assertEqual(payload["messages"][-1]["retrievalSummary"]["selected_resource_filenames"], ["identify_relationships_guide.md"])
```

- [ ] **Step 3: Run GUI payload tests to verify failure**

Run:
```powershell
python -m pytest ragenius_app_skeleton/tests/test_builder_chat_integration.py -k "core_workflow_then_optimization_module or prefers_step_scoped_bible_tutor_resources" -q
```

Expected: FAIL on stale clarification workflow status or widened resource payloads.

### Task 4: Fix compile contract in instruction_understanding_service.py

**Files:**
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\instruction_understanding_service.py`
- Test: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_instruction_understanding_service.py`

- [ ] **Step 1: Populate step resource refs from deterministic step metadata for interactive steps**

```python
for step in procedure_steps:
    refs = deterministic_step_resource_refs.get(step_id, [])
    if refs and not any(str(ref or "").strip() for ref in step.get("resource_refs", []) or []):
        step["resource_refs"] = list(refs)
```

- [ ] **Step 2: Project follow-up modules into runtime-facing service blocks when they are executable targets**

```python
for module in followup_modules:
    block_id = str(module.get("module_id") or module.get("block_id") or "").strip()
    if not block_id:
        continue
    if not any(str(item.get("block_id") or "").strip() == block_id for item in instruction_service_blocks):
        instruction_service_blocks.append(
            {
                "block_id": block_id,
                "block_type": "followup_module",
                "title": str(module.get("title") or module.get("module_title") or block_id).strip(),
                "is_default": False,
            }
        )
```

- [ ] **Step 3: Keep compatibility runtime projected from canonical hybrid runtime only**

```python
compiled_contract["instruction_runtime_model"] = _project_compatibility_instruction_runtime_model(
    dict(compiled_contract.get("instruction_runtime_model") or {}),
    hybrid_runtime_model,
)
```

- [ ] **Step 4: Run targeted compile tests to verify pass**

Run:
```powershell
python -m pytest ragenius_app_skeleton/tests/test_instruction_understanding_service.py -k "bible_tutor_projects_step_resource_refs or church_ministry_projects_optimization_followup_as_runtime_block or parenting_app_preserves_existing_runtime_bindings" -q
```

Expected: PASS.

### Task 5: Fix planner resource precedence and runtime persistence

**Files:**
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\planner.py`
- Test: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_planner_node.py`

- [ ] **Step 1: Prefer active-step resources over broad phase bindings**

```python
if active_step_scope_id and step_resource_files:
    suppress_phase_binding_expansion = True
```

```python
for binding_scope_id in active_binding_ids:
    if suppress_phase_binding_expansion and str(binding_scope_id).startswith("phase:"):
        continue
```

- [ ] **Step 2: Persist workflow progression when content path enters bundled workflow execution**

```python
if bundled_step is not None:
    session_state["active_step_scope_id"] = bundled_step.get("step_scope_id")
    session_state["active_step_title"] = bundled_step.get("title")
    session_state["active_step_order"] = bundled_step.get("order")
    workflow_progress = {
        "workflow_id": selected_workflow_id,
        "workflow_title": selected_workflow_title,
        "step_order": bundled_step.get("order"),
        "step_title": bundled_step.get("title"),
    }
```

- [ ] **Step 3: Promote queued follow-up module to active service block when refinement/optimization turn is selected**

```python
if queued_followup_ids:
    active_service_block_id = queued_followup_ids[0]
    active_service_block_type = "followup_module"
    active_service_block_title = _service_block_title_by_id(state, active_service_block_id)
```

- [ ] **Step 4: Keep protected parenting route binding unchanged**

```python
if active_service_block_id and active_service_block_id.startswith("workflow:3x1"):
    return existing_binding
```

- [ ] **Step 5: Run targeted planner tests to verify pass**

Run:
```powershell
python -m pytest ragenius_app_skeleton/tests/test_planner_node.py -k "suppresses_module_phase_resource_expansion or core_and_optimization_turns_persist_runtime_state or parenting_role_routing_keeps_existing_runtime_binding" -q
```

Expected: PASS.

### Task 6: Verify GUI payload and cross-app non-regression

**Files:**
- Test: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_builder_chat_integration.py`
- Test: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_instruction_understanding_service.py`
- Test: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_planner_node.py`
- Test: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_llm_runtime_compat.py`

- [ ] **Step 1: Run GUI payload regression slice**

Run:
```powershell
python -m pytest ragenius_app_skeleton/tests/test_builder_chat_integration.py -k "core_workflow_then_optimization_module or prefers_step_scoped_bible_tutor_resources or parenting_route_when_role_target_should_bind_workflow" -q
```

Expected: PASS.

- [ ] **Step 2: Run compile/planner non-regression slices**

Run:
```powershell
python -m pytest ragenius_app_skeleton/tests/test_instruction_understanding_service.py -k "preserves_existing_support_module_ids_for_cross_app_routes or parenting_app_preserves_existing_runtime_bindings" -q
python -m pytest ragenius_app_skeleton/tests/test_planner_node.py -k "life_guidance_query_prefers_life_application_over_shadow_bible_study or church_ministry_prompt_designer_starter_binds_clarification_workflow_from_default_workflow_alias or parenting_role_routing_keeps_existing_runtime_binding" -q
python -m pytest ragenius_app_skeleton/tests/test_llm_runtime_compat.py -q
```

Expected: PASS.

- [ ] **Step 3: Run the practical-standard verification bundle**

Run:
```powershell
python -m pytest ragenius_app_skeleton/tests/test_instruction_understanding_service.py -q
python -m pytest ragenius_app_skeleton/tests/test_planner_node.py -q
python -m pytest ragenius_app_skeleton/tests/test_builder_chat_integration.py -k "core_workflow_then_optimization_module or prefers_step_scoped_bible_tutor_resources or parenting_route_when_role_target_should_bind_workflow or shows_life_application_for_life_guidance_starter" -q
python -m pytest ragenius_app_skeleton/tests/test_llm_runtime_compat.py -q
```

Expected: all PASS.
