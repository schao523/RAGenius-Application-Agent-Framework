# Normal User Query Token Optimization Contract

Scope: normal user query in `ragenius_app_skeleton` chat runtime.

Goal: reduce DeepSeek input tokens while preserving planner correctness, evidence coverage, answer quality, citations, app isolation, and workflow state continuity.

## 1. Scope

This contract applies only to normal text chat turns handled by:

- `POST /sessions/{session_id}/chat`
- `_handle_normal_chat_turn(...)`
- `run_chat_pipeline(...)`
- planner, optional hybrid planner, optional evidence analysis, and answer generation LLM calls

Out of scope:

- exec turns
- upload-analysis turns
- instruction-understanding compile/review/revision
- Builder admin workflows
- `rag_subsystem` retrieval/indexing internals

### 1.1 Eligibility Gate

Optimization is eligible only when all of these conditions are true:

```text
turn_input_type == "text_query"
pending_upload_analysis == false
session_upload_event_ids is empty
the request is not an exec turn or execution-lane command
```

When any condition is false, planner, evidence-analysis, and answer-generation contexts must use the current unoptimized behavior. The eligibility decision must be calculated once per turn and propagated to every task call. Task nodes must not independently broaden eligibility.

Session-upload analysis, artifact analysis, exec turns, instruction-understanding tasks, and Builder tasks must remain behaviorally and structurally unchanged.

## 2. Non-Negotiable Behavior

Optimization must not change these externally observable outputs:

- valid `planner_output`
- valid `turn_execution_plan`
- app-scoped retrieval filters
- selected workflow/module/step behavior
- evidence coverage result shape
- final answer schema
- citations
- session persistence
- GUI workflow status payloads
- task model diagnostics

Optimization must preserve:

- `app_id` isolation
- file-backed instruction assumptions
- compatibility shims
- existing fallback behavior
- deterministic fallback paths when LLM calls fail or are disabled

## 3. DeepSeek Request Contract

All DeepSeek task calls must keep the existing OpenAI-compatible request shape:

```json
{
  "model": "...",
  "messages": [
    {"role": "system", "content": "...task prompt..."},
    {"role": "user", "content": "Context JSON:\n{...compact task context...}"}
  ],
  "tools": ["..."],
  "tool_choice": "auto",
  "temperature": "task temperature"
}
```

The response schemas must remain unchanged:

- planner: `create_planner_output`
- hybrid planner: `create_hybrid_planner_decision`
- evidence analysis: `evidence_analysis`
- answer generation: `create_final_answer`

Compact contexts must preserve the logical key names referenced by existing prompts unless the prompt and all associated tests are changed in the same implementation unit. In particular, compact planner contexts should retain `config_json`, `adapter_json`, and `template_registry` as compact projections rather than silently replacing them with differently named keys.

## 4. Task Context Budgets

Recommended hard budgets before sending to DeepSeek:

```text
planner:             <= 8k input tokens
hybrid planner:      <= 8k input tokens
evidence analysis:   <= 3k input tokens
answer generation:   <= 12k input tokens
normal query total:  <= 25k input tokens
```

If a budget is exceeded, the runtime must compact lower-priority fields before making the call.

Budget evaluation must distinguish:

- `actual_outbound_tokens`: estimate for the payload that will actually be sent
- `compact_candidate_tokens`: estimate for the compact candidate
- `estimated_tokens_saved`: `actual_full_tokens - compact_candidate_tokens`
- `estimated_saving_percent`: savings divided by `actual_full_tokens`
- `turn_estimated_outbound_tokens`: aggregate estimate across all DeepSeek calls made by the normal query

The runtime must apply ordered compaction stages until the task is within budget or no permitted compaction remains. Merely recording that a context exceeds budget does not satisfy this contract.

Budget enforcement is fail-open for planner and answer generation, because user-facing continuity is more important than strict cost control. If all allowed compaction steps have been applied and the context still exceeds budget, the runtime may proceed with the oversized context only after recording an overflow diagnostic with `budget_exceeded: true`, `budget_limit_tokens`, `estimated_input_tokens`, and `overflow_reason`.

Budget enforcement is fail-closed for evidence analysis when deterministic coverage is available. If evidence-analysis context still exceeds budget after compaction, skip the DeepSeek evidence-analysis call and use deterministic local evidence coverage. If deterministic coverage is unavailable and the call is explicitly required by configuration, cap evidence to the highest-priority items and record `budget_exceeded: true`.

The aggregate `normal query total` budget is observational during initial rollout. It must generate diagnostics and warnings but must not suppress planner or answer calls. It may become enforceable only after representative parity tests demonstrate that doing so does not reduce answer quality or workflow correctness.

Maximum truncation rules:

- planner and hybrid planner may truncate candidate descriptions, triggers, and summaries, but must preserve ids, titles, types, routing targets, active state ids, and retrieval filters
- evidence analysis may cap evidence to the top 8 items and snippets to 500 characters per item
- answer generation may cap knowledge evidence to the top 8 items, template evidence to the top 3 items, instruction resource context to selected active resources only, and snippets/context excerpts to 800 characters per item
- current `user_query`, `app_id`, active workflow/module/step identifiers, retrieval filters, and citation identity fields must never be truncated away

## 5. Planner Context Contract

Planner context may send:

- `user_query`
- `turn_input_type`
- compact chat summary plus the last 4 chat turns
- `app_id`
- app name/domain
- active workflow/session state summary
- intent overrides
- routing rules
- workflow/module/step candidates
- retrieval defaults
- relevant resource bindings by id/title/role only

Planner compaction must preserve these logical structures under their existing keys:

- `config_json`: goals, step skeletons, style/safety rules needed for planning, retrieval rules, and task model-independent application policy
- `adapter_json`: intent overrides, step skeleton mapping, retrieval defaults/mapping rules, and planner guardrails
- `template_registry`: intent categories, executable workflow/module/step candidates, routing rules, and resource binding identities required by the current turn
- `chat_history`: compact summary plus the last 4 turns

Planner context must not send by default:

- full `config_json`
- full `adapter_json`
- full `template_registry`
- full compiled instruction snapshot
- full document catalog
- old chat history beyond configured window

The planner prompt and compact context must be changed atomically. A prompt must not reference a field or shape absent from the outbound compact context.

Planner output must still include:

- `intentType`
- `confidence`
- `steps`
- `infoTypes`
- `retrievalPlan`
- `systemInstructionSummary`
- `normalizedQuery`
- `contextualQuery`

## 6. Hybrid Planner Context Contract

Hybrid planner context may send:

- app mission/objective summary
- active session state
- latest user message
- last assistant message
- candidate roles/workflows/modules/followups/steps
- routing rules
- module orchestration summary
- clarification gate summary

Candidate objects must be compacted to:

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

Hybrid planner context must not send:

- full procedure bodies
- full instruction block bodies
- full resource content
- full compiled runtime model

## 7. Evidence Analysis Context Contract

Evidence analysis context may send:

- `infoTypes`
- top evidence items with:
  - `doc_id`
  - `title`
  - `snippet`, capped
  - `score`
  - `metadata.info_type`
  - `metadata.info_types`
  - `metadata.tags`

Evidence analysis must not duplicate identical evidence under multiple keys.

If `compressed_evidence` and `knowledge_evidence` are identical, send one canonical field.

Preferred normal-query behavior:

- use deterministic local evidence coverage when metadata is sufficient
- call DeepSeek only when evidence coverage is ambiguous or explicitly configured

Evidence-analysis mode must be explicit:

```text
auto          = use deterministic coverage only when the sufficiency predicate passes
deterministic = always use deterministic coverage and never call DeepSeek
llm_required  = call DeepSeek whenever an evidence-analysis model is available; do not skip solely because deterministic coverage appears sufficient
```

If `llm_required` is configured but no evidence-analysis model is available, preserve the current deterministic fallback and record the fallback reason.

Metadata is sufficient for deterministic local evidence coverage when all of these are true:

- `planner_output.infoTypes` is empty, or every requested info type can be matched against at least one evidence item using `metadata.info_type`, `metadata.info_types`, `metadata.tags`, `title`, or capped `snippet`
- at least one evidence item is available when `planner_output.infoTypes` is non-empty
- each matched evidence item has a stable citation identity: `doc_id` or equivalent source id, plus `title` or filename
- no matched evidence item is below the configured minimum retrieval score when such a score is available; default minimum score is `0.2`

Evidence coverage is ambiguous and may call DeepSeek when any of these are true:

- requested info types use broad semantic labels that cannot be matched by direct metadata/text containment
- evidence items have missing or conflicting metadata
- the top evidence item has no usable snippet/title text
- multiple evidence items conflict on whether an info type is present
- configuration explicitly sets evidence analysis mode to LLM-required

The deterministic predicate must also reject local sufficiency when evidence items with usable citation identity materially conflict about a requested info type. Direct text containment alone is not enough to resolve a conflict.

## 8. Answer Generation Context Contract

Answer generation context may send:

- `user_query`
- compact chat summary plus the last 6 chat turns
- compact `planner_output`
- `evidence_analysis`
- top `knowledge_evidence` with citation fields
- selected instruction block summary
- selected instruction block text only when active
- instruction resource context only when explicitly loaded
- template context only when explicitly selected
- session upload evidence only when the turn references uploads
- compact style/safety/guardrail policy
- presentation policy
- visible outputs when they affect the answer

Answer fields are classified as follows:

Required and lossless:

- `user_query`
- citation identity fields for retained knowledge/session-upload evidence
- `evidence_analysis`
- active workflow/module/step ids
- safety rules and active guardrails
- `missing_infoTypes` and `previous_answer` during the safe-answer pass

Required but compactable without changing logical key names:

- `chat_history`
- `planner_output`
- `prepared_inputs`
- `instruction_evidence`
- `selected_instruction_block`
- `selected_instruction_block_text`
- `instruction_resource_load_plan`
- `instruction_resource_context`
- `template_resource_load_plan`
- `template_resource_context`
- `global_instruction_context`
- `knowledge_evidence`
- `template_evidence`
- `session_upload_evidence`
- `config_json`
- `adapter_json`
- `template_registry`
- relevant parts of `turn_execution_plan`, `turn_action_plan`, and `session_execution_state`
- `presentation_policy`, `visible_outputs`, and required execution artifacts

Conditionally removable:

- duplicate `compressed_evidence` when all retained evidence is represented by domain-specific evidence fields
- `hidden_outputs` only when no answer, validation, assembly, or artifact obligation depends on them
- session-upload evidence only when the eligible normal text turn does not reference an active upload and has no active session-upload ids

Compaction must preserve semantic units. Authoritative instruction text may be shortened only at section or rule boundaries, with the active procedure/step and its complete safety constraints retained. Blind character truncation of `selected_instruction_block_text` is prohibited.

Answer generation must not send by default:

- full `config_json`
- full `adapter_json`
- full `template_registry`
- full `turn_execution_plan`
- full `session_execution_state`
- hidden outputs unless required
- duplicate evidence collections

Final answer must still validate as:

```json
{
  "content": "...",
  "citations": [],
  "missing_infoTypes": []
}
```

## 9. Compaction Rules

Compaction priority:

1. Remove duplicate fields.
2. Replace full objects with task-specific projections.
3. Replace old chat history with rolling summary.
4. Cap evidence count.
5. Cap snippet length.
6. Strip unused metadata.
7. Summarize large instruction/template contexts.
8. Preserve selected active path and citation-bearing evidence last.

Never compact away:

- `app_id`
- current `user_query`
- active workflow/module/step identifiers
- retrieval filters
- citation fields for evidence used in answer
- explicit user-upload evidence when the user asks about the upload
- safety rules relevant to the answer

Chat summary storage rules:

- rolling summaries must be stored in `session_execution_state.chat_summary` or a backward-compatible nested runtime-state field owned by the session
- summaries must refresh after every assistant answer once the session exceeds the task chat-window size
- summaries must preserve active workflow id, active module id, active step id, unresolved user commitments, filled clarification slots, cited source ids from recent turns, and pending artifact/output obligations
- summaries must not replace `workflow_progress` or `session_execution_state`; they are compression aids only
- if summary generation fails, the runtime must keep the bounded recent-turn window and proceed without deleting existing state

The summary must contain actual conversation information, not a fixed marker. At minimum it must preserve:

- user decisions, preferences, and constraints
- material assistant conclusions and generated-output references
- unresolved user questions and commitments
- active workflow/module/step ids and titles
- filled clarification slots
- pending resource, artifact, and output obligations
- recent citation/source ids needed for follow-up continuity

The summary must exist before any task drops history older than its retained window. Because planner retains 4 turns, summary refresh must occur no later than the point at which history first exceeds 4 turns. Summary refresh must include the just-completed user and assistant messages or receive them explicitly before persistence.

## 10. Diagnostics Contract

Each LLM task call should record:

```json
{
  "task": "...",
  "provider": "...",
  "model": "...",
  "context_mode": "full|compact",
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
  "compaction_applied": true,
  "compaction_reasons": []
}
```

Diagnostics must be internal or exposed through existing model diagnostics without breaking frontend payload compatibility.

The initial estimator is `chars_per_token:v1`: estimate tokens as `ceil(character_count / 4)` over the serialized messages and compact context JSON, including prompt text but excluding HTTP headers. A later tokenizer-specific estimator may replace it only if diagnostics continue to record `estimator_name` and `estimator_version`.

Per-turn diagnostics must also report call count and `turn_estimated_outbound_tokens`. Diagnostic mode must estimate both the actual full outbound context and the compact candidate while sending the full context.

## 11. Acceptance Criteria

A normal user query is considered optimized when:

- total DeepSeek input tokens are reduced by at least `40%` on representative sessions
- planner regression tests still pass
- answer schema validation still passes
- citations remain grounded in knowledge/session-upload evidence
- app isolation tests still pass
- Church Ministry and `與孩子一起成長` protected scenarios do not regress
- fallback behavior remains unchanged when DeepSeek is unavailable
- upload-analysis and exec-turn parity tests prove that optimization is bypassed
- full and compact modes produce equivalent planner path, selected resources, answer schema, citation validity, and persisted workflow state on representative fixtures
- diagnostic measurements use the actual outbound payload and demonstrate at least `40%` estimated input-token reduction for the representative fixture set

## 12. Expected Savings

Target savings per normal user query:

```text
minimum acceptable: 30%
expected:           45-70%
high-complexity app: 70%+
```

Largest expected savings:

1. answer-generation context compaction
2. evidence-analysis LLM removal or compaction
3. planner context projection
