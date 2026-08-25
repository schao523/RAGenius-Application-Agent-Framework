# Codex Interactive Skill, Plugin, And MCP Interaction Addendum

Date: 2026-08-25

## Status

Normative contract and execution-subsystem design addendum for generic MCP
elicitation and managed skill/plugin handoffs in Codex Interactive Agent mode.

This addendum extends:

- `docs/interactive-agent-execution-contract.md`
- `ragenius_execution_subsystem/docs/codex-app-server-interactive-provider-design.md`
- `docs/agent-execution-lifecycle-evidence-contract.md`

Those documents remain authoritative unless this addendum explicitly changes
Codex MCP elicitation handling or interactive result normalization.

## Purpose

Codex skills, plugins, and MCP servers may require confirmation, bounded input,
authentication, or a manual user action after a turn has started. RAGenius must
mediate supported structured requests as durable provider-neutral interactions
instead of rejecting them, parsing assistant prose, exposing secrets, or
reporting a blocked operation as successful.

The implementation is generic Codex interactive protocol support. Gmail is the
first live MCP acceptance case, not a special-case provider implementation.

## Observed Basis

On 2026-08-24, Codex app-server `0.146.0` execution
`execution_89fa03b0fb31` reached a Gmail MCP send call after RAGenius policy
confirmation. The MCP operation requested provider-time approval, but the
Codex adapter created no interaction and the operation returned
`permission_denied`. No message was sent.

Generated Codex `0.146.0` app-server bindings identify the relevant server
request as:

```text
mcpServer/elicitation/request
```

The generated request has three modes:

```ts
type McpServerElicitationRequestParams = {
  threadId: string;
  turnId: string | null;
  serverName: string;
} & (
  | {
      mode: "form";
      message: string;
      requestedSchema: McpElicitationSchema;
      _meta: JsonValue | null;
    }
  | {
      mode: "openai/form";
      message: string;
      requestedSchema: JsonValue;
      _meta: JsonValue | null;
    }
  | {
      mode: "url";
      message: string;
      url: string;
      elicitationId: string;
      _meta: JsonValue | null;
    }
);
```

The generated response is:

```ts
type McpServerElicitationRequestResponse = {
  action: "accept" | "decline" | "cancel";
  content: JsonValue | null;
  _meta: JsonValue | null;
};
```

The protocol is experimental. Support remains version-gated and must be
validated against generated bindings for every enabled Codex version.

## Scope

The MVP adds:

- generic handling of `mcpServer/elicitation/request` in Codex Interactive
  Agent mode;
- conservative normalization to `approval`, `selection`, `clarification`, or
  `authentication_handoff`;
- a managed `ragenius_request_authentication_handoff` tool for instruction
  skills and plugin guidance that cannot initiate MCP URL elicitation;
- a separate managed `ragenius_request_user_action` tool for bounded manual
  actions that MCP elicitation cannot classify safely;
- same-turn persistence and resolution through the existing interaction state
  machine;
- generic operation-outcome normalization so a failed or blocked required MCP
  operation cannot become a successful execution merely because the Codex turn
  completed.

The MVP does not add:

- Builder interaction-capability fields or per-skill Composer labels;
- arbitrary multi-field form rendering;
- secret entry through RAGenius;
- automatic acceptance based only on provider or model prose;
- session-wide or permanent approval;
- OpenClaw elicitation support;
- Gmail-specific adapter branches.

## Product Boundary

`ragenius_execution_subsystem` owns protocol validation, interaction
classification, policy binding, protected provider request state, response
translation, same-turn resumption, and authoritative execution outcome.

`ragenius_app_skeleton` owns scoped interaction presentation and collection of
non-secret user responses. The browser never communicates directly with Codex
app-server or an MCP server.

`ragenius_builder` has no new MVP responsibility. Interactive Agent mode and
runtime adapter capability are sufficient to enable the supported flow.

Codex plugins, skills, and MCP servers may initiate a supported structured
request, but they do not control RAGenius authorization or persistence.

The supported request sources are:

| Source | Structured mechanism | Eligible normalized types |
| --- | --- | --- |
| MCP server | `mcpServer/elicitation/request` | `approval`, `selection`, `clarification`, `authentication_handoff` |
| Instruction skill | managed Codex dynamic tool | `authentication_handoff`, `user_action_required` |
| Plugin instructions | managed Codex dynamic tool | `authentication_handoff`, `user_action_required` |
| Assistant prose | none | none |

An underlying MCP server remains the preferred source when it can provide an
authoritative provider request. Managed tools cover instruction-driven flows
without treating prose as protocol.

## Runtime Capability Contract

Codex preflight may advertise these interaction types only when the running
protocol version has passing adapter tests:

```ts
type CodexMcpElicitationCapabilities = {
  approval: boolean;
  authentication_handoff: boolean;
  clarification: boolean;
  selection: boolean;
  user_action_required: boolean;
};
```

Interactive Agent mode enables the transport. It does not pre-authorize a
future interaction. Provider-time requests are evaluated when received.

Request-side `allowed_types` and `required_types` remain limited to
`clarification` and `selection`. Authentication and user actions are
runtime-driven and cannot be demanded by untrusted user request metadata.

Capability advertisement is controlled by these execution-subsystem settings:

```text
CODEX_MCP_ELICITATION_ENABLED=false
CODEX_INTERACTIVE_AUTH_HANDOFF_ENABLED=false
CODEX_INTERACTIVE_USER_ACTION_ENABLED=false
CODEX_MCP_AUTH_ALLOWED_HOSTS_JSON=[]
CODEX_MANAGED_AUTH_TARGETS_JSON=[]
```

The host allowlist is a JSON array of exact lowercase ASCII host names. Empty
or invalid configuration permits no authentication launch. Wildcards, URL
paths, query fragments, and user-info components are not valid entries.

The managed target registry is a JSON array with this schema:

```ts
type ManagedAuthenticationTarget = {
  id: string;
  label: string;
  launch:
    | { kind: "https_url"; url: string }
    | { kind: "provider_window"; provider: "computer_use"; application: string };
  allowedHosts: string[];
  verifierId: string;
};
```

Target ids, launch definitions, and verifier ids are administrator-controlled
runtime configuration. Skills, plugins, user prompts, and models cannot create
or modify registry entries. Every `verifierId` must resolve to an installed
trusted read-only verifier during preflight; otherwise the target is disabled.

## Canonical Normalized Request

The version-specific Codex decoder produces one internal request before any
interaction record is created:

```ts
type NormalizedMcpElicitation = {
  interactionType:
    | "approval"
    | "clarification"
    | "selection"
    | "authentication_handoff";
  prompt: string;
  options: Array<{ id: string; label: string; description?: string }>;
  allowsFreeText: boolean;
  serverName: string;
  threadId: string;
  turnId: string | null;
  providerRequestId: string | number;
  responseBinding:
    | { kind: "approval" }
    | { kind: "field"; propertyName: string }
    | { kind: "authentication_url"; elicitationId: string };
  protectedLaunchTarget?: {
    kind: "https_url";
    url: string;
  };
};
```

`providerRequestId`, the complete authentication URL, raw schema, and raw
metadata remain protected execution-subsystem state. They are not written to
public logs or returned in ordinary execution results.

Managed dynamic-tool requests normalize through the same interaction record
but use a tool-call id as `providerRequestId` and one of these response
bindings:

```ts
type ManagedHandoffResponseBinding =
  | {
      kind: "managed_authentication";
      targetId: string;
      verifierId: string;
    }
  | { kind: "managed_user_action" };
```

## Classification Rules

Classification is structural and fail-closed. The adapter must not infer an
interaction type from assistant prose or from an unrecognized `_meta` field.

### Form Mode

The MVP accepts only an object schema with zero or one property.

| Validated shape | Normalized interaction |
| --- | --- |
| No properties and an authorization-bound active operation | `approval` |
| One boolean confirmation property and an authorization-bound active operation | `approval` |
| One single-select enum property | `selection` |
| One bounded non-secret string property | `clarification` |

Additional rules:

- The prompt is the bounded MCP `message`, with a maximum of 2,000 UTF-8
  characters.
- Selection options are capped at 20 and each label at 200 characters.
- Clarification input is capped at 8,000 characters.
- Number, integer, array, multi-select, nested object, and multiple-property
  forms are unsupported in the MVP.
- A boolean form is not an approval unless the execution has an active
  authorization-bound operation. Otherwise it is unsupported rather than
  silently treated as consent.
- The active operation and provider request are bound to the existing
  `policy_binding_hash` before the interaction is shown.

### OpenAI Form Mode

`openai/form` is accepted only when a version-specific decoder reduces it to
the same zero-or-one-field subset above. Unknown widgets, actions, callbacks,
embedded resources, or metadata fail with `MCP_ELICITATION_UNSUPPORTED`.

### URL Mode

URL mode normalizes to `authentication_handoff` only when all conditions hold:

- the URL uses HTTPS;
- its host passes the administrator-configured authentication-target
  allowlist;
- the request is correlated to the active thread and turn;
- no credential, token, cookie, authorization code, or URL query is copied to
  public logs or interaction summaries;
- the adapter can perform a non-mutating provider authentication check after
  completion.

The full URL is protected service data. It may transit the trusted app backend
only in a no-store service response used immediately for a scoped browser
redirect. The interaction record may expose only the approved host and a
bounded label.

### Managed Authentication Handoff

Instruction skills and plugin instructions may ask Codex to invoke a second
managed dynamic tool when authentication is required but no MCP URL
elicitation is available:

```json
{
  "type": "function",
  "name": "ragenius_request_authentication_handoff",
  "description": "Pause for sign-in or account consent at an administrator-approved authentication target. Never request credentials in RAGenius.",
  "inputSchema": {
    "type": "object",
    "additionalProperties": false,
    "required": ["authentication_target_id", "instruction"],
    "properties": {
      "authentication_target_id": {
        "type": "string",
        "minLength": 1,
        "maxLength": 100
      },
      "instruction": { "type": "string", "maxLength": 2000 },
      "completion_label": { "type": "string", "maxLength": 100 }
    }
  }
}
```

The adapter resolves `authentication_target_id` only against
`CODEX_MANAGED_AUTH_TARGETS_JSON`. The model cannot provide a URL, executable,
application path, verifier, credential field, or callback. Unknown or disabled
target ids fail with `AUTHENTICATION_TARGET_NOT_APPROVED`.

The adapter creates `authentication_handoff` using the registry label and
protected launch definition. After the user reports completion, the registered
read-only verifier must succeed before the same Codex turn receives a
successful tool result. Verification failure keeps the interaction pending
when the provider request remains resumable; otherwise the execution fails.

The managed tool is exposed only when authentication handoff is enabled and at
least one registry target passes preflight. Trusted turn guidance lists only
eligible target ids and labels. A skill or plugin may recommend a target but
cannot make an unregistered target eligible.

### User Action

MCP form text alone cannot safely distinguish a manual action from approval or
ordinary input. The MVP therefore provides a separate managed dynamic tool:

```json
{
  "type": "function",
  "name": "ragenius_request_user_action",
  "description": "Pause for one bounded non-secret action in an already approved browser or application.",
  "inputSchema": {
    "type": "object",
    "additionalProperties": false,
    "required": ["instruction"],
    "properties": {
      "instruction": { "type": "string", "maxLength": 2000 },
      "completion_label": { "type": "string", "maxLength": 100 }
    }
  }
}
```

This tool creates `user_action_required`. It cannot request credentials,
authorize an external write, launch an arbitrary executable, mutate policy, or
claim that the action succeeded. The user returns only `completed` or
`cancelled`, and the provider must verify the observable result when possible.

## Secret And Unsafe Input Rejection

RAGenius rejects an elicitation before persistence when any of these apply:

- the schema or message requests a password, passcode, OTP, token, API key,
  cookie, private key, recovery code, or other credential;
- the URL is non-HTTPS or its host is not allowlisted;
- the form exceeds size, field-count, nesting, or option limits;
- the provider request is not correlated to the active execution thread;
- the request attempts permanent approval, policy mutation, or expanded
  permissions outside the confirmed operation plan;
- the Codex version or request mode is unsupported.

The provider receives `decline` for a safely rejectable request. RAGenius
records a bounded diagnostic code without raw sensitive content.

## Durable Interaction Mapping

Every accepted request becomes the existing `AgentInteractionRecord`. The
protected pending-request registry is extended to retain the elicitation mode
and response binding:

```ts
type PendingCodexProviderRequest = {
  requestId: string | number;
  type: AgentInteractionType;
  options: Array<{ id: string; label: string }>;
  responseBinding:
    | { kind: "approval" }
    | { kind: "field"; propertyName: string }
    | { kind: "authentication_url"; elicitationId: string }
    | {
        kind: "managed_authentication";
        targetId: string;
        verifierId: string;
      }
    | { kind: "managed_user_action" };
};
```

`provider_correlation_ref` uses the request method and JSON-RPC request id. It
must not contain the authentication URL or form values.

The execution enters `waiting_for_interaction` until the single-use response
is resolved, cancelled, or expired. A provider turn must not complete while a
pending elicitation remains unresolved.

## Response Translation

The existing provider-neutral responses translate as follows:

| RAGenius response | Codex MCP response |
| --- | --- |
| `approval.allow_once` | `{ action: "accept", content: {}, _meta: null }` |
| `approval.deny` | `{ action: "decline", content: null, _meta: null }` |
| `approval.cancel_execution` | `{ action: "cancel", content: null, _meta: null }`, then scoped execution cancellation |
| `selection.option_ids` | `{ action: "accept", content: { [propertyName]: selectedValue }, _meta: null }` |
| `clarification.text` | `{ action: "accept", content: { [propertyName]: text }, _meta: null }` |
| authentication `completed` | `{ action: "accept", content: null, _meta: null }`, followed by non-mutating authentication verification |
| authentication `cancelled` | `{ action: "cancel", content: null, _meta: null }` |
| managed authentication `completed` | successful managed-tool result only after the registered verifier succeeds |
| managed authentication `cancelled` | cancelled managed-tool result |
| user action `completed` | successful managed-tool result, followed by provider verification when available |
| user action `cancelled` | cancelled managed-tool result |

Selection option ids are resolved only against the persisted interaction
options. Arbitrary client values are never forwarded. Duplicate responses use
the existing idempotency result and do not produce a second provider response.

An expired interaction is declined or cancelled according to the request mode,
then the execution fails with `AGENT_INTERACTION_EXPIRED`.

## Authorization Semantics

RAGenius pre-execution confirmation and provider-time MCP elicitation are
separate controls.

For the MVP, a provider approval is shown even when RAGenius already confirmed
the outer external-write operation. RAGenius must not auto-accept an MCP
elicitation merely because the provider message appears similar to the
confirmed request.

Future approval deduplication is permitted only when the adapter can bind the
provider request to the exact confirmed operation, target, content digest, and
single-use authorization. Similar prose is insufficient.

Authentication completion and manual-action completion are acknowledgements,
not external-write authorization. A later send, publish, delete, or other
external write remains governed by its confirmed operation and provider-time
approval.

## App Presentation Contract

The app presents one pending blocking interaction in the existing standalone
interaction panel:

- `approval`: prompt plus **Allow once**, **Deny**, and **Cancel execution**;
- `selection`: bounded option buttons and optional free text only when allowed;
- `clarification`: non-secret text input;
- `authentication_handoff`: approved provider host, **Open sign-in**,
  **Authentication completed**, and **Cancel**;
- `user_action_required`: bounded instruction, configurable completion label,
  and **Cancel**.

The UI must state that passwords, OTPs, tokens, and recovery codes belong only
in the provider-controlled browser or application. It must never render an
arbitrary provider HTML form.

Interactive Agent mode may show one generic notice that sign-in or manual
actions can occur. Per-skill capability labels are deferred.

For a managed authentication target, the panel shows its administrator-defined
label rather than an MCP server name. The app does not distinguish whether the
request originated from a skill, plugin instruction, or MCP server because the
runtime interaction semantics are identical.

## Authentication Launch Contract

The complete authentication URL remains protected by the execution subsystem.
The app backend exposes a scoped launch endpoint:

```text
POST /sessions/{session_id}/executions/{execution_id}/interactions/{interaction_id}/launch
```

The backend verifies `{app_id, session_id, user_id, execution_id,
interaction_id}`, current interaction state, and expected version before
requesting a single-use launch target from the execution subsystem:

```text
POST /executions/{execution_id}/interactions/{interaction_id}/launch?app_id=&session_id=
```

The service endpoint requires execution-service authentication and returns a
bounded `{ launch_url, expires_at }` response with `Cache-Control: no-store`.
The app backend immediately returns an HTTP redirect to the browser and must
not persist or log the URL. The execution subsystem revalidates scheme, exact
host, interaction state, execution scope, and expiry on every launch request.
Launch does not resolve the interaction.

After the user selects **Authentication completed**, the adapter performs a
non-mutating authentication/capability check. Failure returns the interaction
to pending with a bounded error when the provider request remains resumable;
otherwise the execution fails with `AUTHENTICATION_HANDOFF_NOT_VERIFIED`.

## Result Normalization

Provider turn completion and operation success are independent.

The execution subsystem records MCP tool item status and provider responses.
For every required operation:

- a successful tool result with operation-specific evidence may satisfy the
  operation;
- `permission_denied`, rejected elicitation, failed MCP tool status, missing
  required evidence, or a provider-reported `blocked` outcome does not satisfy
  it;
- assistant prose claiming success or failure is diagnostic only;
- `turn/completed` cannot override a failed or unsatisfied required operation.

If the Codex turn completes after a required MCP operation is blocked, the
execution becomes `failed` with a normalized recoverable error such as
`MCP_OPERATION_BLOCKED`. The final assistant response remains available as
diagnostic output but does not change the authoritative status.

## Error Codes

| Code | Meaning |
| --- | --- |
| `MCP_ELICITATION_UNSUPPORTED` | The request mode or form shape is outside the supported subset. |
| `MCP_ELICITATION_SECRET_INPUT_BLOCKED` | The request may collect credentials or secret material. |
| `MCP_ELICITATION_SCOPE_MISMATCH` | The request does not belong to the active thread or turn. |
| `MCP_ELICITATION_TARGET_BLOCKED` | The authentication URL is not an approved HTTPS target. |
| `MCP_ELICITATION_RESPONSE_REJECTED` | Codex app-server rejected the normalized response. |
| `AUTHENTICATION_TARGET_NOT_APPROVED` | A managed skill/plugin request named an unknown or disabled authentication target. |
| `AUTHENTICATION_HANDOFF_NOT_VERIFIED` | The user completed the handoff but provider authentication could not be verified. |
| `USER_ACTION_NOT_VERIFIED` | A required manual action was acknowledged but its observable result was absent. |
| `MCP_OPERATION_BLOCKED` | A required MCP operation was denied, cancelled, or otherwise blocked. |

Errors are bounded and redact raw schemas, form content, authentication URLs,
tokens, and provider credentials.

## Recovery And Cancellation

- Pending MCP JSON-RPC requests remain process-local protected handles in the
  MVP.
- A process restart while an elicitation is pending fails with
  `AGENT_EXECUTION_INTERRUPTED`; RAGenius must not fabricate a provider
  response after restart.
- Persisted interaction state remains available for diagnosis and is marked
  cancelled or expired during reconciliation.
- Cancellation first claims the interaction, sends `cancel` when the provider
  request is still live, interrupts the exact Codex turn, and then performs
  bounded process-tree cleanup.
- A late provider resolution is deduplicated and cannot reopen a terminal
  execution.

## Security Constraints

- Only Interactive Agent transport is eligible.
- The execution subsystem service token and provider credentials never reach
  the browser.
- Public logs contain server labels and bounded prompts only; they exclude raw
  URLs, request schemas, form values, and MCP metadata.
- Authentication hosts use an administrator-configured allowlist. Redirects
  are revalidated before launch.
- `user_action_required` cannot authorize an external write or request secret
  input.
- Provider-time approval is single-use and bound to the execution policy
  fingerprint.
- Unsupported or ambiguous requests fail closed without falling back to
  assistant prose.

## Verification Matrix

### Protocol And Unit Tests

- Decode all three generated `0.146.0` modes.
- Resolve managed authentication target ids without accepting model-provided
  URLs, verifier ids, or application paths.
- Normalize confirmation, one-field selection, and one-field clarification.
- Reject secret fields, multiple fields, unsupported widgets, oversized
  payloads, scope mismatch, and unapproved URLs.
- Translate accept, decline, cancel, selection, clarification, authentication,
  and user-action responses exactly once.
- Verify expiry, cancellation, stale version, duplicate idempotency key, and
  process loss.
- Preserve failed required operation status after `turn/completed`.

### App Tests

- Render every supported interaction with correct controls.
- Keep secret-entry warnings visible for authentication and user actions.
- Launch only through the scoped backend endpoint.
- Restore the pending interaction after refresh.
- Remove action controls after resolution or terminal execution.

### Live Acceptance

1. Gmail send approval accepted: one message is sent and provider evidence is
   returned.
2. Gmail send approval denied: no message is sent and status is failed or
   blocked, not completed.
3. Gmail send approval cancelled: execution cancellation is authoritative.
4. Authentication URL handoff: sign-in completes outside RAGenius and a
   non-mutating provider check succeeds.
5. Managed skill authentication: an instruction-only skill requests an
   approved target, the registered verifier succeeds, and the same turn
   resumes.
6. Unknown managed target: the request fails without opening a URL or
   application.
7. Computer Use manual action: a file-selection or browser-permission handoff
   resumes the same Codex turn.
8. Duplicate response: only one provider response and at most one external
   write occur.

Live external-write tests use a controlled account and uniquely identifiable
test content. They require explicit user confirmation and must verify absence
of duplicates.

## Rollout

1. Enable parser and mocked adapter tests without changing production
   capability advertisement.
2. Enable approval, selection, and clarification for Codex `0.146.0`.
3. Run Gmail accept/deny/cancel live acceptance.
4. Enable URL authentication handoff after launch-target validation passes.
5. Enable managed skill/plugin authentication after registry and verifier
   acceptance passes.
6. Enable managed user actions after same-turn Computer Use testing passes.
7. Advertise each capability only after its live acceptance evidence is
   recorded.

Builder metadata and OpenClaw parity remain separate future decisions.
