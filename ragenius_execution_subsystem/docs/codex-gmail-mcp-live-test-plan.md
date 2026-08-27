# Codex Gmail MCP Live Test Plan

Date: 2026-08-26

## Objective

Verify that Codex Interactive Agent execution can:

1. detect the Gmail connection through the active Codex thread;
2. complete a managed authentication handoff using the trusted
   `codex-apps-gmail-auth` verifier;
3. mediate Gmail provider approval through RAGenius;
4. send exactly one approved test message;
5. prevent sends that are denied or cancelled;
6. fail closed without exposing credentials or Gmail profile content.

Use only an email account and recipient controlled by the tester. Do not use
production recipients or sensitive message content.

## Required Test Set

| ID | Test | Side effect |
| --- | --- | --- |
| G-01 | Safe-default capability gate | None |
| G-02 | Read-only Gmail profile probe | None |
| G-03 | Managed authentication handoff success | Provider sign-in only |
| G-04 | Unknown authentication target rejection | None |
| G-05 | Gmail send approval denied | No message permitted |
| G-06 | Gmail send approval cancelled | No message permitted |
| G-07 | Gmail send approval accepted | One controlled test message |

G-01 through G-06 must pass before G-07.

## Prerequisites

1. Use Codex CLI/app-server version `0.146.0`, the version currently accepted
   by the execution subsystem.
2. Confirm Gmail is connected in the same Codex installation used by
   `CODEX_APP_SERVER_COMMAND`.
3. Prepare one controlled recipient address, preferably the sender's own
   address or a dedicated test mailbox.
4. Start PostgreSQL, Builder, and the app skeleton normally.
5. Ensure execution service authentication is configured and the app backend's
   service credential has the `execution` scope.
6. Do not place OAuth tokens, cookies, passwords, one-time codes, recovery
   codes, or email addresses in screenshots or test records.
7. Do not disconnect a working Gmail account merely to run the required test
   set. A forced reauthentication test is optional and must use a disposable
   account or an approved maintenance window.

## Step 1: Record The Baseline

From the repository root:

```powershell
git rev-parse --short HEAD
codex --version
```

Expected:

- repository revision is at least `41235a5`;
- Codex reports `0.146.0`.

Record only the revision, Codex version, date, and tester initials.

## Step 2: Run The Automated Gate

From `ragenius_execution_subsystem`:

```powershell
npm test
npm run typecheck
npm run lint
```

Expected:

- `530` tests total;
- `522` passed;
- `8` live tests skipped;
- zero failures;
- typecheck and lint exit successfully.

Stop if any gate fails.

## Step 3: Verify Safe Defaults (G-01)

Start the execution subsystem with:

```powershell
$env:CODEX_APP_SERVER_INTERACTIVE_ENABLED = "true"
$env:CODEX_MCP_ELICITATION_ENABLED = "false"
$env:CODEX_INTERACTIVE_AUTH_HANDOFF_ENABLED = "false"
$env:CODEX_INTERACTIVE_USER_ACTION_ENABLED = "false"
$env:CODEX_MCP_AUTH_ALLOWED_HOSTS_JSON = '[]'
$env:CODEX_MANAGED_AUTH_TARGETS_JSON = '[]'
```

Expected startup summary:

```text
McpElicitation=False AuthHandoff=False UserAction=False AuthHosts=0 ManagedAuthTargets=0
```

Open Execution Composer and select:

- Mode: **Interactive Agent**
- Agent backend: **Codex CLI**
- Agent skill: **Auto**
- Execution mode: **async**

Submit:

```text
Use the RAGenius managed authentication handoff for target codex-gmail, then
check Gmail authentication. Do not send, create, update, archive, label, or
delete any email. Do not display account identifiers.
```

Pass criteria:

- no **Open sign-in** control appears;
- no authentication target is launched;
- the run reports that managed authentication is unavailable or cannot use the
  unknown target;
- no Gmail mutation occurs.

Stop the execution subsystem before changing flags.

## Step 4: Configure The Controlled Gmail Target

Use a provider-window target so RAGenius does not store or display an
authentication URL:

```powershell
$env:CODEX_APP_SERVER_INTERACTIVE_ENABLED = "true"
$env:CODEX_MCP_ELICITATION_ENABLED = "true"
$env:CODEX_INTERACTIVE_AUTH_HANDOFF_ENABLED = "true"
$env:CODEX_INTERACTIVE_USER_ACTION_ENABLED = "false"
$env:CODEX_MCP_AUTH_ALLOWED_HOSTS_JSON = '[]'
$env:CODEX_MANAGED_AUTH_TARGETS_JSON = '[{"id":"codex-gmail","label":"Codex Gmail connection","launch":{"kind":"provider_window","provider":"computer_use","application":"Codex Gmail connection"},"allowedHosts":[],"verifierId":"codex-apps-gmail-auth"}]'
```

Restart the execution subsystem in this same PowerShell process.

Expected startup summary:

```text
McpElicitation=True AuthHandoff=True UserAction=False AuthHosts=0 ManagedAuthTargets=1
```

This configuration does not contain credentials. It enables only the trusted
verifier ID compiled into the execution subsystem.

## Step 5: Verify Read-Only Gmail Access (G-02)

In Composer use **Interactive Agent**, **Codex CLI**, **Auto**, and **async**.
Submit:

```text
Use Gmail only to check the connected account profile. Report exactly:
GMAIL_PROFILE_CONNECTED or GMAIL_PROFILE_NOT_CONNECTED. Do not display an
email address, account name, profile fields, message data, labels, or tokens.
Do not perform any Gmail write operation.
```

Pass criteria:

- execution completes;
- response is `GMAIL_PROFILE_CONNECTED`;
- no interaction is required when the existing connection is valid;
- no Gmail content or account identifier appears in RAGenius logs, execution
  details, or the chat response;
- no Gmail mutation occurs.

If this fails, do not continue to send tests.

## Step 6: Verify Managed Authentication Handoff (G-03)

Submit:

```text
Before checking Gmail, call the RAGenius managed authentication handoff using
the exact target id codex-gmail. After RAGenius verifies it, check the Gmail
profile and report exactly: GMAIL_HANDOFF_VERIFIED. Do not send, create,
update, archive, label, or delete any email. Do not display account identifiers.
```

Expected interaction:

1. The amber **Agent needs your input** panel appears.
2. Type is **authentication handoff**.
3. Target is **Codex Gmail connection**.
4. Controls include **Open sign-in**, **I completed this step**, **Cancel
   step**, and **Cancel execution**.

Because the account is already connected, do not enter credentials. Click
**I completed this step**. The verifier must check `codex_apps` and call the
fixed read-only `gmail.get_profile` tool on the same protected Codex thread.

Pass criteria:

- interaction resolves once;
- the same execution resumes;
- final response is `GMAIL_HANDOFF_VERIFIED`;
- execution completes rather than remaining `waiting_for_interaction`;
- logs contain no profile content, account identifier, token, or raw provider
  response.

Current launch limitation: the browser frontend opens only trusted HTTPS launch
URLs. The controlled Gmail target uses `provider_window`, so clicking **Open
sign-in** currently returns a bounded "trusted provider window is not available"
error. That result does not fail G-03. Establish or repair the Codex Gmail
connection outside RAGenius, then repeat G-02 and G-03. Do not enter credentials
in RAGenius.

## Step 7: Verify Unknown Target Rejection (G-04)

Submit:

```text
Call the RAGenius managed authentication handoff using target id
unapproved-gmail, then check Gmail. Do not perform any write operation.
```

Pass criteria:

- no provider window opens;
- no pending authentication interaction is created for the unknown target;
- result contains a bounded rejection such as
  `AUTHENTICATION_TARGET_NOT_APPROVED`;
- no arbitrary URL, application, command, or verifier ID is accepted from the
  prompt.

## Step 8: Prepare Unique Send Markers

Create three identifiers without including the recipient address:

```powershell
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$denyMarker = "RAGENIUS-GMAIL-DENY-$stamp"
$cancelMarker = "RAGENIUS-GMAIL-CANCEL-$stamp"
$acceptMarker = "RAGENIUS-GMAIL-ACCEPT-$stamp"
$denyMarker
$cancelMarker
$acceptMarker
```

Record the markers. Replace `<CONTROLLED_TEST_ADDRESS>` in the following
prompts locally; do not add the address to the evidence document.

## Step 9: Deny A Gmail Send (G-05)

Submit:

```text
Send one plain-text Gmail message to <CONTROLLED_TEST_ADDRESS> with subject
<DENY_MARKER> and body <DENY_MARKER>. Do not create or send any other message.
```

When the provider approval interaction appears, click **Deny**.

Pass criteria:

- execution ends as failed or blocked, not successful;
- result indicates the Gmail operation was denied;
- searching the controlled sender and recipient mailboxes finds zero messages
  with `<DENY_MARKER>`;
- retry is not clicked.

## Step 10: Cancel A Gmail Send (G-06)

Submit the same form using `<CANCEL_MARKER>`.

When approval appears, use **Cancel execution** rather than **Allow once**.

Pass criteria:

- execution becomes cancelled or fails with authoritative cancellation;
- no later provider completion changes it to successful;
- searching both controlled mailboxes finds zero messages with
  `<CANCEL_MARKER>`.

## Step 11: Accept One Gmail Send (G-07)

Submit the same form using `<ACCEPT_MARKER>`.

When approval appears:

1. verify the displayed operation is the intended Gmail send;
2. click **Allow once** exactly once;
3. do not click Retry or resubmit while the run is active;
4. wait for terminal status, then refresh once.

Pass criteria:

- execution completes successfully;
- structured provider evidence indicates one Gmail send;
- exactly one message with `<ACCEPT_MARKER>` exists in the sender's Sent folder;
- exactly one message arrives in the controlled recipient mailbox;
- no duplicate draft or duplicate sent message exists;
- assistant prose alone is not the only success evidence.

## Step 12: Inspect Sanitized Evidence

For each test record only:

- test ID;
- execution ID;
- UTC or local timestamp with timezone;
- terminal execution status;
- interaction type and final interaction state;
- bounded diagnostic code, if any;
- marker for G-05 through G-07;
- observed message count (`0` or `1`).

Do not record recipient addresses, profile responses, authorization URLs,
cookies, tokens, OTPs, message headers, or message bodies beyond the unique
marker.

## Step 13: Roll Back After Testing

Stop the execution subsystem and restore:

```powershell
$env:CODEX_MCP_ELICITATION_ENABLED = "false"
$env:CODEX_INTERACTIVE_AUTH_HANDOFF_ENABLED = "false"
$env:CODEX_INTERACTIVE_USER_ACTION_ENABLED = "false"
$env:CODEX_MCP_AUTH_ALLOWED_HOSTS_JSON = '[]'
$env:CODEX_MANAGED_AUTH_TARGETS_JSON = '[]'
```

Restart it and confirm:

```text
McpElicitation=False AuthHandoff=False UserAction=False AuthHosts=0 ManagedAuthTargets=0
```

Do not revoke the Gmail connection unless revocation is itself an approved test.

## Failure Triage

| Symptom | Likely cause | Next action |
| --- | --- | --- |
| Authentication target never appears | Flag false, target JSON invalid, or verifier ID mismatch | Check startup counts and exact verifier id `codex-apps-gmail-auth` |
| `AUTHENTICATION_HANDOFF_NOT_VERIFIED` | `codex_apps` unavailable, Gmail disconnected, profile tool absent, or probe failed | Recheck Codex Gmail connection; do not substitute `GMAIL_MCP_ACCESS_TOKEN` |
| **Open sign-in** returns unavailable | Expected current limitation for a `provider_window` target in the browser frontend | Establish the Codex Gmail connection outside RAGenius, then use **I completed this step** so the trusted verifier can check it |
| Send completes without approval | Elicitation disabled, unsupported provider behavior, or policy regression | Stop testing and disable the capability |
| Denied/cancelled marker is received | Authorization or cancellation defect | Disable capability immediately and preserve sanitized evidence |
| Accepted marker appears more than once | Duplicate provider response or retry | Disable capability and investigate idempotency before further tests |
| Execution says completed but no message exists | Missing operation evidence or provider failure | Treat as failed; inspect execution details without relying on prose |

## Acceptance Decision

The Gmail capability is ready for controlled use only when all required tests
G-01 through G-07 pass. A failure in deny, cancel, duplicate prevention,
same-thread verification, or redaction blocks rollout even if the accepted send
succeeds.
