# RAGenius Content and Execution Separation Contract v2

## Purpose

This document defines the architectural contract for separating:

1. content generation
2. execution intent generation
3. runtime execution

inside `ragenius_app`, while aligning with the current capabilities of:

- `ragenius_builder`
- `ragenius_execution_subsystem`

This revision replaces the earlier two-layer split with a more precise three-boundary model so the contract matches the system as it exists today.

The contract exists to ensure:

- deterministic execution behavior
- safe tool execution
- scalable agent architecture
- independent testing
- permission isolation
- future multi-agent extensibility
- workflow stability
- maintainable code boundaries
- execution provenance and auditability

---

# Core Architectural Principle

The RAGenius system must separate:

```text
Cognitive / Content Layer
```

from:

```text
Deterministic Execution Intent Layer
```

from:

```text
Execution Runtime Layer
```

The execution subsystem must not directly consume raw conversational user queries.

The required flow is:

```text
User Query
  -> Intent Planning
  -> Content Generation
  -> User Review / Revisions
  -> ApprovedContent
  -> ExecutionIntent
  -> StructuredExecutionRequest
  -> Execution Runtime
```

The only approved bridges are:

- `ApprovedContent`
- `ExecutionIntent`

`ApprovedContent` is the boundary for user-approved semantic content.

`ExecutionIntent` is the boundary for deterministic execution mapping.

---

# Design Goals

## Primary Goals

- isolate content-generation complexity from runtime execution
- make execution deterministic after approval
- support safe permissions and confirmations
- support synchronous and asynchronous execution
- support retries and compensation
- preserve user-approved content integrity
- enable future distributed execution
- allow independent testing and scaling
- support runtime provenance and fallback audit trails

## Non-Goals

The execution intent generation layer must NOT:

- perform retrieval
- generate new content
- rewrite user-approved content
- call LLMs
- infer missing semantic intent from ambiguous conversation
- directly perform tool execution
- directly invoke external APIs

The runtime execution layer must NOT:

- reinterpret user intent from raw chat text
- perform content generation
- silently rewrite approved content

---

# High-Level Architecture

```text
ragenius_app
    content_generation/
        intent_planner
        retrieval_planner
        draft_generator
        revision_handler
        approval_manager
        approved_content_builder

    execution_intent/
        skill_selector
        execution_input_mapper
        request_validator
        request_builder
        provenance_builder

ragenius_execution_subsystem
    workflow_runtime
    tool_engine
    permission_engine
    queue_worker_runtime
    execution_state_manager
```

The directory structure above is conceptual, not mandatory.

The repository integration rule remains:

- adapt these boundaries into the existing repository
- do not redesign the repository structure unless explicitly requested

---

# Layer Responsibilities

## Layer 1 - Content Generation Layer

### Responsibilities

- understand user intent
- retrieval planning
- RAG orchestration
- drafting
- rewriting
- summarization
- editing
- revision handling
- approval flow
- content lifecycle management

### Characteristics

This layer is:

```text
LLM-centric
creative
iterative
non-deterministic
user-facing
```

### Allowed Dependencies

This layer MAY:

- use LLMs
- use prompts
- perform retrieval
- use embeddings
- use RAG
- use conversational memory
- use agent planning

### Forbidden Behaviors

This layer must NOT:

- directly execute runtime tools
- bypass permission systems
- mutate runtime execution state
- directly manage runtime retries

---

## Layer 2 - Execution Intent Layer

### Responsibilities

- select the correct skill
- map approved content into structured inputs
- attach target references
- validate execution schemas
- determine execution options
- build runtime-safe requests
- preserve content integrity and provenance

### Characteristics

This layer is:

```text
schema-driven
deterministic
strict
validated
runtime-safe
non-LLM
```

### Critical Rule

Execution intent generation must NEVER depend directly on:

- raw user query text for semantic interpretation
- prompt chains
- draft-generation internals
- conversational ambiguity

Execution intent generation may consume:

- `ApprovedContent`
- selected app/runtime state
- Builder-published skill contracts
- target references already chosen by the user or upstream flow

### Forbidden Behaviors

This layer must NOT:

- call LLMs
- rewrite approved content
- perform tool execution
- perform external API calls

---

## Layer 3 - Execution Runtime Layer

### Responsibilities

- consume only structured execution requests
- validate request schemas
- enforce permissions
- run workflow steps
- manage confirmations
- emit provenance
- support retries and background work
- persist execution state

### Characteristics

This layer is:

```text
deterministic
validated
permission-aware
observable
side-effect-controlled
```

---

# Approved Content Contract

## Definition

`ApprovedContent` represents user-reviewed semantic content that is frozen for execution purposes.

It is the approved boundary between:

- content generation
- execution intent generation

It is not itself a runtime execution request.

## ApprovedContent Type

```ts
export type ApprovedContent = {
  id: string;
  appId: string;
  sessionId: string;
  userId?: string;

  sourceUserQuery: string;

  contentType:
    | "script"
    | "article"
    | "summary"
    | "storyboard"
    | "video_brief"
    | "email_draft"
    | "briefing"
    | "prompt_payload";

  title?: string;
  body?: string;
  script?: string;

  storyboard?: Array<{
    scene: number;
    narration?: string;
    visualDescription?: string;
  }>;

  artifactRefs?: Array<{
    artifactId: string;
    kind?: string;
    role?: string;
  }>;

  sourceRefs?: Array<{
    id: string;
    type: string;
    title?: string;
  }>;

  targetRefs?: Record<string, unknown>;

  metadata?: Record<string, unknown>;

  revisionId: string;
  contentHash: string;
  approvedAt: string;
  approvedBy?: string;
};
```

## Rules

- `ApprovedContent` must be immutable for execution purposes after approval.
- If content changes materially, a new `ApprovedContent` object must be created.
- `contentHash` must identify the exact approved semantic payload used for execution.

---

# Execution Intent Contract

## Definition

`ExecutionIntent` represents the deterministic mapping from approved content into an executable skill request shape.

It is the approved boundary between:

- approved semantic content
- runtime request generation

This object exists because:

- the same approved content may be executed through different skills
- execution-specific selectors are not always part of the semantic content itself
- provenance and idempotency need their own contract

## ExecutionIntent Type

```ts
export type ExecutionIntent = {
  id: string;

  approvedContentId: string;
  appId: string;
  sessionId: string;

  skillId: string;
  skillVersion?: string;

  input: Record<string, unknown>;

  executionMode: "sync" | "async";

  requireConfirmation: boolean;
  dryRun?: boolean;

  idempotencyKey?: string;

  targetRefs?: Record<string, unknown>;
  metadata?: Record<string, unknown>;

  generatedAt: string;
};
```

## Rules

- `ExecutionIntent` must be generated deterministically from:
  - approved content
  - skill contract
  - selected target references
  - app/runtime state
- `ExecutionIntent` must not be produced by LLM free-form reasoning.
- `ExecutionIntent` must not rewrite semantic content.

---

# Structured Execution Request Contract

## Definition

Structured execution requests are runtime-safe payloads consumed by:

```text
ragenius_execution_subsystem
```

Execution requests must be:

- deterministic
- validated
- schema-compliant
- permission-aware
- execution-safe

## StructuredExecutionRequest Type

The current runtime-compatible minimum contract is:

```ts
export type StructuredExecutionRequest = {
  request_type: "execute_skill";

  app_id: string;
  session_id: string;

  skill_id: string;

  input: Record<string, unknown>;

  execution_options?: {
    dry_run?: boolean;
    require_confirmation?: boolean;
  };
};
```

## Recommended Extended Type

For `ragenius_app`, the preferred app-side request envelope should evolve toward:

```ts
export type StructuredExecutionRequestV2 = {
  request_type: "execute_skill";

  request_id: string;
  app_id: string;
  session_id: string;

  skill_id: string;
  skill_version?: string;

  approved_content_id?: string;
  execution_intent_id?: string;

  input: Record<string, unknown>;

  execution_mode?: "sync" | "async";

  execution_options?: {
    dry_run?: boolean;
    require_confirmation?: boolean;
  };

  idempotency_key?: string;

  metadata?: {
    initiated_by?: string;
    source?: string;
    planner_trace_id?: string;
  };
};
```

The current execution subsystem may keep accepting the existing minimal shape, while `ragenius_app` internally adopts the richer model.

---

# Lifecycle Flow

## Required Lifecycle

```text
draft_content
    -> user_review
    -> revised_content
    -> approved_content
    -> execution_intent_created
    -> execution_request_created
    -> execution_submitted
    -> execution_running
    -> execution_completed
```

## Additional Required States

The system should also support:

- `approval_pending`
- `approval_rejected`
- `request_validated`
- `request_rejected`
- `execution_queued`
- `execution_timeout`
- `execution_failed`
- `execution_completed_with_fallback`
- `compensation_required`

---

# Required Separation Rules

## Rule 1

Execution intent generation code MUST be isolated from content generation code.

## Rule 2

Execution intent generation MUST NOT call LLMs.

## Rule 3

Execution intent generation MUST NOT rewrite approved content.

## Rule 4

Execution intent generation MUST validate required runtime fields.

## Rule 5

Raw user queries MUST NOT be directly converted into execution payloads unless explicitly allowed by policy.

## Rule 6

Side-effecting skills SHOULD default to:

```text
require_confirmation = true
```

## Rule 7

The runtime subsystem MUST consume only structured execution requests.

## Rule 8

Once `ApprovedContent` exists, downstream execution mapping MUST use approved content and selected target references, not raw conversation text.

## Rule 9

Execution provenance must record:

- approved content id/hash
- execution intent id
- selected skill/version
- execution path
- fallback usage
- confirmation decisions

---

# Repository Integration Strategy

## Important Constraint

This contract assumes the repository already exists.

The purpose of this document is NOT to redesign or restructure the repository from scratch.

Instead, this contract defines:

- architectural boundaries
- module responsibilities
- execution contracts
- integration rules
- separation principles

Codex Desktop and future contributors must adapt these concepts to the existing repository structure.

## Integration Rules

### Rule 1 - Preserve Existing Repository Structure

Do NOT perform large-scale repository restructuring unless explicitly requested.

Avoid:

- moving large directory trees
- renaming stable modules
- breaking import paths
- rewriting unrelated architecture
- reorganizing the repository for aesthetic reasons

### Rule 2 - Integrate Incrementally

Prefer:

- extending existing modules
- adding focused submodules
- preserving current runtime behavior
- maintaining backward compatibility

### Rule 3 - Respect Existing Boundaries

If the repository already contains:

- planners
- retrieval logic
- workflow orchestration
- tool registries
- execution handlers

extend them instead of replacing them.

### Rule 4 - Builder Contracts Are First-Class

`ragenius_app` should consume Builder-published skill/runtime contracts rather than inventing parallel execution semantics.

### Rule 5 - Execution Subsystem Contract Is Canonical

The app must submit runtime-safe structured requests to `ragenius_execution_subsystem` rather than performing direct tool execution itself.

---

# Current System Alignment

This contract assumes and aligns with the current RAGenius direction:

- Builder already compiles skill markdown into runtime contracts
- Builder already exposes contract preview, confidence, and authoring diagnostics
- execution subsystem already validates structured `execute_skill` requests
- execution subsystem already maintains provider/tool inventories
- execution subsystem already emits execution provenance and fallback diagnostics
- NotebookLM, MCP, and adapter-backed skills already operate through explicit tool contracts

This contract therefore extends the current system; it does not replace it.

---

# Example Flow

## User Query

```text
Create a short NotebookLM video explaining RAG for non-technical users.
```

## Approved Content

```json
{
  "id": "ac_001",
  "appId": "app_001",
  "sessionId": "sess_001",
  "contentType": "video_brief",
  "title": "RAG Explained Simply",
  "script": "Retrieval-Augmented Generation helps AI retrieve external knowledge before generating answers.",
  "metadata": {
    "duration_seconds": 30,
    "style": "friendly explainer"
  },
  "targetRefs": {
    "notebookTitle": "GPT Application Designer"
  },
  "revisionId": "rev_004",
  "contentHash": "sha256:...",
  "approvedAt": "2026-06-03T10:00:00Z"
}
```

## Execution Intent

```json
{
  "id": "ei_001",
  "approvedContentId": "ac_001",
  "appId": "app_001",
  "sessionId": "sess_001",
  "skillId": "notebooklm_generate_video",
  "input": {
    "notebookTitle": "GPT Application Designer",
    "instructions": "Create a short, user-friendly explanatory video about RAG.",
    "language": "en",
    "waitForCompletion": false,
    "persistArtifacts": true
  },
  "executionMode": "async",
  "requireConfirmation": true,
  "generatedAt": "2026-06-03T10:02:00Z"
}
```

## Structured Execution Request

```json
{
  "request_type": "execute_skill",
  "app_id": "app_001",
  "session_id": "sess_001",
  "skill_id": "notebooklm_generate_video",
  "input": {
    "notebookTitle": "GPT Application Designer",
    "instructions": "Create a short, user-friendly explanatory video about RAG.",
    "language": "en",
    "waitForCompletion": false,
    "persistArtifacts": true
  },
  "execution_options": {
    "dry_run": false,
    "require_confirmation": true
  }
}
```

---

# Runtime Principles

## Principle 1 - User Approval Boundary

Only user-approved content may enter execution intent generation.

## Principle 2 - Runtime Determinism

Runtime execution must behave deterministically given:

- approved content
- execution intent
- structured execution request
- runtime state

## Principle 3 - Execution Safety

All runtime actions must:

- pass permission checks
- validate schemas
- support confirmations
- support logging
- support retries
- support provenance

## Principle 4 - Cognitive / Execution Separation

Cognitive planning and runtime execution are separate concerns.

## Principle 5 - Builder Contract Reuse

The app should map approved content into Builder-defined skill contracts rather than inventing separate tool-level request shapes.

---

# Testing Requirements

## Required Tests

The system must test:

1. approved content generation
2. approval lifecycle
3. execution intent validation
4. skill selection
5. deterministic request mapping
6. permission handling
7. confirmation defaults
8. runtime request normalization
9. separation boundary enforcement
10. execution provenance persistence
11. async execution lifecycle
12. fallback-path reporting

---

# Future Extensions

This architecture is designed to support:

- multi-agent orchestration
- distributed workers
- persistent execution queues
- workflow retries
- compensation logic
- execution replay
- audit logs
- execution simulation
- approval workflows
- policy engines
- MCP runtime integration
- adapter-backed long-running jobs

---

# Final Contract Statement

The RAGenius architecture MUST maintain a strict separation between:

```text
content cognition
```

and:

```text
deterministic execution intent generation
```

and:

```text
runtime execution
```

The approved semantic boundary is:

```text
ApprovedContent
```

The deterministic mapping boundary is:

```text
ExecutionIntent
```

All runtime execution must occur through:

```text
StructuredExecutionRequest
```

The execution subsystem must never directly interpret conversational ambiguity or raw drafting logic.
