# Phase 3.3 Design: Gmail Draft Sending With Confirmation Gating

## Purpose

Phase 3.3 extends the Gmail MCP slice from draft creation to the first controlled outbound send path:

- send an existing Gmail draft
- still through remote HTTP MCP
- still using a shared integration identity
- always confirmation-gated at runtime

This phase keeps the draft-review boundary introduced in Phase 3.2 instead of allowing direct compose-and-send.

## Scope

Phase 3.3 will add:

- one new write-capable Gmail action: `send_draft`
- Builder normalization support for Gmail draft-send skills as `review_required`
- runtime permission classification as `external_api.write`
- confirmation gating before outbound send executes
- execution persistence and audit visibility for the draft-send path

Phase 3.3 will not add:

- direct `send_message`
- compose-and-send in one step
- update draft
- delete draft
- per-user Gmail identity
- auto-finalization of Gmail send contracts in Builder

## Goals

- add one real outbound Gmail MCP path safely
- preserve the draft-first workflow from Phase 3.2
- reuse the existing review + confirmation + resume model
- keep Gmail outbound send explicit, narrow, and auditable

## Non-Goals

- no direct freeform message send
- no broad Gmail outbound surface
- no bypass of prior draft creation or review
- no removal of explicit confirmation before send

## Why `send_draft` First

Compared to `send_message`, `send_draft`:

- reuses a previously created Gmail draft
- preserves a natural human review step before outbound delivery
- narrows the required input contract
- gives a cleaner audit trail across two explicit operations:
  - create draft
  - send draft

This keeps the outbound path aligned with the current subsystem maturity and safety posture.

## Capability Model

The Phase 3.3 Gmail send tool should be:

- `mcp.gmail.send_draft`

Builder contract:

- explicit required tool
- explicit input schema
- explicit output schema
- explicit workflow
- `review_required`

Runtime contract:

- side-effecting tool
- permission scope `external_api.write`
- `require_confirmation` expected before execution

## Configuration Model

Continue using the Gmail MCP runtime config and extend the allowlist:

```json
[
  {
    "id": "gmail",
    "transport": "http",
    "baseUrl": "https://gmailmcp.googleapis.com/mcp/v1",
    "authTokenEnv": "GMAIL_MCP_ACCESS_TOKEN",
    "allowedToolNames": ["search_messages", "create_draft", "send_draft"],
    "enabled": true
  }
]
```

Runtime secret remains:

- `GMAIL_MCP_ACCESS_TOKEN`

No new secret model is required.

## Builder Normalization

Add a narrow template family:

- `gmail_send_draft_operation`

Supported natural-language intent examples:

- send a Gmail draft
- send an existing draft email
- deliver a prepared Gmail draft

Builder behavior:

- infer `mcp.gmail.send_draft`
- generate explicit input schema
- generate explicit output schema
- generate explicit workflow
- always mark `review_required`
- never auto-finalize

## Input Contract

The first send contract should be intentionally minimal.

Suggested input:

- `draftId`

Possible schema:

- `draftId: string`

The runtime contract should normalize from the Gmail MCP tool shape if needed, but Builder should expose only the stable minimal field.

## Output Contract

Expected result should return enough information to audit successful outbound delivery.

Suggested output:

- `id`
- `threadId` if available
- `status`

Minimum acceptable output:

- a stable sent-message id plus status

## Workflow Shape

No new workflow primitive is required.

Use:

- `service_call` to `mcp.gmail.send_draft`

Flow:

1. validate input
2. pending confirmation if permission requires it
3. `service_call` executes draft send
4. end

This stays aligned with the existing Phase 3 MCP workflow shape.

## Permission And Confirmation Model

`mcp.gmail.send_draft` must be:

- `side_effecting = true`
- permission scope `external_api.write`

Expected runtime behavior:

- without prior confirmation, execution becomes `pending_confirmation`
- after confirmation, the same persisted execution resumes and completes

This mirrors the Phase 2 mutation path and the Phase 3.2 Gmail draft-creation confirmation flow, but the side effect is now a real outbound send.

## Allowlist Rules

Phase 3.3 still should not expose all Gmail write tools.

Allowlist remains explicit:

- `search_messages`
- `create_draft`
- `send_draft`

Anything else:

- not registered
- not invokable
- fails closed

## Observability

Execution records should capture:

- provider id: `gmail`
- tool id: `mcp.gmail.send_draft`
- pending-confirmation state
- confirmed completion state
- normalized send result summary

Logs should prefer:

- tool id
- draft id
- sent message id
- thread id
- execution state

Logs should avoid unnecessary sensitive payload content such as full message body or bearer tokens.

## Error Handling

Add or reuse clear failure classes for:

- Gmail provider missing
- Gmail token missing/invalid
- send tool not allowlisted
- draft id invalid or not found
- MCP tool call failure
- confirmation required

Do not log bearer tokens or unnecessary message content.

## Testing Strategy

### Unit tests

- Gmail send tool discovery when allowlisted
- side-effecting metadata classification
- send result normalization

### Integration tests

- discover Gmail tools with `send_draft` allowlisted
- execute send skill and receive `pending_confirmation`
- confirm execution and complete successfully
- verify non-allowlisted Gmail send tool is blocked
- verify missing token fails cleanly

### Sample skill

Add:

- `gmail_send_draft`

Input:

- `draftId`

Required tool:

- `mcp.gmail.send_draft`

Permission:

- `external_api.write`

Result type:

- `json`

## Acceptance Criteria

Phase 3.3 is complete when:

- Gmail `send_draft` can be discovered and registered from MCP
- Builder can normalize Gmail send-draft skills into explicit `review_required` contracts
- send execution returns `pending_confirmation` before outbound delivery
- confirmed execution sends the Gmail draft successfully
- execution records persist the confirmation lifecycle
- tests cover discovery, confirmation, completion, and allowlist failure

## Recommended Implementation Order

1. extend Gmail allowlist/config to support `send_draft`
2. map Gmail send tool metadata as side-effecting write
3. add Builder `gmail_send_draft_operation` normalization
4. add sample `gmail_send_draft` skill
5. add confirmation/resume execution test
6. document Gmail send scope and confirmation rules

## Recommendation

Phase 3.3 should stop at `send_draft`.

The next slice after that, if needed, should be:

- Phase 3.4: direct `send_message` with stricter confirmation, higher policy scrutiny, and stronger audit requirements
