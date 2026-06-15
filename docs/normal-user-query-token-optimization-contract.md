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

## 5. Planner Context Contract

Planner context may send:

- `user_query`
- `turn_input_type`
- last N chat turns or compact chat summary
- `app_id`
- app name/domain
- active workflow/session state summary
- intent overrides
- routing rules
- workflow/module/step candidates
- retrieval defaults
- relevant resource bindings by id/title/role only

Planner context must not send by default:

- full `config_json`
- full `adapter_json`
- full `template_registry`
- full compiled instruction snapshot
- full document catalog
- old chat history beyond configured window

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

## 8. Answer Generation Context Contract

Answer generation context may send:

- `user_query`
- compact chat summary plus last N turns
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
  "top_level_keys": [],
  "evidence_count": 3,
  "chat_history_turn_count": 4,
  "compaction_applied": true,
  "compaction_reasons": []
}
```

Diagnostics must be internal or exposed through existing model diagnostics without breaking frontend payload compatibility.

## 11. Acceptance Criteria

A normal user query is considered optimized when:

- total DeepSeek input tokens are reduced by at least `40%` on representative sessions
- planner regression tests still pass
- answer schema validation still passes
- citations remain grounded in knowledge/session-upload evidence
- app isolation tests still pass
- Church Ministry and `與孩子一起成長` protected scenarios do not regress
- fallback behavior remains unchanged when DeepSeek is unavailable

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
