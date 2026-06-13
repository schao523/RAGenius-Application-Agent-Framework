# Google Docs MCP Read-Only Design

## Purpose

Add the first Google Docs MCP slice as a read-only provider family for architecture validation.

This slice is intentionally narrow:

- search/list Google Docs documents
- remote HTTP MCP transport
- shared OAuth2 bearer token
- no document mutation
- no document-content read yet

The goal is to validate that the Generic MCP Layer can onboard a second real provider family cleanly after Gmail.

## Scope

This slice will add:

- one Google Docs MCP provider family over remote HTTP
- one allowlisted read tool for searching/listing Docs
- Builder normalization support for a Google Docs read-only skill family
- one sample Docs search skill
- read-only execution through the existing `service_call` seam

This slice will not add:

- create/update/delete Docs
- document-content read by id
- Drive export/download
- attachment workflows
- Sheets support
- auto-finalization in Builder

## Goals

- prove that the MCP transport and provider onboarding model generalizes beyond Gmail
- keep the first Docs slice small, stable, and low-risk
- validate Builder normalization for a second real MCP provider family
- preserve explicit review/governance around provider-backed skills

## Non-Goals

- no Docs write behavior
- no Drive workflow
- no email attachment workflow
- no Sheets support in this slice

## Why Search/List First

Compared to content read or write support, `search/list documents`:

- has the smallest contract surface
- is the easiest place to validate discovery, allowlisting, permission mapping, and normalization
- does not require file export or content-shape normalization
- aligns well with current Builder and execution-subsystem maturity

This is the best first Docs slice for architecture validation.

## Capability Model

The first Google Docs MCP tool should be:

- `mcp.gdocs.search_documents`

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

Use the same remote HTTP MCP config style established for Gmail:

```json
[
  {
    "id": "gdocs",
    "transport": "http",
    "baseUrl": "https://<google-docs-mcp-endpoint>",
    "authTokenEnv": "GOOGLE_DOCS_MCP_ACCESS_TOKEN",
    "allowedToolNames": ["search_documents"],
    "enabled": true
  }
]
```

Runtime secret:

- `GOOGLE_DOCS_MCP_ACCESS_TOKEN`

No Builder-side secret storage should be introduced.

## Builder Normalization

Add a new narrow template family:

- `google_docs_read_operation`

Supported natural-language intent examples:

- search Google Docs
- list matching Google documents
- find Docs related to a topic

Builder behavior:

- infer `mcp.gdocs.search_documents`
- generate explicit input schema
- generate explicit output schema
- generate explicit workflow
- mark all Docs MCP contracts `review_required`
- never auto-finalize this provider family in the first slice

## Input Contract

Suggested first-pass input:

- `query`

Possible schema:

- `query: string`

Keep it intentionally minimal for the first slice.

## Output Contract

Expected output should return a normalized list of Docs metadata.

Suggested output:

- `results[]`

Each item should contain at least:

- `id`
- `title`

Optional normalized fields if the MCP server provides them cleanly:

- `url`
- `modifiedAt`
- `owner`

Minimum acceptable output:

- a stable `results[]` array with `id` and `title`

## Workflow Shape

No new workflow primitive is required.

Use:

- `service_call` to `mcp.gdocs.search_documents`

Flow:

1. validate input
2. `service_call` executes Docs search/list
3. end

This keeps the Docs slice aligned with the existing MCP-backed workflow model.

## Permission Model

`mcp.gdocs.search_documents` must be:

- `side_effecting = false`
- permission scope `external_api.read`

Even though the capability is read-only, Builder should still mark these contracts `review_required` in the first provider slice so operators can inspect the inferred contract and the provider/tool mapping before publish.

## Allowlist Rules

Only allowlist the first Docs read tool:

- `search_documents`

Anything else:

- not registered
- not invokable
- fails closed

This keeps the onboarding slice narrow and architecture-focused.

## Observability

Execution records should capture:

- provider id: `gdocs`
- tool id: `mcp.gdocs.search_documents`
- normalized result summary

Logs should prefer:

- tool id
- query
- result count
- execution state

Logs should avoid secret leakage.

## Error Handling

Add or reuse clear failure classes for:

- Docs provider missing
- Docs token missing/invalid
- Docs tool not allowlisted
- MCP discovery failure
- MCP tool call failure

Do not log bearer tokens.

## Testing Strategy

### Unit tests

- Docs search tool discovery when allowlisted
- read-only metadata classification
- Docs search result normalization

### Integration tests

- discover Docs tools through mocked HTTP MCP responses
- execute one Docs read-only sample skill end to end
- verify missing token fails cleanly
- verify non-allowlisted Docs tool is not exposed

### Sample skill

Add:

- `google_docs_search`

Input:

- `query`

Required tool:

- `mcp.gdocs.search_documents`

Permission:

- `external_api.read`

Result type:

- `json`

## Acceptance Criteria

This slice is complete when:

- `ragenius_execution_subsystem` can connect to a Google Docs MCP provider over HTTP
- bearer-token auth works through runtime env config
- Docs `tools/list` can be fetched and filtered
- `mcp.gdocs.search_documents` can be registered into the tool registry
- one Docs read-only skill executes successfully end to end
- Builder can normalize a Docs read-only skill draft as `review_required`
- tests cover discovery, execution, auth failure, and allowlist filtering

## Recommended Implementation Order

1. add Google Docs provider config usage
2. extend the MCP provider mapping for Docs search/list
3. add one sample Docs search skill
4. add Builder `google_docs_read_operation` normalization
5. add provider/unit/integration tests
6. update Docs MCP runtime documentation

## Recommendation

Stop after `search/list documents` for this slice.

The next Docs slice, if needed, should be:

- document-content read by id

Only after that should write/edit flows be considered.
