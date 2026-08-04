# Clarification-to-Core Slot-State Advancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make clarification-to-core transition advance from persisted slot state instead of fragile prompt-text heuristics, so Church Ministry enters `核心流程` as soon as required variables are present without regressing Bible Tutor or `與孩子一起成長`.

**Architecture:** Keep the active snapshot contract unchanged and harden the planner state machine. The planner will infer slot fills from conversation turns, persist them into `session_execution_state.clarification_gate_status.filled_slots_map`, and use that slot state as the primary transition signal for interactive clarification steps and control gates. Prompt-text heuristics remain a secondary fallback only when slot state is unavailable.

**Tech Stack:** Python 3.14, FastAPI backend, LangGraph-style workflow nodes, pytest/unittest hybrid test suite, JSON-schema validated planner outputs.

---

## File Structure

**Modify:** `ragenius_app_skeleton/workflows/nodes/planner.py`
- Responsibility: slot extraction, clarification gate persistence, gate-step collapse, clarification-to-core advancement ordering, and active-path consistency.

**Modify:** `ragenius_app_skeleton/tests/test_planner_node.py`
- Responsibility: planner-level failing regressions for Church Ministry slot-state advancement and non-regression coverage for Bible Tutor and `與孩子一起成長`.

**Modify:** `ragenius_app_skeleton/tests/test_builder_chat_integration.py`
- Responsibility: builder/API-facing regression that the third Church Ministry turn surfaces `核心流程` and loads only `template_library.md` + `dynamic_prompt_optimizer.md`.

**Read-only reference:** `ragenius_app_skeleton/backend/app/main.py`
- Responsibility: GUI workflow payload projection from persisted session state. No planned code changes unless planner-state fixes prove insufficient.

**Read-only reference:** `ragenius_app_skeleton/backend/app/chat_service.py`
- Responsibility: graph wiring and response assembly. No planned code changes unless planner-state fixes prove insufficient.

---

### Task 1: Lock Church Ministry Slot-State Regressions

**Files:**
- Modify: `ragenius_app_skeleton/tests/test_planner_node.py`
- Test: `ragenius_app_skeleton/tests/test_planner_node.py`

- [ ] **Step 1: Write failing planner regression for clarification-to-core advancement from persisted slot state**

```python
def test_planner_hybrid_active_church_ministry_advances_from_clarification_when_goal_slot_arrives(self):
    state = self.state.copy()
    state["planner_mode"] = "hybrid_active"
    state["instruction_understanding_mode"] = "hybrid_active"
    state["user_query"] = "核心目標（goal）是幫助青年認識在基督裡的屬靈福氣"
    state["chat_history"] = [
        {"role": "assistant", "content": "請問這次查經分享的對象主要是誰？"},
        {"role": "user", "content": "準備以弗所書第一章的查經分享材料"},
        {"role": "assistant", "content": "請提供主要對象（audience）。"},
        {"role": "user", "content": "對象主要是小組長訓練"},
    ]
    state["workflow_progress"] = {
        "workflow_id": "primary_workflow:interaction_logic_execution_flow",
        "workflow_title": "Interaction Logic & Execution Flow",
        "step_order": 1,
        "step_title": "Clarification",
    }
    state["session_execution_state"] = {
        "primary_scope_id": "workflow:interaction_logic_execution_flow",
        "primary_scope_type": "workflow",
        "primary_scope_title": "Interaction Logic & Execution Flow",
        "active_mode": "interaction_logic_execution_flow",
        "active_workflow": "Interaction Logic & Execution Flow",
        "active_step_order": 1,
        "active_step_title": "Clarification",
        "active_step_scope_id": "step:interaction_logic_execution_flow:1",
        "clarification_gate_status": {
            "filled_slots_map": {
                "passage": True,
                "audience": True,
            }
        },
    }
    state["template_registry"] = _church_ministry_slot_state_registry()
    state["instruction_runtime_model"] = _church_ministry_slot_state_runtime_model()

    def llm(_prompt, _tools, _context):
        output = json.loads(json.dumps(self.valid))
        output["normalizedQuery"] = state["user_query"]
        output["contextualQuery"] = state["user_query"]
        output["retrievalPlan"]["query_text"] = state["user_query"]
        return output

    out = planner.run(state, llm_planner=llm)
    self.assertEqual(out["instruction_step"]["order"], 2)
    self.assertEqual(out["session_execution_state"]["active_step_scope_id"], "step:interaction_logic_execution_flow:2")
    self.assertEqual(out["session_execution_state"]["active_service_block_type"], "primary_workflow")
```

- [ ] **Step 2: Write failing planner regression that filled slot state is persisted generically**

```python
def test_planner_hybrid_active_updates_clarification_gate_status_from_current_turn_slot_signals(self):
    state = self.state.copy()
    state["planner_mode"] = "hybrid_active"
    state["instruction_understanding_mode"] = "hybrid_active"
    state["user_query"] = "核心目標（goal）是幫助青年認識在基督裡的屬靈福氣"
    state["workflow_progress"] = {
        "workflow_id": "primary_workflow:interaction_logic_execution_flow",
        "workflow_title": "Interaction Logic & Execution Flow",
        "step_order": 1,
        "step_title": "Clarification",
    }
    state["session_execution_state"] = {
        "active_step_scope_id": "step:interaction_logic_execution_flow:1",
        "clarification_gate_status": {"filled_slots_map": {"passage": True, "audience": True}},
    }
    state["template_registry"] = _church_ministry_slot_state_registry()
    state["instruction_runtime_model"] = _church_ministry_slot_state_runtime_model()

    out = planner.run(state, llm_planner=lambda _p, _t, _c: json.loads(json.dumps(self.valid)))
    filled = out["session_execution_state"]["clarification_gate_status"]["filled_slots_map"]
    assert filled["passage"] is True
    assert filled["audience"] is True
    assert filled["goal"] is True
```

- [ ] **Step 3: Run targeted planner tests to verify they fail first**

Run: `python -m pytest ragenius_app_skeleton/tests/test_planner_node.py -k "advances_from_clarification_when_goal_slot_arrives or updates_clarification_gate_status_from_current_turn_slot_signals" -v`

Expected: FAIL because the planner remains on `step:interaction_logic_execution_flow:1` and does not persist `goal` into `filled_slots_map`.

- [ ] **Step 4: Commit the failing tests checkpoint**

```bash
git add ragenius_app_skeleton/tests/test_planner_node.py
git commit -m "test: lock clarification slot-state advancement regressions"
```

### Task 2: Implement Generic Slot-State Extraction and Persistence

**Files:**
- Modify: `ragenius_app_skeleton/workflows/nodes/planner.py`
- Test: `ragenius_app_skeleton/tests/test_planner_node.py`

- [ ] **Step 1: Add generic slot detector helpers near the existing signal helpers**

```python
SLOT_SIGNAL_DETECTORS: dict[str, Callable[[str], bool]] = {
    "theme": _has_topic_signal,
    "passage": _query_specifies_passage,
    "audience": _has_audience_signal,
    "goal": _has_goal_signal,
}


def _merge_filled_slot_state(
    existing: Dict[str, Any] | None,
    current_query: str,
    conversation_user_messages: list[str],
) -> dict[str, bool]:
    merged: dict[str, bool] = {}
    if isinstance(existing, dict):
        for name, value in existing.items():
            key = str(name).strip()
            if key:
                merged[key] = bool(value)
    for message in conversation_user_messages + [str(current_query or "").strip()]:
        for slot_name, detector in SLOT_SIGNAL_DETECTORS.items():
            if detector(message):
                merged[slot_name] = True
    return merged
```

- [ ] **Step 2: Add a helper that updates clarification gate status only for active clarification/gate paths**

```python
def _updated_clarification_gate_status(state: GraphState, current_query: str) -> dict[str, Any]:
    session_state = state.get("session_execution_state", {}) or {}
    prior_status = session_state.get("clarification_gate_status", {}) if isinstance(session_state, dict) else {}
    prior_map = prior_status.get("filled_slots_map", {}) if isinstance(prior_status, dict) else {}
    filled_map = _merge_filled_slot_state(
        prior_map if isinstance(prior_map, dict) else {},
        current_query,
        _conversation_user_messages(state, current_query),
    )
    return {
        "filled_slots_map": filled_map,
        "filled_slot_names": sorted(name for name, value in filled_map.items() if value),
    }
```

- [ ] **Step 3: Persist the updated slot state into `session_execution_state` before step selection logic is finalized**

```python
current_query = _combined_query_text(state, planner_output)
if isinstance(state.get("session_execution_state"), dict):
    state["session_execution_state"]["clarification_gate_status"] = _updated_clarification_gate_status(state, current_query)
```

- [ ] **Step 4: Run the two targeted tests to verify they now pass**

Run: `python -m pytest ragenius_app_skeleton/tests/test_planner_node.py -k "advances_from_clarification_when_goal_slot_arrives or updates_clarification_gate_status_from_current_turn_slot_signals" -v`

Expected: PASS

- [ ] **Step 5: Commit the slot-state persistence checkpoint**

```bash
git add ragenius_app_skeleton/workflows/nodes/planner.py ragenius_app_skeleton/tests/test_planner_node.py
git commit -m "feat: persist clarification slot state from conversation"
```

### Task 3: Make Clarification Advancement Depend on Slot State, Not Prompt Wording

**Files:**
- Modify: `ragenius_app_skeleton/workflows/nodes/planner.py`
- Test: `ragenius_app_skeleton/tests/test_planner_node.py`

- [ ] **Step 1: Replace the narrow prompt-shape dependency with slot-state-first advancement**

```python
def _should_enter_bundled_followup_step(
    state: GraphState,
    workflow: Dict[str, Any],
    current_step: Dict[str, Any] | None,
    current_query: str,
) -> Dict[str, Any] | None:
    if not isinstance(current_step, dict) or not current_step:
        return None
    steps = _workflow_steps(workflow)
    current_order = current_step.get("order")
    if current_order is None:
        return None
    next_step = _find_step_by_order(steps, int(current_order) + 1)
    if not isinstance(next_step, dict) or not next_step:
        return None
    current_step_definition = _procedure_step_definition_for_scope(state, str(current_step.get("step_scope_id") or "").strip()) or {}
    next_step_definition = _procedure_step_definition_for_scope(state, str(next_step.get("step_scope_id") or "").strip()) or {}
    if str((current_step_definition or {}).get("execution_mode") or "").strip() != "interactive":
        return None
    if str((next_step_definition or {}).get("execution_mode") or "").strip() != "bundled":
        return None
    gate_rule = _matching_clarification_gate_rule(state, current_step_definition, next_step_definition)
    if _clarification_gate_satisfied_from_session_state(state, gate_rule):
        return next_step
    if _clarification_targets_satisfied(state, current_query):
        return next_step
    return None
```

- [ ] **Step 2: Keep `_current_turn_answers_clarification_prompt(...)` as a fallback helper only**

```python
def _current_turn_answers_clarification_prompt(state: GraphState, current_query: str) -> bool:
    # Legacy fallback only.
    # Do not require this helper once slot-state completion already satisfies the gate.
    assistant_messages = _conversation_assistant_messages(state)
    if not assistant_messages:
        return False
    last_assistant = assistant_messages[-1].lower()
    query = str(current_query or "").strip()
    if not query:
        return False
    if any(token in last_assistant for token in ("經文", "经文", "主題", "主题", "scripture", "passage", "theme", "topic")):
        return _has_topic_signal(query)
    if any(token in last_assistant for token in ("受眾", "受众", "對象", "对象", "audience", "給誰", "给谁")):
        return _has_audience_signal(query)
    return False
```

- [ ] **Step 3: Add a regression that prompt wording can vary while slot-state still advances**

```python
def test_planner_hybrid_active_clarification_advances_without_audience_or_topic_prompt_keywords(self):
    state = self.state.copy()
    state["planner_mode"] = "hybrid_active"
    state["instruction_understanding_mode"] = "hybrid_active"
    state["user_query"] = "The goal is to help leaders understand the theology of Ephesians 1."
    state["chat_history"] = [
        {"role": "assistant", "content": "One last question: what outcome should this prompt achieve?"},
    ]
    state["workflow_progress"] = {
        "workflow_id": "primary_workflow:interaction_logic_execution_flow",
        "workflow_title": "Interaction Logic & Execution Flow",
        "step_order": 1,
        "step_title": "Clarification",
    }
    state["session_execution_state"] = {
        "active_step_scope_id": "step:interaction_logic_execution_flow:1",
        "clarification_gate_status": {"filled_slots_map": {"passage": True, "audience": True}},
    }
    state["template_registry"] = _church_ministry_slot_state_registry()
    state["instruction_runtime_model"] = _church_ministry_slot_state_runtime_model()

    out = planner.run(state, llm_planner=lambda _p, _t, _c: json.loads(json.dumps(self.valid)))
    self.assertEqual(out["session_execution_state"]["active_step_scope_id"], "step:interaction_logic_execution_flow:2")
```

- [ ] **Step 4: Run the focused clarification advancement slice**

Run: `python -m pytest ragenius_app_skeleton/tests/test_planner_node.py -k "clarification_advances_without_audience_or_topic_prompt_keywords or advances_from_clarification_when_goal_slot_arrives" -v`

Expected: PASS

- [ ] **Step 5: Commit the clarification advancement checkpoint**

```bash
git add ragenius_app_skeleton/workflows/nodes/planner.py ragenius_app_skeleton/tests/test_planner_node.py
git commit -m "feat: advance clarification from slot-state completion"
```

### Task 4: Keep Core Workflow and Follow-Up Ordering Correct

**Files:**
- Modify: `ragenius_app_skeleton/workflows/nodes/planner.py`
- Test: `ragenius_app_skeleton/tests/test_planner_node.py`

- [ ] **Step 1: Preserve the existing gate-turn guard so a same-turn gate resolution cannot immediately promote a follow-up module**

```python
gate_resolved_this_turn = bool(str(state.get("_control_gate_resolved_step_scope_id") or "").strip())
if gate_resolved_this_turn and block_type == "followup_module":
    continue
```

- [ ] **Step 2: Add a regression that Church Ministry enters Step 2 before Optimization Module**

```python
def test_planner_hybrid_active_church_ministry_core_step_wins_before_followup_module_after_slot_completion(self):
    state = self.state.copy()
    state["planner_mode"] = "hybrid_active"
    state["instruction_understanding_mode"] = "hybrid_active"
    state["user_query"] = "The goal is to help small-group leaders understand the theology of Ephesians 1."
    state["chat_history"] = [
        {"role": "assistant", "content": "Who is the audience for this Bible-study prompt?"},
        {"role": "user", "content": "Prepare Bible-study sharing materials for Ephesians chapter 1."},
        {"role": "assistant", "content": "Please provide the audience."},
        {"role": "user", "content": "The audience is small-group leader training."},
    ]
    state["workflow_progress"] = {
        "workflow_id": "primary_workflow:interaction_logic_execution_flow",
        "workflow_title": "Interaction Logic & Execution Flow",
        "step_order": 1,
        "step_title": "Clarification",
    }
    state["session_execution_state"] = {
        "active_step_scope_id": "step:interaction_logic_execution_flow:1",
        "clarification_gate_status": {"filled_slots_map": {"passage": True, "audience": True}},
        "active_module_queue": ["followup_module:optimization_module"],
        "primary_support_module_id": "followup_module:optimization_module",
        "bundled_execution_completed": True,
    }
    state["template_registry"] = _church_ministry_slot_state_registry()
    state["instruction_runtime_model"] = _church_ministry_slot_state_runtime_model()

    out = planner.run(state, llm_planner=lambda _p, _t, _c: json.loads(json.dumps(self.valid)))
    self.assertEqual(out["session_execution_state"]["active_service_block_id"], "primary_workflow:interaction_logic_execution_flow")
    self.assertEqual(out["session_execution_state"]["active_step_scope_id"], "step:interaction_logic_execution_flow:2")
```

- [ ] **Step 3: Run the ordering-specific tests**

Run: `python -m pytest ragenius_app_skeleton/tests/test_planner_node.py -k "core_step_wins_before_followup_module_after_slot_completion or persists_optimization_module_instead_of_bundled_step_two_scope" -v`

Expected: PASS

- [ ] **Step 4: Commit the ordering checkpoint**

```bash
git add ragenius_app_skeleton/workflows/nodes/planner.py ragenius_app_skeleton/tests/test_planner_node.py
git commit -m "fix: preserve core workflow before followup activation"
```

### Task 5: Lock Builder/API Regression for the Third Church Ministry Turn

**Files:**
- Modify: `ragenius_app_skeleton/tests/test_builder_chat_integration.py`
- Test: `ragenius_app_skeleton/tests/test_builder_chat_integration.py`

- [ ] **Step 1: Add builder integration regression for Church Ministry third turn**

```python
def test_session_messages_workflow_status_shows_core_workflow_after_goal_slot_completes_clarification(self):
    starter = self.client.post(
        f"/sessions/{session_id}/chat",
        json={
            "user_id": "user1",
            "app_id": church_ministry_app_id,
            "user_query": "準備以弗所書第一章的查經分享材料",
            "template_version": 1,
        },
    )
    self.assertEqual(starter.status_code, 200)

    audience_turn = self.client.post(
        f"/sessions/{session_id}/chat",
        json={
            "user_id": "user1",
            "app_id": church_ministry_app_id,
            "user_query": "對象主要是小組長訓練",
            "template_version": 1,
        },
    )
    self.assertEqual(audience_turn.status_code, 200)

    goal_turn = self.client.post(
        f"/sessions/{session_id}/chat",
        json={
            "user_id": "user1",
            "app_id": church_ministry_app_id,
            "user_query": "深入理解以弗所書第一章的神學真理",
            "template_version": 1,
        },
    )
    self.assertEqual(goal_turn.status_code, 200)

    messages = self.client.get(
        f"/sessions/{session_id}/messages",
        params={"app_id": church_ministry_app_id, "user_id": "user1"},
    )
    payload = messages.json()
    self.assertEqual(payload["workflow_status"]["current_step"]["title"], "核心流程（Workflow Execution）")
    self.assertEqual(payload["workflow_status"]["active_step_scope_id"], "step:interaction_logic_execution_flow:2")
    latest_assistant = payload["messages"][-1]
    self.assertCountEqual(
        latest_assistant["retrievalSummary"]["selected_resource_filenames"],
        ["template_library.md", "dynamic_prompt_optimizer.md"],
    )
```

- [ ] **Step 2: Run the targeted builder integration regression**

Run: `python -m pytest ragenius_app_skeleton/tests/test_builder_chat_integration.py -k "shows_core_workflow_after_goal_slot_completes_clarification" -v`

Expected: PASS

- [ ] **Step 3: Commit the builder regression checkpoint**

```bash
git add ragenius_app_skeleton/tests/test_builder_chat_integration.py
git commit -m "test: lock church ministry core-step builder regression"
```

### Task 6: Full Verification and Protected Non-Regression

**Files:**
- Modify: none
- Test: `ragenius_app_skeleton/tests/test_planner_node.py`
- Test: `ragenius_app_skeleton/tests/test_builder_chat_integration.py`
- Test: `ragenius_app_skeleton/tests/test_instruction_understanding_service.py`
- Test: `ragenius_app_skeleton/tests/test_llm_runtime_compat.py`

- [ ] **Step 1: Run compile contract suite**

Run: `python -m pytest ragenius_app_skeleton/tests/test_instruction_understanding_service.py -v`

Expected: `102 passed`

- [ ] **Step 2: Run full planner/runtime persistence suite**

Run: `python -m pytest ragenius_app_skeleton/tests/test_planner_node.py -v`

Expected: PASS with the new Church Ministry slot-state tests included.

- [ ] **Step 3: Run targeted builder/GUI payload suite**

Run: `python -m pytest ragenius_app_skeleton/tests/test_builder_chat_integration.py -k "bible_tutor_three_turn_flow_via_api or session_messages_workflow_status_shows_core_workflow_when_bundled_step_two_is_active or session_messages_workflow_status_shows_optimization_module_when_optimization_turn_is_active or session_messages_workflow_status_shows_parenting_route_when_role_target_should_bind_workflow or session_messages_workflow_status_shows_life_application_for_life_guidance_starter or shows_core_workflow_after_goal_slot_completes_clarification" -v`

Expected: PASS

- [ ] **Step 4: Run cross-app non-regression suite**

Run: `python -m pytest ragenius_app_skeleton/tests/test_llm_runtime_compat.py -v`

Expected: `8 passed, 3 subtests passed`

- [ ] **Step 5: Manual live verification checklist**

Run these flows against `http://127.0.0.1:8012` after backend restart:

```text
Church Ministry Prompt Designer
1. starter: 準備以弗所書第一章的查經分享材料
2. answer audience: 對象主要是小組長訓練
3. answer goal: 深入理解以弗所書第一章的神學真理
Expected third assistant turn:
- GUI current step = 核心流程（Workflow Execution）
- loaded docs = template_library.md + dynamic_prompt_optimizer.md
- not Clarification
- not Optimization Module
```

```text
Bible Tutor
1. starter: 我想查考一段經文
2. provide passage
Expected:
- step-specific guide only
- no Church Ministry regression
```

```text
與孩子一起成長
1. starter: 最近在教養孩子時，我遇到的挑戰是…
Expected:
- workflow still visible
- no route-state regression
```

- [ ] **Step 6: Commit the verification checkpoint**

```bash
git add ragenius_app_skeleton/workflows/nodes/planner.py ragenius_app_skeleton/tests/test_planner_node.py ragenius_app_skeleton/tests/test_builder_chat_integration.py
git commit -m "fix: advance clarification from slot-state completion"
```
