# Planner Prompt Contract For Hybrid Application-Instruction Understanding

**Date:** 2026-05-09  
**Status:** Draft for review  
**Scope:** `ragenius_app_skeleton` planner LLM prompt contract for turn-level intent inference and next-action selection using compiled application-instruction understanding.

## Goal

Define a strict planner prompt contract so the planner uses LLM only for bounded semantic judgment at turn time, while deterministic code continues to own:
- application-instruction compilation
- structural validity
- runtime state invariants
- resource existence
- workflow/module legality
- final execution-plan validation

The planner LLM must not reinterpret the whole app from raw instructions. It must choose among compiled candidates and return structured decisions that the planner can validate.

## Core Principle

The planner does not ask:
- "what does this app mean?"

The planner asks:
- "given this already compiled app contract and this user turn, what is the most plausible intent, scope, and next action?"

## Planner Responsibilities Before LLM

Before invoking the planner LLM, deterministic planner code must:

1. load the published compiled application-instruction understanding
2. load current session execution state
3. apply hard deterministic rules first
4. reduce the decision space to valid candidates
5. construct a compact turn-decision packet for the LLM

## Deterministic Inputs To Planner

### A. Current user turn
- latest user message
- optionally normalized query
- optionally contextual query
- current date/time if needed for relative language normalization

### B. Recent conversation context
- last assistant turn
- recent turn summary
- persisted slot state
- persisted outputs/artifacts if relevant

### C. Current runtime state
- active role id
- active workflow id
- active service block id/type
- active step id
- active execution mode
- active module queue if any
- clarification progress
- prior output roles
- whether the system is waiting for user input

### D. Compiled app contract summary
The planner should send only the relevant compiled sections, not the full instruction file.

Relevant sections may include:
- global app contract
- relevant interaction logic blocks
- role profiles
- routing rules
- module orchestration
- active or candidate workflows/modules/supplementary workflows
- clarification gate rules
- reachable next steps
- output contract summaries if they affect routing

## Deterministic Rules That Must Run Before LLM

The planner must skip or narrow LLM use when deterministic rules are sufficient.

### Hard deterministic cases
1. explicit slash/command trigger
2. explicit stop/end request
3. explicit continue marker when current interaction logic defines it
4. explicit forced admin/runtime action
5. explicit supplementary workflow request when the target is unambiguous
6. explicit follow-up module command when required artifact gates are already satisfied
7. current active bundled execution unit already determined and no routing ambiguity remains

In these cases the planner may bypass LLM entirely or ask the LLM only for response shaping later, not for routing.

## Planner LLM Use Cases

The planner LLM is for bounded semantic decisions such as:
- infer current user-turn intent label
- decide whether the user continues the current scope or switches scope
- match the turn to one compiled routing rule among valid candidates
- choose the most plausible role profile
- decide which workflow/module/supplementary workflow should be active now
- decide whether clarification is complete under the compiled gate rule
- determine which ordered module sequence should start or continue
- determine the next executable unit:
  - clarification step
  - bundled execution entry step
  - ordered module execution item
  - follow-up step
  - summarize/stop

## Required Planner Prompt Structure

The planner LLM prompt should be assembled from these logical sections.

### 1. System contract
A short system instruction telling the model:
- it is not interpreting raw app instructions
- it must choose only among supplied compiled candidates
- it must return strict JSON
- it must not invent ids, workflows, modules, or resources
- if uncertain, it must choose the best candidate and state uncertainty in structured form

### 2. Planner task description
The prompt must explicitly request:
- classify current turn intent
- select role if applicable
- select workflow/module/supplementary workflow if applicable
- decide continue vs switch
- decide clarification completion if a gate is active
- decide next executable unit

### 3. Turn-decision packet
A compact JSON-like context containing:
- app summary
- runtime state
- candidates
- routing rules
- clarification gate
- module orchestration rules
- recent conversation

### 4. Output schema instruction
The prompt must show the exact JSON response schema and require the model to return only that schema.

## Planner Turn-Decision Packet Schema

```json
{
  "task": "turn_intent_and_next_action_inference",
  "app": {
    "app_id": "string",
    "app_name": "string",
    "mission": "string | null",
    "objective": "string | null",
    "constraints": ["string"],
    "security_rules": ["string"],
    "boundaries": ["string"]
  },
  "interaction_logic": [
    {
      "logic_id": "string",
      "scope": "global | workflow | step",
      "summary_rules": ["string"]
    }
  ],
  "session_state": {
    "active_role_id": "string | null",
    "active_workflow_id": "string | null",
    "active_service_block_id": "string | null",
    "active_service_block_type": "string | null",
    "active_step_id": "string | null",
    "active_execution_mode": "interactive | bundled | null",
    "active_module_queue": ["string"],
    "current_module_index": 0,
    "filled_slots": {},
    "waiting_for_user": false,
    "prior_output_roles": ["string"],
    "supplementary_workflow_active": false
  },
  "conversation": {
    "last_assistant_message": "string | null",
    "latest_user_message": "string",
    "recent_summary": "string | null"
  },
  "candidates": {
    "roles": [],
    "workflows": [],
    "support_modules": [],
    "followup_modules": [],
    "supplementary_workflows": [],
    "reachable_steps": []
  },
  "routing_rules": [],
  "module_orchestration": {
    "selection_mode": "semantic | trigger_based | mixed | null",
    "starter_required": false,
    "assistant_suggestion_allowed": false,
    "allow_multi_module": false,
    "composition_mode": "ordered_sequential | null",
    "task_module_mappings": []
  },
  "clarification_gate": {
    "gate_rule_id": "string | null",
    "clarification_step_id": "string | null",
    "completion_step_id": "string | null",
    "minimum_filled_slots": 0,
    "required_slots": ["string"],
    "optional_slots": ["string"]
  },
  "required_output": {
    "classify_intent": true,
    "select_role": true,
    "select_target_scope": true,
    "decide_continue_or_switch": true,
    "decide_clarification_complete": true,
    "decide_next_execution_unit": true
  }
}
```

## Candidate Object Expectations

### Role candidate
```json
{
  "role_id": "string",
  "name": "string",
  "purpose": "string | null",
  "tone_style": ["string"],
  "allowed_workflow_ids": ["string"],
  "allowed_module_ids": ["string"]
}
```

### Workflow candidate
```json
{
  "workflow_id": "string",
  "title": "string",
  "selection_mode": "default | explicit_trigger | intent_routed | delegated_from_rule",
  "intent_signals": ["string"],
  "reachable_step_ids": ["string"]
}
```

### Module candidate
```json
{
  "module_id": "string",
  "module_type": "support | followup",
  "title": "string",
  "purpose": "string | null",
  "required_inputs": ["string"],
  "depends_on_output_roles": ["string"]
}
```

### Step candidate
```json
{
  "step_id": "string",
  "title": "string",
  "execution_mode": "interactive | bundled",
  "wait_for_user": false
}
```

## Required Planner LLM Output Schema

The planner LLM must return JSON only.

```json
{
  "intent_label": "string",
  "confidence": 0.0,
  "continue_current_scope": true,
  "selected_role_id": "string | null",
  "selected_workflow_id": "string | null",
  "selected_support_module_ids": ["string"],
  "selected_followup_module_ids": ["string"],
  "selected_supplementary_workflow_id": "string | null",
  "module_sequence": ["string"],
  "clarification_status": {
    "is_active": false,
    "is_complete": false,
    "missing_slots": ["string"],
    "filled_slot_names": ["string"]
  },
  "next_action": {
    "action_type": "stay_idle | ask_clarification | enter_interactive_step | enter_bundled_execution | start_ordered_module_sequence | continue_ordered_module_sequence | switch_scope | summarize_and_stop",
    "target_service_block_id": "string | null",
    "target_workflow_id": "string | null",
    "target_step_id": "string | null",
    "bundled_step_ids": ["string"],
    "module_queue": ["string"]
  },
  "reasoning_summary": ["string"]
}
```

## Output Constraints

The LLM output must obey these rules:
- all returned ids must appear in the supplied candidate set
- `selected_role_id` must be null if no role is relevant
- `selected_workflow_id` must be null when only a module action is selected
- `selected_supplementary_workflow_id` cannot coexist with an unrelated primary workflow selection
- `module_sequence` must be ordered and contain only supplied modules
- `bundled_step_ids` must be a subset of the supplied reachable steps
- if `clarification_status.is_complete = false`, `next_action.action_type` should usually be `ask_clarification` unless a hard stop/switch applies

## Planner Validation After LLM Return

Deterministic planner code must validate the LLM response before creating the execution plan.

### Required validations
1. all selected ids exist
2. selected role is compatible with selected workflow/module
3. selected workflow/module is reachable from current state
4. selected module queue respects ordered sequential orchestration
5. clarification completion is consistent with the compiled gate rule
6. selected next step is reachable from the selected workflow
7. bundled execution selection uses a valid bundled entry step
8. no constraint, boundary, or security rule is violated

### On validation failure
Planner must not execute an invalid LLM decision directly.
Instead it should:
- fall back to the best deterministic choice when possible
- or request a narrower reclassification pass
- or stop at a safe clarification action

## Planner Prompt Template

### System message

```text
You are the planner-routing model for a compiled application contract.
You are not interpreting raw instructions. You must choose only among the candidates and ids provided.
Return JSON only. Do not invent workflows, roles, modules, steps, resources, or ids.
If uncertain, choose the best valid candidate and reflect uncertainty in the confidence field and reasoning_summary.
```

### User message template

```text
Task: infer user-turn intent and decide the next planner action using the compiled application contract.

Rules:
- Use only the supplied ids and candidates.
- Respect current session state.
- Respect clarification gates.
- Respect ordered sequential module orchestration.
- Prefer continuing the current scope when the new user turn is a clear continuation.
- Select a new scope only when the turn meaningfully switches task.
- Return JSON only using the required schema.

Decision packet:
<INSERT SERIALIZED TURN-DECISION PACKET JSON>

Return schema:
<INSERT REQUIRED PLANNER LLM OUTPUT SCHEMA>
```

## Example Use: No Default Workflow App

For an app like `Grow With Children`, the planner packet may include:
- multiple peer primary workflows
- no default workflow id
- routing rules that choose among:
  - `3x1 advice`
  - `stepwise planning`
  - `deep analysis`
- role candidates such as:
  - coach
  - consultant
  - mentor
- interaction logic that says clarification or encouragement rules apply globally

The planner LLM should classify which routed workflow best matches the current parenting query, not invent a default.

## Example Use: Sequential Module Orchestration App

For an app like `GPT Application Design Assistant`, the planner packet may include:
- current workflow or phase
- task-to-module mappings such as:
  - fuzzy idea -> `Use Case Writing Support Module`
  - architecture -> `MODULE_GENERATOR`
  - resources -> `RESOURCE_MANIFEST_SUPPORT`
  - module resources -> `RESOURCE_BINDING`
  - configuration issue -> `Configuration Support Module`
  - interaction issue -> `Interaction Mode Support Module`
  - testing -> `Testing & Optimization Support Module`
- module orchestration contract:
  - starter not required
  - assistant suggestion allowed
  - ordered sequential composition only

If the turn and session content map to multiple modules, the planner LLM should return an ordered `module_sequence`, and deterministic planner code should queue them sequentially.

## Example Use: Clarification Gate App

For an app like `Church Ministry Prompt Designer`, the planner packet may include:
- active clarification step
- gate rule such as `minimum_filled_slots = 3`
- completion step id pointing to a bundled generation step
- currently filled slots from accumulated conversation

The planner LLM should determine whether the latest user turn completes the gate under the supplied contract, not using hardcoded field-specific heuristics.

## Suggested Planner Runtime Flow

1. load published compiled understanding
2. load current session state
3. apply hard deterministic routing rules
4. construct candidate set and decision packet
5. call planner LLM only if semantic judgment is needed
6. validate LLM output
7. build turn execution plan
8. persist updated session state

## Success Criteria

This prompt contract is successful when:
- planner stops reinterpreting raw instruction text at turn time
- planner decisions are explainable from the compiled contract
- apps with no default workflow route correctly
- role selection and workflow/module selection can be made together
- clarification completion no longer depends on app-specific hardcoded heuristics
- ordered sequential module orchestration is supported
- bundled execution entry is chosen through compiled rules rather than title heuristics
- invalid LLM outputs are safely rejected or narrowed by deterministic validation
