# Google Drive MCP Read-Only Design

## Purpose

Add the first Google Drive MCP slice as a read-only provider family for architecture validation and future attachment workflows.

This slice is intentionally narrow:

- search/list Google Drive files
- remote HTTP MCP transport
- shared OAuth2 bearer token
- no file download/export yet
- no file mutation

The goal is to validate that the Generic MCP Layer can onboard a file-oriented provider family cleanly after Gmail and Google Docs, while also laying groundwork for later Gmail attachment flows.

## Scope

This slice will add:

- one Google Drive MCP provider family over remote HTTP
- one allowlisted read tool for searching/listing Drive files
- Builder normalization support for a Google Drive read-only skill family
- one sample Drive search skill
- read-only execution through the existing `service_call` seam

This slice will not add:

- file download by id
- export of Docs/Sheets/Slides content
- file mutation or upload
- Gmail attachment workflows
- auto-finalization in Builder

## Goals

- prove that the MCP transport and provider onboarding model generalizes to a file-oriented Google provider
- keep the first Drive slice small, stable, and low-risk
- validate Builder normalization for another real MCP provider family
- establish the discovery layer needed for future attachment-oriented workflows

## Non-Goals

- no Drive write behavior
- no file content retrieval
- no Docs export pipeline
- no Gmail attachment workflow in this slice
- no Sheets or Calendar support in this slice

## Why Search/List First

Compared to download/export or write support, `search/list files`:

- has the smallest contract surface
- is the easiest place to validate discovery, allowlisting, permission mapping, and normalization
- creates immediate value for later attachment workflows by establishing file discovery and metadata lookup
- does not require content-shape normalization or file transport handling yet

This is the best first Drive slice for architecture validation and future attachment readiness.

## Capability Model

The first Google Drive MCP tool should be:

- `mcp.gdrive.search_files`

Builder contract:

- explicit required tool
- explicit input schema
- explicit output schema
- explicit workflow
- `review_required`

Runtime contract:

- non-side-effecting tool
- permission scope `external_api.read`

## Configuration Model

Use the same remote HTTP MCP config style established for Gmail and Docs:

```json
[
  {
    "id": "gdrive",
    "transport": "http",
    "baseUrl": "https://<google-drive-mcp-endpoint>",
    "authTokenEnv": "GOOGLE_DRIVE_MCP_ACCESS_TOKEN",
    "allowedToolNames": ["search_files"],
    "enabled": true
  }
]
```

Runtime secret:

- `GOOGLE_DRIVE_MCP_ACCESS_TOKEN`

No Builder-side secret storage should be introduced.

## Builder Normalization

Add a new narrow template family:

- `google_drive_read_operation`

Supported natural-language intent examples:

- search Google Drive files
- list matching Drive files
- find files in Google Drive related to a topic

Builder behavior:

- infer `mcp.gdrive.search_files`
- generate explicit input schema
- generate explicit output schema
- generate explicit workflow
- mark all Drive MCP contracts `review_required`
- never auto-finalize this provider family in the first slice

## Input Contract

Suggested first-pass input:

- `query`

Possible schema:

- `query: string`

Keep it intentionally minimal for the first slice.

## Output Contract

Expected output should return a normalized list of Drive file metadata.

Suggested output:

- `results[]`

Each item should contain at least:

- `id`
- `name`

Optional normalized fields if the MCP server provides them cleanly:

- `mimeType`
- `webViewLink`
- `modifiedAt`
- `owners`

Minimum acceptable output:

- a stable `results[]` array with `id` and `name`

## Workflow Shape

No new workflow primitive is required.

Use:

- `service_call` to `mcp.gdrive.search_files`

Flow:

1. validate input
2. `service_call` executes Drive search/list
3. end

This keeps the Drive slice aligned with the existing MCP-backed workflow model.

## Permission Model

`mcp.gdrive.search_files` must be:

- `side_effecting = false`
- permission scope `external_api.read`

Even though the capability is read-only, Builder should still mark these contracts `review_required` in the first provider slice so operators can inspect the inferred contract and the provider/tool mapping before publish.

## Allowlist Rules

Only allowlist the first Drive read tool:

- `search_files`

Anything else:

- not registered
- not invokable
- fails closed

This keeps the onboarding slice narrow and architecture-focused.

## Future Attachment Path

This slice is intentionally not an attachment feature, but it should make the next slices cleaner.

Planned progression:

1. Drive read-only file discovery
2. Drive controlled export/download for supported file types
3. Gmail attachment-capable draft/send workflows using approved Drive file references

So the first Drive slice should preserve stable file ids and metadata needed for later export and attachment workflows.

## Observability

Execution records should capture:

- provider id: `gdrive`
- tool id: `mcp.gdrive.search_files`
- normalized result summary

Logs should prefer:

- tool id
- query
- result count
- execution state

Logs should avoid secret leakage.

## Error Handling

Add or reuse clear failure classes for:

- Drive provider missing
- Drive token missing/invalid
- Drive tool not allowlisted
- MCP discovery failure
- MCP tool call failure

Do not log bearer tokens.

## Testing Strategy

### Unit tests

- Drive search tool discovery when allowlisted
- read-only metadata classification
- Drive search result normalization

### Integration tests

- discover Drive tools through mocked HTTP MCP responses
- execute one Drive read-only sample skill end to end
- verify missing token fails cleanly
- verify non-allowlisted Drive tool is not exposed

### Sample skill

Add:

- `google_drive_search`

Input:

- `query`

Required tool:

- `mcp.gdrive.search_files`

Permission:

- `external_api.read`

Result type:

- `json`

## Acceptance Criteria

This slice is complete when:

- runtime can discover Google Drive tools through the generic MCP layer
- only allowlisted Drive read tools are registered
- at least one Drive read-only skill executes successfully end to end
- Builder can normalize natural Drive search/list skills into explicit `review_required` contracts
- tests cover discovery, execution, auth failure, and allowlist filtering

## Recommended Implementation Order

1. add the `gdrive` provider family to runtime MCP config assumptions
2. allowlist and map `search_files`
3. add Builder `google_drive_read_operation` normalization
4. add sample `google_drive_search` skill
5. add unit and integration coverage
6. document Drive MCP runtime setup and the future attachment path

## Recommendation

Stop at Drive search/list in the first slice.

The next logical follow-up after this slice is:

- **Google Drive export/read design**

That is the point where the system can start building toward real Gmail attachment workflows.
