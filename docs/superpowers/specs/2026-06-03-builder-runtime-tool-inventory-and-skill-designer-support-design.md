# Builder Runtime Tool Inventory And Skill-Designer Support Design

## Purpose

Improve Builder and `ragenius_execution_subsystem` so skill designers can clearly understand:

- which integrations are configured
- which tools are actually available to runtime
- which author-facing aliases normalize into which runtime tools
- what default input/output contracts Builder can infer
- what gaps still require explicit `Skill.md` schema details

The current subsystem view is too MCP-centric. It surfaces MCP provider state well, but it does not give skill designers a complete view of adapter-backed integrations such as NotebookLM, nor does it explain normalization coverage in a way that helps author skills confidently.

## Problem Statement

Today:

- Builder subsystem diagnostics focus on MCP providers and discovered MCP tools.
- NotebookLM is runtime-supported, but it is adapter-backed rather than MCP-backed, so it is effectively invisible in the same diagnostics surface.
- Builder test pages show generated input JSON, but they do not explain why a given field appears, whether it came from explicit schema or inferred defaults, or whether a skill is using a known normalization family.
- Skill designers cannot easily answer:
  - "Can I use this tool in a skill today?"
  - "Will Builder infer the right contract from `required_tools` alone?"
  - "What inputs are expected if I use this alias?"
  - "Is this tool read-only, write-capable, fallback-capable, or confirmation-gated?"

This creates a design-time blind spot. Runtime and normalization capabilities exist, but they are not surfaced in a skill-designer-friendly way.

## Goals

- show all runtime tool families, not just MCP
- make NotebookLM and other adapter-backed integrations first-class in Builder diagnostics
- expose normalization coverage as a design aid for skill authors
- show inferred default contracts before a skill is published
- distinguish between:
  - configured integration
  - enabled runtime tool
  - Builder-supported normalization family
  - actual execution path and fallback path

## Non-Goals

- not a full end-user `ragenius_app` design
- not a generic graphical workflow builder
- not a replacement for `Skill.md` authoring
- not a live schema editor for every runtime tool in phase 1

## User Types

### Skill Designer

Primary target for this work.

Needs to know:

- what aliases are supported
- what tool contracts exist
- whether Builder can infer a contract automatically
- what fields Builder will generate for testing
- when explicit `Input Schema` and `Expected Output` are still necessary

### Operator / Admin

Secondary target.

Needs to know:

- whether integrations are configured and healthy
- whether runtime tool discovery or allowlisting is broken
- whether executions are using MCP, adapter, local, or fallback paths

## Core Design Principle

The Builder surface should explain runtime capabilities in the language of skill design, not only infrastructure.

The UI should answer four questions in order:

1. What integrations exist?
2. What tools do they expose?
3. What aliases and workflow families can Builder infer from them?
4. What will the runtime contract look like if I design a skill with them?

## Proposed Information Model

Builder should distinguish five layers:

### 1. Integration

A configured external or internal capability family, such as:

- Gmail MCP
- Google Drive MCP
- Google Docs MCP
- NotebookLM adapter
- research paper provider
- OpenAI provider

An integration is not always MCP-backed.

### 2. Tool

A concrete runtime tool id, such as:

- `mcp.gdrive.download_file_content`
- `mcp.gmail.create_draft_with_attachments`
- `adapter.notebooklm.ask`
- `adapter.notebooklm.generate_video`

### 3. Author Alias

A skill-author-facing alias, such as:

- `gmail.create_draft_with_attachments`
- `drive.download_file`
- `notebooklm.ask`
- `notebooklm.generate_video`

### 4. Normalization Family

A Builder-known contract family, such as:

- `gmail_attachment_draft_operation`
- `notebooklm_existing_notebook_ask_operation`
- `notebooklm_generate_video_operation`

### 5. Execution Path

How runtime actually executed the tool:

- `mcp`
- `adapter`
- `local`
- `api`
- `rest_fallback`

## Proposed Builder UX

## A. Replace MCP-Only Runtime Status With Integration Inventory

Rename or expand the current subsystem section from "MCP Runtime Status" to:

- `Runtime Integration Inventory`

It should include separate panels for:

- MCP integrations
- adapter-backed integrations
- local/runtime-native tool families
- API-backed providers

Each integration row should show:

- integration id
- family
  - `mcp`
  - `adapter`
  - `local`
  - `api`
  - `rag_adapter`
- configured
- enabled
- auth configured
- startup/discovery state if applicable
- tool count
- health / last error
- refresh action if applicable

NotebookLM should appear here as:

- integration id: `notebooklm`
- family: `adapter`
- configured: yes/no
- enabled: yes/no
- allowed operations
- exposed runtime tools

## B. Add Tool Inventory Table

Add a new subsystem section:

- `Runtime Tool Inventory`

This table should be filterable by:

- integration family
- provider/integration id
- side-effecting vs read
- normalization-supported vs unsupported
- fallback-capable vs direct only

Each tool row should show:

- tool id
- family
- integration/provider id
- enabled
- policy class
- confirmation expectation
- fallback-capable
- timeout
- normalization support

For phase 1, the table can be server-rendered and filterable with query params or simple client-side filtering.

## C. Add Alias And Family Coverage Matrix

Add a Builder section:

- `Skill Authoring Coverage`

This is the skill-designer-specific view.

Each row should show:

- author alias
- resolved runtime tool(s)
- normalization family
- contract source
  - `explicit schema required`
  - `default family inference supported`
  - `partial inference only`
- default policy class
- notes

Examples:

- `notebooklm.generate_video`
  - resolved tool: `adapter.notebooklm.generate_video`
  - family: `notebooklm_generate_video_operation`
  - contract source: `default family inference supported`
  - policy: `review_required`
  - note: `supports notebookId or notebookTitle`

- `adapter.my_custom_provider.do_complex_thing`
  - family: `unsupported`
  - contract source: `explicit schema required`

This is the most important view for skill designers.

## D. Add "Why This Test Input Was Generated" To Skill Test / Review Surfaces

On the skill detail/test page, show a compact contract explanation panel:

- inferred family
- inferred from
  - `required_tools`
  - alias match
  - explicit `Input Schema`
  - explicit `Expected Output`
- generated sample input rules
  - `required`
  - `conditional anyOf`
  - `defaults`

For the NotebookLM video case, the UI should explain:

- `instructions` came from required fields
- `notebookTitle` came from conditional `anyOf` preference
- `language`, `waitForCompletion`, `persistArtifacts` came from defaults

This removes confusion about why the test JSON looks the way it does.

## E. Add Tool Contract Preview For Supported Families

When viewing a skill or selecting a supported alias/tool, Builder should show:

- inferred input schema
- inferred output schema
- inferred workflow shape
- required permissions
- expected execution path

This does not require a new workflow editor. It is a read-only preview for confidence.

## Backend Requirements

Builder currently has good MCP-specific data, but it needs broader runtime metadata.

## 1. Add Runtime Integration Status Endpoint

New runtime endpoint:

- `GET /v1/runtime/integrations`

Returns:

- integrations grouped by family
- provider/adapter configuration summary
- enabled status
- auth/config summary
- exposed tool ids
- integration-specific metadata

Example NotebookLM integration object:

```json
{
  "id": "notebooklm",
  "family": "adapter",
  "configured": true,
  "enabled": true,
  "auth_configured": true,
  "allowed_operations": [
    "list_notebooks",
    "ask",
    "generate_video"
  ],
  "tool_ids": [
    "adapter.notebooklm.list_notebooks",
    "adapter.notebooklm.ask",
    "adapter.notebooklm.generate_video"
  ],
  "health": {
    "status": "ready",
    "last_error": null
  }
}
```

## 2. Add Runtime Tool Inventory Endpoint

New runtime endpoint:

- `GET /v1/tools/inventory`

Returns normalized tool metadata across all provider families:

- tool id
- family
- provider/integration id
- enabled
- sideEffecting
- permissionScopes
- timeoutMs
- metadata.policyClass
- metadata.providerId
- fallback metadata when relevant

This endpoint should be derived from the actual registered tool registry plus runtime config, not hand-maintained separately.

## 3. Add Builder Normalization Coverage Endpoint or Internal View Model

Builder needs a coverage model assembled from:

- `AUTHOR_TOOL_ALIAS_MAP`
- family inference tables in `skill_normalization.py`
- family policy metadata in `policy.py`

This can remain internal to Builder initially and does not need a new runtime endpoint.

The view model should include:

- alias
- resolved tools
- inferred family
- inference support level
- default policy class
- notes

## 4. Extend Recent Diagnostics With Integration Family

Recent execution diagnostics already track execution path and provider/tool use.
Add or ensure availability of:

- integration family
- integration id
- tool family summary

This helps Builder correlate design-time support with runtime behavior.

## Skill-Designer-Focused UX Rules

- Prefer "integration" and "tool" over raw infrastructure terms when possible.
- Show aliases and family inference before low-level implementation details.
- Keep infrastructure diagnostics available, but secondary.
- Clearly label unsupported cases:
  - `Builder cannot infer full contract from required_tools alone`
- Prefer explanation text over silent omission.

## NotebookLM-Specific Requirements

The new surfaces must make NotebookLM visible as a supported integration.

At minimum:

- NotebookLM appears in Integration Inventory
- NotebookLM tools appear in Tool Inventory
- NotebookLM aliases appear in Skill Authoring Coverage
- NotebookLM family previews explain:
  - `notebookId` or `notebookTitle`
  - title resolution behavior
  - default generation fields
  - `waitForCompletion` implications

## Phased Rollout

### Phase 1

- Runtime Integration Inventory endpoint
- Runtime Tool Inventory endpoint
- Builder subsystem UI expanded beyond MCP
- Skill Authoring Coverage section

### Phase 2

- Skill test/review explanation panel for generated input JSON
- Tool contract preview for supported families

### Phase 3

- richer filtering/search
- app-specific diagnostics slicing
- explicit unsupported/custom-tool guidance in skill import/review UI

## Acceptance Criteria

- A skill designer can see NotebookLM in Builder without knowing it is adapter-backed.
- A skill designer can tell whether a tool/alias is normalization-supported.
- A skill designer can tell whether `required_tools` alone is enough for a given family.
- The subsystem page no longer implies MCP is the only integration model.
- The skill test page can explain why a generated field appears in sample input JSON.
- Unsupported or partially supported authoring cases are visibly labeled.

## Risks

- Tool metadata can become too infrastructure-heavy if not curated for Builder UX.
- Coverage labeling must stay synced with normalization logic.
- Overly generic "support" labels could mislead authors about custom workflows.

## Mitigations

- derive Builder coverage from existing normalization maps where possible
- prefer conservative support labels
- distinguish:
  - fully inferred
  - partially inferred
  - explicit schema required

## Recommendation

Implement this as a Builder/runtime diagnostics expansion aimed first at skill designers, with MCP folded into a broader integration inventory rather than kept as the only mental model.
