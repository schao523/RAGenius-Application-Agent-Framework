# Normal User Query Token Optimization Verification

Date: 2026-07-15

## Scope

Implemented only in `ragenius_app_skeleton` and the approved documentation. No retrieval implementation, Builder workflow, legacy `ragenius_app` runtime, frontend contract, or execution subsystem code was changed by this implementation.

Compact mode remains opt-in:

```text
RAGENIUS_LLM_CONTEXT_OPTIMIZATION=0
RAGENIUS_LLM_CONTEXT_OPTIMIZATION_MODE=off
RAGENIUS_LLM_EVIDENCE_ANALYSIS_MODE=auto
```

## Functional Evidence

Implemented and tested:

- normal-query eligibility requires `text_query`, no pending upload analysis, and no upload event ids
- upload and exec turns cannot select compact context
- diagnostic mode measures full and compact payloads while sending full context
- compact mode preserves prompt-visible logical keys
- planner, hybrid planner, evidence analysis, answer generation, and safe-answer calls use common accounting
- evidence modes support `auto`, `deterministic`, and `llm_required`
- rolling summaries contain actual conversation and workflow state and include the current completed turn
- task budgets and the observational 25k aggregate budget emit overflow diagnostics
- compact mode remains disabled by default

## Token Evidence

Estimator: `chars_per_token:v1`, calculated as `ceil(serialized characters / 4)` over the exact system/user messages and normalized tool schemas.

Representative planner-plus-answer fixture:

```text
full estimate:       46,670 input tokens
compact estimate:    10,269 input tokens
estimated saving:    36,401 input tokens
estimated reduction: 78.0%
```

Per-call fixture results:

```text
planner: 13,402 -> 1,307 (90.25%)
answer:  33,268 -> 8,962 (73.06%)
```

The evidence-analysis call was deterministically skipped because the fixture had sufficient, non-conflicting metadata with stable citation identity. These figures are executable test-fixture estimates, not live DeepSeek billing telemetry. Diagnostic mode should be used in representative real sessions before production compact-mode approval.

## Commands And Results

```powershell
python -m pytest ragenius_app_skeleton/tests/test_llm_context_optimization.py ragenius_app_skeleton/tests/test_llm_context_optimization_integration.py ragenius_app_skeleton/tests/test_llm_context_optimization_parity.py -q
```

Result: 25 passed.

The final focused regression set covering optimization, planner, evidence, answer, and persistence completed with 157 passed tests and 3 passed subtests.

```powershell
$env:RAGENIUS_LLM_CONTEXT_OPTIMIZATION='1'
$env:RAGENIUS_LLM_CONTEXT_OPTIMIZATION_MODE='compact'
python -m pytest ragenius_app_skeleton/tests/test_llm_context_optimization_integration.py ragenius_app_skeleton/tests/test_builder_chat_integration.py::BuilderChatIntegrationTests::test_session_upload_endpoint_and_chat_state_include_uploaded_artifact ragenius_app_skeleton/tests/test_retrieve_node.py -k "session_upload or llm_context_optimization" -q
```

Result: 9 passed, 28 deselected. Upload/session-upload behavior remained on full context.

```powershell
python -m pytest ragenius_app_skeleton/tests ragenius_app_skeleton/backend/tests -q
```

Result: 482 passed, 9 subtests passed, 6 failed in 326.66 seconds.

Five failures exactly matched the focused pre-change baseline. One additional full-suite failure was outside the focused baseline and concerns Builder runtime LLM metadata. None involved optimization tests or changed optimization behavior:

- `test_run_chat_pipeline_uses_runtime_resolved_llm_callables`
- `test_bible_tutor_first_observation_followup_keeps_step_context`
- `test_bible_tutor_passage_selection_turn_loads_observation_guide`
- `test_bible_tutor_starter_turn_uses_mode_block_only`
- `test_pipeline_resolves_builder_document_filename_for_instruction_step`
- `test_derives_schema_valid_config_and_adapter`

```powershell
python -m compileall -q ragenius_app_skeleton/backend/app ragenius_app_skeleton/workflows ragenius_app_skeleton/tests/test_llm_context_optimization.py ragenius_app_skeleton/tests/test_llm_context_optimization_integration.py ragenius_app_skeleton/tests/test_llm_context_optimization_parity.py
git diff --check
```

Result: clean, aside from repository line-ending warnings.

## Parity Outcomes

- Full and compact fixtures returned identical planner output.
- Full and compact fixtures returned identical evidence analysis.
- Full and compact fixtures returned identical final answer and citations.
- Full and compact fixtures preserved identical session execution state.
- Hybrid compact context retained the protected Church Ministry and `與孩子一起成長` candidate ids.
- Upload analysis retained full uploaded content and upload event identity even when compact mode was globally enabled.
- Normal text turns can retain explicitly active session-upload evidence through `active_session_upload_ids`.

## Known Limitations

- The workspace `.venv` lacks required backend dependencies, so verification used the configured system Python 3.14 environment.
- No paid/live DeepSeek request was made; production savings must be confirmed with diagnostic-mode telemetry.
- The existing six full-suite failures remain unresolved because they predate or are outside this implementation scope.
- Compact mode must not become the default until maintainers review real-session diagnostic data and protected workflow results.
