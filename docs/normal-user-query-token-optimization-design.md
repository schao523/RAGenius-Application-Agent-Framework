# Normal User Query Token Optimization Design

Date: 2026-06-15

Status: design proposal

Revision: 2026-07-15 pre-implementation safety review

Related contract: [normal-user-query-token-optimization-contract.md](./normal-user-query-token-optimization-contract.md)

## 1. Purpose

This design implements the normal-user-query token optimization contract for `ragenius_app_skeleton` without changing the externally visible behavior of the active runtime.

The goal is to reduce DeepSeek input tokens for normal text chat turns while preserving:

- planner correctness
- evidence coverage shape
- final answer schema and citations
- app isolation
- workflow/session continuity
- GUI workflow status payloads
- existing fallback behavior
- all non-normal-query capabilities

## 2. Scope

In scope:

- normal text turns handled by `POST /sessions/{session_id}/chat`
- `_handle_normal_chat_turn(...)`
- `run_chat_pipeline(...)`
- planner LLM context
- optional hybrid planner LLM context
- optional evidence-analysis LLM context
- answer-generation LLM context
- task model diagnostics enrichment

Out of scope:

- exec turns and execution-lane commands
- session upload analysis turns
- instruction-understanding compile/review/revision
- Builder admin/control-plane workflows
- `rag_subsystem` retrieval/indexing/vector internals
- changing DeepSeek/OpenAI-compatible request or response schemas
- changing frontend payload contracts

## 3. Current Runtime Path

Normal chat currently flows through:

1. `main.py::_handle_normal_chat_turn(...)`
2. `chat_service.py::run_chat_pipeline(...)`
3. workflow graph:
   `load_session_context -> extract_config_pdf -> load_or_generate_adapter -> load_template_registry -> planner -> retrieve -> execute_turn_plan -> evidence_postprocess -> evidence_analysis -> answer -> persist_run`
4. `chat_service.py` assembles final response diagnostics and workflow payloads.

The DeepSeek wrapper lives in `backend/app/llm_runtime.py`. It builds:

- one system message
- one user message containing `Context JSON`
- existing function tools
- existing `tool_choice`
- existing task temperature and model configuration

This design keeps that wrapper compatible and provider-thin.

## 4. Design Principles

1. Preserve runtime state; compact only LLM input context.
2. Keep full `GraphState` available to graph nodes.
3. Keep tool schemas and validators unchanged.
4. Keep retrieval delegated to `rag_subsystem`.
5. Avoid changing Builder state, instruction storage, or app definitions.
6. Add compact context builders as projections, not replacements.
7. Fail open for planner and answer generation; fail closed for evidence analysis when deterministic coverage is enough.
8. Make rollout feature-flagged and reversible.
9. Calculate optimization eligibility once per turn and never optimize upload, artifact-analysis, or exec turns.
10. Preserve prompt-referenced logical key names and compact their values instead of silently renaming contracts.
11. Measure the payload actually sent, not only the compact candidate.

## 5. Proposed Architecture

Add a small task-context projection layer:

```text
GraphState
  -> normal-query eligibility decision
  -> task-specific compact context builder
  -> full and compact token estimates
  -> ordered budget compaction stages
  -> existing llm task callable
  -> existing schema validation and fallback path
```

Recommended module:

```text
ragenius_app_skeleton/backend/app/llm_context_optimization.py
```

This module should be pure and side-effect-light. It should not call DeepSeek, mutate retrieval behavior, or persist sessions directly.

Primary functions:

```python
build_planner_context(state) -> dict
build_hybrid_planner_context(state, decision_packet) -> dict
build_evidence_analysis_context(state, info_types, evidence, instruction_evidence) -> dict
build_answer_context(state, full_context) -> dict
estimate_input_tokens(prompt, context, tools) -> dict
apply_task_budget(task, prompt, context, tools) -> ContextOptimizationResult
normal_query_optimization_eligible(state) -> bool
build_or_refresh_chat_summary(state, current_user_message, current_answer) -> dict
```

`ContextOptimizationResult` should include:

```python
{
    "context": dict,
    "diagnostics": dict,
    "budget_exceeded": bool,
    "skip_llm": bool,
    "skip_reason": str | None,
    "actual_full_tokens": int,
    "compact_candidate_tokens": int,
    "actual_outbound_tokens": int,
}
```

### 5.1 Eligibility Boundary

`main.py::_handle_normal_chat_turn(...)` should set an internal turn flag after evaluating:

```python
eligible = (
    str(state.get("turn_input_type") or "") == "text_query"
    and not bool(state.get("pending_upload_analysis"))
    and not list(state.get("session_upload_event_ids") or [])
)
```

`run_chat_pipeline(...)` propagates this flag to planner, evidence, and answer nodes. Every optimization helper must return the original context unchanged when the flag is false. The upload route that sets `turn_input_type="session_upload"` therefore remains on the current path even when compact mode is globally enabled.

## 6. Feature Flags

Optimization must default to safe behavior during rollout.

Recommended controls:

```text
RAGENIUS_LLM_CONTEXT_OPTIMIZATION=0|1
RAGENIUS_LLM_CONTEXT_OPTIMIZATION_MODE=off|diagnostic|compact
RAGENIUS_LLM_EVIDENCE_ANALYSIS_MODE=auto|deterministic|llm_required
```

Modes:

- `off`: current behavior.
- `diagnostic`: build compact contexts and diagnostics, but send current full contexts.
- `compact`: send compact contexts subject to budget rules.

Initial default should be `off` or `diagnostic`. Do not make compact mode default until regression tests and representative sessions pass.

Feature flags apply only after the eligibility boundary passes. They must not broaden scope.

## 7. Planner Context Design

Current planner sends broad `config_json`, `adapter_json`, `template_registry`, full chat history, and uploads.

Compact planner context should include:

- `user_query`
- `turn_input_type`
- `app_id` and `collection_id`
- compact chat summary plus last 4 chat turns
- active workflow/session summary
- intent overrides
- routing rules
- compact workflow/module/step candidates
- retrieval defaults
- relevant resource binding identity fields

The planner prompt can remain unchanged initially. The context object changes shape, so the context should keep stable key names where practical:

```json
{
  "user_query": "...",
  "turn_input_type": "text_query",
  "chat_history": [],
  "chat_summary": {},
  "app_id": "...",
  "collection_id": "...",
  "config_json": {},
  "adapter_json": {},
  "template_registry": {},
  "active_session": {}
}
```

The values of `config_json`, `adapter_json`, and `template_registry` are compact projections, but their logical names and prompt-visible shapes remain compatible. If a projection cannot preserve a prompt assumption, update the prompt and its regression tests in the same change.

Compatibility guard:

- Keep `_enforce_app_scoped_retrieval(...)` after the planner response.
- Keep `validate_planner_output(...)`.
- Keep fallback planner behavior for low confidence or exceptions.
- Do not remove full `config_json`, `adapter_json`, or `template_registry` from `GraphState`; only omit them from the LLM context.
- Preserve upload metadata unchanged by bypassing planner optimization for ineligible turns.

## 8. Hybrid Planner Context Design

Current hybrid planner already sends a decision packet, but candidate objects may include verbose bodies.

Compact hybrid planner context should preserve:

- app id/name
- mission/objective summary
- current active role/workflow/module/step state
- latest user message
- last assistant message
- compact candidate roles/workflows/modules/followups/steps
- routing rules
- module orchestration summary
- clarification gate summary

Candidate projection:

```json
{
  "id": "...",
  "type": "...",
  "title": "...",
  "objective": "...",
  "triggers": [],
  "allowed_targets": []
}
```

Compatibility guard:

- Preserve all ids used by downstream planner harmonization.
- Do not compact away follow-up module ids or active queue state.
- Keep `hybrid_planner_decision_packet` and `hybrid_planner_shadow_output` response fields unchanged.

## 9. Evidence Analysis Design

Evidence analysis is the lowest-risk optimization target.

Behavior:

- If no evidence-analysis task model is configured, keep current deterministic behavior.
- If configured and deterministic sufficiency passes, skip DeepSeek and use deterministic local coverage.
- If ambiguous or configured as `llm_required`, send compact evidence context.

Mode behavior:

- `auto`: use the deterministic predicate only when all sufficiency and non-conflict checks pass.
- `deterministic`: always use current deterministic analysis.
- `llm_required`: call the configured evidence LLM even when deterministic checks pass; fall back locally only when the model is unavailable or errors.

Compact evidence item:

```json
{
  "doc_id": "...",
  "title": "...",
  "snippet": "... capped to 500 chars ...",
  "score": 0.83,
  "metadata": {
    "info_type": "...",
    "info_types": [],
    "tags": []
  }
}
```

Compatibility guard:

- Output shape remains `infoTypes_with_evidence`, `infoTypes_missing`, `evidence_summary`.
- On LLM errors, keep existing deterministic fallback.
- Do not use evidence analysis to alter retrieval behavior.
- Do not remove citation-bearing fields from evidence later used by answer generation.
- Do not treat direct substring matching as sufficient when evidence conflicts or lacks stable citation identity.

## 10. Answer Generation Design

Answer generation likely yields the largest savings.

Compact answer context should include:

- `user_query`
- compact chat summary plus last 6 chat turns
- compact `planner_output`
- `evidence_analysis`
- top 8 `knowledge_evidence` items with citation fields
- selected instruction block summary
- selected instruction block text only when active
- explicitly loaded instruction resource context only
- top 3 template evidence/context items when template output is active
- session upload evidence only when the turn references uploads or active upload ids
- compact style/safety/guardrail policy
- presentation policy
- visible outputs only when they affect answer content
- compact `prepared_inputs`
- compact instruction evidence
- instruction and template resource load plans
- relevant turn action/execution state and assembly obligations
- hidden outputs only when referenced by answer, validation, assembly, or artifact obligations

Must not send by default:

- full `config_json`
- full `adapter_json`
- full `template_registry`
- unrelated fields from `turn_execution_plan` and `session_execution_state`
- unrelated hidden outputs
- duplicate evidence collections

Compatibility guard:

- Keep direct answer bypasses:
  - general out-of-scope direct answer
  - direct instruction-block answer
  - visible-output answer
- Keep `validate_final_answer(...)`.
- Keep provider-error and generic fallback behavior.
- Keep safe-answer second pass when `missing_infoTypes` is non-empty, but pass compact safe context plus `previous_answer`.
- Preserve citations from knowledge/session-upload evidence only.
- Preserve the existing logical context keys asserted by `test_answer_node.py`.
- Compact authoritative instruction text by complete semantic sections; do not apply blind character truncation.
- Include session-upload evidence only when the eligible normal text turn references active session-upload ids. Ineligible upload-analysis turns bypass optimization entirely.

## 11. Chat Summary Design

Rolling summaries are compression aids only. They must not become the source of truth for workflow state.

Storage:

```text
session_execution_state.chat_summary
```

Payload:

```json
{
  "summary_text": "...",
  "last_refreshed_message_id": "...",
  "covered_message_count": 12,
  "active_workflow_id": "...",
  "active_module_id": "...",
  "active_step_id": "...",
  "filled_slots": {},
  "unresolved_user_commitments": [],
  "recent_cited_source_ids": [],
  "pending_artifact_obligations": []
}
```

Refresh rules:

- Refresh no later than the first turn that would push history beyond the planner's 4-turn window.
- Preserve existing `workflow_progress` and `session_execution_state`.
- If refresh fails, retain bounded recent-turn history and existing summary.
- Do not require summary generation to complete the user turn.
- Include the current user message and completed assistant answer explicitly because the input `chat_history` does not yet contain the current turn before `persist_run` appends it.

Implementation note:

- Initial implementation should use deterministic extraction from actual message content and runtime state: user decisions/constraints, assistant conclusions, unresolved questions, active workflow state, filled slots, pending obligations, and citation ids.
- LLM-generated summaries should be avoided in the first rollout to prevent adding another token-consuming task.

## 12. Diagnostics Design

Diagnostics should extend existing task model diagnostics without breaking consumers.

Add optional fields under each selected task model diagnostic:

```json
{
  "context_optimization": {
    "context_mode": "full|diagnostic|compact",
    "context_bytes": 12345,
    "estimated_input_tokens": 3000,
    "actual_full_tokens": 5200,
    "compact_candidate_tokens": 3000,
    "actual_outbound_tokens": 3000,
    "estimated_tokens_saved": 2200,
    "estimated_saving_percent": 42.3,
    "estimator_name": "chars_per_token",
    "estimator_version": "v1",
    "top_level_keys": [],
    "evidence_count": 3,
    "chat_history_turn_count": 4,
    "budget_limit_tokens": 8000,
    "budget_exceeded": false,
    "overflow_reason": null,
    "compaction_applied": true,
    "compaction_reasons": []
  }
}
```

Estimator:

```text
chars_per_token:v1 = ceil(character_count / 4)
```

Estimate serialized messages plus compact context JSON and prompt text. Exclude HTTP headers and API keys.

Diagnostic mode estimates both full and compact payloads and sends the full payload. Compact mode estimates both and sends the compact payload. Per-turn diagnostics aggregate `actual_outbound_tokens` across planner, hybrid planner, evidence analysis, answer generation, and safe-answer retries.

## 13. Budget Enforcement

Task budgets:

```text
planner:             <= 8k input tokens
hybrid planner:      <= 8k input tokens
evidence analysis:   <= 3k input tokens
answer generation:   <= 12k input tokens
normal query total:  <= 25k input tokens
```

Fail-open tasks:

- planner
- hybrid planner
- answer generation
- safe answer generation

If these still exceed budget after all compaction, proceed and record overflow diagnostics.

Ordered compaction stages:

1. Remove exact duplicate collections and unused metadata.
2. Apply bounded history plus the persisted real summary.
3. Project full runtime objects into prompt-compatible task views.
4. Rank and cap evidence while preserving citation identity.
5. Shorten prose only at semantic section/rule boundaries.
6. Re-estimate and record fail-open overflow if no permitted stage remains.

Fail-closed task:

- evidence analysis when deterministic coverage is sufficient

If evidence-analysis context exceeds budget and deterministic coverage is sufficient, skip DeepSeek and use deterministic coverage.

## 14. Integration Points

Recommended minimal code touch points:

- `backend/app/llm_runtime.py`
  - optionally accept already-optimized context diagnostics, or keep unchanged and optimize before calling task callable
- `workflows/nodes/planner.py`
  - call planner context builder before `_call_planner(...)`
  - call hybrid context builder before `_call_hybrid_planner_shadow(...)`
- `workflows/nodes/evidence_analysis.py`
  - apply deterministic sufficiency check and compact evidence context before LLM call
- `workflows/nodes/answer.py`
  - build compact answer context before `_call_answer_llm(...)`
  - build compact safe-answer context before safe pass
- `backend/app/chat_service.py`
  - calculate/propagate eligibility, aggregate task token estimates, and merge optimization diagnostics into `_task_model_diagnostics`
- `workflows/nodes/persist_run.py` or existing session persistence path
  - persist `session_execution_state.chat_summary` after assistant answer when needed

Avoid touching:

- `rag_subsystem`
- Builder data model
- root compatibility shims
- frontend workflow status schema
- function schema files unless a separate schema change is explicitly approved

## 15. Rollout Plan

Phase 1: diagnostics only

- Add compact context builders.
- Estimate token use for current full context and proposed compact context.
- Send existing full contexts.
- Record diagnostics in existing task diagnostics.
- Verify ineligible upload and exec turns produce `optimization_eligible=false` and unchanged contexts.

Phase 2: evidence analysis optimization

- Enable deterministic sufficiency predicate.
- Skip DeepSeek evidence analysis when safe.
- Compact LLM evidence context when LLM is required.

Phase 3: answer-generation compaction

- Enable compact answer context.
- Preserve direct answer bypasses and safe-answer fallback.
- Compare answer/citation behavior against representative sessions.

Phase 4: planner and hybrid planner compaction

- Enable planner compact context after targeted regression tests pass.
- Roll out hybrid planner candidate compaction separately.

Phase 5: default enablement

- Switch default from `diagnostic` to `compact` only after acceptance criteria pass.

## 16. Test Strategy

Unit tests:

- context builders preserve required fields
- budget estimator returns stable values
- evidence sufficiency predicate accepts/declines expected cases
- truncation preserves ids and citation fields
- diagnostics include estimator and budget fields

Planner regression tests:

- normal QA query still produces valid planner output
- low-confidence fallback still works
- app-scoped retrieval filter is preserved
- Church Ministry workflow/module/follow-up paths do not regress
- `與孩子一起成長` protected scenario does not regress

Answer tests:

- answer schema remains valid
- citations remain grounded in knowledge/session-upload evidence
- safe-answer second pass still works
- direct instruction-block answer still bypasses LLM
- visible-output answer still bypasses LLM
- general out-of-scope answer still uses only direct context

Persistence tests:

- `session_execution_state.chat_summary` persists without replacing workflow state
- sessions survive restart with the same runtime DB path
- message history and workflow status APIs remain backward-compatible

Integration tests:

- run normal query through `run_chat_pipeline(...)`
- compare full mode vs diagnostic mode vs compact mode
- assert output schema equivalence and workflow-status compatibility
- assert input token estimate reduction meets minimum threshold on representative fixtures
- assert upload analysis and exec turns bypass every compact context builder
- assert current answer prompt keys remain present after compaction

Representative parity fixtures:

- simple factual QA
- multi-turn workflow continuation beyond 4 turns
- Church Ministry first turn and refinement follow-up
- `與孩子一起成長` protected flow
- missing-evidence safe-answer second pass
- out-of-scope general question
- session-upload analysis proving optimization bypass
- normal text follow-up that explicitly references an active upload

For each eligible fixture, compare full and compact modes for planner intent/path, active workflow/module/step, resource requests, evidence coverage, answer schema, citation validity, and persisted runtime state. Compare token estimates from the exact serialized outbound messages and tools.

## 17. Acceptance Criteria

Implementation is acceptable when:

- representative normal queries reduce estimated DeepSeek input tokens by at least 40%
- planner, answer, evidence, and persistence tests pass
- no app isolation regression is introduced
- retrieval remains delegated to `rag_subsystem`
- existing response keys remain present
- task model diagnostics remain backward-compatible
- DeepSeek unavailable/error fallback behavior remains unchanged
- Church Ministry and `與孩子一起成長` protected scenarios pass
- upload-analysis and exec-turn outputs remain unchanged with compact mode globally enabled
- representative eligible fixtures achieve at least 40% aggregate estimated input-token reduction without parity failures

## 18. Risks and Mitigations

Risk: planner loses needed routing context.

Mitigation: roll out planner compaction last, preserve ids/routing targets, keep fail-open overflow, and run targeted planner regressions.

Risk: answer quality drops because policy context is over-compacted.

Mitigation: keep compact style/safety/guardrail policy, selected instruction block text, explicitly loaded instruction resources, and citation-bearing evidence.

Risk: GUI workflow status changes.

Mitigation: do not compact or mutate persisted `workflow_progress`, `session_execution_state`, or `turn_execution_plan`; compact only LLM input projections.

Risk: session continuity changes due to chat summaries.

Mitigation: summaries are additive under `session_execution_state.chat_summary`; they never replace workflow state or recent-turn history.

Risk: diagnostics break frontend consumers.

Mitigation: add diagnostics under optional nested keys and preserve existing fields.

Risk: global compact mode changes out-of-scope upload or exec behavior.

Mitigation: enforce one pipeline-level eligibility decision and test ineligible turns with compact mode enabled.

Risk: compact keys no longer match prompts.

Mitigation: retain existing logical key names or update prompts and tests atomically.

## 19. Non-Goals

- No retrieval rewrite.
- No Builder workflow changes.
- No new answer schema.
- No prompt/schema redesign.
- No removal of compatibility projections.
- No broad planner refactor.
- No extra LLM summarization task in the first rollout.

## 20. Implementation Checklist

1. Add feature flags and default to `diagnostic` or `off`.
2. Add pure context builder module.
3. Add estimator and diagnostics helpers.
4. Add evidence sufficiency predicate.
5. Add diagnostics-only integration.
6. Add tests for builders, diagnostics, and evidence predicate.
7. Enable evidence-analysis optimization.
8. Enable answer-generation compaction.
9. Enable planner/hybrid planner compaction after protected regressions pass.
10. Review token savings and behavior parity before default enablement.
