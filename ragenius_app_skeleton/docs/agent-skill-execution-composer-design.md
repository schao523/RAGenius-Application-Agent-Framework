# Agent Skill Execution Composer Design

Date: 2026-08-04

## Status

App-skeleton design implementing the user-facing responsibilities in
`docs/agent-skill-discovery-selection-contract.md`.

This design extends `openclaw-execution-composer-design.md`. The approved
cross-subsystem contract is authoritative for catalog, approval, selection, and
activation semantics. Existing Agent execution lifecycle and artifact contracts
remain authoritative for submission, confirmation, status, and results.

## Objective

Let a user choose an administrator-approved Codex or OpenClaw instruction skill
from Execution Composer without remembering a provider-native name.

The app displays only skills bound to the active application and currently
reported selectable by the execution subsystem. It never scans provider paths,
constructs approval decisions, or treats a display name as authorization.

## Existing Extension Points

The current app already has the needed transport and UI structure:

- `backend/app/execution_subsystem_client.py` is the service-authenticated HTTP
  boundary to the execution subsystem.
- `backend/app/main.py` proxies executable tool and skill inventories and owns
  app/session/user scope checks.
- `frontend/src/App.jsx` loads execution inventories and submits structured
  Composer context alongside the human-readable `@exec` command.
- `frontend/src/components/ExecutionComposer.jsx` switches between tool, skill,
  and Agent modes and already has a backend selector.
- Agent Skill Hint is currently a Codex-only hardcoded `Auto`/`NotebookLM`
  selector.

Agent-skill inventory must be separate from `skillInventory`, which represents
executable RAGenius skills and workflows.

## Data Flow

```text
Browser Composer
  -> app FastAPI session-scoped inventory route
  -> execution-subsystem active local governance projection
  -> execution-subsystem provider availability validation

Browser Composer submission
  -> app FastAPI chat route with structured execution_request
  -> execution-subsystem execute_agent with agent_skill_ref
  -> policy / confirmation / provider execution
  -> normalized selection and activation evidence
  -> app execution card and inspector
```

The browser never calls Builder or the execution subsystem directly. The app
backend never calls Builder for Agent-skill inventory or execution. After
Builder has published and execution has acknowledged a governance revision,
Builder may be stopped without interrupting selection or invocation of those
synchronized skills.

## App Backend Client

Add to `ExecutionSubsystemClient`:

```python
def get_agent_skill_inventory(
    self,
    *,
    app_id: str,
    backend: str,
) -> dict[str, Any]:
    return self._json_request(
        "GET",
        "/agent-skills/inventory",
        query={"app_id": app_id, "backend": backend},
    )
```

Extend `submit_agent` with:

```python
agent_skill_ref: dict[str, str] | None = None
```

When present, it sends `agent_skill_ref`. During compatibility, an integration
may also carry a legacy `agent_skill_hint`; the execution subsystem must resolve
both to the same skill or reject the request. New Composer submissions send
only the structured reference.

## App Backend API

### Session-scoped inventory

Add:

`GET /sessions/{session_id}/exec/agent-skills?app_id=<id>&user_id=<id>&backend=<backend>`

The route:

1. calls `_require_session_scope` before any downstream request;
2. validates backend as `codex_cli` or `openclaw_cli`;
3. asks the execution subsystem for app-bound inventory;
4. validates and allowlists public item fields;
5. returns `{items, inventory_revision}` from execution's active projection;
6. maps downstream failure to a bounded app error without leaking service
   configuration.

Session scope is preferred over the existing unscoped `/exec/skills` pattern
because Agent-skill selection participates in an end-user Agent execution and
the contract requires app/session identity enforcement before inventory is
returned.

The response item shape is:

```json
{
  "agent_skill_id": "agent_skill_...",
  "backend": "codex_cli",
  "display_name": "NotebookLM",
  "description": "Use NotebookLM through the configured runtime.",
  "provider_skill_name": "notebooklm",
  "approved_fingerprint": "sha256:v1:...",
  "availability": "available"
}
```

No locator, filesystem path, WSL path, missing environment variable name,
approval actor, or unrestricted provider metadata is proxied to the browser.

### Chat execution request

Extend the structured request accepted by the chat route with:

```json
{
  "request_type": "execute_agent",
  "agent_backend": "codex_cli",
  "agent_skill_ref": {
    "agent_skill_id": "agent_skill_...",
    "approved_fingerprint": "sha256:v1:..."
  }
}
```

The backend takes the selection only from the validated structured execution
request. It must not reconstruct the opaque id from the display label or parse
it from the human-readable command string.

For defense in depth, the backend requires that the selected item's backend
equals the requested Agent backend. The execution subsystem remains
authoritative and revalidates app binding and fingerprint.

`inventory_revision` identifies the active published Builder instance,
revision, and digest. The app treats it as opaque diagnostic metadata and never
uses it as authorization.

The app reads this inventory only through the execution subsystem. It never
calls Builder for selection, and Builder does not need to be running after a
revision has been successfully published.

## Frontend State

`App.jsx` adds state independent from executable skills:

```js
const [agentSkillInventoryByBackend, setAgentSkillInventoryByBackend] = useState({
  codex_cli: [],
  openclaw_cli: [],
});
const [agentSkillInventoryLoading, setAgentSkillInventoryLoading] = useState(false);
const [agentSkillInventoryError, setAgentSkillInventoryError] = useState("");
```

Inventory is scoped by the active `(app_id, session_id, user_id, backend)`.
Changing app, session, user, or backend invalidates the visible selection before
loading replacement data.

The initial implementation may fetch both configured backends when Composer
opens. Fetching on backend change is also acceptable, but cached data must be
keyed by the full scope rather than reused across apps or sessions.

Abort or ignore stale responses when the active scope changes before a request
completes.

## Composer API

Add props:

```js
agentSkillInventoryByBackend
agentSkillInventoryLoading
agentSkillInventoryError
```

Replace `agentSkillHint` GUI state with a structured selection id:

```js
const [selectedAgentSkillId, setSelectedAgentSkillId] = useState("");
```

The empty value represents Auto. The selected inventory record remains the
source of the approved fingerprint; the user cannot edit it.

When Agent backend changes, reset selection to Auto before rendering the new
backend inventory. A Codex skill must never remain selected for OpenClaw or vice
versa.

## Picker UX

Agent mode always shows an `Agent Skill` selector for both backends:

- `Auto - let the agent choose`;
- one option per current selectable item for the selected backend.

Option labels use `display_name`. The selected option displays its description
and a small provider label. Provider-native name may appear as secondary text
for diagnostics but is not the value submitted.

The picker does not display unavailable or unbound entries. Those belong in
Builder administrator UX. An empty catalog is not an error: Auto remains
available and helper text states that no approved skills are bound to this app.

Loading behavior:

- disable non-Auto selection while loading;
- preserve the Agent request text and other form state;
- show a compact retryable inventory error;
- permit Auto execution when inventory loading fails;
- do not permit a previously selected explicit skill after refresh failure or
  scope change.

If execution has no active governance projection, the inventory is empty and
the app shows a bounded setup message. Auto Agent execution remains available;
explicit Agent-skill selection is unavailable until Builder successfully
publishes a projection.

While Composer is open, the app refreshes the current execution inventory on:

- Composer open, after preparing a draft session when necessary;
- Agent backend change, for that backend only;
- window focus return, for the selected backend only;
- explicit `Refresh Agent Skills`, with a forced network request.

The focus listener exists only while Composer is mounted. Every request remains
scoped by current app, session, user, and backend. Responses replace inventory
only when `inventory_revision` changes; an unchanged non-null revision preserves
the list identity and any still-valid selection. Scope changes and a changed
revision still clear a selection that no longer exists.

Auto is a user-visible choice but is serialized as no `agent_skill_ref`.

## Composer Submission

For an explicit selection, `ExecutionComposer` sends:

```js
{
  commandKind: "agent",
  targetId: "codex_cli",
  executionMode: "async",
  args: {
    request: "Add the selected artifact to the Testing notebook.",
    agentSkillRef: {
      agent_skill_id: selected.agent_skill_id,
      approved_fingerprint: selected.approved_fingerprint,
    },
    artifactRefs: [],
    expectedOutputs: [],
  },
}
```

`buildExecutionRequestForComposer` normalizes this to `agent_skill_ref` and
includes it even when there are no artifact refs or expected outputs. The
current early return based only on artifact/output presence must therefore be
changed.

The human-readable command may still render the provider name for chat history,
for example `@exec codex use notebooklm "..."`, but it is display and legacy
routing text. The accompanying structured request is authoritative.

## Typed Command Compatibility

Manual message-box commands remain supported:

```text
@exec codex use notebooklm "request"
@exec openclaw use spike "request"
```

The app router emits `agent_skill_hint` for these commands because no opaque
catalog id is available in the text. The execution subsystem resolves the hint
only against one unique approved app-bound skill.

Composer must not use this compatibility path when it has a structured
selection. The GUI sends `agent_skill_ref`. If an integration supplies both
forms, the app passes the validated fields and the execution subsystem requires
them to resolve to the same backend skill.

## Execution State And Rendering

Session execution-lane state adds public selection fields:

```json
{
  "latest_agent_skill": {
    "agent_skill_id": "agent_skill_...",
    "backend": "codex_cli",
    "display_name": "NotebookLM",
    "provider_skill_name": "notebooklm",
    "approved_fingerprint": "sha256:v1:..."
  }
}
```

Do not encode the selection only into
`latest_execution_request_skill_id`. Keep that legacy field for compatibility,
but render new Agent-skill metadata from the dedicated object.

Execution cards show:

- selected skill display name or Auto;
- resolution status;
- process-observed activation status when returned;
- a concise warning if activation could not be observed;
- normal execution outcome and artifact actions independently.

The app must not infer activation from assistant prose or an output filename.
The inspector displays normalized evidence from the execution subsystem and
does not parse raw Codex or OpenClaw output.

## Refresh And Drift Behavior

When execution returns a stable Agent-skill state error, the app:

- keeps the failed execution card and diagnostics;
- refreshes the current backend inventory;
- clears the explicit selection if it is no longer present;
- tells the user the selected skill changed, was revoked, became unavailable,
  or is no longer bound;
- never resubmits as Auto automatically.

Retry requires the user to choose Auto or another currently selectable skill.

## Accessibility And Responsive Behavior

- The picker has an explicit `Agent Skill` label and descriptive helper text.
- Loading and error messages use live status semantics without moving focus.
- Backend changes announce that the Agent-skill selection reset to Auto.
- Option text remains concise on narrow screens; full description renders below
  the selector rather than inside a long option label.
- Keyboard submission and existing confirmation flows remain unchanged.

## Error Handling

Public mappings include:

- `AGENT_SKILL_NOT_APPROVED`: no longer administrator approved;
- `AGENT_SKILL_NOT_BOUND`: no longer available to this app;
- `AGENT_SKILL_FINGERPRINT_CHANGED`: content changed and needs administrator
  review;
- `AGENT_SKILL_UNAVAILABLE`: provider cannot currently use the skill;
- `AGENT_SKILL_AMBIGUOUS`: typed legacy hint matches more than one approved
  skill;
- `AGENT_SKILL_PROJECTION_UNAVAILABLE`: Builder has not yet synchronized a
  governance projection to execution;
- inventory transport failure: Auto remains available, explicit selection is
  cleared.

Messages tell ordinary users what action they can take but omit protected
source details. Administrator remediation belongs in Builder.

## Tests

### Backend tests

- inventory route requires matching app/session/user scope;
- unsupported backend returns `400`;
- service token is sent only server to server;
- response strips protected fields;
- structured selection passes unchanged to `submit_agent`;
- structured reference plus a matching legacy hint is accepted downstream,
  while a mismatch is rejected;
- typed command continues to send the legacy hint;
- downstream unavailable and stale-selection errors are bounded;
- inventory and explicit execution do not require Builder connectivity after a
  projection has been published.

### Composer tests

- Codex and OpenClaw each show only their inventory;
- Auto is always available and submits no reference;
- explicit selection submits opaque id and fingerprint;
- backend change clears selection;
- backend change, focus return, and explicit refresh reload from execution;
- focus while Composer is closed performs no request;
- unchanged `inventory_revision` preserves the current list and selection;
- app/session change cannot retain a stale selection;
- empty inventory and loading failure preserve Auto;
- missing projection shows setup guidance without blocking Auto;
- hardcoded NotebookLM option is removed;
- Agent inventory remains separate from executable skill targets;
- artifacts and expected outputs compose with the structured selection.

### App integration tests

- inventory reloads with the active session scope;
- structured request is present even without artifacts or expected outputs;
- confirmation and async status preserve selected-skill metadata;
- drift error refreshes inventory and never retries as Auto;
- published inventory and explicit execution continue while Builder is
  stopped;
- inspector renders normalized requested/resolved/process-observed evidence;
- existing tool, executable skill, Codex Auto, and OpenClaw Auto flows do not
  regress.

## Rollout

1. Add the backend inventory client and session-scoped proxy route behind a
   feature flag.
2. Add structured `agent_skill_ref` transport and tests while retaining hints.
3. Add frontend inventory state and backend-sensitive picker.
4. Add execution-card and inspector selection evidence.
5. Enable for administrator-bound test apps.
6. Run live Codex and OpenClaw Composer smoke tests.
7. Enable generally after drift and isolation tests pass.

## Acceptance Criteria

- Users can select app-bound Codex and OpenClaw skills without typing names.
- The browser receives no provider source paths or protected metadata.
- Selection is an opaque id plus approved fingerprint, not a display label.
- Auto remains explicit and never receives a synthetic skill record.
- Backend/app/session changes cannot retain an invalid explicit selection.
- Typed commands remain backward compatible but resolve through execution-owned
  governance.
- Existing executable RAGenius skill inventory and execution are unchanged.
