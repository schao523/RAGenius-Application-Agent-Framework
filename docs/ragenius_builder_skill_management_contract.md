# RAGenius Builder Skill Creation, Management, and App-Skill Binding Contract

## Purpose

This document defines the architectural contract for:

1. Skill creation and management inside `ragenius_builder`
2. Application-to-skill bindings
3. Skill storage and lifecycle management
4. Runtime retrieval responsibilities
5. Skill folder structure conventions
6. Shared runtime consumption rules

This contract is intended for:

- OpenAI Codex
- Codex Desktop
- AI coding agents
- runtime contributors
- architecture maintainers
- future platform developers

---

# Architectural Principle

`ragenius_builder` is responsible for:

```text
application authoring
+
skill authoring
+
workflow/policy configuration
```

It is NOT responsible for runtime execution.

Runtime execution belongs exclusively to:

```text
ragenius_execution_subsystem
```

---

# Core Separation Principle

The builder platform must separate:

```text
Application Management
```

from:

```text
Skill Management
```

These are independent modules with independent lifecycle management.

However, they are connected through:

```text
App-Skill Bindings
```

---

# High-Level Architecture

```text
ragenius_builder
    ├── application_management
    │
    ├── skill_management
    │
    └── app_skill_bindings


ragenius_app
    ↓ retrieves skill definitions

ragenius_execution_subsystem
    ↓ retrieves skill manifests/workflows/tools

Builder Database + Skill File Storage
    ↓ source of truth
```

---

# Builder Responsibilities

## ragenius_builder Responsibilities

`ragenius_builder` is responsible for:

- application creation
- application management
- skill creation
- skill editing
- skill publishing
- skill versioning
- workflow definition management
- tool binding management
- permission policy management
- app-skill assignment
- skill enable/disable lifecycle
- skill resource uploads
- skill folder management
- skill metadata persistence
- runtime registry publication

---

# Runtime Responsibilities

## ragenius_app Responsibilities

`ragenius_app` is responsible for:

- user interaction
- retrieval planning
- content generation
- revision workflows
- approval flows
- execution request generation
- retrieving skill metadata from builder

`ragenius_app` must NOT:

- own skill definitions
- mutate skill manifests
- manage workflow publishing

---

## ragenius_execution_subsystem Responsibilities

`ragenius_execution_subsystem` is responsible for:

- loading skill manifests
- validating workflows
- resolving tool bindings
- orchestrating execution
- queue/worker execution
- permission enforcement
- state management
- retries and compensation
- execution logging

The execution subsystem must consume:

```text
published skill definitions only
```

---

# Source of Truth Principle

The source of truth for skills is:

```text
ragenius_builder database
+
skill-associated uploaded files
```

Both:

- `ragenius_app`
- `ragenius_execution_subsystem`

must retrieve skill data from builder-managed storage.

---

# Builder Storage Contract

## Purpose

`ragenius_builder` uses multiple storage-resolution patterns intentionally.

These patterns must not be casually merged.

Future changes must preserve the distinction between:

- convention-resolved flat files
- DB-path-resolved uploaded files
- relative-metadata-resolved skill folders
- transient staging storage

---

# Application Storage Contract

## Application Metadata

Application metadata is stored in the builder database.

Examples:

- application identity
- slug
- description
- starter questions

The `applications` table is not the source of truth for filesystem paths.

---

## Application Instructions

Application instructions are convention-resolved from `DatabaseStore.base_dir`.

The DB stores metadata and `uri`, but the actual instruction file location is derived by convention:

```text
instructions/{app_id}/instructions.md
```

This means application instructions are:

- file-backed
- builder-managed
- convention-resolved from `DatabaseStore.base_dir`
- not located from an absolute file path stored in DB

---

## Application Uploaded Documents

Application uploaded document binaries are DB-path-resolved.

The authoritative runtime location is the `documents.file_path` value stored in the builder DB.

This means uploaded documents are:

- physically stored as files
- located at runtime through DB `file_path`
- not convention-resolved from `DatabaseStore.base_dir`

This distinction is intentional and must be preserved unless explicitly redesigned.

---

# Skill Storage Architecture

## Core Principle

Each skill must be stored as a:

```text
self-contained skill folder
```

containing:

- `SKILL.md`
- optional resources
- references
- templates
- workflow assets

This architecture follows the uploaded design guidance describing dedicated skill folders with colocated resources and standardized subfolders. fileciteturn6file0

---

# Skill Folder Structure

## Canonical Skill Structure

```text
skill-folder/
    SKILL.md

    assets/
    references/
    workflows/
    prompts/
    schemas/
```

---

# Required Files

## SKILL.md

The root execution manifest.

Responsible for:

- skill metadata
- workflow definition
- required tools
- execution semantics
- input/output schemas
- permissions
- runtime configuration

---

# Optional Resource Folders

## assets/

May contain:

- templates
- output skeletons
- document structures
- reusable generation assets

---

## references/

May contain:

- style guides
- safety rules
- review checklists
- operational constraints
- domain conventions

---

## workflows/

May contain:

- workflow YAML
- execution graphs
- retry policies
- compensation flows

---

## prompts/

May contain:

- system prompts
- generation prompts
- planner prompts
- execution prompts

---

## schemas/

May contain:

- JSON schemas
- validation contracts
- input/output contracts

---

# Skill Scope Hierarchy

## Three-Tier Skill Scope

Skills may exist in:

1. Workspace Skills
2. Managed Skills
3. Bundled Skills

as described in the uploaded skill folder structure specification. fileciteturn6file0

---

# Workspace Skills

## Highest Priority

Workspace-scoped skills are application-specific.

Typical location:

```text
workspace/skills/
```

Characteristics:

- app-specific
- highest precedence
- may override global skills
- isolated to application scope

---

# Managed Skills

## Shared Global Skills

Managed skills are reusable across applications.

Typical location:

```text
managed-skills/
```

Characteristics:

- reusable
- globally available
- version-managed
- builder-managed lifecycle

---

# Bundled Skills

## Lowest Priority

Bundled skills ship with the platform.

Characteristics:

- platform defaults
- fallback implementations
- lowest override priority

---

# Skill Retrieval Rules

## Retrieval Precedence

The system should resolve skills using:

```text
workspace skill
    ↓
managed skill
    ↓
bundled skill
```

The first valid match wins.

---

# Skill Registry Contract

## Skill Registry Responsibilities

Builder must maintain a registry containing:

- skill ID
- version
- scope
- status
- storage location
- associated app bindings
- permissions
- workflow references
- uploaded resources
- publishing state

---

# Skill Lifecycle States

## Required States

```text
draft
→ review
→ published
→ active
→ deprecated
→ disabled
→ archived
```

---

# Skill Publishing Rules

## Publishing Requirements

Before a skill becomes publishable:

- `SKILL.md` must validate
- workflow definitions must validate
- required tools must exist
- permission policies must validate
- required resources must resolve
- schema contracts must pass

---

# App-Skill Binding Contract

## Purpose

Applications must not automatically inherit all skills.

Instead:

```text
applications explicitly bind to skills
```

through:

```text
app_skill_bindings
```

---

# Binding Responsibilities

App-skill bindings define:

- which skills an app may use
- allowed skill versions
- app-specific overrides
- app-specific permissions
- app-specific execution policies
- enable/disable state

---

# App-Skill Binding Schema

```ts
export type AppSkillBinding = {
  id: string;

  appId: string;
  skillId: string;
  skillVersion?: string;

  enabled: boolean;

  permissionMode:
    | "auto_allow"
    | "restricted"
    | "require_confirmation"
    | "blocked";

  executionPolicy?: {
    allowAsync?: boolean;
    allowRetries?: boolean;
    requireApproval?: boolean;
  };

  createdAt: string;
  updatedAt: string;
};
```

---

# Runtime Retrieval Contract

## Runtime Consumption Rule

Both:

```text
ragenius_app
```

and:

```text
ragenius_execution_subsystem
```

must retrieve:

- skill manifests
- workflows
- references
- templates
- schemas
- policies

from:

```text
builder-managed storage
```

The builder platform is the authoritative registry.

---

# Runtime Loading Flow

```text
Execution Request
    ↓
Resolve App-Skill Binding
    ↓
Resolve Skill Scope
    ↓
Load SKILL.md
    ↓
Load Associated Resources
    ↓
Validate Skill Manifest
    ↓
Resolve Workflow
    ↓
Execute Runtime
```

---

# Uploaded File Integration

## Uploaded Resources

Builder must support uploaded files associated with skills.

Supported examples:

- PDFs
- Markdown files
- templates
- YAML
- JSON schemas
- prompt libraries
- reference guides

These resources must remain:

```text
co-located with the skill folder
```

and retrievable through runtime-safe paths.

---

# Runtime Path Resolution

## Base Directory Rule

Associated skill resources must be resolvable through:

```text
{baseDir}
```

style path references.

Example:

```text
{baseDir}/references/style-guide.md
```

This follows the uploaded skill folder architecture guidance. fileciteturn6file0

---

# Runtime Path Clarification

## Persisted Skill Resolution

The `baseDir` rule above applies to persisted skill storage only.

Persisted skill files are resolved from:

- `DatabaseStore.base_dir`
- DB-stored relative metadata

Examples of relative metadata:

- `skill_md_rel_path`
- `storage_root_rel_path`

This means persisted skills are:

- builder-managed flat files
- not resolved from one absolute skill file path stored in DB
- resolved from `DatabaseStore.base_dir` plus builder-owned relative metadata

Associated skill resources must therefore be resolvable through a persisted skill root, for example:

```text
{skill_root}/references/style-guide.md
```

where `{skill_root}` is itself resolved from builder-managed relative metadata under `DatabaseStore.base_dir`.

---

## Skill Import Staging

Skill upload/import staging is transient storage.

It is separate from persisted skill storage.

This staging area:

- is used only during import/upload handling
- is not the source of truth for persisted skill resources
- must not be confused with the managed persisted skill folder

---

# Cleanup Rules

## Cleanup Must Respect Storage Contract

Cleanup logic must handle each artifact class according to its own storage contract.

Required behavior:

- application instructions cleanup must use the convention-resolved instructions location
- uploaded document cleanup must use DB `documents.file_path`
- persisted skill cleanup must use skill relative metadata plus `DatabaseStore.base_dir`
- transient skill import cleanup must use the staging storage rules

Do not assume one storage root or one resolution strategy for all builder artifacts.

---

# Security Rules

## Builder Security Rules

Builder must:

- validate uploaded resources
- prevent unsafe executable uploads
- validate workflow schemas
- validate permission policies
- prevent invalid tool references
- isolate workspace-scoped skills

---

# Runtime Security Rules

Runtime must:

- consume published skills only
- validate manifests before execution
- enforce permissions before tool calls
- prevent direct filesystem traversal
- normalize execution requests

---

# Architectural Principles

## Principle 1 — Builder Authors, Runtime Executes

Builder creates and manages definitions.

Runtime executes validated published definitions.

---

## Principle 2 — Skill Folders are Self-Contained

Each skill must be independently portable.

---

## Principle 3 — Builder is Source of Truth

Skill definitions must not diverge between:

- app runtime
- execution runtime
- builder registry

---

## Principle 4 — App-Skill Isolation

Applications must explicitly opt into skills.

---

## Principle 5 — Runtime Determinism

Execution runtime must consume:

```text
structured validated skill definitions only
```

---

# Future-Compatible Features

This architecture is designed to support:

- skill marketplace
- reusable shared skills
- multi-app skills
- skill inheritance
- distributed execution
- runtime replay
- skill publishing pipelines
- execution simulation
- version pinning
- workspace overrides
- enterprise policy systems
- MCP integration

---

# Final Contract Statement

`ragenius_builder` is responsible for:

```text
creating
managing
publishing
binding
versioning
and storing
```

applications and skills.

`ragenius_execution_subsystem` is responsible for:

```text
loading
validating
orchestrating
and executing
```

published skill definitions.

`ragenius_app` is responsible for:

```text
user interaction
content generation
planning
and execution request generation
```

All runtime systems must retrieve authoritative skill definitions and associated resources from builder-managed storage and skill folders.
