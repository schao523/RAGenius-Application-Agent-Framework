# Codex Agent Skill Activation Test Results

Date: 2026-08-09

## Runtime

- Codex CLI: `codex-cli 0.146.0`
- Executable: configured production Codex desktop CLI
- Discovery source: `Approved Codex Plugin Cache`
- Plugin id: `superpowers@openai-curated`
- Manifest name: `systematic-debugging`
- Canonical reference: `superpowers:systematic-debugging`
- Task: read-only activation marker; no network request and no file modification

## Discovery

`codex plugin list --json` reported the enabled local plugin. The execution
discovery adapter canonicalized its source, confirmed containment within the
administrator-approved broad root, inspected its manifests, and returned:

```json
{
  "complete": true,
  "provider_skill_name": "systematic-debugging",
  "provider_skill_reference": "superpowers:systematic-debugging",
  "discovery_status": "available"
}
```

Other installed plugins outside the single approved test root were omitted
with `AGENT_SKILL_SOURCE_NOT_ALLOWED`, as required by the fail-closed policy.

## Invocation

| Method | Result | Duration | Evidence |
|---|---|---:|---|
| `$superpowers:systematic-debugging <request>` | passed | 18.1 s | process-observed successful `SKILL.md` read |
| ordinary explicit guidance | diagnostic pass | 31.7 s | process-observed after filesystem search |

The explicit method completed with exit code `0`, no timeout, and prompt first
line `$superpowers:systematic-debugging`. The ordinary-guidance run remains a
diagnostic comparison and is not an acceptable fallback pass condition.

When Codex completes an immutable explicit-reference turn without emitting a
structured skill-file read, RAGenius records `provider_reference_resolved`.
A successful structured read remains the stronger `process_observed` evidence.
Model-produced activation claims alone remain `agent_reported`.

## Migration And Regression

Migration `20260809_codex_plugin_skill_reference` was applied successfully to
the local `ragenius_execution` PostgreSQL database. Prisma validation passed.

- Execution subsystem: lint, typecheck, and full test suite passed.
- Builder: 87 tests passed.
- App Agent-skill inventory boundary: 2 tests passed.
- Public execution and app inventories omit canonical references, provider
  metadata, protected locators, and filesystem paths.

## Repeat

```powershell
$env:CODEX_AGENT_SKILL_SMOKE_NAME = "systematic-debugging"
$env:CODEX_AGENT_SKILL_SMOKE_REFERENCE = "superpowers:systematic-debugging"
$env:CODEX_CLI_COMMAND = "C:\Users\User\AppData\Local\Programs\OpenAI\Codex\bin\codex.exe"
$env:CODEX_CLI_SANDBOX_MODE = "read-only"
npm run smoke:codex-agent-skill
```

The script exits nonzero unless the explicit method completes and reports
`provider_reference_resolved` or stronger `process_observed` evidence.
