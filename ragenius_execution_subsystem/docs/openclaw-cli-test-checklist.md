# OpenClaw CLI Test Checklist

Last updated: 2026-06-13

## Purpose

This checklist establishes observed OpenClaw CLI behavior before writing:

- the OpenClaw agent execution contract
- the integration design
- the staged refactor plan

The goal is to capture facts, not assumptions.

## Test Rules

- Run every command from Windows PowerShell.
- Record the exact command, exit code, stdout, stderr, elapsed time, and verification result.
- Use a dedicated session key prefix: `ragenius-contract-test`.
- Keep all OpenClaw-generated files under `/home/openclaw/.openclaw/workspace/ragenius-tests`.
- Verify every output artifact from Windows after the agent run.
- Do not treat a model reply alone as proof of success if a file was supposed to be created.

## Suggested Evidence Log Template

Use this template for each test:

```text
Test ID:
Purpose:
Command:
Exit code:
Elapsed time:
Stdout:
Stderr:
Artifact path:
Verification command:
Verification result:
Deterministic: yes/no
Contract implication:
```

## Test Variables

Run these first in the same PowerShell session:

```powershell
$OpenClawDistro = "OpenClawGateway"
$OpenClawAgent = "main"
$OpenClawWorkspace = "/home/openclaw/.openclaw/workspace"
$OpenClawTestRoot = "$OpenClawWorkspace/ragenius-tests"
$OpenClawInputRoot = "$OpenClawTestRoot/input"
$OpenClawOutputRoot = "$OpenClawTestRoot/output"
$SessionPrefix = "ragenius-contract-test"
$LocalOutputRoot = "D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\storage\openclaw-test-outputs"
New-Item -ItemType Directory -Force -Path $LocalOutputRoot | Out-Null
```

## Phase 0: Baseline Setup

### T00. CLI Presence

```powershell
wsl -d $OpenClawDistro which openclaw
wsl -d $OpenClawDistro openclaw --version
```

Record:

- whether `openclaw` resolves
- version string

### T01. Runtime Health

```powershell
wsl -d $OpenClawDistro openclaw health --verbose
wsl -d $OpenClawDistro openclaw gateway status --json
wsl -d $OpenClawDistro openclaw doctor
```

Record:

- which checks pass
- whether output is human-only or machine-parseable

### T02. Workspace Baseline

```powershell
wsl -d $OpenClawDistro mkdir -p $OpenClawTestRoot
wsl -d $OpenClawDistro mkdir -p $OpenClawInputRoot
wsl -d $OpenClawDistro mkdir -p $OpenClawOutputRoot
wsl -d $OpenClawDistro ls -R $OpenClawTestRoot
```

Record:

- whether parent directory creation is reliable

## Phase 1: Invocation and Exit Behavior

### T10. Minimal Prompt

```powershell
$sw = [Diagnostics.Stopwatch]::StartNew()
wsl -d $OpenClawDistro openclaw agent --agent $OpenClawAgent --message "Reply with exactly: OK."
$exit = $LASTEXITCODE
$sw.Stop()
"exit=$exit elapsed_ms=$($sw.ElapsedMilliseconds)"
```

Expected observation:

- no interactive prompt
- exit code behavior
- plain-text reply shape

### T11. Minimal Prompt With Session Key

```powershell
$SessionKey = "$SessionPrefix:minimal"
$sw = [Diagnostics.Stopwatch]::StartNew()
wsl -d $OpenClawDistro openclaw agent --agent $OpenClawAgent --session-key $SessionKey --message "Reply with exactly: OK."
$exit = $LASTEXITCODE
$sw.Stop()
"exit=$exit elapsed_ms=$($sw.ElapsedMilliseconds)"
```

### T12. JSON Mode on Minimal Prompt

```powershell
$SessionKey = "$SessionPrefix:minimal-json"
$sw = [Diagnostics.Stopwatch]::StartNew()
wsl -d $OpenClawDistro openclaw agent --agent $OpenClawAgent --session-key $SessionKey --json --message "Reply with exactly: OK."
$exit = $LASTEXITCODE
$sw.Stop()
"exit=$exit elapsed_ms=$($sw.ElapsedMilliseconds)"
```

Record:

- exact JSON envelope
- whether the output is valid JSON every time

### T13. Timeout Behavior

```powershell
$SessionKey = "$SessionPrefix:timeout"
$sw = [Diagnostics.Stopwatch]::StartNew()
wsl -d $OpenClawDistro openclaw agent --agent $OpenClawAgent --session-key $SessionKey --timeout 3 --message "Think carefully for a long time before replying."
$exit = $LASTEXITCODE
$sw.Stop()
"exit=$exit elapsed_ms=$($sw.ElapsedMilliseconds)"
```

Record:

- timeout exit code
- timeout stderr/stdout pattern
- whether it returns structured JSON under `--json`

### T14. Invalid Flag Failure

```powershell
$sw = [Diagnostics.Stopwatch]::StartNew()
wsl -d $OpenClawDistro openclaw agent --bad-flag --message "test"
$exit = $LASTEXITCODE
$sw.Stop()
"exit=$exit elapsed_ms=$($sw.ElapsedMilliseconds)"
```

Record:

- argument validation behavior
- failure diagnostics quality

## Phase 2: Session Semantics

### T20. Session Reuse

```powershell
$SessionKey = "$SessionPrefix:reuse"
wsl -d $OpenClawDistro openclaw agent --agent $OpenClawAgent --session-key $SessionKey --message "Reply with exactly this token: BRAVO-719."
wsl -d $OpenClawDistro openclaw agent --agent $OpenClawAgent --session-key $SessionKey --message "What exact token did you reply with previously? Reply with the token only."
```

Record:

- whether memory actually persists

### T21. Session Isolation

```powershell
$SessionKey = "$SessionPrefix:isolation"
wsl -d $OpenClawDistro openclaw agent --agent $OpenClawAgent --session-key $SessionKey --message "What exact token did you reply with previously? Reply with the token only."
```

Record:

- whether prior session state leaks

### T22. Session Listing

```powershell
wsl -d $OpenClawDistro openclaw sessions --json
```

Record:

- whether session ids and keys are visible enough for contract design

## Phase 3: Workspace Write Contract

### T30. Write Markdown File in Workspace

```powershell
$SessionKey = "$SessionPrefix:write-md"
$OutPath = "$OpenClawOutputRoot/t30.md"
wsl -d $OpenClawDistro openclaw agent --agent $OpenClawAgent --session-key $SessionKey --message "Create a Markdown file at $OutPath with exactly this content:`n# T30`nOpenClaw write test.`nAfter writing it, read it back and return the final path."
wsl -d $OpenClawDistro test -f $OutPath
"verify_exit=$LASTEXITCODE"
wsl -d $OpenClawDistro cat $OutPath
```

### T31. Nested Directory Creation

```powershell
$SessionKey = "$SessionPrefix:nested-dir"
$OutPath = "$OpenClawOutputRoot/nested/deeper/t31.md"
wsl -d $OpenClawDistro openclaw agent --agent $OpenClawAgent --session-key $SessionKey --message "Create a Markdown file at $OutPath with the title '# T31'. Create parent directories if needed. After writing it, return the final path."
wsl -d $OpenClawDistro test -f $OutPath
"verify_exit=$LASTEXITCODE"
```

### T32. Overwrite Existing File

```powershell
$SessionKey = "$SessionPrefix:overwrite"
$OutPath = "$OpenClawOutputRoot/t32.md"
wsl -d $OpenClawDistro openclaw agent --agent $OpenClawAgent --session-key $SessionKey --message "Create a text file at $OutPath containing 'first version'. Return the final path."
wsl -d $OpenClawDistro openclaw agent --agent $OpenClawAgent --session-key $SessionKey --message "Overwrite the file at $OutPath so it contains exactly 'second version'. Return the final path."
wsl -d $OpenClawDistro cat $OutPath
```

Record:

- overwrite semantics
- whether explicit overwrite instructions are needed in the contract

## Phase 4: Constraint Following

### T40. Workspace-Only Constraint

```powershell
$SessionKey = "$SessionPrefix:workspace-only"
$OutPath = "$OpenClawOutputRoot/t40.md"
wsl -d $OpenClawDistro openclaw agent --agent $OpenClawAgent --session-key $SessionKey --message "Create a file at $OutPath. Work only inside $OpenClawWorkspace. After writing it, verify it exists and return the final path."
wsl -d $OpenClawDistro cat $OutPath
```

### T41. Explicit No `/mnt` Constraint

```powershell
$SessionKey = "$SessionPrefix:no-mnt"
$OutPath = "$OpenClawOutputRoot/t41.md"
wsl -d $OpenClawDistro openclaw agent --agent $OpenClawAgent --session-key $SessionKey --message "Create a file at $OutPath. Work only inside $OpenClawWorkspace. Do not use /mnt/c or /mnt/d. After writing it, return the final path."
wsl -d $OpenClawDistro cat $OutPath
```

### T42. Ambiguous Output Path

```powershell
$SessionKey = "$SessionPrefix:ambiguous"
wsl -d $OpenClawDistro openclaw agent --agent $OpenClawAgent --session-key $SessionKey --message "Write a short Markdown report somewhere in your workspace about testing output-path determinism, then tell me where you put it."
```

Record:

- whether vague prompts produce nondeterministic paths

## Phase 5: Text Artifact Import and Consumption

### T50. Import Text Artifact From Windows

```powershell
$LocalInput = Join-Path $LocalOutputRoot "t50-input.md"
@"
# T50 Input
This is a text import test.
"@ | Set-Content -Path $LocalInput -Encoding UTF8

wsl -d $OpenClawDistro mkdir -p $OpenClawInputRoot
Get-Content $LocalInput | wsl -d $OpenClawDistro tee "$OpenClawInputRoot/t50-input.md" > $null
wsl -d $OpenClawDistro cat "$OpenClawInputRoot/t50-input.md"
```

### T51. Summarize Imported Text Artifact

```powershell
$SessionKey = "$SessionPrefix:text-summary"
$InPath = "$OpenClawInputRoot/t50-input.md"
$OutPath = "$OpenClawOutputRoot/t51-summary.md"
wsl -d $OpenClawDistro openclaw agent --agent $OpenClawAgent --session-key $SessionKey --message "Read $InPath. Create a short Markdown summary at $OutPath. Work only inside $OpenClawWorkspace. After writing it, read it back and return the final path."
wsl -d $OpenClawDistro cat $OutPath
```

### T52. Structured Text Input

```powershell
$LocalInput = Join-Path $LocalOutputRoot "t52-input.json"
'{"topic":"OpenClaw","goal":"test structured text input"}' | Set-Content -Path $LocalInput -Encoding UTF8
Get-Content $LocalInput | wsl -d $OpenClawDistro tee "$OpenClawInputRoot/t52-input.json" > $null
wsl -d $OpenClawDistro cat "$OpenClawInputRoot/t52-input.json"
```

## Phase 6: Binary Artifact Import and Consumption

### T60. Import Binary Artifact via Base64

Choose a small existing PDF or image on Windows and set the local path first:

```powershell
$LocalBinaryInput = "C:\Users\User\OneDrive\Desktop\sample.pdf"
wsl -d $OpenClawDistro mkdir -p $OpenClawInputRoot
[Convert]::ToBase64String([IO.File]::ReadAllBytes($LocalBinaryInput)) | wsl -d $OpenClawDistro bash -lc "base64 -d > $OpenClawInputRoot/t60-input.bin"
wsl -d $OpenClawDistro ls -l "$OpenClawInputRoot/t60-input.bin"
```

Record:

- whether byte size looks correct

### T61. Ask OpenClaw To Use Binary Artifact

```powershell
$SessionKey = "$SessionPrefix:binary-summary"
$InPath = "$OpenClawInputRoot/t60-input.bin"
$OutPath = "$OpenClawOutputRoot/t61-summary.md"
wsl -d $OpenClawDistro openclaw agent --agent $OpenClawAgent --session-key $SessionKey --message "Use $InPath as the input artifact. If you can inspect it, create a Markdown summary at $OutPath. Work only inside $OpenClawWorkspace. Return the final output path and a concise status."
wsl -d $OpenClawDistro test -f $OutPath
"verify_exit=$LASTEXITCODE"
if ($LASTEXITCODE -eq 0) { wsl -d $OpenClawDistro cat $OutPath }
```

Record:

- whether OpenClaw can meaningfully consume staged binary input

## Phase 7: Output Verification and Export

### T70. Export Text Output to Windows

```powershell
$OutPath = "$OpenClawOutputRoot/t51-summary.md"
$LocalExport = Join-Path $LocalOutputRoot "t70-exported-summary.md"
wsl -d $OpenClawDistro cat $OutPath > $LocalExport
Get-Content $LocalExport
```

### T71. Export Binary Output via Base64

If OpenClaw ever produces a binary artifact, use:

```powershell
$BinaryWorkspacePath = "$OpenClawOutputRoot/output.bin"
$LocalBinaryExport = Join-Path $LocalOutputRoot "t71-output.bin"
$base64 = wsl -d $OpenClawDistro base64 -w 0 $BinaryWorkspacePath
[IO.File]::WriteAllBytes($LocalBinaryExport, [Convert]::FromBase64String($base64))
Get-Item $LocalBinaryExport | Select-Object FullName,Length,LastWriteTime
```

## Phase 8: JSON Reliability

### T80. JSON Mode on Write Task

```powershell
$SessionKey = "$SessionPrefix:json-write"
$OutPath = "$OpenClawOutputRoot/t80.md"
wsl -d $OpenClawDistro openclaw agent --agent $OpenClawAgent --session-key $SessionKey --json --message "Create a Markdown file at $OutPath with the title '# T80'. Work only inside $OpenClawWorkspace. After writing it, return the final path."
```

Record:

- whether artifact path is present in structured fields or only in free text

### T81. JSON Mode on Failure

```powershell
$SessionKey = "$SessionPrefix:json-failure"
wsl -d $OpenClawDistro openclaw agent --agent $OpenClawAgent --session-key $SessionKey --json --message "Read the missing file $OpenClawInputRoot/does-not-exist.md and summarize it."
```

Record:

- failure envelope shape under `--json`

### T82. Repeated JSON Stability

```powershell
$SessionKey = "$SessionPrefix:json-stability"
1..3 | ForEach-Object {
  wsl -d $OpenClawDistro openclaw agent --agent $OpenClawAgent --session-key "$SessionKey-$_" --json --message "Reply with exactly: OK."
}
```

Record:

- whether field names and result structure stay stable

## Phase 9: Failure Modes

### T90. Missing Input Artifact

```powershell
$SessionKey = "$SessionPrefix:missing-input"
$MissingPath = "$OpenClawInputRoot/not-here.md"
$OutPath = "$OpenClawOutputRoot/t90.md"
wsl -d $OpenClawDistro openclaw agent --agent $OpenClawAgent --session-key $SessionKey --message "Read $MissingPath and create a summary at $OutPath."
```

### T91. Longer Task Timing

```powershell
$SessionKey = "$SessionPrefix:longer-task"
$OutPath = "$OpenClawOutputRoot/t91.md"
$sw = [Diagnostics.Stopwatch]::StartNew()
wsl -d $OpenClawDistro openclaw agent --agent $OpenClawAgent --session-key $SessionKey --message "Create a detailed Markdown note at $OutPath explaining why deterministic workspace paths matter for automation. Include at least 8 concise bullet points. After writing it, return the final path."
$exit = $LASTEXITCODE
$sw.Stop()
"exit=$exit elapsed_ms=$($sw.ElapsedMilliseconds)"
```

Record:

- practical latency range for default timeout planning

## Phase 10: Concurrency and Collision Risk

### T100. Parallel Runs With Different Session Keys

Open two PowerShell windows and run one command in each:

Window 1:

```powershell
wsl -d $OpenClawDistro openclaw agent --agent $OpenClawAgent --session-key "$SessionPrefix:parallel-a" --message "Create $OpenClawOutputRoot/t100-a.md with the text 'parallel a'. Return the final path."
```

Window 2:

```powershell
wsl -d $OpenClawDistro openclaw agent --agent $OpenClawAgent --session-key "$SessionPrefix:parallel-b" --message "Create $OpenClawOutputRoot/t100-b.md with the text 'parallel b'. Return the final path."
```

Then verify:

```powershell
wsl -d $OpenClawDistro cat "$OpenClawOutputRoot/t100-a.md"
wsl -d $OpenClawDistro cat "$OpenClawOutputRoot/t100-b.md"
```

### T101. Parallel Runs With Same Session Key

Open two PowerShell windows and run one command in each:

Window 1:

```powershell
wsl -d $OpenClawDistro openclaw agent --agent $OpenClawAgent --session-key "$SessionPrefix:parallel-same" --message "Create $OpenClawOutputRoot/t101-a.md with the text 'same session a'. Return the final path."
```

Window 2:

```powershell
wsl -d $OpenClawDistro openclaw agent --agent $OpenClawAgent --session-key "$SessionPrefix:parallel-same" --message "Create $OpenClawOutputRoot/t101-b.md with the text 'same session b'. Return the final path."
```

Record:

- whether same-key concurrency is unsafe

## Minimum Required Test Set

Run these before drafting the contract:

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

## Contract Questions This Checklist Must Answer

Before moving on, confirm:

- What is the exact reliable invocation pattern?
- Is `--json` strong enough to trust directly?
- How should session keys be generated and reused?
- Must RAGenius always supply an explicit output path?
- Must RAGenius always verify output files independently?
- What is the safe import/export method for text?
- What is the safe import/export method for binary artifacts?
- What default timeout range is realistic?
- Is same-session parallelism forbidden?
- Which error patterns need first-class mapping in the provider?
