# Bible Tutor Runtime Projection and Module Step Activation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make active snapshots use `instruction_runtime_model` only as a compatibility projection of the canonical hybrid runtime model, and ensure module-owned procedures activate step 1 and step-scoped resources correctly.

**Architecture:** Keep `hybrid_instruction_runtime_model` as the canonical runtime truth. Rebuild the nested `instruction_runtime_model` from that canonical model so module blocks, procedures, steps, and support resources cannot drift. Update planner step activation so routes into executable modules enter the module-owned procedure and first step instead of falling back to module-level blobs.

**Tech Stack:** Python, `unittest`, existing compile pipeline in `instruction_understanding_service.py`, runtime/planner logic in `planner.py`, builder chat integration tests.

---

### File Map

**Modify:**
- `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/app/instruction_understanding_service.py`
  - Own the compatibility projection from canonical hybrid runtime to nested `instruction_runtime_model`.
  - Ensure support module metadata does not keep whole-module guide bundles when step-scoped procedures exist.
- `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/workflows/nodes/planner.py`
  - Activate step scope for module-owned procedures.
  - Prefer canonical procedure step bindings over legacy module blobs.
- `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_instruction_understanding_service.py`
  - Add compile-level regressions for nested runtime projection consistency.
- `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_planner_node.py`
  - Add planner-level regressions for module-first-step activation and step-scoped resource loading.
- `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_builder_chat_integration.py`
  - Add end-to-end regression for Bible Tutor-style starter flow surfacing `????` and narrowed resource requests.

### Task 1: Lock nested runtime projection with failing compile tests

**Files:**
- Modify: `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_instruction_understanding_service.py`

- [ ] **Step 1: Write failing test for nested `instruction_runtime_model` projecting module-owned steps instead of whole-module blobs**

```python
    def test_compile_instruction_understanding_bible_tutor_nested_runtime_projects_module_step_resources(self):
        root = self._tmp_root("instruction_understanding_bible_tutor_nested_projection")
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")

            def semantic_compiler(_context):
                return {
                    "app_semantic_model": {
                        "primary_service_mode": "intent_routed_interaction_logic",
                        "default_workflow_id": None,
                        "global_app_contract": {"mission": "Teach scripture step by step"},
                        "interaction_logic_blocks": [
                            {
                                "block_id": "logic:bible_study_mode",
                                "title": "??????",
                                "subordinate_target": {
                                    "target_type": "support_module",
                                    "target_id": "support_module:??????",
                                },
                            }
                        ],
                        "routing_rules": [
                            {
                                "rule_id": "route:bible_study",
                                "trigger_keywords": ["??", "??"],
                                "target_logic_block_id": "logic:bible_study_mode",
                                "target_module_id": "support_module:??????",
                            }
                        ],
                        "service_blocks": [
                            {
                                "block_id": "support_module:??????",
                                "block_type": "support_module",
                                "title": "??????",
                            }
                        ],
                        "procedures": [
                            {
                                "procedure_id": "procedure:support_module_??????",
                                "service_block_id": "support_module:??????",
                                "title": "??????",
                            }
                        ],
                        "procedure_steps": [
                            {
                                "procedure_id": "procedure:support_module_??????",
                                "step_id": "step:support_module_??????:1",
                                "title": "????",
                                "order": 1,
                                "execution_mode": "interactive",
                                "resource_refs": ["observation_guide.md"],
                            },
                            {
                                "procedure_id": "procedure:support_module_??????",
                                "step_id": "step:support_module_??????:2",
                                "title": "????",
                                "order": 2,
                                "execution_mode": "interactive",
                                "resource_refs": ["identify_relationships_guide.md"],
                            },
                        ],
                        "role_profiles": [],
                        "clarification_gate_rules": [],
                    }
                }

            record = compile_instruction_understanding(
                app_id="app-1",
                instruction_text=self._bible_tutor_markdown(),
                instruction_uri="instructions/app-1/instructions.md",
                instruction_source_version=3,
                documents=self._bible_tutor_documents(),
                repo=repo,
                snapshot_root=root / "snapshots",
                semantic_compiler=semantic_compiler,
            )

            nested = record["compiled_contract"]["instruction_runtime_model"]
            support_module = next(
                item for item in nested["support_modules"]
                if str(item.get("module_id") or "").strip() == "??????"
            )
            self.assertEqual(support_module.get("resource_ids"), [])
            self.assertNotIn("formulate_questions_guide.md", str(support_module.get("notes") or ""))

            step_blocks = [
                item for item in nested["instruction_blocks"]
                if isinstance(item, dict) and str(item.get("block_type") or "").strip() == "step"
            ]
            observation = next(item for item in step_blocks if str(item.get("linked_step_order") or "") == "1")
            self.assertEqual(observation.get("referenced_resources"), ["observation_guide.md"])
        finally:
            self._cleanup_root(root)
```

- [ ] **Step 2: Run the new compile test and verify RED**

Run:
```powershell
python -m unittest ragenius_app_skeleton.tests.test_instruction_understanding_service.InstructionUnderstandingServiceTests.test_compile_instruction_understanding_bible_tutor_nested_runtime_projects_module_step_resources
```

Expected: FAIL because nested runtime still contains whole-module guide content or broad resource projection.

### Task 2: Lock planner step activation with failing runtime tests

**Files:**
- Modify: `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_planner_node.py`

- [ ] **Step 1: Write failing planner test for follow-up turn entering module step 1**

```python
    def test_planner_hybrid_active_followup_turn_enters_first_module_step_for_bible_study(self):
        state = self.state.copy()
        state["planner_mode"] = "hybrid_active"
        state["user_query"] = "?????????"
        state["template_registry"] = {
            "compiled_instruction_understanding": {
                "hybrid_instruction_runtime_model": {
                    "primary_service_mode": "intent_routed_interaction_logic",
                    "instruction_service_blocks": [
                        {"block_id": "module:??????", "block_type": "support_module", "title": "??????"}
                    ],
                    "instruction_procedures": [
                        {
                            "procedure_id": "procedure:module_??????",
                            "service_block_id": "module:??????",
                            "title": "??????",
                        }
                    ],
                    "procedure_steps": [
                        {
                            "step_id": "step:support_module_??????:1",
                            "procedure_id": "procedure:module_??????",
                            "order": 1,
                            "title": "????",
                            "execution_mode": "interactive",
                            "resource_refs": ["observation_guide.md"],
                        }
                    ],
                    "routing_rules": [
                        {
                            "rule_id": "route:bible_study",
                            "trigger_keywords": ["??", "??"],
                            "target_logic_block_id": "logic:bible_study_mode",
                            "target_module_id": "module:??????",
                        }
                    ],
                    "interaction_logic_blocks": [
                        {
                            "block_id": "logic:bible_study_mode",
                            "logic_id": "logic:bible_study_mode",
                            "title": "??????",
                            "subordinate_target": {"target_type": "support_module", "target_id": "module:??????"},
                        }
                    ],
                }
            },
            "instruction_workflows": [],
        }
        state["instruction_runtime_model"] = {
            "instruction_service_blocks": list(state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_service_blocks"]),
            "instruction_procedures": list(state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_procedures"]),
            "procedure_steps": list(state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["procedure_steps"]),
            "support_modules": [
                {"module_id": "??????", "title": "??????", "block_type": "support_module", "resource_ids": [], "notes": ""}
            ],
        }
        state["session_execution_state"] = {
            "selected_routing_rule_id": "route:bible_study",
            "active_service_block_id": "module:??????",
            "active_service_block_type": "support_module",
            "active_service_block_title": "??????",
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        def hybrid_llm(_prompt, _tools, _context):
            return {
                "intent_label": "bible_study",
                "confidence": 0.97,
                "continue_current_scope": True,
                "selected_support_module_ids": [],
                "selected_followup_module_ids": [],
                "module_sequence": [],
                "next_action": {
                    "action_type": "respond",
                    "target_service_block_id": "logic:bible_study_mode",
                    "target_workflow_id": None,
                    "target_step_id": None,
                    "bundled_step_ids": [],
                    "module_queue": [],
                },
            }

        state["_llm_planner_hybrid"] = hybrid_llm
        out = planner.run(state, llm_planner=llm)
        self.assertEqual(out["session_execution_state"]["active_step_scope_id"], "step:support_module_??????:1")
        self.assertEqual(out["turn_execution_plan"]["active_step_scope"]["title"], "????")
```

- [ ] **Step 2: Write failing planner test for step-scoped resource narrowing**

```python
    def test_planner_hybrid_active_step_one_only_loads_observation_guide_for_bible_study(self):
        # Reuse the state shape from the previous test and assert resource requests.
        out = planner.run(state, llm_planner=llm)
        instruction_filenames = [
            str(item.get("filename") or "").strip()
            for item in out["turn_execution_plan"].get("resource_requests", [])
            if str(item.get("purpose") or "").strip() == "instruction_support"
        ]
        self.assertIn("observation_guide.md", instruction_filenames)
        self.assertNotIn("identify_relationships_guide.md", instruction_filenames)
        self.assertNotIn("formulate_questions_guide.md", instruction_filenames)
    ```

- [ ] **Step 3: Run the new planner tests and verify RED**

Run:
```powershell
python -m unittest \
  ragenius_app_skeleton.tests.test_planner_node.PlannerNodeTests.test_planner_hybrid_active_followup_turn_enters_first_module_step_for_bible_study \
  ragenius_app_skeleton.tests.test_planner_node.PlannerNodeTests.test_planner_hybrid_active_step_one_only_loads_observation_guide_for_bible_study
```

Expected: FAIL because step activation still stays at module scope and resource requests still include broad module resources.

### Task 3: Rebuild nested compatibility projection from hybrid runtime

**Files:**
- Modify: `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/app/instruction_understanding_service.py`

- [ ] **Step 1: Add helper that projects nested support modules from canonical hybrid runtime blocks/procedures/steps**
- [ ] **Step 2: For module-owned procedures, strip whole-module guide bundles from projected support-module notes/resources**
- [ ] **Step 3: Project step blocks in nested `instruction_blocks` directly from canonical `procedure_steps` and step resource refs**
- [ ] **Step 4: Keep support modules like exegesis as support modules, but do not merge their metadata into the primary module block**
- [ ] **Step 5: Run the compile projection test and verify GREEN**

### Task 4: Activate module-owned first step in planner

**Files:**
- Modify: `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/workflows/nodes/planner.py`

- [ ] **Step 1: When continuing within a selected executable module that owns a procedure, derive first/current step scope from runtime `procedure_steps` even without an `instruction_workflow`**
- [ ] **Step 2: Ensure `selected_module` carries `step_scope_id`, `order`, `title`, and `primary_resource` from canonical procedure step definitions**
- [ ] **Step 3: Ensure `_layered_scope_context()` uses that module-derived step scope to set `active_step_scope_id` and direct resource files**
- [ ] **Step 4: Verify step-scoped resource requests only include the active step guide**
- [ ] **Step 5: Run the planner tests and verify GREEN**

### Task 5: End-to-end regression

**Files:**
- Modify: `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_builder_chat_integration.py`

- [ ] **Step 1: Add regression that a Bible Tutor-style second turn surfaces `????` as current step and only requests `observation_guide.md` from instruction support**
- [ ] **Step 2: Run that integration slice and verify GREEN**

### Task 6: Non-regression verification

**Files:**
- Test only:
  - `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_instruction_understanding_service.py`
  - `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_planner_node.py`
  - `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_builder_chat_integration.py`
  - `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_llm_runtime_compat.py`

- [ ] **Step 1: Run compiler suite**
```powershell
python -m unittest ragenius_app_skeleton.tests.test_instruction_understanding_service
```
- [ ] **Step 2: Run planner suite**
```powershell
python -m unittest ragenius_app_skeleton.tests.test_planner_node
```
- [ ] **Step 3: Run targeted builder integration slice**
```powershell
python -m unittest ragenius_app_skeleton.tests.test_builder_chat_integration.BuilderChatIntegrationTests
```
- [ ] **Step 4: Run runtime compatibility suite**
```powershell
python -m unittest ragenius_app_skeleton.tests.test_llm_runtime_compat
```
- [ ] **Step 5: Re-run explicit cross-app support-module regression**
```powershell
python -m unittest ragenius_app_skeleton.tests.test_instruction_understanding_service.InstructionUnderstandingServiceTests.test_validate_semantic_compile_candidate_preserves_existing_support_module_ids_for_cross_app_routes
```

