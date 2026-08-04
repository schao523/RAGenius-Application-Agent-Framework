# Phase 3.2 Design: Gmail Draft Creation With Confirmation Gating

## Purpose

Phase 3.2 extends the Phase 3.1 Gmail MCP slice from read-only access to the first controlled write path:

- Gmail draft creation
- still through remote HTTP MCP
- still using a shared integration identity
- always confirmation-gated at runtime

This is intentionally narrower than full outbound email support.

## Scope

Phase 3.2 will add:

- one write-capable Gmail action: `create_draft`
- Builder normalization support for Gmail draft skills as `review_required`
- runtime permission classification as `external_api.write`
- confirmation gating before draft creation executes
- execution persistence and audit visibility for the draft-creation path

Phase 3.2 will not add:

- send message
- update draft
- delete draft
- per-user Gmail identity
- auto-finalization of Gmail write contracts in Builder

## Goals

- add one real side-effecting Gmail MCP path safely
- reuse the existing review + confirmation model
- preserve explicit tool ids and app isolation
- keep the first write slice auditable and reversible in practice

## Non-Goals

- no direct outbound email send
- no freeform arbitrary Gmail operations
- no broad Gmail write surface
- no bypass of runtime confirmation

## Capability Model

The first write-capable Gmail tool should be:

- `mcp.gmail.create_draft`

Builder contract:

- explicit required tool
- explicit input schema
- explicit workflow
- `review_required`

Runtime contract:

- side-effecting tool
- permission scope `external_api.write`
- `require_confirmation` expected before execution

## Why Draft Creation First

Compared to `send message`, draft creation:

- does not transmit to external recipients
- keeps a user-reviewable artifact in Gmail
- reduces accidental harm
- fits the current subsystem’s maturity much better

So the risk envelope is:

- real external write side effect
- but not irreversible outbound communication

That is the right first Gmail write step.

## Configuration Model

Continue using the same Gmail MCP runtime config:

```json
[
  {
    "id": "gmail",
    "transport": "http",
    "baseUrl": "https://gmailmcp.googleapis.com/mcp/v1",
    "authTokenEnv": "GMAIL_MCP_ACCESS_TOKEN",
    "allowedToolNames": ["search_messages", "create_draft"],
    "enabled": true
  }
]
```

Runtime secret remains:

- `GMAIL_MCP_ACCESS_TOKEN`

No new secret model is required.

## Builder Normalization

Add a new narrow template family:

- `gmail_draft_operation`

Supported natural-language intent examples:

- create a draft email
- draft a follow-up email
- prepare an email draft in Gmail

Builder behavior:

- infer `mcp.gmail.create_draft`
- generate explicit input schema
- generate explicit output schema
- generate explicit workflow
- always mark `review_required`
- never auto-finalize

## Input Contract

Minimum draft input should be explicit and structured.

Suggested first-pass input:

- `to`
- `subject`
- `body`

Possible schema:

- `to: string`
- `subject: string`
- `body: string`

If the Gmail MCP server requires a different shape, the runtime contract should follow the real tool schema, but Builder normalization should still target a stable minimal shape that maps cleanly onto it.

## Output Contract

Expected draft result should return enough information to audit success.

Suggested output:

- `id`
- `threadId` if available
- `status`
- possibly normalized draft metadata

Minimum acceptable output:

- draft id plus a stable success shape

## Workflow Shape

No new workflow primitive is needed.

Use:

- `service_call` to `mcp.gmail.create_draft`

Flow:

1. validate input
2. pending confirmation if permission requires it
3. `service_call` executes draft creation
4. end

This stays aligned with the current workflow architecture.

## Permission And Confirmation Model

`mcp.gmail.create_draft` must be:

- `side_effecting = true`
- permission scope `external_api.write`

Expected runtime behavior:

- without prior confirmation, execution becomes `pending_confirmation`
- after confirmation, the same persisted execution resumes and completes

This mirrors the Phase 2 mutation model and the existing Phase 3 write-like MCP tests.

## Allowlist Rules

Phase 3.2 should still not expose all Gmail write tools.

Allowlist remains explicit:

- `search_messages`
- `create_draft`

Anything else:

- not registered
- not invokable
- fails closed

That keeps the Gmail write surface intentionally tiny.

## Observability

Execution records should capture:

- provider id: `gmail`
- tool id: `mcp.gmail.create_draft`
- pending-confirmation state
- confirmed completion state
- normalized result summary

No sensitive draft body content should be sprayed into logs unnecessarily. Logging should prefer:

- tool id
- draft id
- execution state
- non-sensitive summary fields

## Error Handling

Add or reuse clear failure classes for:

- Gmail provider missing
- Gmail token missing/invalid
- draft tool not allowlisted
- MCP tool call failure
- confirmation required

Do not log bearer tokens or raw message body unnecessarily.

## Test Strategy

### Unit tests

- Gmail write tool discovery when allowlisted
- side-effecting metadata classification
- draft call result normalization

### Integration tests

- discover Gmail tools with `create_draft` allowlisted
- execute draft skill and receive `pending_confirmation`
- confirm execution and complete successfully
- verify non-allowlisted Gmail write tool is blocked
- verify missing token fails cleanly

### Sample skill

Add:

- `gmail_create_draft`

Input:

- `to`
- `subject`
- `body`

Required tool:

- `mcp.gmail.create_draft`

Permission:

- `external_api.write`

Result type:

- `json`

## Acceptance Criteria

Phase 3.2 is complete when:

- Gmail draft creation can be discovered and registered from MCP
- Builder can normalize Gmail draft skills into explicit `review_required` contracts
- draft execution returns `pending_confirmation` before side effects
- confirmed execution creates a Gmail draft successfully
- execution records persist the confirmation lifecycle
- tests cover discovery, confirmation, completion, and allowlist failure

## Recommended Implementation Order

1. extend Gmail allowlist/config to support `create_draft`
2. map Gmail draft tool metadata as side-effecting write
3. add Builder `gmail_draft_operation` normalization
4. add sample `gmail_create_draft` skill
5. add confirmation/resume execution test
6. document Gmail write scope and confirmation rules

## Recommendation

Phase 3.2 should stop at `create draft`.

The next slice after that, if needed, should be:

- **Phase 3.3: Gmail send message with stricter confirmation and stronger audit rules**
