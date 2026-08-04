# Google Drive MCP Export/Read Design

## Purpose

Add the second Google Drive MCP slice as a controlled export/read capability that builds on Drive file discovery and creates the missing bridge toward future Gmail attachment workflows.

This slice is intentionally narrower than a full file-transfer subsystem:

- export or read one Drive file by id
- remote HTTP MCP transport
- shared OAuth2 bearer token
- read-only behavior only
- no Drive mutation
- no Gmail attachment send yet

The goal is to move from "find the file" to "safely materialize file content or an export artifact" without broadening into arbitrary file access.

## Scope

This slice will add:

- one read-only Drive-by-id capability over the existing `gdrive` MCP provider family
- one allowlisted export/read tool
- Builder normalization support for a Google Drive export/read skill family
- one sample Drive export/read skill
- artifact-oriented output suitable for later handoff into attachment-capable workflows

This slice will not add:

- file mutation or upload
- arbitrary local filesystem download targets
- Gmail attachment sending
- automatic export of every Google type or MIME variant
- auto-finalization in Builder

## Goals

- extend the Generic MCP Layer from metadata discovery to controlled file materialization
- keep the read surface bounded, explicit, and auditable
- preserve Builder review/governance around provider-backed contracts
- prepare a clean next step for Gmail attachment-capable draft/send workflows

## Non-Goals

- no Drive write behavior
- no arbitrary bulk export
- no cross-app artifact leakage
- no direct email attachment support in this slice

## Why Export/Read Next

Drive search/list already gives the system:

- file ids
- file metadata
- a reviewed, explicit discovery contract

The missing capability for attachment workflows is:

- controlled retrieval or export of the selected file's content into a runtime-owned artifact

That is the right next slice because it adds the minimum new power needed after discovery.

## Capability Model

The next Drive MCP tool should use the official managed Drive MCP server's published read/download capability:

- `mcp.gdrive.download_file_content`

Reason:

- it is an official documented tool on the managed Drive MCP server
- it is the most direct bridge from file discovery to later attachment workflows
- it fits artifact-oriented output better than treating the provider as a general inline-content reader

Builder contract:

- explicit required tool
- explicit input schema
- explicit output schema
- explicit workflow
- `review_required`

Runtime contract:

- non-side-effecting tool
- permission scope `external_api.read`
- result should be normalized into artifact-oriented output

## Configuration Model

Continue using the existing `gdrive` provider family and token:

```json
[
  {
    "id": "gdrive",
    "transport": "http",
    "baseUrl": "https://drivemcp.googleapis.com/mcp/v1",
    "authTokenEnv": "GOOGLE_DRIVE_MCP_ACCESS_TOKEN",
    "allowedToolNames": ["search_files", "download_file_content"],
    "enabled": true
  }
]
```

Runtime secret:

- `GOOGLE_DRIVE_MCP_ACCESS_TOKEN`

No Builder-side secret storage should be introduced.

## Supported Read Shapes

The first export/read slice should be intentionally selective.

Recommended initial support:

- one file id at a time
- one explicit download/export request at a time

Possible input shape:

- `fileId`
- optional format/export hint only if the actual Drive MCP contract exposes one

Recommended first-pass restriction:

- follow the official MCP tool schema exactly
- if the tool supports format/export hints, allow only a small approved set and reject unsupported ones early
- if the tool does not expose format selection, do not invent it at the Builder contract layer

## Output Contract

The result should be normalized for later workflow handoff rather than just dumping raw provider output.

Suggested output:

- `artifact_id`
- `file_id`
- `name`
- `mime_type`
- `format`
- optional `size_bytes`

Alternative if the MCP server returns inline text only:

- still persist it via `save_artifact` rather than returning large raw payloads directly

Recommendation:

- materialize exported content into app-scoped artifact storage
- return artifact metadata as the skill result

That keeps the runtime contract stable and attachment-friendly.

## Workflow Shape

The most reasonable workflow is:

1. validate input
2. `service_call` to Drive export/read tool
3. `save_artifact`
4. end

This means the skill result is not just remote provider output; it becomes a durable runtime artifact for later steps.

## Builder Normalization

Add a new narrow template family:

- `google_drive_export_operation`

Supported natural-language intent examples:

- export a Google Drive file
- read a Drive file by id
- prepare a Drive document as an artifact

Builder behavior:

- infer `mcp.gdrive.download_file_content`
- generate explicit input schema
- generate explicit output schema
- generate explicit workflow that includes artifact persistence
- mark all Drive export/read contracts `review_required`
- never auto-finalize this provider family in the first slice

## Permission Model

The Drive export/read tool must be:

- `side_effecting = false`
- permission scope `external_api.read`

The artifact save step remains:

- `artifact.write`

So the full contract may require:

- `external_api.read`
- `artifact.write`

Even though the provider action is read-only, the overall skill still produces stored artifacts and should remain review-required.

## Allowlist Rules

Only allowlist the specific export/read tool needed for this slice:

- `download_file_content`

Anything else:

- not registered
- not invokable
- fails closed

This prevents the Drive provider from suddenly becoming a broad file-access surface.

## Artifact Strategy

Exported content should not be written to arbitrary filesystem paths.

Instead:

- the execution subsystem stores exported content in app-scoped artifact storage
- later Gmail attachment workflows consume those artifacts explicitly

This preserves:

- app isolation
- auditability
- workflow composability

## Future Attachment Path

This slice is the intended bridge to future Gmail attachment workflows.

Planned progression:

1. Drive search/list files
2. Drive export/read into artifacts
3. Gmail draft/send with attachment-capable artifact references

So the output contract for this slice should be chosen with that next step in mind.

## Observability

Execution records should capture:

- provider id: `gdrive`
- tool id: chosen export/read tool
- file id
- artifact id
- execution state

Logs should avoid:

- bearer tokens
- large raw file payloads

## Error Handling

Add or reuse clear failure classes for:

- Drive provider missing
- Drive token missing/invalid
- Drive export/read tool not allowlisted
- unsupported export format
- MCP discovery failure
- MCP tool call failure
- artifact persistence failure

Do not log raw file contents unnecessarily.

## Testing Strategy

### Unit tests

- Drive export/read tool discovery when allowlisted
- read-only classification
- export result normalization
- export-format allowlist enforcement

### Integration tests

- discover Drive export/read tool through mocked HTTP MCP responses
- execute one export/read sample skill end to end
- verify missing token fails cleanly
- verify non-allowlisted export/read tool is not exposed
- verify result is persisted to artifact storage, not arbitrary filesystem paths

### Sample skill

Add:

- `google_drive_download_file`

Input:

- `fileId`
- optional format/export hint only if supported by the real tool contract

Required tools:

- `mcp.gdrive.download_file_content`
- `save_artifact`

Permissions:

- `external_api.read`
- `artifact.write`

Result type:

- `json`

## Acceptance Criteria

This slice is complete when:

- runtime can discover one allowlisted Drive export/read tool
- one Drive file can be exported/read by id through the MCP seam
- exported content is stored in app-scoped artifact storage
- Builder can normalize natural export/read skills into explicit `review_required` contracts
- tests cover discovery, execution, auth failure, format validation, and artifact persistence

## Recommended Implementation Order

1. choose the exact Drive export/read tool name from the MCP server contract
2. extend `gdrive` allowlisting and output normalization
3. add Builder `google_drive_export_operation` normalization
4. add sample export/read skill
5. wire artifact persistence into the workflow
6. add unit and integration coverage
7. document Drive export/read setup and its attachment-oriented purpose

## Recommendation

Keep the first export/read slice narrow:

- one file at a time
- one reviewed official tool
- one bounded format policy
- artifact output only

The next logical follow-up after this slice is:

- **Gmail attachment-capable draft design**
