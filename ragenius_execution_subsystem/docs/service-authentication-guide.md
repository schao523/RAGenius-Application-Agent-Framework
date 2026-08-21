# Execution Subsystem Service Authentication

## Purpose

Service authentication ensures that only a trusted RAGenius backend can call
the execution subsystem.

It protects execution, status, logs, diagnostics, and confirmation endpoints
under `/v1/*`. Health checks such as `/healthz` remain available without a
token.

## Environment Variables

### `RAGENIUS_EXECUTION_SERVICE_TOKEN`

This is a shared secret between:

- `ragenius_app_skeleton` backend
- `ragenius_execution_subsystem`

The app backend sends the token in this HTTP header:

```text
Authorization: Bearer <token>
```

The execution subsystem returns HTTP `401` when the token is missing or
incorrect.

Use the same strong token in both services. Do not expose it to the frontend or
commit it to Git.

When scoped credentials are configured, the `ragenius_app` credential requires
both `agent_skills:read` and `artifacts:write`. The latter authorizes the app
backend to stream a session upload into the execution artifact store; it does
not grant the browser direct access.

```powershell
$env:RAGENIUS_EXECUTION_SERVICE_CREDENTIALS_JSON = '[{"service_id":"ragenius_app","token":"replace-app-token","scopes":["execution","agent_skills:read","artifacts:write"]},{"service_id":"ragenius_builder","token":"replace-builder-token","scopes":["agent_skills:admin"]}]'
```

### `RAGENIUS_EXECUTION_SERVICE_AUTH_REQUIRED=true`

This setting tells the execution subsystem that service authentication is
mandatory.

When it is `true`, the execution subsystem refuses to start if
`RAGENIUS_EXECUTION_SERVICE_TOKEN` is missing. This prevents the API from being
started accidentally without protection.

## Activate Authentication on Windows

### 1. Generate a token

Run this once in PowerShell:

```powershell
$bytes = New-Object byte[] 32
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($bytes)
$rng.Dispose()
$token = [Convert]::ToBase64String($bytes)

$token
```

Keep this PowerShell window open so that `$token` remains available.

### 2. Start the execution subsystem

In the PowerShell window used to start `ragenius_execution_subsystem`:

```powershell
$env:RAGENIUS_EXECUTION_SERVICE_AUTH_REQUIRED = "true"
$env:RAGENIUS_EXECUTION_SERVICE_ID = "ragenius_app"
$env:RAGENIUS_EXECUTION_SERVICE_TOKEN = $token

cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
.\start-ragenius-execution-subsystem.ps1
```

### 3. Start the app backend

In the separate PowerShell window used to start the
`ragenius_app_skeleton` backend, assign the same token:

```powershell
$env:RAGENIUS_EXECUTION_SERVICE_TOKEN = $token

cd D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton
# Run the existing backend startup command here.
```

Both services must be restarted after changing the token.

For Composer Agent inputs, keep the app and execution limits aligned:

```powershell
$env:RAGENIUS_AGENT_INPUT_MAX_BYTES = "536870912"
$env:AGENT_INPUT_MAX_BYTES = "536870912"
```

## Verify Authentication

The following request should return HTTP `401` because it has no token:

```powershell
Invoke-RestMethod http://localhost:3001/v1/tools/inventory
```

The authenticated request should succeed:

```powershell
Invoke-RestMethod `
  http://localhost:3001/v1/tools/inventory `
  -Headers @{ Authorization = "Bearer $token" }
```

The health check should continue to succeed without authentication:

```powershell
Invoke-RestMethod http://localhost:3001/healthz
```

## `.env` Loading

The execution-subsystem PowerShell script loads values from its local `.env`
when the same process variable has not already been set. Explicit `$env:`
values therefore override `.env`. Restart the service after changing either.

## OpenClaw Chat-Level Continuation

Chat-level continuation is independently disabled by default. Development
testing requires both flags and an exact supported Gateway version:

```powershell
$env:OPENCLAW_GATEWAY_INTERACTIVE_ENABLED = "true"
$env:OPENCLAW_GATEWAY_CHAT_LEVEL_ENABLED = "true"
$env:OPENCLAW_GATEWAY_CHAT_IDLE_TTL_MS = "900000"
```

The startup script rejects chat-level mode when the base Gateway interactive
transport is disabled. Keep chat-level mode off for production until the full
CL-01 through CL-28 acceptance matrix passes.

The `ragenius_app` credential must include the `execution` scope for scoped
interaction, follow-up, cancellation, and chat-session APIs. Keep
`agent_skills:read` for the Composer inventory and `artifacts:write` for session
upload preparation. Builder should retain its separate `agent_skills:admin`
credential rather than receiving the app's execution scope.

## Disable Authentication for Local Development

Stop both services, remove the environment variables from their PowerShell
sessions, and restart:

```powershell
Remove-Item Env:RAGENIUS_EXECUTION_SERVICE_AUTH_REQUIRED -ErrorAction SilentlyContinue
Remove-Item Env:RAGENIUS_EXECUTION_SERVICE_ID -ErrorAction SilentlyContinue
Remove-Item Env:RAGENIUS_EXECUTION_SERVICE_TOKEN -ErrorAction SilentlyContinue
```

Do not disable service authentication when the execution subsystem is exposed
beyond a trusted local development environment.

## Artifact Lifecycle Notes

The `artifacts:write` scope authorizes scoped artifact import and deletion
delegation. It does not bypass app/session ownership, execution confirmation, or
provider policy. The browser never receives this credential and never calls
execution storage directly.

Repeated upload operation ids are idempotent, and same-session duplicate content
is deduplicated by hash, size, and normalized MIME type. Artifact deletion
creates a tombstone rather than erasing all metadata. Normal listing and reuse
reject tombstoned artifacts, while completed execution records retain stable
evidence. A queued, running, or pending-confirmation execution blocks deletion
with `ARTIFACT_IN_USE`; the user may retry after execution reaches a terminal
state.
