# Executable Target Registry Unification Plan

## Goal

Resolve the remaining instruction-understanding inconsistencies for:

- `與孩子一起成長`
- `Bible Tutor`

without affecting:

- `Church Ministry`
- `GPT Application Design Assistant`

## Problem

The current compiler still allows multiple identities for the same executable target:

- route-facing ids
- executable service-block ids
- title aliases
- underscore aliases
- semantic English shorthand ids

This causes recurring invalidation and incomplete runtime models.

## Target Contract

1. Interaction logic is non-executable.
2. Workflows and support modules may be executable.
3. Executable route targets must resolve to existing executable service-block ids.
4. One executable concept must not have two canonical ids inside one compiled model.

## Implementation Order

1. Add compile-level regressions for:
   - `與孩子一起成長` reclassification into `intent_routed_interaction_logic`
   - `Bible Tutor` executable module/procedure/step synthesis from deterministic contract
2. Add/update validator regressions for route-target unification.
3. Implement one executable-target registry / reuse path in `instruction_understanding_service.py`.
4. Reclassify only clearly logic-first semantic shapes.
5. Seed executable service blocks/procedures/steps for logic-first apps when semantic output omits them.
6. Normalize nested interaction-logic executable references.
7. Run compile, planner/runtime, and targeted integration verification.

## Exit Criteria

1. `與孩子一起成長` compiles as `intent_routed_interaction_logic`.
2. `Bible Tutor` active hybrid runtime model contains executable support modules, procedures, and steps.
3. Route-facing ids and executable service-block ids are unified for both apps.
4. Church Ministry and GPT Application Design Assistant retain existing support-module ids and planner behavior.
