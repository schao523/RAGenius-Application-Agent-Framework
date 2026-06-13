# NotebookLM Adapter And User-Workflow Integration Design

## Purpose

Add a NotebookLM capability slice to RAGenius that lets users:

- access existing NotebookLM notebooks visible to the authenticated session
- ask questions against those notebooks
- send RAGenius-created content into NotebookLM as sources
- trigger NotebookLM generation workflows for presentation-style outputs

This design is intentionally capability-oriented, not RPC-oriented. The goal is not to mirror every `notebooklm-py` method inside RAGenius. The goal is to expose the highest-value NotebookLM workflows through explicit Builder contracts and stable runtime adapter seams.

## Scope

This design covers:

- the adapter seam between `ragenius_execution_subsystem` and `notebooklm-py`
- author-facing Builder aliases for NotebookLM capabilities
- runtime tool contracts and policy expectations
- user-workflow phases for:
  - existing notebook access
  - asking questions
  - pushing RAGenius outputs into NotebookLM
  - generation

This design does not cover:

- full NotebookLM RPC parity
- NotebookLM share-management workflows
- NotebookLM notebook deletion or destructive source cleanup
- end-user `ragenius_app` UX implementation
- secret rotation UX beyond initial runtime configuration

## Goals

- support the user workflows that matter most first
- keep NotebookLM integration behind a narrow, explicit adapter seam
- preserve Builder inference, policy review, and runtime contract stability
- reuse RAGenius artifact boundaries rather than inventing NotebookLM-specific file plumbing
- avoid coupling the Node execution runtime directly to undocumented NotebookLM wire details

## Non-Goals

- no attempt to normalize every NotebookLM feature into phase 1
- no direct vendoring of the `notebooklm-py` repo into RAGenius
- no silent use of unofficial NotebookLM APIs without explicit operator configuration
- no bypass of RAGenius artifact isolation rules

## Constraints

The NotebookLM integration has several important constraints:

- `notebooklm-py` is a Python client, while `ragenius_execution_subsystem` is TypeScript/Node
- the library uses undocumented Google-backed NotebookLM interfaces and may break without notice
- authentication is session/cookie-based, not a stable official API-key model
- some operations are read-like, but source import and generation are external side effects

These constraints strongly favor an adapter seam rather than embedding NotebookLM details directly throughout the runtime.

## User-Value Prioritization

The highest-value NotebookLM workflows for RAGenius users are:

1. use an existing NotebookLM notebook as context
2. ask NotebookLM questions against that notebook
3. send content produced by `ragenius_app` into NotebookLM
4. ask NotebookLM to generate presentation-style outputs from that material

This is better than starting with notebook CRUD because it matches what users are trying to accomplish rather than what the low-level library happens to expose.

## Assumptions

This design assumes:

- phase 1 should support any notebooks visible to the authenticated NotebookLM session, not only privately owned notebooks
- the first integration target is runtime support plus Builder contract support, not `ragenius_app` UI
- NotebookLM content imported from RAGenius should flow through app-scoped artifacts or explicit text payloads
- operators are willing to configure NotebookLM session auth in runtime configuration, knowing the integration is unofficial

## Approach Options

### Option 1: Direct TypeScript Reimplementation

Reimplement NotebookLM RPC behavior directly in Node/TypeScript.

Pros:

- single-language runtime
- no Python bridge

Cons:

- duplicates unstable unofficial protocol work
- high maintenance burden
- harder to stay aligned with `notebooklm-py`
- unnecessarily broadens risk inside the execution subsystem

Recommendation:

- reject

### Option 2: Python Subprocess Adapter

Have `ragenius_execution_subsystem` call a local Python bridge command that imports `notebooklm-py` and returns structured JSON.

Pros:

- keeps NotebookLM specifics inside Python
- allows version-pinned reuse of `notebooklm-py`
- smaller first implementation slice
- no long-running extra service required

Cons:

- per-call process startup overhead
- async task polling needs careful orchestration
- structured error mapping must be explicit

Recommendation:

- viable for early implementation

### Option 3: Local NotebookLM Adapter Service

Run a small local Python adapter service that wraps `notebooklm-py`, and let `ragenius_execution_subsystem` talk to it as a local provider.

Pros:

- best long-term seam
- stable local API surface for Node runtime
- easier health checks, retries, and capability discovery
- supports longer-lived polling/generation workflows better than one-shot subprocesses

Cons:

- more moving parts than a subprocess bridge
- needs local service lifecycle management

Recommendation:

- preferred target architecture

## Recommended Architecture

Use a dedicated local NotebookLM adapter seam with a narrow provider contract:

- `notebooklm-py` remains an external Python dependency
- a Python bridge layer owns all direct NotebookLM client interaction
- `ragenius_execution_subsystem` treats that bridge as a local adapter/provider
- Builder works in capability aliases, not Python-library method names

This keeps the system aligned with the Generic MCP layer + Adapter direction:

- official remote services use MCP where available
- unstable or unofficial integrations use controlled local adapters
- policy and workflow contracts stay explicit above both kinds of providers

## Why Keep `notebooklm-py` Outside The RAGenius Repo

The RAGenius repo should not vendor `notebooklm-py` by default.

Reasons:

- it is an independent upstream library with its own release cycle
- vendoring would blur ownership and make upgrades harder
- the runtime seam should depend on a versioned package contract, not a copied code tree

Recommended dependency model:

- install `notebooklm-py` as a pinned Python dependency for the local adapter runtime
- allow development-time use of a checked-out external repo if needed
- keep the adapter seam stable even if the underlying package changes

## Adapter Seam

The NotebookLM adapter should expose a local provider family:

- provider id: `notebooklm`
- provider type: `adapter`

Concrete runtime tool ids should be explicit and capability-shaped:

- `adapter.notebooklm.list_notebooks`
- `adapter.notebooklm.get_notebook`
- `adapter.notebooklm.list_sources`
- `adapter.notebooklm.ask`
- `adapter.notebooklm.add_source_text`
- `adapter.notebooklm.add_source_file`
- `adapter.notebooklm.add_source_url`
- `adapter.notebooklm.generate_slide_deck`
- `adapter.notebooklm.generate_report`
- `adapter.notebooklm.generate_video`

The Node runtime should not know or care which exact `notebooklm-py` service method or RPC id implements each one.

## Bridge Shape

The bridge should present a small local JSON interface, whether subprocess-backed or service-backed.

Required properties:

- explicit operation name
- explicit request JSON
- explicit response JSON
- stable error classes
- no raw cookie/session leakage into execution results

Example conceptual request:

```json
{
  "operation": "ask",
  "arguments": {
    "notebook_id": "nb_123",
    "question": "What are the key themes?",
    "source_ids": ["src_1", "src_2"]
  }
}
```

Example conceptual response:

```json
{
  "ok": true,
  "result": {
    "answer": "…",
    "conversation_id": "conv_123",
    "references": [
      {
        "source_id": "src_1",
        "title": "Paper A"
      }
    ]
  }
}
```

## Authentication Model

NotebookLM auth should be runtime-configured only.

Recommended supported inputs:

- `NOTEBOOKLM_AUTH_JSON`
- optional `NOTEBOOKLM_PROFILE`
- optional `NOTEBOOKLM_HOME`

Builder should not store NotebookLM session cookies or auth JSON.

The adapter should create clients using the library’s supported storage/env precedence, with runtime-only secret injection.

## Capability Families

NotebookLM capabilities should be grouped into three initial workflow families plus generation.

### Phase 1: Existing Notebook Access

Author-facing aliases:

- `notebooklm.list_notebooks`
- `notebooklm.get_notebook`
- `notebooklm.list_sources`
- `notebooklm.ask`

User value:

- inspect available notebooks
- pick a notebook
- ask questions using existing NotebookLM context

### Phase 2: Import RAGenius Content Into NotebookLM

Author-facing aliases:

- `notebooklm.add_source_text`
- `notebooklm.add_source_file`
- `notebooklm.add_source_url`

User value:

- move app-produced content into an existing NotebookLM notebook
- attach a RAGenius artifact as a NotebookLM source
- enrich NotebookLM context without leaving the platform

### Phase 3: Generation

Author-facing aliases:

- `notebooklm.generate_slide_deck`
- `notebooklm.generate_report`
- `notebooklm.generate_video`

User value:

- create presentation-style deliverables from NotebookLM notebook context
- turn imported app outputs into downstream presentation and summary artifacts

## Builder Alias Model

Builder should support NotebookLM aliases the same way it now supports Gmail and Drive aliases.

Recommended aliases:

- `notebooklm.list_notebooks`
- `notebooklm.get_notebook`
- `notebooklm.list_sources`
- `notebooklm.ask`
- `notebooklm.add_source_text`
- `notebooklm.add_source_file`
- `notebooklm.add_source_url`
- `notebooklm.generate_slide_deck`
- `notebooklm.generate_report`
- `notebooklm.generate_video`

Builder should resolve those aliases into explicit runtime tool ids and deterministic workflow families where possible.

## Builder Normalization Families

Recommended first template families:

- `notebooklm_read_existing_notebook_operation`
- `notebooklm_import_source_operation`
- `notebooklm_generation_operation`

Behavior:

- deterministic normalization when explicit aliases are present
- no heuristic fallback to unrelated generic templates
- `review_required` for write/generation families

## Runtime Tool Contracts

### `adapter.notebooklm.list_notebooks`

Input:

- no required fields in the initial slice

Output:

- array of notebook summaries:
  - `id`
  - `title`
  - `sources_count`
  - optional metadata the adapter can safely normalize

Permissions:

- `external_api.read`

### `adapter.notebooklm.get_notebook`

Input:

- `notebookId`

Output:

- notebook summary and metadata visible from NotebookLM

Permissions:

- `external_api.read`

### `adapter.notebooklm.list_sources`

Input:

- `notebookId`

Output:

- list of source summaries:
  - `id`
  - `title`
  - `kind`
  - `status`

Permissions:

- `external_api.read`

### `adapter.notebooklm.ask`

Input:

- `notebookId`
- `question`
- optional `sourceIds`
- optional `conversationId`

Output:

- `answer`
- `conversation_id`
- normalized `references`
- optional `turn_number`

Permissions:

- `external_api.read`

Rationale:

- this is user-visible generation, but it is logically read-oriented because it queries existing notebook context rather than mutating sources

### `adapter.notebooklm.add_source_text`

Input:

- `notebookId`
- `title`
- `content`

Output:

- source summary:
  - `source_id`
  - `title`
  - `status`

Permissions:

- `external_api.write`

Notes:

- this operation is non-idempotent according to `notebooklm-py` docs and should be treated carefully in retry policy

### `adapter.notebooklm.add_source_file`

Input:

- `notebookId`
- `artifactId`
- optional `title`

Output:

- source summary:
  - `source_id`
  - `title`
  - `status`
  - linked `artifact_id`

Permissions:

- `artifact.read`
- `external_api.write`

### `adapter.notebooklm.add_source_url`

Input:

- `notebookId`
- `url`

Output:

- source summary:
  - `source_id`
  - `title`
  - `status`

Permissions:

- `external_api.write`

### `adapter.notebooklm.generate_slide_deck`

Input:

- `notebookId`
- optional `sourceIds`
- optional `instructions`
- optional generation options allowed by policy

Output:

- `task_id`
- normalized generation status
- optionally downloaded artifact metadata if the workflow waits for completion

Permissions:

- `external_api.write`
- optional `artifact.write` if RAGenius persists downloaded output

### `adapter.notebooklm.generate_report`

Input:

- `notebookId`
- optional `sourceIds`
- optional `instructions`
- optional report format

Output:

- `task_id`
- normalized generation status
- optionally runtime artifact metadata

Permissions:

- `external_api.write`
- optional `artifact.write`

### `adapter.notebooklm.generate_video`

Input:

- `notebookId`
- optional `sourceIds`
- optional `instructions`
- optional format/style fields from an allowlisted subset

Output:

- `task_id`
- normalized generation status
- optionally runtime artifact metadata for downloaded MP4 output

Permissions:

- `external_api.write`
- optional `artifact.write`

## Artifact Boundary

The core RAGenius-to-NotebookLM seam should be app-scoped artifacts.

For `add_source_file`:

- Builder/runtime skills should reference `artifactId`, not arbitrary local paths
- the adapter should materialize the artifact into a temporary bridge-owned file upload path if needed
- the external NotebookLM notebook should never get arbitrary filesystem reach-through

This preserves the same design principle already used for Gmail attachments:

- explicit app-scoped artifact boundaries
- no arbitrary local file path contracts
- auditable workflow handoff

## Result Persistence Strategy

Generation workflows should support two result modes:

1. remote-only status mode
- return NotebookLM task metadata

2. downloaded artifact mode
- wait for completion
- download result through `notebooklm-py`
- save to RAGenius artifact storage
- return `artifact_id` plus generation metadata

Recommendation:

- phase 1 generation should favor downloaded artifact mode for slide deck, report, and video because it makes outputs usable by downstream RAGenius workflows

## Policy Model

NotebookLM should be integrated into the existing typed policy model, not as ad hoc provider logic.

### Read-Like Operations

- `list_notebooks`
- `get_notebook`
- `list_sources`
- `ask`

Expected policy:

- allowed under read-oriented external capability rules
- no confirmation by default

### Write/Mutation Operations

- `add_source_text`
- `add_source_file`
- `add_source_url`

Expected policy:

- `review_required`
- explicit `external_api.write`
- confirmation policy configurable

### Generation Operations

- `generate_slide_deck`
- `generate_report`
- `generate_video`

Expected policy:

- `review_required`
- explicit `external_api.write`
- artifact persistence governed by `artifact.write`

## Retry And Fallback Policy

NotebookLM should not start with broad fallback behavior.

Recommended initial rule:

- no alternate provider fallback
- explicit, classified adapter errors only
- limited retry on transient transport failures

Special case:

- `add_source_text` is documented as non-idempotent and must not be blindly retried

This should be formalized in policy metadata rather than left implicit in adapter code.

## Error Model

The adapter should normalize errors into classes RAGenius can reason about:

- auth/config errors
- notebook not found
- source not found
- permission errors
- rate limit errors
- unsupported feature or drift errors
- generation timeout or pending state

The runtime should not expose raw cookies, storage JSON, or browser-derived session details.

## Observability

Execution records should capture:

- provider id: `notebooklm`
- tool id
- execution path: `adapter`
- whether downloaded output was persisted as a RAGenius artifact
- notebook id
- source ids when relevant
- generation task id when relevant

Logs and diagnostics should show:

- which NotebookLM capabilities are configured
- adapter health
- recent execution outcomes
- generation success/failure rates by tool

## Configuration Model

The execution subsystem should expose typed config for the NotebookLM adapter, for example:

- enabled/disabled
- auth source mode
  - env JSON
  - profile
  - storage path
- allowed operations
- allowed generation variants
- wait/download behavior defaults

Builder/admin visibility should show:

- NotebookLM adapter configured or not
- supported capability aliases
- which runtime tools are enabled
- auth health without leaking secrets

## Security And Risk Notes

This integration is higher risk than official Google MCP integrations because it is unofficial and session-based.

Operators should be made aware of:

- undocumented upstream APIs may drift
- auth material is session/cookie-like and must remain runtime-only
- generation outputs may contain user data and should flow through normal artifact governance

This argues for:

- explicit enablement
- explicit policy
- clear diagnostics
- narrow initial capability scope

## Suggested Workflow Shapes

These workflow shapes are recommended defaults for early RAGenius support.

They are meant to:

- guide Builder normalization
- define the first deterministic workflow families
- provide safe, reviewed patterns for common NotebookLM tasks

They are not meant to:

- forbid other NotebookLM-based skill designs
- force every NotebookLM skill into one fixed sequence
- imply that the adapter seam only supports these exact compositions

The intended boundary is:

- the adapter seam defines supported NotebookLM capabilities
- policy defines what is allowed
- Builder may initially normalize only a smaller set of first-class workflow families
- more custom compositions may still be supported through explicit workflow/schema contracts even before Builder inference catches up

So users may still design NotebookLM skills that compose the exposed capabilities in other ways, provided those workflows stay within the published tool contracts and policy boundaries.

### Existing Notebook Q&A Workflow

1. select notebook
2. optionally inspect sources
3. ask question
4. return answer and references

### RAGenius Artifact To NotebookLM Workflow

1. produce artifact in `ragenius_app` or another workflow
2. pass `artifactId` into NotebookLM source import skill
3. adapter uploads artifact as NotebookLM source
4. return source summary

### NotebookLM Generation Workflow

1. identify notebook
2. optionally constrain source ids
3. trigger generation
4. wait for completion
5. download output
6. save output as RAGenius artifact
7. return artifact metadata and NotebookLM generation metadata

## Recommended Phase Order

### Phase 1

- `list_notebooks`
- `get_notebook`
- `list_sources`
- `ask`

### Phase 2

- `add_source_text`
- `add_source_file`
- `add_source_url`

### Phase 3

- `generate_slide_deck`
- `generate_report`
- `generate_video`

This sequence follows user value while keeping the first slice read-heavy and operationally safer.

## Why `generate_video` Belongs In Phase 3

Video generation is higher cost and more side-effecting than simple notebook reads, but it is clearly within the user-value path you described:

- ask questions
- send app-produced material into NotebookLM
- generate presentation-style outputs

It belongs in phase 3 alongside slide deck and report generation because all three depend on the same foundational pieces:

- notebook selection
- source import
- generation task handling
- output download and artifact persistence

## Recommended First Implementation Slice

The first practical implementation slice should be:

- adapter seam scaffolding
- runtime config for NotebookLM auth
- `adapter.notebooklm.list_notebooks`
- `adapter.notebooklm.list_sources`
- `adapter.notebooklm.ask`
- Builder alias support for those three capabilities

Reason:

- fastest path to user-visible value
- lowest write risk
- validates the Python bridge and auth story before source upload and generation

## Acceptance Criteria

This design should be considered ready for implementation when RAGenius can:

- list visible NotebookLM notebooks from the configured session
- ask a question against a selected notebook and return references
- import a RAGenius artifact into a notebook as a source
- generate and persist a slide deck, report, or video as a RAGenius artifact
- classify NotebookLM runs clearly in diagnostics and policy review

## Open Questions Resolved For This Design

- `notebooklm-py` should remain external, not vendored
- the seam should be adapter-based, not direct Node reimplementation
- phase 1 should use visible existing notebooks, not notebook creation first
- generation phase should include `notebooklm.generate_video`

## Next Step

The next step after this design is a concrete implementation plan for:

- the Python bridge/service shape
- runtime provider/tool contracts
- typed policy config additions
- Builder alias normalization for NotebookLM capabilities
