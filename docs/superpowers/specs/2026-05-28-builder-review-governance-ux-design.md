# Builder Review/Governance UX Design

## Purpose

Add a minimal review/governance panel to the existing Builder skill detail page so operators can inspect the inferred executable contract before publishing a skill version.

This slice is about visibility and safer testing, not a full approval workflow.

## Scope

This design will add:

- a review panel on the existing skill detail page
- clear display of normalized contract metadata for each skill version
- clear risk labeling for normalized skills
- explicit visibility into what the execution subsystem will run

This design will not add:

- a separate review page
- editable workflow/schema panels
- approve/reject workflow states
- new persistence schema for governance
- execution-subsystem changes

## Goals

- make inferred contracts visible before publish
- help operators catch normalization mistakes before runtime execution
- make risky skills easy to distinguish from safe ones
- improve manual acceptance testing for Builder-normalized skills

## Non-Goals

- no contract editing UI yet
- no multi-step reviewer workflow yet
- no role-based approval model yet
- no runtime policy redesign

## Why This Is The Right Next Step

The current system can now normalize and execute:

- safe read/admin skills
- bounded mutation skills
- Gmail MCP read/write skills

That means the next practical risk is no longer “can the runtime execute?” It is “did Builder infer the right executable contract?” The fastest way to improve confidence is to make the inferred contract visible at the Builder control point before publish.

## User Experience

### Where it lives

The review/governance panel should be added to the existing skill detail page:

- `ragenius_builder/flask_scaffold/templates/skill_detail.html`

This keeps review close to:

- imported skill metadata
- version list
- publish action
- app bindings

### What it shows

For the currently displayed version, show:

- `state`
- `policy_class`
- `auto_finalize`
- `template_family`
- `required_tools`
- `required_permissions`
- input schema preview
- output schema preview
- workflow preview

### Risk display

Display a visible contract risk badge:

- `safe_read`
- `review_required`
- `unsupported`

Recommended behavior:

- `safe_read`
  - calm/neutral styling
  - text indicating the contract is eligible for low-risk publish behavior
- `review_required`
  - stronger warning styling
  - text indicating the contract contains mutation, external write, or provider-backed behavior requiring explicit review
- `unsupported`
  - blocked/error styling
  - text indicating the uploaded skill is descriptive only or not executable in the current system

### Publish guidance

If the version is `review_required`, show an explanatory note such as:

- this version publishes an executable contract
- execution may still pause at runtime for confirmation on write-capable steps
- review tools, permissions, schemas, and workflow carefully before publish

If the version is `safe_read`, show a lighter guidance note that the normalized contract is low-risk and read-oriented.

If the version is `unsupported`, publish should remain blocked by the existing underlying state/rules and the panel should make clear that no supported executable contract exists.

## Data Model

This design should reuse existing version metadata instead of inventing new persistence.

Expected contract data already lives in version metadata from Builder normalization:

- `template_family`
- `policy_class`
- `required_tools`
- `required_permissions`
- `input_schema`
- `output_schema`
- `workflow_definition`
- `auto_finalize`

The detail route should load and pass this metadata into the template in a structured way rather than making the template parse raw JSON ad hoc.

## Backend Changes

### Route shaping

Update the existing skill detail route in:

- `ragenius_builder/flask_scaffold/app.py`

to prepare a review-ready version view model for each version or for the selected/latest version.

Recommended view model fields:

- `version_id`
- `version`
- `state`
- `policy_class`
- `risk_label`
- `auto_finalize`
- `template_family`
- `required_tools`
- `required_permissions`
- `input_schema_pretty`
- `output_schema_pretty`
- `workflow_pretty`

Pretty-print JSON on the server side so the template can stay simple.

### No storage redesign

Do not redesign `storage.py` for this slice.

Only reuse the metadata already persisted for normalized skill versions.

## Frontend/Template Changes

### Layout

Add a contract review section to `skill_detail.html`, ideally near the version/publish controls.

Suggested section order:

1. version summary
2. contract risk badge and review note
3. required tools
4. required permissions
5. input schema
6. output schema
7. workflow preview

### Rendering style

Use:

- short summary rows for scalar metadata
- simple flat lists for tools and permissions
- `<pre>` blocks for schema/workflow JSON previews

Do not overdesign this page. The value is clarity, not visual flourish.

### Empty states

If a version has no normalized contract metadata:

- show `No normalized executable contract available`

If the version is unsupported:

- make the unsupported state explicit rather than rendering empty boxes

## Testing Strategy

### Builder route tests

Add tests covering:

- normalized `safe_read` skill detail page shows risk label and required tools
- normalized `review_required` skill detail page shows risk label and required permissions
- Gmail or mutation skill detail page renders workflow/service/tool preview
- unsupported skill detail page renders the unsupported message

### Manual acceptance cases

Use the Builder UI to inspect:

- file inventory skill
- mutation skill
- Gmail read skill
- Gmail draft/direct-send skill

Expected outcome:

- safe read is visibly low-risk
- write-capable or Gmail write skills are visibly review-required
- tools/permissions/workflow match the inferred contract

## Acceptance Criteria

This slice is complete when:

- the skill detail page shows normalized contract metadata for imported skills
- the page clearly distinguishes `safe_read`, `review_required`, and `unsupported`
- operators can inspect required tools, permissions, schemas, and workflow before publish
- no new Builder approval workflow or DB redesign was introduced
- existing publish/bind/test flows still work

## Recommended Implementation Order

1. inspect current version metadata shape on the skill detail route
2. add a route-level review view model in `app.py`
3. add the contract review panel to `skill_detail.html`
4. add route/template tests
5. verify with one safe skill and one risky skill

## Recommendation

Stop after the minimal review panel for this slice.

The next Builder governance UX slice, if needed, should be:

- explicit reviewer actions
- publish warnings/acknowledgements
- eventually editable draft contract review
