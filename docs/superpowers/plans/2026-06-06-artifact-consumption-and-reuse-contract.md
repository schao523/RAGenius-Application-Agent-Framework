# Artifact Consumption And Reuse Contract

## Goal

Define how stored artifacts are consumed by later execution turns so artifact reuse is:

- explicit
- type-safe
- policy-aware
- user-friendly

This contract extends the existing artifact creation and visibility work. It does not replace it.

## Problem

The current system is ahead on:

- artifact persistence
- artifact metadata normalization
- execution-turn artifact rendering
- artifact picker UX

But it is still incomplete on:

- how consumers should use an artifact after resolving `artifact_id`
- whether a consumer wants file content, inline content, or metadata
- which artifact types are reusable vs inspect-only
- how new provider outputs such as NotebookLM artifacts should participate in later turns

Without a consumption contract, different consumers will read artifact records ad hoc and drift into incompatible behavior.

## Design Principles

1. Users act on artifact objects, not raw ids.
2. Execution requests carry `artifact_id`; consumers never trust display labels.
3. Artifact consumption is driven by declared capabilities, not heuristics.
4. `file_path` is useful but not universally the right payload.
5. Reuse eligibility is per artifact type and per consumer/tool.
6. App scoping remains mandatory. No cross-app artifact reuse.

## Core Concepts

### 1. Stored Artifact

Persisted app-scoped object with stable metadata and optional file backing.

Examples:

- `chat_export`
- `google_drive_export`
- `notebooklm_report`
- `notebooklm_slide_deck`
- `notebooklm_video`

### 2. Artifact Consumption Mode

The form in which a consumer expects to use an artifact.

Allowed modes:

- `file_backed`
- `inline_text`
- `binary_payload`
- `metadata_only`

### 3. Artifact Resolver

A subsystem service that takes:

- `app_id`
- `artifact_id`
- optional consumption intent

and returns a normalized reusable view for downstream code.

## Artifact Type Contract

Each stored artifact type must declare:

- `artifact_type`
- `default_consumption_mode`
- `supported_consumption_modes`
- `reusable`
- `picker_visibility`
- `eligible_consumers`

Suggested shape:

```json
{
  "artifact_type": "notebooklm_report",
  "default_consumption_mode": "file_backed",
  "supported_consumption_modes": ["file_backed", "inline_text", "metadata_only"],
  "reusable": true,
  "picker_visibility": "selectable",
  "eligible_consumers": ["export", "future_markdown_processors"]
}
```

## Canonical Artifact Resolver Output

Consumers should not read raw stored artifact records directly. They should consume a normalized resolved object:

```json
{
  "artifact_id": "artifact_1780704681245",
  "artifact_type": "notebooklm_report",
  "display_name": "GPT-Application-Designer-report.md",
  "summary": "NotebookLM report generated from GPT Application Designer",
  "app_id": "2302c77b-3d82-4650-bd15-e0ff9c0faab7",
  "status": "ready",
  "consumption": {
    "default_mode": "file_backed",
    "supported_modes": ["file_backed", "inline_text", "metadata_only"],
    "resolved_mode": "file_backed"
  },
  "payload": {
    "file_path": "D:\\...\\artifact_...-GPT-Application-Designer-report.md",
    "mime_type": "text/markdown",
    "text_content": "# NotebookLM Report",
    "binary_content_base64": null,
    "metadata": {
      "notebook_id": "nb_1",
      "task_id": "task_1",
      "artifact_kind": "report"
    }
  },
  "provenance": {
    "created_by_execution_id": "execution_abc",
    "source_skill_id": "notebooklm_generate_report",
    "provider_origin": "notebooklm"
  }
}
```

Rules:

- `resolved_mode` must always be present
- `payload` fields may be sparse depending on artifact type
- consumers should rely on `resolved_mode`, not guess from fields

## Consumption Mode Semantics

### `file_backed`

Use when the consumer needs a concrete saved file.

Expected fields:

- `payload.file_path`
- optional `payload.mime_type`

Examples:

- slide deck export
- video export
- future local file-processing flows

### `inline_text`

Use when the consumer wants text content directly.

Expected fields:

- `payload.text_content`

Examples:

- markdown summarization
- future prompt-chaining tools

### `binary_payload`

Use when the consumer needs encoded bytes in-process.

Expected fields:

- `payload.binary_content_base64`
- `payload.mime_type`

Examples:

- Gmail attachment assembly when the provider requires inline base64

### `metadata_only`

Use when the consumer only needs bookkeeping or display information.

Expected fields:

- `payload.metadata`

Examples:

- inspector rendering
- status/reference UX

## Current Artifact-Type Rules

### `chat_export`

- default mode: `file_backed`
- supported modes:
  - `file_backed`
  - `inline_text`
  - `metadata_only`
- reusable: yes
- picker visibility: selectable
- eligible consumers:
  - export
  - future markdown/text processors
- not outbound-eligible for Gmail attachments

### `google_drive_export`

- default mode: `binary_payload`
- supported modes:
  - `binary_payload`
  - `file_backed`
  - `metadata_only`
- reusable: yes
- picker visibility: selectable
- eligible consumers:
  - gmail_attachments
  - export

### `file_inventory`

- default mode: `metadata_only`
- supported modes:
  - `metadata_only`
  - `inline_text`
- reusable: limited
- picker visibility: selectable
- eligible consumers:
  - debug
  - future audit/report flows

### `notebooklm_report`

- default mode: `file_backed`
- supported modes:
  - `file_backed`
  - `inline_text`
  - `metadata_only`
- reusable: yes
- picker visibility: selectable
- eligible consumers:
  - export
  - future markdown/text processors
- not outbound-eligible for Gmail attachments by default

### `notebooklm_slide_deck`

- default mode: `file_backed`
- supported modes:
  - `file_backed`
  - `metadata_only`
- reusable: yes
- picker visibility: selectable
- eligible consumers:
  - export
  - future presentation/file workflows
- not outbound-eligible for Gmail attachments until policy is updated

### `notebooklm_video`

- default mode: `file_backed`
- supported modes:
  - `file_backed`
  - `metadata_only`
- reusable: yes
- picker visibility: selectable
- eligible consumers:
  - export
  - future media/file workflows
- not outbound-eligible for Gmail attachments until policy is updated

## Consumer Contract

Each artifact-consuming tool or skill should declare:

- accepted artifact types
- required consumption mode
- max count if multiple

Suggested shape:

```json
{
  "consumer_id": "gmail_attachment_draft",
  "accepted_artifact_types": ["google_drive_export"],
  "required_consumption_mode": "binary_payload",
  "max_artifact_count": 10
}
```

Rules:

- the composer picker should filter by `accepted_artifact_types`
- the resolver should validate that the required consumption mode is supported
- if not supported, execution should fail with a validation error, not silently degrade

## Execution Turn Contract

When a later execution turn consumes artifacts:

- the composer submits stable artifact handles in the configured picker field
- the default picker field is `artifactIds`
- the app backend resolves selected artifacts before submitting to the execution subsystem
- the execution subsystem may still resolve `artifactIds` internally for providers that need raw payloads
- the transcript should show semantic reuse:
  - `Using 1 artifact: Quarterly Plan.pdf`
  - `Using 1 artifact: GPT-Application-Designer-report.md`

The turn should not expose raw ids unless the user opens the inspector.

## Implemented Execution Submission Contract

As of the app-side artifact reuse implementation, execution submissions use a two-layer contract.

### 1. Picker Input: `artifactIds`

`artifactIds` remains the stable user-selection field for attachment-style tools.

Example composer/runtime input:

```json
{
  "to": "alice@example.com",
  "subject": "Review",
  "body": "See attached.",
  "artifactIds": ["artifact_pdf"]
}
```

Rules:

- the frontend selects artifacts by object/display name, not by manual id entry
- the submitted value remains `artifact_id`
- the app backend validates each id against the current session artifact inventory
- missing or out-of-session artifacts fail before provider execution
- Gmail attachment flows keep `artifactIds` because the execution subsystem already resolves them to binary payloads under policy

### 2. Resolved Request Metadata: `artifactRefs`

Before submitting an execution request, the app backend enriches mapped input with `artifactRefs`.

Example:

```json
{
  "artifactRefs": [
    {
      "artifact_id": "artifact_pdf",
      "field_name": "artifactIds",
      "display_name": "Execution Summary.pdf",
      "artifact_type": "google_drive_export",
      "mime_type": "application/pdf",
      "file_path": "D:\\...\\Execution-Summary.pdf",
      "metadata_path": "D:\\...\\artifact_pdf.json",
      "consumption": {
        "default_mode": "binary_payload",
        "supported_modes": ["binary_payload", "file_backed", "metadata_only"],
        "resolved_mode": "binary_payload"
      }
    }
  ]
}
```

Rules:

- `artifactRefs` is request metadata, not the primary user input field
- `artifactRefs` is saved in `execution_intent.mapped_input`
- `artifactRefs` is forwarded to the execution subsystem for tools that can use richer metadata
- inspector renders `artifactRefs` as `Submitted artifact inputs`
- raw `artifact_id` remains available in details/debug views

### 3. Reuse Summary Metadata: `artifact_reuse`

The backend also adds compact reuse bookkeeping:

```json
{
  "artifact_reuse": {
    "fields": {
      "artifactIds": ["artifact_pdf"]
    },
    "artifact_count": 1
  }
}
```

Rules:

- `artifact_reuse.fields` records which execution input field consumed which artifact ids
- `artifact_reuse.artifact_count` records total resolved artifact refs
- this object is intended for inspector/debug/analytics, not provider execution

### 4. Field-Specific Consumption Mapping

Not every consuming tool should receive raw artifact ids.

Current implemented mapping:

- `artifactIds`: preserve artifact ids for subsystem/provider-side resolution
- non-`artifactIds` picker fields with `required_consumption_mode=file_backed`: replace the submitted field value with the resolved `file_path`
- unresolved file-backed artifacts fail before submission

Example:

```json
{
  "filePath": "artifact_export"
}
```

becomes:

```json
{
  "filePath": "D:\\...\\chat-export.md",
  "artifactRefs": [
    {
      "artifact_id": "artifact_export",
      "field_name": "filePath",
      "display_name": "Chat Export.md",
      "consumption": {
        "resolved_mode": "file_backed"
      }
    }
  ],
  "artifact_reuse": {
    "fields": {
      "filePath": ["artifact_export"]
    },
    "artifact_count": 1
  }
}
```

Future mappings should follow the same pattern:

- `inline_text`: map to explicit text-content fields only when the target tool declares that field
- `binary_payload`: keep provider-specific handling behind policy, usually not as raw frontend input
- `metadata_only`: map only to tools that explicitly accept artifact metadata

## UI Rules

### Composer

- selection by `display_name`
- optional secondary text:
  - `artifact_type`
  - `summary`
  - created time
- do not ask the user to type `artifact_id`

### Inspector

- show submitted artifact inputs separately from produced artifacts
- show resolved consumption mode
- show whether a submitted artifact was used as:
  - file
  - inline text
  - base64 payload
  - metadata
- label reused inputs as `Submitted artifact inputs`
- label execution outputs as `Produced artifacts`

## Error UX Rules

Artifact reuse failures must be visible as execution failures in the transcript.

Current behavior:

- failed `@exec` submissions create an assistant execution-error turn
- missing/out-of-session artifacts show a concrete backend message
- artifact-not-found guidance tells users to select a current-session artifact from Artifact Library
- unsupported consumption modes tell users to choose a compatible artifact

These failures should not disappear into only a global app error banner.

## Policy Rules

Policy remains the final authority on reuse.

Requirements:

- artifact type eligibility is enforced before provider execution
- outbound attachment policy stays explicit
- future enablement of NotebookLM artifacts for Gmail must be intentional

Current outbound attachment rule to preserve:

- allowed types: `google_drive_export`

## Backward Compatibility

During migration:

- existing artifact records remain valid
- existing consumers that read raw `content` may keep working temporarily
- new consumers should use the resolver
- old code paths should be migrated incrementally

## Non-Goals

This contract does not require:

- changing artifact id generation
- rewriting the artifact store backend
- enabling every artifact type for every consumer
- cross-app reuse

## Recommendation

The system should move to:

- one generic resolver
- explicit per-type consumption rules
- explicit per-consumer accepted modes

That is the clean boundary between artifact creation and artifact reuse.
