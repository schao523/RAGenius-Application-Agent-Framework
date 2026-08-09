# Codex Agent Skill Activation Test Results

Date: 2026-08-04

## Runtime

- Codex CLI: `codex-cli 0.146.0`
- Executable: configured production Codex desktop CLI
- Codex home: active user Codex home
- Test skill: `research-paper-finder`
- Skill manifest observed: `<CODEX_HOME>/skills/research-paper-finder/SKILL.md`
- Task: read-only activation marker; no network request and no file modification

## Comparison

Both methods caused Codex to emit a successful structured command event reading
the exact effective `research-paper-finder/SKILL.md` and then complete the turn.

| Method | Result | Duration | Evidence |
|---|---|---:|---|
| `$research-paper-finder <request>` | passed | 14.6 s | process-observed `SKILL.md` read |
| ordinary explicit guidance | passed | 13.5 s | process-observed `SKILL.md` read |

The observed durations are diagnostic only and are not treated as a performance
benchmark.

## Decision

Use `codex_explicit_reference` for the MVP. The `$<provider_skill_name>` line is
provider-supported, deterministic, and preserves the existing RAGenius prompt
envelope. Ordinary guidance remains documented as a tested fallback strategy,
but the runtime must not silently switch methods for one execution.

Normalized activation is `process_observed` only when the structured Codex JSONL
contains a successful command event reading the canonical selected skill's
`SKILL.md`. Model-produced `activated_skills` without that event remains
`agent_reported` evidence.

## Repeat

```powershell
$env:CODEX_AGENT_SKILL_SMOKE_NAME = "research-paper-finder"
$env:CODEX_CLI_COMMAND = "C:\Users\User\AppData\Local\Programs\OpenAI\Codex\bin\codex.exe"
npm run smoke:codex-agent-skill
```

The script exits nonzero unless at least one method produces process-observed
activation evidence and reports the selected method in its JSON summary.
