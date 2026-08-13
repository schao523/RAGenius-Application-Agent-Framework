# OpenClaw Execution Policy Profiles

Date: 2026-08-13

## Purpose

Define the administrator-controlled OpenClaw policy profiles used while
RAGenius transitions from the autonomous one-shot CLI provider to the
interactive Gateway adapter. RAGenius startup and runtime code must inspect but
must not change these policies.

## Normal One-Shot Profile

Use this profile until the interactive OpenClaw adapter passes production
acceptance and is enabled for users:

```text
security: full
ask: on-miss
askFallback: deny
```

`security: full` means commands do not produce an allowlist miss, so
`ask: on-miss` does not normally pause execution. This preserves the existing
`openclaw agent --json` provider, which cannot mediate Gateway approval events.
It is less restrictive than the interactive profile and is not valid for
approval acceptance testing.

Activate and verify from PowerShell:

```powershell
wsl -d OpenClawGateway -- openclaw config set tools.exec.security full
wsl -d OpenClawGateway -- openclaw config set tools.exec.ask on-miss
wsl -d OpenClawGateway -- openclaw config set tools.exec.askFallback deny
wsl -d OpenClawGateway -- openclaw gateway restart
wsl -d OpenClawGateway -- openclaw approvals get --gateway --json
```

The effective policy must report `security: full`, `ask: on-miss`, and
`askFallback: deny`.

## Interactive Approval Test Profile

Use this profile only for interactive-adapter development and acceptance:

```text
security: allowlist
ask: on-miss
askFallback: deny
```

Activate and verify:

```powershell
wsl -d OpenClawGateway -- openclaw config set tools.exec.security allowlist
wsl -d OpenClawGateway -- openclaw config set tools.exec.ask on-miss
wsl -d OpenClawGateway -- openclaw config set tools.exec.askFallback deny
wsl -d OpenClawGateway -- openclaw gateway restart
wsl -d OpenClawGateway -- openclaw approvals get --gateway --json
```

The effective policy must report `security: allowlist`, `ask: on-miss`, and
`askFallback: deny`. OpenClaw 2026.6.8 external approval mediation also requires
a protected credential with both `operator.admin` and `operator.approvals`.
That credential must remain in the execution subsystem and must never be sent
to the app, browser, logs, or execution results.

## Transition Rules

1. Stop or drain new OpenClaw Agent submissions before switching profiles.
2. Change policy only through an explicit administrator action.
3. Restart the Gateway and verify the effective policy before testing.
4. Run only disposable allow-once, deny, and expiry acceptance cases.
5. Restore the normal profile after testing until the interactive adapter is
   the enabled production transport.
6. Smoke-test the current one-shot provider after restoring the normal profile.

Under the interactive test profile, the existing one-shot provider may wait
until timeout or fail whenever a command needs approval. This is expected and
must not be bypassed by changing `askFallback` to an allow mode.

## Rollback

If interactive testing fails, disable the interactive feature flag, restore
`security: full`, restart the Gateway, verify the effective policy, and run a
read-only plus harmless-exec one-shot smoke test. Do not mutate approval
allowlists or issue `allow-always` as a rollback mechanism.
