# Compiled Instruction and Query Planner Runtime Design

**Status:** Current design

**Date:** 2026-09-06

**Normative contract:** `docs/compiled-instruction-understanding-query-planner-runtime-contract.md`

## Scope

This design records how `ragenius_app_skeleton` implements the canonical compiled-instruction and query-planner contract without replacing existing compatibility paths.

## Architecture

The runtime uses a snapshot-first pipeline:

1. `instruction_understanding_service.py` compiles authored Markdown into canonical hybrid service blocks, procedures, steps, routing rules, module orchestration, and resource ownership.
2. `load_template_registry.py` loads the active snapshot and creates compatibility projections without changing canonical ownership.
3. `planner.py` combines the current user turn, persisted session state, and bounded compiled candidates. The hybrid LLM may select among supplied targets, but deterministic code validates identity, reachability, progression, and resource scope.
4. `persist_run.py` and chat repositories persist the selected turn and current session state.
5. Backend response shaping and the frontend project the persisted state rather than inferring workflow state from answer text.

## Compiler Design

### Heading and execution-shape normalization

Normalization recognizes bilingual and mixed-format headings through semantic role markers, then grounds them in the current instruction tree. A module-orchestration heading is retained as orchestration only when its body contains orchestration semantics. Numbered child headings become steps only under an executable parent procedure.

This prevents procedure labels such as `按步就班法` from becoming phantom modules while allowing explicit application-local structures such as `模組調度規則_module_orchestration`.

Support-module numbered content is narrowed by procedural labels. When a module
contains both a numbered reference taxonomy and a labeled list such as
`使用原則`, only the labeled list is converted into executable procedure steps;
the full section remains available as module guidance. This avoids duplicate
step identities when numbering restarts and prevents reference categories from
appearing as sequential GUI steps.

### Canonical target registry

Compiler normalization builds one app-local registry of executable targets. Routing aliases, role mappings, procedure owners, and module references resolve through that registry before publication. Compatibility aliases remain boundary inputs, not persisted runtime identities.

### Resource ownership

Step resources are represented on canonical procedure steps. The runtime distinguishes:

- mapped procedure with a resource-bearing active step
- mapped procedure with an intentionally resource-free active step
- legacy/unmapped procedure requiring module fallback
- bundled entry step requiring bundled resources

This distinction is preserved into the compatibility runtime model.

## Planner Design

### Hybrid decision boundary

The hybrid planner receives a compact candidate packet and returns semantic intent plus target ids. It does not create executable identities or resources. Deterministic validation resolves the selected target and rejects invalid cross-app, cross-procedure, or unreachable selections.

An explicit valid `target_step_id` selects its owning service block even when prior session state points to an older module. The module index is derived from the validated queue rather than reset.

The same call may also return an optional semantic-scope classification. This
is deliberately advisory: deterministic code activates the existing general
out-of-scope route only for a coherent `out_of_scope` result at or above `0.85`
confidence. Continuations, step advancement, refinements, option selection,
uploads, attachments, and decisions containing an application target cannot
take that route. Missing or unusable scope output is a no-op, preserving older
providers and persisted sessions.

An activated general route bypasses application retrieval and application
workflow selection, then uses the existing direct answer path for general model
knowledge. The decision is stored in graph state and persisted diagnostics so
operators can distinguish classification from route activation without adding
another model invocation.

The active behavior completed representative manual acceptance testing on
2026-09-06 and remains enabled in the hybrid-planner path.

### Active versus planned state

The planner separates:

- active service block and active step for the current turn
- queued modules and next-action candidates for future turns
- activated follow-up modules that have passed their gates

Binding matching uses active state. Queue membership alone never activates a current-turn binding.

### Resource planning

When a procedure has step resource mappings, the active step is authoritative even when its own mapping is empty. Module binding expansion is used only for legacy procedures without any step mappings. Explicit active follow-up modules retain their separate loading path.

The final turn plan canonicalizes each request through the runtime resource catalog and deduplicates by `(resource_role, canonical_resource_identity)`. Provenance and required flags are merged into the retained request.

## State and Persistence Design

Hybrid decision fields are declared in `GraphState` so LangGraph preserves them. Session state is reconciled before persistence so service block, step, support module, and module index describe one path.

Turn inspection uses persisted turn summaries. This prevents later session progression from rewriting the state displayed for earlier turns.

## Compatibility Strategy

Compatibility is fail-narrow:

- Existing snapshots remain readable.
- Module-only resource definitions continue to load when no step mapping exists.
- Commands, artifact gates, session uploads, and follow-up modules retain their specialized paths.
- A compatibility path cannot broaden a valid active compiled step.

## Failure Handling

- Invalid hybrid output falls back to a validated deterministic or legacy choice.
- Invalid snapshot identity is repaired through known aliases when unambiguous; otherwise the runtime uses its documented safe fallback.
- Missing optional resources do not activate unrelated files.
- Planner or answer provider failure must remain observable in diagnostics and must not corrupt persisted workflow state.

## Verification

Changes are accepted only after focused compiler/planner tests and cross-boundary suites pass. Real-session checks should verify state, loaded resource filenames, raw resource requests, and GUI projection for all four supported application patterns.

| Application | Protected runtime pattern | Required acceptance signal |
| --- | --- | --- |
| Bible Tutor | rule-routed study modules with step resources | correct module/step and only active-step resources |
| Church Ministry Prompt Designer | clarification, core workflow, and gated follow-up optimization | content, persisted state, and GUI transition together |
| GPT Application Design Assistant | app-local module orchestration and ordered support modules | section-owned module identity, correct step, no future-module resources |
| 與孩子一起成長 | role/logic routing with optional executable paths | no forced workflow shape and no cross-app orchestration behavior |
