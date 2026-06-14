# OpenClaw CLI Test Results

Date: 2026-06-13

Checklist source: [openclaw-cli-test-checklist.md](/D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/docs/openclaw-cli-test-checklist.md)

## Scope

Executed the minimum required test set against the real `OpenClawGateway` WSL runtime from Windows PowerShell.

## Environment Facts

- `wsl -d OpenClawGateway which openclaw` resolved to `/usr/local/bin/openclaw`
- `openclaw --version` returned `OpenClaw 2026.6.6 (8c802aa)`
- `openclaw gateway status --json` reported the gateway running on `ws://127.0.0.1:18789`
- baseline WSL access required running outside the Codex sandbox; inside the sandbox, `wsl` returned `E_ACCESSDENIED`

## Executed Tests

- `T00-T02`
- `T10-T14`
- `T20-T22`
- `T30-T32`
- `T40-T42`
- `T50-T51`
- `T60-T61`
- `T80-T82`
- `T90-T91`
- `T101`

## Observed Results

### Invocation and Exit Behavior

- `T10` passed. Plain `openclaw agent --agent main --message ...` returned exit code `0` and a direct text response.
- `T11` passed after using a simple session key form such as `ragenius-contract-test-minimal`.
- `T12` passed. `--json` returned valid JSON with a stable top-level shape:
  - `runId`
  - `status`
  - `summary`
  - `result`
- `T13` showed timeout is not surfaced as a CLI process failure. With `--timeout 3`, the command still exited `0` and returned a plain-text timeout message: `Request timed out before a response was generated...`
- `T14` invalid flags produced exit code `1` with explicit CLI diagnostics.

### Session Semantics

- `T20` confirmed session reuse. A token set in the first prompt was recalled correctly in the second prompt using the same session key.
- `T21` confirmed session isolation. A fresh session did not inherit prior context.
- `T22` confirmed `openclaw sessions --json` exposes:
  - session key
  - session id
  - updated timestamp
  - model/provider metadata
- session keys appear in stored form as `agent:main:<key>`

### Workspace Write Contract

- `T30` passed. OpenClaw created `/home/openclaw/.openclaw/workspace/ragenius-tests/output/t30.md` and the file contents matched verification by `cat`.
- `T31` passed. OpenClaw created nested parent directories automatically.
- `T32` passed. Explicit overwrite instructions were followed.

### Constraint Following

- `T40` passed. Explicit workspace-only instructions were followed.
- `T41` passed. The agent produced the requested file while instructed not to use `/mnt/c` or `/mnt/d`.
- `T42` showed ambiguous prompts are less deterministic. OpenClaw selected `/home/openclaw/.openclaw/workspace/report-output-determinism.md` on its own. This reinforces the need for RAGenius to provide exact output paths.

### Text Artifact Import and Consumption

- `T50` passed. Text import from Windows via `Get-Content ... | wsl ... tee ...` worked reliably.
- `T51` passed. OpenClaw read the imported Markdown file and produced a summary file at the requested workspace path.

### Binary Artifact Import and Consumption

- `T60` produced a mixed result:
  - the base64 import pipeline returned nonzero (`t60_import_exit=1`)
  - the target PNG file still appeared at the expected workspace path with the expected size (`68` bytes)
- `T61` passed. OpenClaw inspected the staged `1x1` PNG and produced a correct Markdown summary.
- implication: binary import works, but the chosen base64 pipeline may report noisy/non-clean exit behavior and should be wrapped carefully.

### JSON Reliability

- `T80` passed. `--json` on a write task returned valid JSON and included the resulting path in `result.payloads[0].text`.
- `T81` is a critical finding:
  - missing-input failure still returned exit code `0`
  - JSON `status` remained `ok`
  - JSON `summary` remained `completed`
  - the failure was only expressed in assistant text
- `T82` passed for shape stability on simple prompts. Across repeated runs:
  - exit code stayed `0`
  - `status=ok`
  - `summary=completed`
  - `payload0=OK.`

### Failure Modes

- `T90` missing input artifact returned exit code `0` and a conversational explanation of `ENOENT`; no structured hard error was emitted.
- `T91` longer task completed successfully in about `14.2s` and wrote the requested Markdown output.

### Same-Session Concurrency

- `T101` passed operationally. Two concurrent runs using the same session key both completed and created separate files:
  - `t101-a.md`
  - `t101-b.md`
- This does not prove same-session concurrency is safe semantically. It only proves it is not immediately rejected by the CLI/runtime.

## Contract Implications

### Confirmed

- OpenClaw is feasible as a real agent execution backend.
- Session keys are usable and observable.
- Workspace-path-based file generation is reliable when RAGenius provides explicit paths.
- Windows-to-workspace text staging is straightforward.
- OpenClaw can consume staged binary artifacts, at least for simple files.

### Required Contract Rules

- RAGenius must always provide explicit output paths.
- RAGenius must independently verify expected output artifacts after the run.
- RAGenius must not rely on exit code alone for success/failure.
- RAGenius must not rely on top-level OpenClaw JSON `status` alone for success/failure.
- RAGenius must treat OpenClaw JSON as advisory and still enforce provider-side verification rules.
- RAGenius should keep all inputs and outputs under `/home/openclaw/.openclaw/workspace`.

### Open Questions

- Whether binary import should use a different transfer method than the current base64 pipeline wrapper.
- Whether same-session parallel runs should be forbidden by contract even though they technically run.
- Whether OpenClaw provides any stronger structured failure indicator than the observed `status=ok/summary=completed` pattern for user-level task failures.

## Recommended Next Step

Use these results to write the OpenClaw execution contract before any design or refactor planning.
