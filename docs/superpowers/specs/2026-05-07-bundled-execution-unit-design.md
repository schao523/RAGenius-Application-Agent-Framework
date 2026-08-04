# Bundled Execution Unit Design

## Purpose

Extend the current immediate-step runtime contract with a generic bundled execution mode.

This is needed for applications where one user turn should execute a series of internal instruction steps as one unit after the required inputs are complete.

Examples:
- Church Ministry Prompt Designer
- GPT Application Design Assistant
- other generation/configuration modules that describe internal multi-step execution without user checkpoints between each step

This design does **not** replace immediate-step support.
It adds a higher-level execution mode on top of it.

## Problem

The current runtime is strongest when a procedure behaves like:
- select one step
- bind that step's resources
- ask or answer
- wait for user
- continue next turn

That works well for:
- Bible Tutor
- parenting coaching checkpoints
- clarification-heavy workflows

It is weaker for procedures like Church Ministry after enough inputs are collected.
Those procedures need:
- one explicit workflow/checkpoint selection
- then several internal steps executed together in one turn
- with all relevant `.md` resources loaded in one shot

Current symptoms:
- workflow can be selected correctly
- but no single immediate step is a good runtime unit
- resource loading stalls because it depends on one active step
- routing/output/validation resources are not loaded together when they should be

## Relationship To Immediate Steps Enhancements

Immediate-step enhancements already provide:
- workflow identity
- step identity
- step provenance
- support-module provenance
- session continuity across turns

Bundled execution should build on that.

### Immediate step role
Immediate steps remain the right abstraction for:
- user-facing checkpoints
- clarification steps
- wait-for-user boundaries
- follow-up choices

### Bundled execution role
Bundled execution adds a new behavior for some steps:
- when this step is reached, the runtime should execute several internal steps as one unit
- resources should be merged across the bundled steps
- LLM performs the internal sequence in one turn
- runtime does not need to trace every substep transition

## Core Design

## 1. New execution mode on procedure steps

Extend `ProcedureStepDefinition` with:
- `execution_mode`
  - `interactive`
  - `bundled`
- `bundled_step_ids`
  - ordered list of step ids executed as one unit
- `bundled_resource_refs`
  - merged resources for the bundled unit
- `stop_after_completion`
  - whether runtime should stop after the bundled unit finishes

Default behavior:
- existing steps without explicit mode behave as `interactive`

## 2. Runtime state additions

Extend turn/session execution state with:
- `active_execution_mode`
- `active_bundled_step_ids`
- `bundled_execution_completed`
- `bundled_entry_step_id`

This keeps the current step/checkpoint identity while making bundled execution explicit.

## 3. Planner behavior

Planner should continue to select:
- primary workflow
- current checkpoint step

Then:
- if selected step is `interactive`
  - existing immediate-step behavior continues
- if selected step is `bundled`
  - planner merges bundled resources from all bundled steps
  - planner builds one bundled execution context
  - planner does not require substep-by-substep progression inside the turn

## 4. Retrieval behavior

For bundled execution steps:
- all bundled step resources should load together in one turn
- provenance should still identify:
  - bundled entry step
  - bundled member steps
  - support modules if any

Retrieval remains request-driven.
The main change is that bundled entry steps emit one merged request set instead of one immediate-step request set.

## 5. Answer-generation behavior

Answer generation receives:
- selected workflow
- selected bundled entry step
- bundled step list
- merged resource set
- explicit instruction to execute the bundled internal sequence as one unit

LLM is responsible for the internal orchestration of the bundled series.
Runtime is responsible for:
- selecting the unit
- loading the resources
- preserving checkpoint-level state

## Execution Model Categories

## A. Interactive checkpoint steps
Use for:
- clarification
- user choices
- pedagogical guided steps
- any step that must pause for user input

Behavior:
- select step
- optionally load step resources
- answer or ask
- persist step as active
- wait for user when appropriate

## B. Bundled execution steps
Use for:
- analysis + routing + output + validation sequences
- config/build/generation phases that are meant to run together
- prompt optimization/refinement units that are internally multi-step but externally one turn

Behavior:
- select bundled entry step
- load all bundled resources together
- let LLM execute internal steps as one unit
- persist bundled execution completion
- move to next interactive checkpoint if defined

## App Mapping

## Church Ministry Prompt Designer
Recommended mapping:
- Step 0: `interactive`
- Step 1: `interactive`
- Step 2: `bundled`
  - bundled members:
    - Step 2 core analysis
    - Step 3 routing
    - Step 4 prompt output
    - Step 5 quality check
- Step 6: `interactive`
- Step 7: edge handling stays normal/non-primary

Effect:
- clarification remains explicit
- prompt generation uses one bundled execution unit
- `template_library.md` / `dynamic_prompt_optimizer.md` and related output-rule resources can load together

## GPT Application Design Assistant
Recommended mapping:
- early requirement clarification remains `interactive`
- generation/configuration phases can be marked `bundled` where the instructions describe internal execution rather than user checkpoints
- testing/optimization follow-up may be either `interactive` or `bundled` depending on the module

## Bible Tutor
Recommended mapping:
- mostly remain `interactive`
- do not force bundled execution into pedagogical stepwise study

## Parsing Rules

Parser should infer bundled execution conservatively.

Strong signals for `bundled`:
- step/section describes several internal operations that are meant to run in order without user wait
- later steps in the same local chain are output/routing/validation steps
- no explicit wait-for-user checkpoint between the internal steps

Strong signals for `interactive`:
- explicit clarification question
- explicit ask/wait/continue behavior
- pedagogical questioning
- human-in-the-loop selection checkpoint

Parser should prefer correctness over aggressiveness.
If uncertain, default to `interactive`.

## Compatibility

This design must preserve:
- existing immediate-step workflows
- existing support-module provenance
- existing follow-up/continuation handling
- existing retrieval request contracts as much as possible

Bundled execution is additive.

## Expected Result

After this change:
- workflows still identify checkpoints explicitly
- generation-oriented apps can execute internal multi-step units in one turn
- resource loading can happen at bundled-unit granularity instead of one-step granularity
- runtime remains inspectable without tracking every internal substep transition

## Non-goals

This design does not attempt to:
- build a general arbitrary workflow engine
- trace every internal substep executed by the LLM
- replace interactive-step workflows with bundled execution globally
- remove the current immediate-step contract
