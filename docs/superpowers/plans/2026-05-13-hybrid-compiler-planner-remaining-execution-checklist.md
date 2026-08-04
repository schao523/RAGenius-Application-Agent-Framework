# Hybrid Compiler/Planner Remaining Execution Checklist

**Date:** 2026-05-13  
**Scope:** Remaining work after current implementation progress for hybrid instruction compiler + planner integration.
**Source plan:** [2026-05-13-hybrid-instruction-compiler-and-planner-prompt-implementation.md](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\docs\superpowers\plans\2026-05-13-hybrid-instruction-compiler-and-planner-prompt-implementation.md)

## Execution Order

1. Phase 4 completion: publish control
2. Phase 5 completion: planner hybrid active mode
3. Phase 6 completion: shadow comparison observability
4. Phase 7 completion: fixture-level validation and regression pass
5. Plan closure and status update

## Phase 4 Completion: Publish Control

- [ ] Add `POST /apps/{app_id}/instruction-understanding/publish` in backend route layer.
- [ ] Add service-layer publish helper that promotes only validated compiled/revised understanding.
- [ ] Add guardrails:
  - reject publish when no validated candidate exists
  - preserve last valid published record on publish failure
- [ ] Add tests:
  - publish success path
  - publish rejected when candidate invalid/missing
  - published pointer/status payload updates correctly

**Primary files**
- [main.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\main.py)
- [instruction_understanding_service.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\instruction_understanding_service.py)
- [test_instruction_understanding_service.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_instruction_understanding_service.py)
- [test_builder_chat_integration.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_builder_chat_integration.py)

**Exit criteria**
- Publish endpoint exists and is enforced.
- Active compiled-understanding switches only on explicit publish.

## Phase 5 Completion: Hybrid Planner Active Mode

- [ ] Implement planner-mode behavior:
  - `hybrid_shadow`: advisory only (existing)
  - `hybrid_active`: hybrid decision becomes routing source after validation
- [ ] Add hybrid decision validator in planner flow:
  - selected ids exist
  - workflow/module reachability
  - clarification gate legality
  - bundled step legality
- [ ] Add deterministic fallback path when hybrid decision invalid/unavailable.
- [ ] Limit legacy app-specific clarification heuristics to legacy mode only.
- [ ] Add tests for:
  - hybrid active valid decision path
  - hybrid active invalid decision fallback
  - mode isolation (legacy unchanged)

**Primary files**
- [planner.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\planner.py)
- [chat_service.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\chat_service.py)
- [test_planner_node.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_planner_node.py)

**Exit criteria**
- Hybrid routing works in active mode and fails closed to deterministic fallback.

## Phase 6 Completion: Observability And Shadow Diff

- [ ] Add compile-shadow comparison summary:
  - parser-only vs hybrid candidate deltas
  - validation warning/error rollups
- [ ] Add planner-shadow comparison summary:
  - legacy decision vs hybrid decision delta fields
  - reason/fallback indicators
- [ ] Expose comparison payloads in admin/runtime endpoints.
- [ ] Add tests that assert comparison payload structure and non-breaking defaults.

**Primary files**
- [instruction_understanding_service.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\instruction_understanding_service.py)
- [main.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\main.py)
- [planner.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\planner.py)
- [test_builder_chat_integration.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_builder_chat_integration.py)

**Exit criteria**
- Admin can inspect shadow differences directly from API payloads.

## Phase 7 Completion: Fixture Validation + Regression

- [ ] Add/finish fixture scenario coverage for:
  - Church Ministry Prompt Designer
  - GPT Application Design Assistant
  - Grow With Children
  - Bible Tutor
- [ ] Validate bundled execution resource loading and step progression for Church Ministry.
- [ ] Validate no-default-workflow routing for Grow With Children.
- [ ] Validate ordered sequential multi-module orchestration for GPT App Design Assistant.
- [ ] Run full backend unittest discovery and capture final pass evidence.

**Primary files**
- [test_load_template_registry.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_load_template_registry.py)
- [test_instruction_understanding_service.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_instruction_understanding_service.py)
- [test_planner_node.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_planner_node.py)
- [test_builder_chat_integration.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_builder_chat_integration.py)

**Exit criteria**
- Fixture tests cover all known gaps.
- Full backend discovery pass completes successfully.

## Closure

- [ ] Update source plan status from draft to in-progress/completed with completion notes.
- [ ] Record rollback strategy for hybrid active mode.
- [ ] Record known residual risks and follow-up backlog items.

## Suggested Verification Commands

```powershell
python -m unittest ragenius_app_skeleton.tests.test_instruction_understanding_service
python -m unittest ragenius_app_skeleton.tests.test_planner_node
python -m unittest ragenius_app_skeleton.tests.test_builder_chat_integration
python -m unittest discover ragenius_app_skeleton/tests
```

