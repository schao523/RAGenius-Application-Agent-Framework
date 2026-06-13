# Google Drive MCP Export/Read Implementation Plan

## Objective

Implement the second Google Drive MCP slice as a controlled export/read capability using the official managed Drive MCP endpoint and tool contract.

This slice is intentionally narrow:

- provider family: `gdrive`
- endpoint: `https://drivemcp.googleapis.com/mcp/v1`
- read/download tool: `mcp.gdrive.download_file_content`
- artifact-oriented output
- no Drive mutation
- no Gmail attachment send yet

Out of scope:

- file upload or mutation
- arbitrary local download targets
- bulk export
- attachment-capable Gmail workflows

## Implementation Tasks

### Task 1: Extend Builder normalization for Google Drive export/read skills

Update [D:\GitHub\Codex-RAGenius-System\ragenius_builder\flask_scaffold\skill_normalization.py](D:/GitHub/Codex-RAGenius-System/ragenius_builder/flask_scaffold/skill_normalization.py:1)

Changes:
- add `google_drive_export_operation` to `SAFE_TEMPLATE_TOOL_MAP`
- infer it from natural-language Drive export/read intent
- map it to:
  - `required_tools = ["mcp.gdrive.download_file_content", "save_artifact"]`
  - `required_permissions = ["external_api.read", "artifact.write"]`
  - input schema using `fileId`
  - optional format/export hint only if the chosen runtime contract actually exposes one
  - output schema centered on artifact metadata
  - workflow using `service_call` to `mcp.gdrive.download_file_content`, then `save_artifact`
- keep all Drive export/read contracts `review_required`
- keep `auto_finalize = False`

Acceptance criteria:
- natural Drive export/read skills normalize to `google_drive_export_operation`
- normalized contracts remain explicit and reviewable

### Task 2: Add Builder regression coverage

Update [D:\GitHub\Codex-RAGenius-System\ragenius_builder\flask_scaffold\tests\test_skill_management.py](D:/GitHub/Codex-RAGenius-System/ragenius_builder/flask_scaffold/tests/test_skill_management.py:1)

Add tests for:
- Drive export/read normalization becomes `google_drive_export_operation`
- `required_tools` contains:
  - `mcp.gdrive.download_file_content`
  - `save_artifact`
- workflow points at `mcp.gdrive.download_file_content`
- policy is `review_required`

Acceptance criteria:
- Builder tests cover the new Drive export/read normalization path

### Task 3: Extend MCP provider mapping for Drive download/read

Update [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\tools\providers\mcp-tool-provider.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/core/tools/providers/mcp-tool-provider.ts:1)

Changes:
- extend default allowlist support for `gdrive`
- register `download_file_content` as read-only
- provide normalized output schema for the downloaded/exported content result
- preserve provider-scoped tool id format:
  - `mcp.gdrive.download_file_content`

Do not:
- add arbitrary filesystem writes
- add Drive write tools

Acceptance criteria:
- `discover("gdrive")` can return the allowlisted download/read tool
- tool metadata classifies it as non-side-effecting with `external_api.read`

### Task 4: Define artifact-oriented result handling

Update the Drive export/read runtime path so the remote MCP result can be handed into artifact persistence cleanly.

Likely touch points:
- [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\tools\providers\mcp-tool-provider.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/core/tools/providers/mcp-tool-provider.ts:1)
- existing artifact-saving workflow path through [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\tools\providers\local-tool-provider.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/core/tools/providers/local-tool-provider.ts:1) via `save_artifact`

Goal:
- normalize remote Drive output into a shape that the workflow can persist without inventing arbitrary local file targets

Acceptance criteria:
- Drive export/read results can be saved as app-scoped artifacts
- no cross-app leakage or arbitrary path writes are introduced

### Task 5: Add sample Google Drive export/read skill

Update [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\skills\sample-skills.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/core/skills/sample-skills.ts:1)

Add:
- `google_drive_download_file`

Contract:
- input: `fileId`
- optional format/export hint only if justified by the chosen runtime contract
- required tools:
  - `mcp.gdrive.download_file_content`
  - `save_artifact`
- required permissions:
  - `external_api.read`
  - `artifact.write`
- workflow:
  1. `service_call` to `mcp.gdrive.download_file_content`
  2. `save_artifact`
  3. `end`

Acceptance criteria:
- sample skill executes through the existing workflow seam with no new workflow primitives

### Task 6: Add MCP provider unit coverage

Update [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\tests\tools\mcp-tool-provider.test.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/tests/tools/mcp-tool-provider.test.ts:1)

Add tests for:
- Drive download/read discovery when allowlisted
- read-only classification
- normalized remote result handling for the download/read tool

Acceptance criteria:
- provider unit tests prove Drive download/read discovery/execution through mocked HTTP MCP responses

### Task 7: Add failure-path coverage for missing Drive auth

If needed, extend [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\tests\execution\permission-block.test.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/tests/execution/permission-block.test.ts:1)

Add or adapt:
- one failure-path test where `gdrive` is configured for `download_file_content` but `GOOGLE_DRIVE_MCP_ACCESS_TOKEN` is missing

Acceptance criteria:
- runtime fails cleanly with `MCP_PROVIDER_AUTH_FAILED`

### Task 8: Add end-to-end execution coverage

Update [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\tests\execution\execute-skill.test.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/tests/execution/execute-skill.test.ts:1)

Add an integration-style test that:
- configures `gdrive` in `MCP_SERVERS_JSON` using:
  - `https://drivemcp.googleapis.com/mcp/v1`
  - allowlisted tools including `download_file_content`
- provides `GOOGLE_DRIVE_MCP_ACCESS_TOKEN`
- mocks:
  - `initialize`
  - `notifications/initialized`
  - `tools/list`
  - `tools/call`
- discovers `mcp.gdrive.download_file_content`
- executes `google_drive_download_file`
- asserts completed result includes artifact metadata rather than arbitrary local file output

Acceptance criteria:
- one Drive export/read skill executes end to end through the real MCP HTTP seam and artifact path

### Task 9: Update runtime docs

Update [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\README.md](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/README.md:1)

Document:
- official Drive MCP endpoint:
  - `https://drivemcp.googleapis.com/mcp/v1`
- `GOOGLE_DRIVE_MCP_ACCESS_TOKEN`
- allowlisted tools:
  - `search_files`
  - `download_file_content`
- artifact-oriented nature of the export/read slice
- explicit note that this is a prerequisite for later attachment workflows, not attachment support itself

Acceptance criteria:
- README explains runtime config and intended scope clearly

## Verification Plan

Run:

```powershell
python -m unittest ragenius_builder.flask_scaffold.tests.test_skill_management
```

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npx prisma validate
```

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- mcp-tool-provider.test.ts permission-block.test.ts execute-skill.test.ts local-tool-provider.test.ts
```

Success criteria:
- Builder normalization tests pass
- Prisma schema validates
- execution-subsystem MCP tests pass with the new Drive export/read slice included
- artifact persistence path remains clean

## Expected Deliverables

- Builder normalization for `google_drive_export_operation`
- Drive MCP provider mapping for `mcp.gdrive.download_file_content`
- sample `google_drive_download_file` skill
- unit and end-to-end tests
- README documentation for the Drive export/read slice

## Follow-On Recommendation

If this slice lands cleanly, the next logical design is:

- **Gmail attachment-capable draft design**

That is the point where the system can start combining:

- Drive file discovery
- Drive controlled file materialization
- Gmail draft/send workflows

into a real attachment-capable contract pipeline.
