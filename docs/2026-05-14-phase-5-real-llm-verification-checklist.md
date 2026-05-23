# Phase 5 Real LLM Verification Checklist

## Goal
Verify the instruction-understanding compiler/reviewer/revision path and representative end-user app behavior with real configured task models, not only test doubles.

## Current Environment Finding
As of 2026-05-14, the live Builder SQLite data contains applications, instructions, settings, and documents, but none of the app settings rows contain `config_settings.meta.llm_settings`.

Implication:
- `maybe_build_task_callable(...)` resolves to `None` for:
  - `instruction_understanding_compile`
  - `instruction_understanding_review`
  - `instruction_understanding_revision`
- real LLM-assisted Phase 5 execution is blocked until per-app LLM settings and matching provider API secrets are configured.

## Preconditions
1. Add per-app LLM task settings under `config_settings.meta.llm_settings`.
2. Provide provider secrets in the runtime environment.
3. Confirm the target app uses `instruction_understanding_mode = hybrid_shadow` or `hybrid_active`.
4. Confirm the target app uses a planner mode compatible with semantic runtime validation.

## Required LLM Settings Contract
Minimum shape:

```json
{
  "meta": {
    "llm_settings": {
      "provider": "openai",
      "models": {
        "planner": "gpt-4.1",
        "answer_generation": "gpt-4.1",
        "instruction_understanding_compile": "gpt-4.1",
        "instruction_understanding_review": "gpt-4.1",
        "instruction_understanding_revision": "gpt-4.1"
      },
      "temperature": {
        "planner": 0.2,
        "answer_generation": 0.2,
        "instruction_understanding_compile": 0.2,
        "instruction_understanding_review": 0.2,
        "instruction_understanding_revision": 0.2
      }
    }
  }
}
```

Accepted provider secret sources:
- `OPENAI_API_KEY`
- `DEEPSEEK_API_KEY`
- `RAGENIUS_LLM_API_KEY`
- optional `RAGENIUS_LLM_BASE_URL`

## Execution Order
1. Church Ministry Prompt Designer
2. ???????
3. GPT Application Design Assistant
4. Bible Tutor ????? 4.0

## Slice A: Church Ministry Compiler/Reviewer Verification
1. Configure `llm_settings` for app `053eb2ca-54e0-49bf-b7dd-604c9608489e`.
2. Trigger instruction-understanding recompile.
3. Verify compiled understanding contains:
   - default workflow `Interaction Logic & Execution Flow`
   - clarification step before bundled generation
   - bundled generation unit with expected `.md` resources
4. Trigger instruction-understanding review.
5. Verify review output is advisory and persisted.
6. If needed, approve selected findings and trigger revision.
7. Verify revised understanding preserves IDs where appropriate.

## Slice B: Church Ministry End-to-End Acceptance
1. Start a fresh chat session.
2. Send starter query:
   - `??????????????????????`
3. Verify the planner starts in clarification when threshold is not yet satisfied.
4. Answer the clarification turn.
5. Verify planner advances into the bundled generation step.
6. Verify runtime source summary exposes bundled `.md` resources.
7. Verify `bundled_execution` payload is coherent with the displayed active step.
8. Verify final prompt/output generation uses the bundled resource context.

## Slice C: ??????? Acceptance
1. Configure `llm_settings` for app `0ea6ac80-c96d-4a65-b7e7-645f3ee848e9`.
2. Recompile understanding with the real compiler.
3. Verify there is no default workflow.
4. Verify review catches misclassification if the compiler invents one.
5. Run three representative prompts:
   - simple advice
   - stepwise guidance
   - deep analysis
6. Verify routing chooses the correct workflow/role/module path per prompt.

## Slice D: GPT Application Design Assistant Acceptance
1. Configure `llm_settings` for app `dd494ba5-face-4eaf-95d1-a55cb9f80c78`.
2. Recompile understanding with the real compiler.
3. Verify ordered sequential multi-module orchestration is preserved.
4. Run a prompt that should map to multiple modules.
5. Verify ordered module execution is reflected in planner state and output.

## Slice E: Bible Tutor Acceptance
1. Configure `llm_settings` for app `2302c77b-3d82-4650-bd15-e0ff9c0faab7`.
2. Recompile understanding with the real compiler.
3. Run a representative Bible teaching prompt.
4. Verify workflow selection, retrieval/resource loading, and final output stay within app scope.

## Evidence To Capture
- compiled understanding detail payload
- review payload
- revision payload if used
- chat turn raw/runtime payloads
- retrieval summary
- bundled execution payload
- final generated answer or prompt package

## Exit Criteria
1. At least one real app completes compile + review with a real task model.
2. Church Ministry completes a clarification-to-bundled-generation chat flow correctly.
3. At least one intent-routed app completes a routing-sensitive acceptance flow.
4. Any semantic mismatches are recorded as concrete defects, not assumptions.

## Current Status
Blocked by missing per-app `llm_settings` in live Builder settings data.
