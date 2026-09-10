# Computer Use Application Approval Inheritance Runtime Test Specification

Date: 2026-09-10

## Status

Approved investigation scope. This document defines a disposable runtime test;
it does not authorize a production behavior change.

## Governing Decision

**Investigation required, not currently a RAGenius defect:** Determine
experimentally whether `item/permissions/requestApproval` participates in
Computer Use application authorization. Until verified, retain RAGenius's
fail-closed behavior and do not build a separate Computer Use approval
mechanism.

Codex remains the authority for Computer Use application approval. RAGenius
must not copy, synchronize, infer, or persist Codex Desktop's application
approval state.

## Purpose

Determine whether a Computer Use application approval made in Codex Desktop is
honored by:

1. an independently launched Codex CLI process;
2. a directly launched Codex App Server process; and
3. the Codex App Server process launched by RAGenius.

The test must also determine whether an application-authorization request is
visible to an App Server client as `item/permissions/requestApproval`, another
protocol method, or no protocol event at all.

## Questions To Answer

1. Does Codex Desktop approval apply to an independent Codex CLI process using
   the same Windows account and Codex profile?
2. Does it apply to `codex app-server --stdio` launched independently using
   the same executable and environment?
3. Does it apply to the App Server subprocess launched by RAGenius?
4. Does the result change when Codex Desktop is running versus closed?
5. Does the result survive App Server, Codex Desktop, or Windows restart?
6. Which App Server request or notification, if any, represents initial
   application authorization?
7. Is `item/permissions/requestApproval` an application-authorization request,
   a broader sandbox-permission request, or context-dependent?
8. Can application discovery, state inspection, and interaction fail
   independently of approval?

## Non-Goals

- Do not implement an application-approval database in RAGenius.
- Do not auto-accept any provider permission request.
- Do not add an **Always allow** control to RAGenius.
- Do not change the current handling of
  `item/permissions/requestApproval` during this investigation.
- Do not enable Computer Use or generic user-action capabilities by default.
- Do not test external writes, credentials, payments, publishing, email,
  deletion, or access to private user content.
- Do not treat skill discovery as proof of application readiness.

## Current RAGenius Baseline

The test evaluates the released implementation without modifying it:

- Interactive Codex execution launches
  `codex app-server --stdio` as a child process.
- Codex preflight verifies App Server enablement and supported version, then
  advertises protocol and interaction capabilities.
- `item/permissions/requestApproval` is declined with
  `CODEX_PERMISSION_EXPANSION_BLOCKED`.
- Other recognized provider approval methods can become RAGenius
  `approval` interactions.
- `ragenius_request_user_action` is a bounded manual-action pause for an
  already approved application. It is not an application-approval mechanism.
- Generic user action is disabled by default.
- Browser and Computer Use post-action semantic verification remains deferred.

## Terms And Result States

The following states must be recorded separately:

| State | Meaning |
| --- | --- |
| `computer_use_available` | The tested transport can invoke Computer Use. |
| `application_discoverable` | The target application can be uniquely found. |
| `application_interactable` | A bounded test action can be performed. |
| `approval_prompt_seen` | A Codex-owned application approval prompt was visibly presented. |
| `protocol_permission_request_seen` | The client received a permission-related App Server request. |
| `approval_inherited` | A prior Desktop approval was repeatably honored by another transport. |
| `approval_persisted` | The same behavior remained after the specified restart boundary. |
| `policy_permitted` | The active Codex and RAGenius policies allowed the bounded operation. |

Each Boolean observation supports `true`, `false`, or `unknown`. Use `unknown`
when the test cannot distinguish authorization from application discovery,
runtime availability, protocol, or policy failure.

## Safety Profile

### Test machine and account

- Use a non-production Windows test account.
- Use the same Windows account for Desktop, CLI, App Server, and RAGenius tests.
- Record whether all paths resolve the same `%USERPROFILE%` and Codex profile
  directory, but do not record profile contents.
- Remove unrelated applications and private documents from the visible test
  workspace.

### Test applications

Use two harmless targets so one application's implementation does not determine
the conclusion:

1. Windows Calculator, with a bounded expression such as `7 + 5`.
2. Notepad with a disposable unsaved document containing only a unique marker.

If either application does not expose the required Computer Use surface, use a
second similarly harmless local application and record the substitution and
reason. Do not use File Explorer, email, browser accounts, IDE source trees, or
other applications containing private or externally mutable data for the
inheritance test.

### Allowed actions

- List or uniquely identify the target application window.
- Read the title or bounded visible test state.
- Enter a calculator expression without copying data elsewhere.
- Enter a unique non-secret marker into a new unsaved Notepad document.
- Close the disposable document without saving after evidence is collected.

No test action may create an external side effect.

## Fixed Environment Record

Capture this metadata before testing:

```yaml
test_run_id: cu-approval-YYYYMMDD-NN
tested_at: ISO-8601 timestamp with timezone
windows_version: bounded version and build
architecture: x64 | arm64
codex_version: semantic version
codex_command_path: absolute executable path
codex_profile_path: path only, no contents
codex_desktop_version: bounded version
ragenius_commit: full Git SHA
ragenius_execution_config:
  codex_app_server_interactive_enabled: true | false
  codex_interactive_user_action_enabled: true | false
desktop_running: true | false
host_environment: windows_native | wsl
target_application:
  name: string
  executable_or_package_identity: bounded identifier
```

Never record access tokens, cookies, environment-variable values, full
configuration files, screenshots containing private data, or unredacted
provider payloads.

## Protocol Observation Requirements

For direct App Server and RAGenius App Server tests, capture a bounded protocol
transcript containing only:

- timestamp and sequence number;
- request, response, or notification direction;
- JSON-RPC method name;
- JSON-RPC request id;
- top-level parameter key names;
- thread and turn correlation identifiers after hashing or replacement with
  stable test aliases;
- decision returned by the client;
- bounded error code and status.

For every permission-related message, separately record:

```yaml
method: item/permissions/requestApproval | other | none
parameter_keys: []
request_correlated_to_active_turn: true | false | unknown
request_preceded_visible_codex_prompt: true | false | unknown
request_followed_application_access: true | false | unknown
client_decision: accept | decline | cancel | none
provider_outcome: succeeded | blocked | failed | unknown
```

Raw screen state, command arguments, file paths, URLs, authentication material,
and private application content must not enter the transcript.

## Test Preparation

1. Confirm the target application is not already approved in Codex Desktop. If
   approval cannot be safely cleared, use a fresh Windows test account or a
   harmless application with no prior approval.
2. Record the exact Codex executable and version used by Desktop where visible,
   CLI, direct App Server, and RAGenius.
3. Confirm the independent CLI and App Server processes use the intended Codex
   profile path.
4. Keep RAGenius's current fail-closed permission behavior unchanged.
5. Disable unrelated MCP servers, skills, plugins, and external-action tools.
6. Prepare unique markers for each test case so stale application state cannot
   be mistaken for a successful action.
7. Run each non-restart case twice. A single successful observation is not
   sufficient evidence of inheritance.

## Staged Test Matrix

The stages are sequential. Stop and classify the result if a safety condition
is violated.

### Stage A: Codex Desktop baseline

Run each target application directly through Codex Desktop.

#### A1 - Unapproved application

1. Start the target application in the disposable state.
2. Ask Computer Use to perform the bounded test action.
3. Record whether an application approval prompt appears.
4. Deny or cancel the first request.
5. Verify that the action did not occur.

#### A2 - Persistent Desktop approval

1. Repeat the bounded action.
2. Select Codex Desktop's persistent approval option, if available.
3. Verify the bounded action succeeds.
4. Reset the application state and repeat without granting another approval.
5. Mark the Desktop baseline valid only if the second action succeeds without
   another application approval prompt.

If Desktop cannot establish a repeatable approved baseline, stop testing that
application and report `approval_inherited: unknown` for all dependent cases.

### Stage B: Independent Codex CLI

With the validated Desktop approval still present:

1. Launch Codex CLI independently from Windows PowerShell.
2. Request the same bounded action against the same application identity.
3. Record Computer Use availability, application discovery, any approval
   prompt, and the action result.
4. Reset the application state and repeat in a new CLI process.
5. Repeat once with Codex Desktop running and once with Desktop closed.

Do not classify approval as inherited merely because no prompt appeared. The
application must be uniquely discovered and the bounded action must succeed.

### Stage C: Direct Codex App Server

Use a disposable protocol recorder that starts the same configured Codex
executable with `app-server --stdio` outside RAGenius.

1. Initialize the App Server using the minimum supported client capabilities.
2. Start one scoped thread and turn requesting the bounded action.
3. Record all bounded protocol metadata defined above.
4. Do not automatically accept any permission request.
5. If a permission request appears, return `decline`, record the provider
   result, and end the case.
6. If no permission request appears and the action succeeds, reset and repeat
   in a new App Server process.
7. Repeat with Codex Desktop running and closed.

The disposable recorder must not be merged into production code. Its output is
test evidence only.

### Stage D: RAGenius Codex App Server

Run the same bounded request through RAGenius Interactive Agent mode.

1. Confirm the execution uses `codex_app_server` transport.
2. Keep `item/permissions/requestApproval` fail-closed.
3. Record whether RAGenius emits `CODEX_PERMISSION_EXPANSION_BLOCKED`.
4. Record whether Codex reports the application as unapproved, inaccessible,
   or unavailable.
5. If the action succeeds without permission expansion, reset and repeat in a
   new RAGenius execution.
6. Repeat with Codex Desktop running and closed.

This stage tests whether RAGenius's subprocess context changes the direct App
Server result. It does not test or grant approval through RAGenius.

### Stage E: Host boundary

Run only after Windows-native behavior is classified.

1. Attempt the same independent CLI probe from the supported WSL environment.
2. Record Computer Use availability before testing application discovery.
3. If Computer Use is unavailable, stop and record the remaining states as
   `unknown`, not `false`.
4. Do not attempt to bridge Windows application authorization into WSL.

### Stage F: Persistence boundaries

Run only for a transport where inheritance was provisionally observed twice.
Test in this order:

1. Restart the independent CLI or App Server process.
2. Restart Codex Desktop.
3. Restart RAGenius execution subsystem for the RAGenius case.
4. Restart Windows only after the preceding cases are complete and recorded.

After each boundary, reset the harmless application state and repeat the exact
bounded action twice. Record persistence independently for every boundary.

## Per-Case Evidence Record

```yaml
case_id: D-calculator-desktop-running-01
test_run_id: cu-approval-YYYYMMDD-NN
transport: desktop | cli | direct_app_server | ragenius_app_server
host_environment: windows_native | wsl
desktop_running: true | false
restart_boundary: none | cli | app_server | desktop | execution_subsystem | windows
target_application:
  name: Calculator
  identity: bounded identifier
desktop_baseline_approved: true | false | unknown
computer_use_available: true | false | unknown
application_discoverable: true | false | unknown
application_interactable: true | false | unknown
approval_prompt_seen: true | false | unknown
protocol_permission_request_seen: true | false | unknown
protocol_permission_method: string | null
client_decision: accept | decline | cancel | none
policy_permitted: true | false | unknown
operation_result: succeeded | blocked | failed | unknown
approval_inherited: true | false | unknown
approval_persisted: true | false | unknown
bounded_error_code: string | null
evidence_refs: []
notes: bounded non-secret text
```

## Classification Rules

### `approval_inherited: true`

All of the following must hold:

1. Desktop persistent approval was established and verified twice.
2. The tested path used the same Windows account, Codex profile, target
   application identity, and bounded action.
3. The other transport discovered the application and completed the action in
   two fresh provider processes.
4. No new application approval prompt appeared.
5. No permission request was silently auto-accepted by the recorder or
   RAGenius.

### `approval_inherited: false`

Use `false` only when Computer Use is available, the exact target application
is discoverable, policy otherwise permits the bounded action, and Codex
explicitly requests new application approval or reports that the application
is not approved.

### `approval_inherited: unknown`

Use `unknown` for all ambiguous outcomes, including Computer Use unavailable,
application not found, multiple matching windows, unsupported host, protocol
failure, stale application state, provider timeout, or policy rejection that
occurs before application authorization can be evaluated.

## Decision Rules After Testing

### If `item/permissions/requestApproval` is observed

1. Record the method and bounded schema shape across at least two applications.
2. Determine whether it occurs specifically for initial application approval
   or for unrelated sandbox expansion.
3. Keep production handling fail-closed.
4. Produce a separate contract/design proposal before considering any user
   presentation or response support.
5. Never infer that `accept` means persistent approval unless the provider
   protocol explicitly defines that behavior and a live test confirms it.

### If approval is enforced below the App Server protocol

1. Keep Codex Desktop as the sole approval UI.
2. Document the required Desktop setup and same-profile constraint.
3. Preserve exact provider errors in RAGenius with bounded remediation text.
4. Do not add a RAGenius approval interaction for an event it cannot bind and
   verify.

### If Desktop approval is inherited by App Server

1. Document it as a tested compatibility result tied to the exact Codex,
   Windows, profile, and host versions.
2. Continue treating readiness as runtime-dependent, not permanent metadata.
3. Do not persist an approval copy in Builder or the execution database.
4. Re-run the compatibility test when the Codex version or launch model
   materially changes.

### If Desktop approval is not inherited

1. Continue failing closed.
2. Explain that Computer Use must be approved in the provider context that owns
   the App Server operation.
3. If Codex exposes no safe provider-owned approval path, mark that application
   workflow unavailable rather than constructing a parallel approval system.

## Acceptance Criteria

The investigation is complete when:

- both harmless applications have valid Desktop baselines or a recorded reason
  why one could not be used;
- Desktop-to-CLI and Desktop-to-App-Server results are recorded separately;
- direct and RAGenius-launched App Server results are compared;
- Desktop-running and Desktop-closed states are tested;
- every permission-related App Server method is captured in bounded form;
- `item/permissions/requestApproval` is classified as participating,
  unrelated, context-dependent, or not observed;
- every inheritance conclusion satisfies the classification rules;
- restart persistence is tested only for provisionally inherited paths;
- no external action or private-data access occurs; and
- the final recommendation explicitly preserves or proposes a separately
  reviewed change to the fail-closed production behavior.

## Deliverables

1. Completed environment and per-case evidence records.
2. Redacted direct App Server protocol transcript.
3. Redacted RAGenius execution event and warning transcript.
4. Comparison table for Desktop, CLI, direct App Server, and RAGenius App
   Server.
5. A concise conclusion stating what was verified, what remains unknown, and
   whether a separate production contract/design task is justified.
