# Hybrid Instruction Compiler And Planner Prompt Implementation Plan

**Date:** 2026-05-13  
**Status:** Draft implementation plan  
**Scope:** Implement the revised hybrid application-instruction compiler, review-approve-revise loop, and planner prompt contract in `ragenius_app_skeleton` while preserving current production behavior behind controlled rollout.

## Source Specs

This plan implements:
- [2026-05-08-llm-assisted-application-instruction-compiler-design.md](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\docs\superpowers\specs\2026-05-08-llm-assisted-application-instruction-compiler-design.md)
- [2026-05-09-planner-prompt-contract-for-hybrid-application-instruction-understanding.md](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\docs\superpowers\specs\2026-05-09-planner-prompt-contract-for-hybrid-application-instruction-understanding.md)

## Goal

Move from the current parser-dominant application-instruction understanding pipeline to a hybrid pipeline where:
- deterministic parser extracts structure
- LLM compiles semantic application understanding under schema
- deterministic validator normalizes and publishes compiled understanding
- independent LLM review critiques compiled understanding
- human-approved findings can drive revision
- planner consumes the published compiled understanding through a strict prompt contract

## Constraints

Must preserve:
- file-backed instruction storage
- app isolation by `app_id`
- no retrieval-core redesign in `rag_subsystem`
- backward compatibility for existing apps during rollout
- production safety via staged opt-in and fallback

## Out Of Scope

This plan does not include:
- Builder UI authoring for manual compiled-JSON editing
- generalized parallel module orchestration
- automatic publish without validation
- replacing answer-generation prompts in this phase

## Implementation Strategy

Implement in seven phases:
1. schema and runtime-model foundation
2. deterministic structural candidate extraction
3. semantic compiler and validator
4. review / approve / revise persistence and APIs
5. planner prompt integration
6. rollout controls and fallback behavior
7. verification and app-fixture validation

## Phase 1: Schema And Runtime-Model Foundation

### Objective
Add the new compiled-understanding schema and planner-facing runtime fields without changing live behavior yet.

### Tasks
1. Extend runtime models for compiled understanding
- add models for:
  - `GlobalAppContract`
  - `InteractionLogicBlock`
  - `RoleProfile`
  - `RoutingRule`
  - `ModuleOrchestration`
  - `ClarificationGateRule`
  - revised `ServiceBlock`
  - revised `ProcedureDefinition`
  - revised `ProcedureStepDefinition`

2. Extend persistence record models
- add versioned record support for:
  - semantic compiler output candidate
  - normalized hybrid compiled understanding
  - approval session
  - revision candidate

3. Extend session/planner runtime state
- add fields for:
  - active role id
  - active module queue
  - current module index
  - selected routing rule id
  - clarification gate status snapshot

### Target files
- [runtime_models.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\runtime_models.py)
- [chat_repos.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\chat_repos.py)
- [instruction_understanding_service.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\instruction_understanding_service.py)

### Exit criteria
- models exist and validate
- no runtime behavior change yet
- tests cover serialization/deserialization of new contract types

## Phase 2: Deterministic Structural Candidate Extraction

### Objective
Refactor the existing parser so it produces a deterministic structural candidate graph suitable for the semantic compiler.

### Tasks
1. Keep heading-tree parser as canonical structural extractor
2. Add explicit structural candidate outputs:
- `section_candidates`
- `step_candidates`
- `resource_candidates`
- `rule_candidates`
- `trigger_candidates`
- `role_candidates`
- `interaction_logic_candidates`

3. Add safe extraction for explicit threshold/gate rules
- support cases like:
  - variable count thresholds
  - explicit IF/THEN routing statements

4. Preserve current parser outputs for backward compatibility during transition

### Target files
- [load_template_registry.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\load_template_registry.py)

### Exit criteria
- structural candidate graph is deterministic and persisted in compile pipeline
- current parser-only runtime still works unchanged
- tests cover candidate extraction from real fixture apps

## Phase 3: Semantic Compiler And Validator

### Objective
Implement LLM-assisted semantic compilation plus deterministic normalization/validation.

### Tasks
1. Add semantic compiler prompt builder
- serialize structural candidate graph into the compiler input packet
- include prior published understanding optionally for incremental compile

2. Add compiler LLM runtime entry
- new task key for semantic compilation
- strict JSON-only contract

3. Add validator/normalizer
- validate ids, references, roles, workflows, routing rules, module orchestration, clarification gates, and resource bindings
- normalize top-level contract into the canonical runtime shape

4. Support `no default workflow` apps explicitly
5. Support first-class `interaction_logic`
6. Support first-class `role_profile`
7. Support first-class `module_orchestration` with ordered sequential composition only
8. Downgrade unresolved resources to warnings rather than active runtime resources

### Target files
- [instruction_understanding_service.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\instruction_understanding_service.py)
- [llm_runtime.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\llm_runtime.py)
- [load_template_registry.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\load_template_registry.py)

### Exit criteria
- hybrid semantic compile candidate can be generated and validated
- published compiled understanding can be produced for opted-in apps
- current parser-only fallback remains available

## Phase 4: Review, Approve, Revise

### Objective
Extend the current advisory review flow into a controlled correction loop.

### Tasks
1. Extend independent review prompt
- review global contract, interaction logic, role profiles, routing rules, module orchestration, and clarification gates

2. Add approval record persistence
- store finding-by-finding decisions:
  - approve
  - reject
  - modify
  - manual_only

3. Add revision prompt builder
- use only approved findings
- preserve ids where possible
- revise only approved areas

4. Add revision validation pass
- revised candidate re-enters deterministic normalization

5. Add publish controls
- published active understanding switches only after validation success and explicit publish action

### Target files
- [instruction_understanding_service.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\instruction_understanding_service.py)
- [chat_repos.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\chat_repos.py)
- [main.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\main.py)

### Suggested API surfaces
- `GET /apps/{app_id}/instruction-understanding`
- `POST /apps/{app_id}/instruction-understanding/recompile`
- `POST /apps/{app_id}/instruction-understanding/review`
- `POST /apps/{app_id}/instruction-understanding/approve-findings`
- `POST /apps/{app_id}/instruction-understanding/revise`
- `POST /apps/{app_id}/instruction-understanding/publish`

### Exit criteria
- review findings can be approved selectively
- revision candidate can be produced from approved findings
- publish remains controlled and explicit

## Phase 5: Planner Prompt Integration

### Objective
Make planner consume published hybrid compiled understanding using the strict prompt contract, while keeping deterministic guardrails.

### Tasks
1. Add planner decision-packet builder
- build compact packet from:
  - global app contract
  - interaction logic
  - role profiles
  - routing rules
  - module orchestration
  - clarification gate rule
  - current session state
  - candidate workflows/modules/supplementary workflows/steps

2. Add planner LLM prompt builder
- system contract
- decision packet
- output schema

3. Add planner response validator
- validate selected ids, role compatibility, workflow reachability, module ordering, clarification completion, bundled-step legality

4. Change planner routing model
- prefer compiled routing rules over local heuristics
- support apps with no default workflow
- support role + workflow selection together
- support ordered sequential module orchestration
- support compiled clarification-gate rules instead of app-specific field heuristics

5. Keep deterministic bypass path
- explicit command/stop/continue/hard runtime cases skip LLM routing

### Target files
- [planner.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\planner.py)
- [llm_runtime.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\llm_runtime.py)
- [runtime_models.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\runtime_models.py)

### Exit criteria
- planner uses compiled contract for routing on opted-in apps
- planner no longer relies on hardcoded app-specific clarification heuristics in opted-in mode
- planner still falls back safely when LLM output fails validation

## Phase 6: Rollout Controls And Fallback

### Objective
Introduce safe opt-in rollout and regression protection.

### Tasks
1. Add per-app compiler mode switch
- `parser_only`
- `hybrid_shadow`
- `hybrid_active`

2. Add planner mode switch
- `legacy_planner`
- `hybrid_planner_shadow`
- `hybrid_planner_active`

3. Shadow logging for comparison
- compare parser-only vs hybrid compiled understanding
- compare legacy planner vs hybrid planner decisions

4. Fallback behavior
- if semantic compile fails, keep last valid published understanding
- if planner LLM output fails validation, fall back to deterministic safe choice

### Exit criteria
- hybrid pipeline can run safely beside current behavior
- rollout can be enabled app by app

## Phase 7: Verification And App-Fixture Validation

### Objective
Verify correctness against the apps that exposed the current design gaps.

### Required fixture apps
1. Church Ministry Prompt Designer
2. GPT Application Design Assistant
3. Grow With Children
4. Bible Tutor

### Verification scenarios

#### Church Ministry Prompt Designer
- compile clarification gate rule from instructions
- compile bundled generation path correctly
- planner routes starter -> clarification -> bundled generation via compiled gate
- `.md` routing resources load through compiled bundled step path

#### GPT Application Design Assistant
- compile semantic module orchestration
- starter-independent module activation works
- ordered sequential module sequence can be selected by planner
- support vs follow-up modules remain distinct

#### Grow With Children
- compile no-default-workflow intent-routed model correctly
- compile role profiles and tone/style associations
- routing rule chooses among three peer workflows
- Bible-study supplementary workflow remains supplementary

#### Bible Tutor
- compile global interaction logic distinctly from workflow steps
- study mode routes into inductive workflow
- support modules remain supportive, not primary workflows

### Test suites to add or extend
- [test_load_template_registry.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_load_template_registry.py)
- [test_instruction_understanding_service.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_instruction_understanding_service.py)
- [test_chat_repo_persistence.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_chat_repo_persistence.py)
- [test_planner_node.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_planner_node.py)
- [test_chat_pipeline_runtime_contracts.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_chat_pipeline_runtime_contracts.py)
- [test_builder_chat_integration.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_builder_chat_integration.py)

### Exit criteria
- hybrid compile and hybrid planner pass fixture scenarios
- full backend discovery passes
- no regression in parser-only mode

## Recommended Execution Order

1. Phase 1
2. Phase 2
3. Phase 3
4. Phase 4
5. Phase 6 compiler-mode controls
6. Phase 5 planner integration in shadow mode
7. Phase 7 verification
8. planner activation for selected apps

Planner integration is intentionally after compile/review/publish foundation so planner consumes a stable published contract instead of a moving target.

## Risks

1. semantic compiler output may drift if prompt/schema are too loose
2. planner could become slower if decision packets are too large
3. review and revision may create record/provenance complexity
4. shadow-mode comparisons may reveal app-specific ambiguities that require schema expansion

## Mitigations

1. keep strict JSON schema and deterministic normalization
2. keep planner packets compact and candidate-bounded
3. keep explicit publish control
4. preserve parser-only fallback and per-app rollout switches

## Success Criteria

This implementation plan is successful when:
- hybrid compiled understanding can represent global contract, interaction logic, roles, routing, clarification gates, and ordered module orchestration
- review-approve-revise works end to end under explicit publish control
- planner uses published compiled understanding rather than raw instruction reinterpretation
- apps with no default workflow route correctly
- ordered sequential module composition works for GPT Application Design Assistant
- Church Ministry no longer depends on app-specific clarification heuristics
- parser-only fallback remains available until hybrid mode is proven stable
