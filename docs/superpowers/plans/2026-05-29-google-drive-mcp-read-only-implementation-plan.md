# Google Drive MCP Read-Only Implementation Plan

## Objective

Implement the first Google Drive MCP slice as a read-only provider family that validates the Generic MCP Layer against a file-oriented provider and establishes the discovery layer needed for later attachment workflows.

Scope is intentionally narrow:

- one `gdrive` MCP provider family
- one allowlisted read tool: `mcp.gdrive.search_files`
- Builder `google_drive_read_operation`
- sample `google_drive_search` skill
- read-only execution and failure-path coverage
- Drive MCP runtime docs

Out of scope:

- file download/export
- file mutation or upload
- Gmail attachment workflows
- Drive write flows

## Implementation Tasks

### Task 1: Extend Builder normalization for Google Drive read-only skills

Update [D:\GitHub\Codex-RAGenius-System\ragenius_builder\flask_scaffold\skill_normalization.py](D:/GitHub/Codex-RAGenius-System/ragenius_builder/flask_scaffold/skill_normalization.py:1)

Changes:
- add `google_drive_read_operation` to `SAFE_TEMPLATE_TOOL_MAP`
- infer it from natural-language Drive search/list intent
- map it to:
  - `required_tools = ["mcp.gdrive.search_files"]`
  - `required_permissions = ["external_api.read"]`
  - input schema with `query`
  - output schema with `results[]`
  - workflow using `service_call` to `mcp.gdrive.search_files`
- keep all Drive contracts `review_required`
- keep `auto_finalize = False`

Acceptance criteria:
- natural Drive search/list skills normalize to `google_drive_read_operation`
- normalized contracts remain explicit and reviewable

### Task 2: Add Builder regression coverage

Update [D:\GitHub\Codex-RAGenius-System\ragenius_builder\flask_scaffold\tests\test_skill_management.py](D:/GitHub/Codex-RAGenius-System/ragenius_builder/flask_scaffold/tests/test_skill_management.py:1)

Add tests for:
- Drive search/list normalization becomes `google_drive_read_operation`
- `required_tools == ["mcp.gdrive.search_files"]`
- workflow points at `mcp.gdrive.search_files`
- policy is `review_required`

Acceptance criteria:
- Builder tests cover the new Drive normalization path

### Task 3: Extend MCP provider mapping for Google Drive

Update [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\tools\providers\mcp-tool-provider.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/core/tools/providers/mcp-tool-provider.ts:1)

Changes:
- add default allowlist support for `gdrive`
- register `search_files` as read-only
- provide normalized output schema for Drive search results
- preserve provider-scoped tool id format:
  - `mcp.gdrive.search_files`

Do not:
- add download/export logic
- add write-side Drive tools

Acceptance criteria:
- `discover("gdrive")` returns the allowlisted Drive tool
- tool metadata classifies it as non-side-effecting with `external_api.read`

### Task 4: Add sample Google Drive search skill

Update [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\skills\sample-skills.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/core/skills/sample-skills.ts:1)

Add:
- `google_drive_search`

Contract:
- input: `query`
- output: `results[]`
- required tool: `mcp.gdrive.search_files`
- required permission: `external_api.read`
- workflow: one `service_call`, then `end`

Acceptance criteria:
- sample skill executes through the existing workflow seam with no new workflow primitives

### Task 5: Add MCP provider unit coverage

Update [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\tests\tools\mcp-tool-provider.test.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/tests/tools/mcp-tool-provider.test.ts:1)

Add tests for:
- Drive discovery when `search_files` is allowlisted
- read-only classification
- normalized result handling for search/list results

Acceptance criteria:
- provider unit tests prove Drive discovery/execution through mocked HTTP MCP responses

### Task 6: Add failure-path coverage for missing Drive auth

Update [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\tests\execution\permission-block.test.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/tests/execution/permission-block.test.ts:1)

Add:
- one failure-path test where `gdrive` is configured but `GOOGLE_DRIVE_MCP_ACCESS_TOKEN` is missing

Acceptance criteria:
- runtime fails cleanly with `MCP_PROVIDER_AUTH_FAILED`

### Task 7: Add end-to-end execution coverage

Update [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\tests\execution\execute-skill.test.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/tests/execution/execute-skill.test.ts:1)

Add an integration-style test that:
- configures `gdrive` in `MCP_SERVERS_JSON`
- provides `GOOGLE_DRIVE_MCP_ACCESS_TOKEN`
- mocks:
  - `initialize`
  - `notifications/initialized`
  - `tools/list`
  - `tools/call`
- discovers `mcp.gdrive.search_files`
- executes `google_drive_search`
- asserts completed `json` result with normalized metadata

Acceptance criteria:
- one Drive read-only skill executes end to end through the real MCP HTTP seam

### Task 8: Update runtime docs

Update [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\README.md](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/README.md:1)

Document:
- `GOOGLE_DRIVE_MCP_ACCESS_TOKEN`
- `gdrive` example in `MCP_SERVERS_JSON`
- allowed tool `search_files`
- read-only nature of the slice
- explicit note that this is groundwork for later attachment workflows, not attachment support itself

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
npm test -- mcp-tool-provider.test.ts permission-block.test.ts execute-skill.test.ts
```

Success criteria:
- Builder normalization tests pass
- Prisma schema validates
- execution-subsystem MCP tests pass with the new Drive slice included

## Expected Deliverables

- Builder normalization for `google_drive_read_operation`
- Drive MCP provider mapping for `mcp.gdrive.search_files`
- sample `google_drive_search` skill
- unit and end-to-end tests
- README documentation for the Drive read-only slice

## Follow-On Recommendation

If this slice lands cleanly, the next logical design is:

- **Google Drive export/read design**

That is the earliest point where the system can begin building a real attachment-capable Gmail workflow on top of Drive-discovered files.
