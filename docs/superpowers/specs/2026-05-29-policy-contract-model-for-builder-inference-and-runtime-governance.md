# Policy Contract Model For Builder Inference And Runtime Governance

## Purpose

Define a generic contract model for how RAGenius should combine:

- natural skill intent from `SKILL.md`
- Builder inference
- configurable governance policy
- hard safety invariants
- explicit runtime execution contracts

This document is not specific to Gmail attachments. Attachment-capable Gmail workflows are only one example of the policy model in action.

## Problem Statement

As the system grows beyond simple read-only skills, more decisions appear that should not be left to:

- freeform markdown alone
- silent inference alone
- scattered hard-coded conditionals

Examples:

- whether a skill may mutate files
- whether an MCP tool is allowed
- whether an outbound action requires confirmation
- whether an attachment must come from an app-scoped artifact
- whether a provider family is auto-finalizable or always review-required

The system needs a stable contract that separates:

- what must never be violated
- what may be configured
- what may be inferred
- what must be materialized explicitly before execution

## Core Principle

RAGenius should execute only **explicit finalized contracts**, but those contracts may be derived from:

1. skill intent
2. Builder inference
3. platform policy
4. hard safety invariants

So the system model is:

- `SKILL.md` describes intent
- Builder infers a draft contract
- policy constrains and shapes that draft
- hard invariants override everything
- runtime executes only the resulting explicit contract

## Contract Layers

### Layer 1: Skill Intent

Source:

- uploaded `SKILL.md`

Purpose:

- express what the user wants at a human level

May include:

- task description
- expected inputs
- expected outputs
- workflow hints
- domain intent

Should not be treated as final authority for:

- permissions
- provider allowlists
- side-effect policy
- attachment source trust model
- file isolation rules

### Layer 2: Builder-Inferred Draft Contract

Produced by:

- Builder normalization/inference pipeline

Purpose:

- convert intent into a machine-usable draft

Contains:

- template family
- candidate tools
- draft workflow
- draft schemas
- draft permissions
- confidence
- policy classification

Important rule:

- this draft is not yet the final execution truth

### Layer 3: Configurable Policy

Owned by:

- platform/runtime configuration
- potentially Builder-admin-visible configuration in the future

Purpose:

- govern how draft contracts may be finalized and executed

Examples:

- provider enablement
- MCP tool allowlists
- review-required families
- confirmation requirements
- allowed MIME types
- attachment size/count limits
- artifact-source restrictions
- app/provider capability allowlists

Important rule:

- policy should be typed, explicit, and environment-aware

### Layer 4: Hard Safety Invariants

Owned by:

- code-level guarantees

Purpose:

- enforce boundaries that should not become optional through config

Examples:

- app isolation
- no cross-app artifact leakage
- no arbitrary local file path access where disallowed
- no secrets in Builder skill metadata
- no execution without a finalized explicit contract

Important rule:

- config may narrow these rules, but not disable them

### Layer 5: Finalized Execution Contract

Produced by:

- Builder after inference + policy application

Consumed by:

- `ragenius_execution_subsystem`

Purpose:

- provide the explicit contract that runtime can execute deterministically

Contains:

- required tools
- required permissions
- workflow definition
- input schema
- output schema
- policy class
- finalization state

Important rule:

- runtime should never depend on freeform markdown at execution time

## Decision Ownership Model

### Inferred From Skill Intent

These may be inferred:

- likely task family
- likely candidate tools
- likely workflow shape
- likely input fields
- likely output shape

Examples:

- a Gmail search skill likely needs a read-only Gmail MCP tool
- a Drive search skill likely needs `mcp.gdrive.search_files`

### Controlled By Configurable Policy

These should be configurable:

- whether a family is auto-finalizable
- whether a capability is review-required
- which provider/tool ids are allowlisted
- attachment size/type/count limits
- which artifact types are allowed as outbound inputs
- whether an app may use a provider family

### Enforced As Hard Invariants

These should not be left to draft inference or ordinary config:

- app isolation
- no cross-app leakage
- no secret storage in skill metadata
- no runtime execution from unfinalized draft
- no bypass of confirmation on required side-effecting flows

## Generic Policy Categories

Every finalized contract should be categorizable by policy class.

Recommended generic categories:

- `safe_read`
- `review_required`
- `mutation`
- `external_write`
- `unsupported`

And optionally orthogonal traits:

- `requires_confirmation`
- `requires_artifact_source`
- `provider_backed`
- `side_effecting`

This keeps policy reasoning more general than one-off provider flags.

## Artifact Source Model

For workflows that move content between providers, artifacts should be a first-class boundary object.

Recommended rule:

- high-risk cross-provider workflows should prefer **artifact ids** over raw local file paths or arbitrary provider-native ids

Why:

- preserves app scoping
- improves auditability
- makes workflows composable
- keeps retrieval/export/send boundaries explicit

This applies broadly, not only to Gmail attachments.

Examples:

- Drive export -> artifact -> Gmail draft attachment
- retrieval report -> artifact -> external publish adapter

## Confirmation Model

Confirmation should be driven by policy, not by ad hoc workflow authoring.

Recommended rule:

- side-effecting contracts may be inferred from intent, but confirmation requirements come from policy and invariants

Examples:

- file mutation -> confirmation required
- Gmail outbound send -> confirmation required
- read-only search -> no confirmation

The workflow may express the path, but policy decides whether execution pauses first.

## Finalization Rules

A draft contract may become finalized only when:

- inference produced a supported template family
- policy permits finalization for that family
- required tools exist and are allowlisted
- required schemas are complete
- hard invariants are satisfied

Auto-finalization should be policy-driven and limited to low-risk families.

Examples:

- safe read file/report skill -> may auto-finalize
- provider-backed outbound send skill -> should remain review-required

## Runtime Contract Rules

The execution subsystem should assume:

- all inputs come from a finalized contract
- permissions and policy class are already explicit
- provider/tool use is already narrowed

The execution subsystem should still enforce:

- permission checks
- app isolation
- provider allowlists
- confirmation gating
- artifact scoping

So Builder is not the only gate; runtime remains the enforcement boundary.

## Configuration Model Guidance

### Hard-Coded Invariants

Keep in code:

- app isolation
- no cross-app artifact leakage
- no execution of unfinalized contracts
- no secret storage in Builder skill metadata

### Typed Configurable Policy

Move to config:

- provider enablement
- tool allowlists
- per-family review requirements
- confirmation policies
- attachment and artifact rules
- max sizes and allowed types

### Inference Rules

May live in Builder logic, but should reference policy rather than duplicate it.

## Example: Attachment-Capable Gmail

This model applied to Gmail attachments would look like:

- skill intent says: send an email with an attachment
- Builder infers:
  - Gmail write family
  - attachment-capable workflow
  - likely dependency on artifact input
- policy says:
  - review-required
  - confirmation required
  - attachment source must be app-scoped artifact
  - size/type/count limits apply
- hard invariants say:
  - no cross-app artifact leakage
  - no arbitrary local path attachments
- final contract explicitly encodes:
  - required tools
  - required permissions
  - workflow
  - artifact-based input model

This example is only one instance of the generic model.

## Acceptance Standard For This Model

The system is aligned with this contract model when:

- `SKILL.md` expresses intent, not hidden runtime truth
- Builder produces explicit draft contracts
- configurable policy shapes finalization outcomes
- hard invariants cannot be disabled casually
- runtime executes only finalized explicit contracts
- cross-provider workflows prefer artifact boundaries where appropriate

## Recommended Next Steps

1. Introduce a typed policy config surface for provider-backed and side-effecting contracts
2. Refactor Builder normalization rules to consult policy instead of embedding more ad hoc conditionals
3. Use this model as the contract basis for attachment-capable Gmail workflows
4. Apply the same pattern to future Drive, Calendar, Docs, and Sheets write-capable flows
