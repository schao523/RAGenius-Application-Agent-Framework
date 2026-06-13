# Phase 2 Design: Controlled Mutation Tools And Review-Gated Contracts

## Purpose

This spec defines Phase 2 of the safe Builder-authored skill system for RAGenius.

Phase 2 adds tightly bounded file mutation support for app administration and content workflows while preserving the same architectural boundaries established in Phase 1:

- Builder remains the control plane that normalizes and publishes explicit contracts
- `ragenius_execution_subsystem` remains the runtime executor
- `rag_subsystem` remains the only owner of retrieval and indexing logic

The focus of Phase 2 is not general local automation. It is controlled content mutation with explicit review, confirmation, and auditability.

## Problem Statement

Phase 1 can execute read-safe and artifact-safe contracts, but many real Builder-managed admin/content workflows require bounded edits:

- update markdown content
- patch a template or settings file
- apply a reviewed change to website content

Without mutation tools, the system can inspect and propose, but not complete these workflows end to end.

The gap is not just missing tool implementations. Mutation must also be constrained by:

- path policy
- contract shape
- Builder-side review rules
- runtime confirmation rules
- per-app isolation

## Goals

- Add `write_file` and `patch_file` as bounded local runtime tools
- Keep mutation skills review-required by default in Builder
- Require runtime confirmation before mutation execution
- Preserve allowed-root enforcement and app isolation
- Persist mutation intent and outcome in execution records and logs
- Support practical content-editing workflows without enabling arbitrary local automation

## Non-Goals

- No arbitrary shell execution
- No arbitrary Python execution
- No create/move/delete primitives in Phase 2
- No broad filesystem command surface
- No silent auto-finalization of write-capable contracts
- No runtime inference from freeform prose

## Architectural Position

Phase 2 extends the Phase 1 explicit-contract model rather than replacing it.

Natural `SKILL.md` files may still be uploaded, but Builder must normalize them into explicit mutation contracts before publish. Mutation-capable skills are never executed from descriptive prose alone.

Execution remains explicit:

1. Builder infers a draft mutation contract
2. Builder marks it `review_required`
3. The reviewed contract is published
4. Runtime executes it only after confirmation gates pass

## Phase 2 Tool Set

Phase 2 adds two new local tools.

### `write_file`

Purpose:
- Replace the full content of an existing text file within an allowed root

Inputs:
- `path: string`
- `content: string`
- `encoding?: string`
- `if_exists?: "overwrite"`

Outputs:
- `path: string`
- `bytes_written: integer`
- `updated: boolean`

Policy:
- existing file only in Phase 2
- allowed roots only
- text-oriented files only
- bounded write size
- no path creation outside existing parent directories

### `patch_file`

Purpose:
- Apply a bounded patch operation to an existing text file

Inputs:
- `path: string`
- `patch: string`
- `format?: "unified_diff"`

Outputs:
- `path: string`
- `updated: boolean`
- `summary: string`

Policy:
- existing file only
- allowed roots only
- bounded patch size
- patch must apply cleanly
- no binary patching

## Policy Model

Phase 2 uses a stricter policy class than Phase 1.

### Mutation Classification

Contracts using `write_file` or `patch_file` are classified as:

- `review_required`
- `mutation`

They are never auto-finalized by Builder.

### Allowed Root Enforcement

Mutation tools may operate only within configured mutation roots. These may be the same as or narrower than the Phase 1 read roots, but they must be explicit runtime config.

### Existing-File Constraint

Phase 2 does not create new files. Mutation applies only to files that already exist.

### Confirmation Requirement

Runtime must require confirmation for mutation tools even when the contract is valid and permissions are configured.

### Audit Requirement

Mutation executions must persist:

- requested target path
- tool id
- mutation intent
- confirmation outcome
- completion/failure state

## Builder Inference And Review Rules

Phase 2 extends the normalization pipeline from Phase 1.

### Supported Mutation Template Families

- content replace
- content patch
- template update

These map onto known workflow templates only. Freeform mutation workflows remain unsupported.

### Review Trigger Conditions

Builder must mark a contract `review_required` if any of the following are true:

- inferred tool set includes `write_file`
- inferred tool set includes `patch_file`
- path target semantics are ambiguous
- multiple workflow interpretations are plausible
- output expectations are underspecified

### Auto-Finalization Policy

Phase 2 mutation contracts are never auto-finalized. Builder may infer them, but publish requires explicit review.

## Workflow Templates

Phase 2 introduces two mutation-safe workflow templates.

### File Replace Workflow

- inspect current file state with `read_file`
- optionally save a pre-mutation artifact
- write replacement with `write_file`
- save a result artifact
- end

### File Patch Workflow

- inspect current file state with `read_file`
- apply `patch_file`
- optionally save a patch/result artifact
- end

These may include `local_decision` steps where needed, but no arbitrary service-call or subprocess semantics are introduced.

## Runtime Execution Rules

### Permissions

Phase 2 mutation permissions add:

- `filesystem.write`
- `filesystem.patch`

These are distinct from `filesystem.read`.

### Confirmation Flow

If a mutation tool is required and the execution request does not explicitly confirm execution, runtime returns `pending_confirmation` and persists the execution state.

The existing confirmation/resume lifecycle from the execution subsystem becomes mandatory for these workflows.

### Failure Handling

Mutation tools fail closed when:

- target path is outside allowed roots
- file does not exist
- file content exceeds configured size limits
- patch format is invalid
- patch does not apply cleanly

## Execution Persistence And Observability

Phase 2 builds on the existing execution store and status APIs.

Mutation-oriented execution records must include enough data to answer:

- what file was targeted
- what tool was used
- whether confirmation was required
- whether execution completed

No new persistence subsystem is required for Phase 2, but existing execution records and logs should include mutation-specific details.

## Configuration Requirements

Phase 2 runtime config adds:

- `FILESYSTEM_MUTATION_ROOTS`
- `FILESYSTEM_MAX_WRITE_BYTES`
- `FILESYSTEM_MAX_PATCH_BYTES`

If mutation roots are not configured, mutation tools should be treated as unavailable.

## Acceptance Criteria

Phase 2 is complete when:

- Builder can infer draft mutation contracts from natural mutation-oriented `SKILL.md`
- Builder marks all mutation contracts `review_required`
- runtime registers `write_file` and `patch_file`
- runtime enforces mutation-root policy and existing-file-only behavior
- runtime returns `pending_confirmation` for unconfirmed mutation requests
- confirmed mutation requests execute successfully within allowed roots
- cross-app artifact and execution isolation remain intact
- tests cover:
  - write-file success
  - patch-file success
  - out-of-root rejection
  - missing-file rejection
  - unconfirmed mutation returns `pending_confirmation`
  - confirmed mutation executes and persists outcome

## Recommended Implementation Order

1. Extend Builder normalization and policy classification for mutation templates
2. Add failing runtime tests for `write_file` and `patch_file`
3. Implement mutation root policy and bounded file mutation helpers
4. Wire mutation permissions and confirmation behavior through execution flows
5. Add end-to-end normalized mutation skill coverage
6. Update runtime and Builder docs
