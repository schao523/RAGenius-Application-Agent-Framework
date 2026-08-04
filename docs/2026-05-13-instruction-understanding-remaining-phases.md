# Instruction Understanding Remaining Phases

Date: 2026-05-13

## Current State

Completed:
- instruction-understanding persistence layer
- compiled/review/approval/revision record storage
- cache and invalidation plumbing
- read-only seeding behavior for builder routes
- repo reconstruction and cleanup for instruction-understanding services/repos
- compatibility import shims for repo-root test discovery
- cleanup refactor to reduce duplicated status/context building
- builder-route integration coverage for:
  - read-only seeding on missing compiled understanding
  - review route execution and persisted review payload
  - semantic compile flags surfaced from builder read-only route

Verification status:
- `python -m unittest discover ragenius_app_skeleton/tests`
- current result: `272` tests passing

Out of scope for this completed work:
- planner migration to semantic compiled understanding
- bundled execution behavior across real apps
- real app semantic remediation
- builder UI lifecycle completion
- real LLM acceptance validation

## Recommended Order

1. Phase 1: Planner migration to compiled semantic understanding
2. Phase 2: Bundled execution unit behavior
3. Phase 3: Real app remediation and semantic compiler hardening
4. Phase 4: Builder UI lifecycle completion
5. Phase 5: Real LLM verification and end-to-end acceptance

## Phase 1: Planner Migration

Goal:
- make planner decisions depend primarily on compiled semantic understanding instead of mixed raw-instruction heuristics

Tasks:
- define planner input contract from `hybrid_instruction_runtime_model`
- route planner through:
  - `primary_service_mode`
  - `default_workflow_id`
  - `interaction_logic_blocks`
  - `role_profiles`
  - `routing_rules`
  - `clarification_gate_rules`
  - `instruction_service_blocks`
  - `instruction_procedures`
  - `procedure_steps`
  - `module_orchestration`
- preserve fallback behavior when semantic compile is absent or invalid
- remove duplicated ad hoc inference where compiled semantics already provide the decision
- add planner tests for:
  - single default workflow apps
  - intent-routed multi-workflow apps
  - no-default workflow apps
  - role-based routing
  - clarification gate entry/exit

Exit criteria:
- planner uses compiled semantic understanding as primary source
- legacy heuristics are fallback-only
- planner tests cover workflow routing and clarification gates

## Phase 2: Bundled Execution Unit

Goal:
- support workflows/modules whose steps should execute as one bundled LLM unit with all required `.md` resources loaded together

Tasks:
- formalize bundled execution metadata in compiled understanding
- ensure planner can emit bundled execution step decisions
- load all required `.md` resources at bundle start rather than step-by-step
- keep active step labels consistent with bundle semantics
- define UI/runtime semantics for:
  - current step
  - next step
  - bundle completion
- make behavior generic across apps, not Church Ministry-specific
- add tests for:
  - bundled generation path
  - resource loading count/source presence
  - active-step transitions during bundled execution

Exit criteria:
- bundled generation loads expected resources
- runtime step/status display matches bundled semantics
- behavior is generic across multiple app instruction styles

## Phase 3: Real App Remediation And Compiler Hardening

Goal:
- make the semantic compiler robust enough for real natural-language application instructions

Tasks:
- revise semantic compiler contract to fully support:
  - top-level global interaction logic
  - multiple roles
  - role-specific tone/style
  - intent-routed role selection
  - role-to-workflow mapping
  - ordered multi-module composition
  - apps with no default workflow
- strengthen validation for:
  - false trigger extraction
  - phantom resources
  - empty step bodies
  - prose-only procedures that need execution structure
  - default workflow misclassification
- recompile and inspect these real apps:
  - Church Ministry Prompt Designer
  - 與孩子一起成長
  - GPT Application Design Assistant
- compare compiler output with accepted review findings
- iterate prompt/validation until compiled understanding is acceptable for those apps

Exit criteria:
- the three known problematic apps compile into acceptable semantic understanding
- known review findings are either resolved or intentionally preserved with rationale

## Phase 4: Builder UI Lifecycle Completion

Goal:
- expose the full instruction-understanding lifecycle in builder UI

Tasks:
- surface:
  - compiled understanding summary
  - review findings
  - review summary markdown
  - approval state
  - revision state
  - cache status
  - invalidation reasons
- add actions for:
  - recompile
  - review
  - approve findings
  - revise
- add compare/diff view between active compiled understanding and revised draft
- ensure read-only builder panels do not trigger recompute when compiled understanding already exists

Exit criteria:
- builder UI can drive compile/review/approve/revise lifecycle without backend-only inspection

## Phase 5: Real LLM Verification And End-To-End Acceptance

Goal:
- verify that actual configured task models work reliably for compile/review/revise flows and produce usable app behavior

Tasks:
- test configured task models for:
  - `instruction_understanding_compile`
  - `instruction_understanding_review`
  - `instruction_understanding_revision`
- verify provider-specific tool-calling behavior and JSON compliance
- validate fallback behavior when no model or API key is present
- run end-to-end starter-question acceptance checks on representative apps
- confirm:
  - correct workflow selection
  - correct clarification behavior
  - correct bundled or interactive execution mode
  - correct resource loading
  - correct final prompt/output generation

Exit criteria:
- real configured LLMs successfully support the instruction-understanding lifecycle
- representative apps behave correctly under real end-to-end sessions

## Phase Dependencies

Phase 1 depends on:
- completed persistence and compiled understanding storage

Phase 2 depends on:
- planner being able to emit semantic execution decisions

Phase 3 depends on:
- stable planner and bundled execution contracts

Phase 4 depends on:
- backend lifecycle and status contracts being stable

Phase 5 depends on:
- phases 1 through 4 being stable enough for real-app acceptance testing

## Immediate Next Task

Recommended immediate execution target:
- start Phase 1 with a concrete planner contract implementation task:
  - define the exact planner input payload derived from `hybrid_instruction_runtime_model`
  - define planner output decisions for:
    - enter clarification
    - select workflow
    - select role
    - execute bundled unit
    - execute interactive step
    - compose ordered multi-module path
