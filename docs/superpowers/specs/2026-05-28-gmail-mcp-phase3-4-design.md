# Phase 3.4 Design: Gmail Direct Send With Confirmation Gating

## Purpose

Phase 3.4 extends the Gmail MCP slice from sending existing drafts to the first direct-send path:

- send a Gmail message directly
- still through remote HTTP MCP
- still using a shared integration identity
- always confirmation-gated at runtime

This phase intentionally keeps direct send narrower than the draft-based flows that came before it.

## Scope

Phase 3.4 will add:

- one new write-capable Gmail action: `send_message`
- Builder normalization support for Gmail direct-send skills as `review_required`
- runtime permission classification as `external_api.write`
- confirmation gating before outbound send executes
- execution persistence and audit visibility for the direct-send path

Phase 3.4 will not add:

- `cc`
- `bcc`
- `replyTo`
- attachments
- HTML body variants
- per-user Gmail identity
- auto-finalization of Gmail direct-send contracts in Builder

## Goals

- add one direct Gmail outbound path safely
- keep the first direct-send contract minimal and explicit
- reuse the existing review + confirmation + resume model
- keep Gmail direct send narrow, auditable, and policy-controlled

## Non-Goals

- no rich email envelope support
- no attachments
- no broad outbound mail feature set
- no bypass of explicit confirmation before send

## Why Minimal `send_message` First

Compared to a broader email contract, a minimal direct-send shape:

- reduces schema ambiguity
- makes Builder inference simpler
- narrows the side-effect surface
- keeps confirmation and logging easier to reason about

The first direct-send slice should only accept:

- `to`
- `subject`
- `body`

Anything richer should be deferred until the direct-send seam is proven stable.

## Capability Model

The Phase 3.4 Gmail send tool should be:

- `mcp.gmail.send_message`

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
    "allowedToolNames": ["search_messages", "create_draft", "send_draft", "send_message"],
    "enabled": true
  }
]
```

Runtime secret remains:

- `GMAIL_MCP_ACCESS_TOKEN`

No new secret model is required.

## Builder Normalization

Add a narrow template family:

- `gmail_send_message_operation`

Supported natural-language intent examples:

- send an email in Gmail
- send a Gmail message
- send a follow-up email directly

Builder behavior:

- infer `mcp.gmail.send_message`
- generate explicit input schema
- generate explicit output schema
- generate explicit workflow
- always mark `review_required`
- never auto-finalize

## Input Contract

The first direct-send contract should be intentionally minimal.

Suggested input:

- `to`
- `subject`
- `body`

Possible schema:

- `to: string`
- `subject: string`
- `body: string`

If the Gmail MCP server expects a slightly different shape, the runtime contract can normalize it, but Builder should expose only this minimal stable surface.

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

- `service_call` to `mcp.gmail.send_message`

Flow:

1. validate input
2. pending confirmation if permission requires it
3. `service_call` executes direct send
4. end

This stays aligned with the existing Phase 3 MCP workflow shape.

## Permission And Confirmation Model

`mcp.gmail.send_message` must be:

- `side_effecting = true`
- permission scope `external_api.write`

Expected runtime behavior:

- without prior confirmation, execution becomes `pending_confirmation`
- after confirmation, the same persisted execution resumes and completes

This mirrors the earlier Gmail write flows, but direct send is operationally riskier than draft creation or draft send, so the confirmation gate is non-negotiable.

## Allowlist Rules

Phase 3.4 still should not expose all Gmail write tools.

Allowlist remains explicit:

- `search_messages`
- `create_draft`
- `send_draft`
- `send_message`

Anything else:

- not registered
- not invokable
- fails closed

## Observability

Execution records should capture:

- provider id: `gmail`
- tool id: `mcp.gmail.send_message`
- pending-confirmation state
- confirmed completion state
- normalized send result summary

Logs should prefer:

- tool id
- recipient summary
- sent message id
- thread id
- execution state

Logs should avoid storing the full body in routine logs unless a future audit policy explicitly requires it.

## Error Handling

Add or reuse clear failure classes for:

- Gmail provider missing
- Gmail token missing/invalid
- send tool not allowlisted
- invalid recipient/input shape
- MCP tool call failure
- confirmation required

Do not log bearer tokens or unnecessary message body content.

## Testing Strategy

### Unit tests

- Gmail send-message discovery when allowlisted
- side-effecting metadata classification
- direct-send result normalization

### Integration tests

- discover Gmail tools with `send_message` allowlisted
- execute direct-send skill and receive `pending_confirmation`
- confirm execution and complete successfully
- verify non-allowlisted Gmail direct-send tool is blocked
- verify missing token fails cleanly

### Sample skill

Add:

- `gmail_send_message`

Input:

- `to`
- `subject`
- `body`

Required tool:

- `mcp.gmail.send_message`

Permission:

- `external_api.write`

Result type:

- `json`

## Acceptance Criteria

Phase 3.4 is complete when:

- Gmail `send_message` can be discovered and registered from MCP
- Builder can normalize Gmail direct-send skills into explicit `review_required` contracts
- direct-send execution returns `pending_confirmation` before outbound delivery
- confirmed execution sends the Gmail message successfully
- execution records persist the confirmation lifecycle
- tests cover discovery, confirmation, completion, and allowlist failure

## Recommended Implementation Order

1. extend Gmail allowlist/config to support `send_message`
2. map Gmail send-message tool metadata as side-effecting write
3. add Builder `gmail_send_message_operation` normalization
4. add sample `gmail_send_message` skill
5. add confirmation/resume execution test
6. document Gmail direct-send scope and confirmation rules

## Recommendation

Phase 3.4 should stop at minimal `send_message`.

The next slice after that, if needed, should be:

- Phase 3.5: richer direct-send envelope support such as `cc`, `bcc`, and attachments metadata, with stronger validation and audit policy
