# Proposed `@exec codex` Contract

Date: 2026-06-05

## Purpose

Add a first-class agent execution mode to RAGenius that lets users issue natural-language execution requests while reusing Codex CLI runtime skills installed under `.agents/skills`.

Primary motivating example:
- a user installs the `notebooklm` Codex skill
- Codex runtime can activate that skill directly
- RAGenius should support natural-language agent execution without duplicating the entire `notebooklm-py` command surface as native runtime tools

## User-Facing Contract

Primary form:

```text
@exec codex "<natural language request>"
```

Examples:

```text
@exec codex "Use NotebookLM to create a Traditional Chinese study guide for Micah 2:1-11."
```

```text
@exec codex "Create a NotebookLM video from the approved content for Bible study beginners."
```

Optional explicit skill-hint form:

```text
@exec codex use notebooklm "<natural language request>"
```

Example:

```text
@exec codex use notebooklm "Generate a quiz and flashcards from the approved content."
```

Recommended behavior:
- support both forms
- prefer the plain form initially
- treat `use <skill>` as a hint, not a hard requirement

## Semantics

`@exec codex` means:

- route the turn into the execution lane
- do not use the normal planner/chat path
- invoke a Codex runtime execution backend
- let Codex decide which installed agent skill(s) to use
- run inside RAGenius application/session/policy context
- capture structured execution results back into the execution lane

This is an `Agent` execution mode, distinct from:

- `@exec tool ...`
- `@exec skill ...`
- `@exec status ...`

## Product Model

Recommended execution modes:

1. `Tool`
- direct runtime tool execution

2. `Skill`
- Builder-bound application skill execution

3. `Agent`
- natural-language Codex execution using installed Codex skills

Recommended UI exposure:
- show `Tool`
- show `Skill`
- show `Agent`

`@exec codex` should be the advanced/manual textual form of `Agent` mode.

## Internal Request Shape

Normalized request model:

```json
{
  "request_type": "execute_agent",
  "agent_backend": "codex_cli",
  "agent_mode": "natural_language",
  "app_id": "app_123",
  "session_id": "session_456",
  "agent_query": "Use NotebookLM to create a Traditional Chinese study guide for Micah 2:1-11.",
  "agent_skill_hint": "notebooklm",
  "approved_content_id": "ac_123",
  "approved_revision_id": "rev_123",
  "context": {
    "app_name": "Bible Tutor",
    "selected_instruction_scope": "...",
    "artifacts": [],
    "session_uploads": []
  },
  "policy": {
    "execution_class": "agent",
    "workspace_access": "none|read_only|scoped_write",
    "network_access": "allowlisted",
    "confirmation_mode": "auto_allow|require_confirmation"
  }
}
```

Notes:
- `agent_skill_hint` is optional
- `approved_content_id` and `approved_revision_id` are optional
- this request shape is internal, not user-facing

## Architecture

### `ragenius_app_skeleton`

Responsibilities:

- parse `@exec codex ...`
- collect session/app/approved-content context
- classify risk and approval requirements
- submit structured agent execution requests
- persist execution-lane state
- render summary, status, and result previews

### `ragenius_execution_subsystem`

Add a new backend/provider family:

- `codex_cli`

Responsibilities:

- receive `execute_agent` requests
- construct a constrained Codex runtime invocation
- pass contextual inputs to Codex
- capture:
  - final answer
  - execution trace summary
  - artifacts
  - errors
- normalize results back into the execution contract

### Codex Runtime

Responsibilities:

- read installed skills from:
  - `~/.agents/skills`
- interpret the natural-language request
- activate relevant installed skill(s), such as `notebooklm`
- run allowed tools/commands under policy
- return a structured final result

## Provider Contract in `ragenius_execution_subsystem`

Proposed request type:

```ts
type AgentExecutionRequest = {
  executionId: string;
  backend: "codex_cli";
  appId: string;
  sessionId: string;
  agentQuery: string;
  skillHint?: string | null;
  approvedContent?: {
    approvedContentId?: string | null;
    revisionId?: string | null;
    contentText?: string | null;
  };
  context: {
    appName?: string | null;
    sessionUploads?: Array<Record<string, unknown>>;
    artifacts?: Array<Record<string, unknown>>;
  };
  policy: {
    workspaceAccess: "none" | "read_only" | "scoped_write";
    networkAccess: "deny" | "allowlisted";
    confirmationMode: "auto_allow" | "require_confirmation";
  };
};
```

Proposed normalized result:

```ts
type AgentExecutionResult = {
  status: "completed" | "failed" | "pending_confirmation" | "running";
  executionId: string;
  backend: "codex_cli";
  resultType: "json";
  result: {
    final_message?: string;
    activated_skills?: string[];
    tool_summary?: string[];
    artifacts?: Array<{
      artifact_id?: string;
      artifact_type?: string;
      name?: string;
      path?: string;
    }>;
    output?: Record<string, unknown>;
  };
  provenance?: {
    backend: "codex_cli";
    skill_hint?: string | null;
    activated_skills?: string[];
  };
};
```

## Codex Invocation Model

RAGenius should not treat `@exec codex` as a raw shell escape.

Instead, Codex should be invoked with a constrained execution envelope containing:

- application context
- session context
- approved content context
- policy constraints
- optional skill hint
- user natural-language request

Conceptual envelope:

```text
You are executing inside RAGenius application context.

App: Bible Tutor
Session: session_456
Approved content revision: rev_123
Requested task: Use NotebookLM to create a Traditional Chinese study guide for Micah 2:1-11.

Preferred skill hint: notebooklm

Constraints:
- Only use installed Codex agent skills and allowed tools.
- Respect app-scoped artifact and workspace boundaries.
- Return a concise final result plus structured outputs.
```

## Policy Model

`@exec codex` should be policy-gated more strongly than deterministic `@exec tool` requests.

Suggested classes:

### `agent_read_only`

Examples:
- inspect notebooks
- summarize existing content
- ask NotebookLM questions

Default:
- auto-allow

### `agent_external_write`

Examples:
- generate NotebookLM artifacts
- create Gmail drafts
- create CMS pages

Default:
- require confirmation or explicit app policy allow

### `agent_workspace_write`

Examples:
- create/edit local files
- patch workspace artifacts

Default:
- require confirmation
- restrict writes to scoped roots only

### `agent_destructive`

Examples:
- delete notebooks
- delete files
- destructive data removal

Default:
- blocked or admin-only

## Approval Rules

Recommended:

- if Codex execution is read-only, allow directly
- if Codex execution is likely to cause external writes, require confirmation
- if Codex execution can write locally, require confirmation and scope limits
- do not allow Codex to silently escalate beyond declared policy

Examples:

`@exec codex "list my NotebookLM notebooks"`
- auto-allow

`@exec codex "generate a NotebookLM video from the approved content"`
- likely require confirmation

## App UX

Recommended `Execution Composer` modes:

- `Tool`
- `Skill`
- `Agent`

Agent-mode fields:

- natural-language request
- optional skill hint
- execution mode
- approval/risk indicator
- selected approved revision indicator

Example:

- Mode: `Agent`
- Skill hint: `Auto` / `notebooklm`
- Request: free text
- Run

After execution:

- transcript shows compact summary
- side inspector shows:
  - backend: `codex_cli`
  - activated skills
  - tool summary
  - artifacts created
  - raw result

## Transcript Behavior

Execution turn text should remain concise.

Examples:

- `Codex agent completed the NotebookLM task.`
- `Codex agent created a NotebookLM report.`
- `Codex agent requires confirmation before generating a video.`

Inline preview examples:

- `Activated skills: notebooklm`
- `Result: Report generated`
- `Artifacts: 1 created`

## Relationship to Existing Structured Modes

Recommended split:

- `@exec tool`
  - deterministic runtime tools
- `@exec skill`
  - Builder-bound application skills
- `@exec codex`
  - agentic natural-language Codex execution

This avoids duplicating the full `notebooklm-py` contract in two places:

- as native RAGenius runtime tools
- and as Codex-installed agent skills

## Rollout Phases

### Phase A

- parser support for:
  - `@exec codex "<request>"`
  - `@exec codex use <skill> "<request>"`
- `codex_cli` backend stub in `ragenius_execution_subsystem`
- transcript/status plumbing

### Phase B

- `Agent` mode in `Execution Composer`
- approval/risk handling
- execution inspector support for Codex runs

### Phase C

- artifact/result normalization
- activated-skill reporting
- retry/status support for Codex agent runs

## Recommendation

Recommended direction:

- add `@exec codex` as a first-class agent execution mode
- back it with a dedicated `codex_cli` provider/backend
- let Codex runtime use installed `.agents/skills` such as `notebooklm`
- keep RAGenius responsible for:
  - application context
  - policy
  - approval
  - audit
  - result persistence

This gives:

- natural-language execution UX
- Codex skill reuse
- no full duplication of the `notebooklm-py` command surface inside RAGenius
- a clean separation between:
  - structured tools
  - structured app skills
  - agentic Codex execution
