# Typed Policy Modules And Gmail Attachments Implementation Plan

## Objective

Introduce the first typed policy modules in:

- `ragenius_builder`
- `ragenius_execution_subsystem`

and use them to support the first attachment-capable Gmail workflow in a policy-driven way.

This plan assumes the first supported attachment-capable Gmail path is:

- **create Gmail draft with artifact-based attachments**

and not:

- arbitrary local file attachments
- direct outbound send with attachments in the first slice

That keeps the implementation aligned with the policy-contract model and the current artifact-first architecture.

## Scope

This implementation slice will add:

- a typed Builder policy module for template-family finalization and review rules
- a typed execution policy module for provider/tool/artifact/attachment enforcement
- policy-driven normalization for selected existing families
- attachment-capable Gmail draft support using app-scoped artifact ids as the attachment source
- targeted tests proving policy-driven behavior

This slice will not add:

- a full DB-backed policy admin UI
- fully dynamic runtime policy editing
- arbitrary file-path attachments
- per-user Gmail OAuth
- direct send-with-attachments in the first slice

## Assumptions

The first attachment-capable Gmail contract will:

- accept one or more `artifactIds`
- resolve those artifacts from app-scoped artifact storage
- use Gmail MCP draft creation, not direct send, as the first attachment workflow
- remain `review_required`
- remain confirmation-gated because it is a write-capable external action

## Workstreams

### Workstream 1: Builder typed policy module

#### Task 1.1: Add Builder policy types and seeded defaults

Create a Builder-side policy module, for example:

- [D:\GitHub\Codex-RAGenius-System\ragenius_builder\flask_scaffold\policy.py](D:/GitHub/Codex-RAGenius-System/ragenius_builder/flask_scaffold/policy.py:1)

Define typed/default policy data for:

- template families
- review requirements
- auto-finalization rules
- inferred tools
- baseline required permissions

Initial families to include:

- `file_inspection_report`
- `content_replace`
- `content_patch`
- `gmail_read_operation`
- `gmail_draft_operation`
- `gmail_send_draft_operation`
- `gmail_send_message_operation`
- `google_docs_read_operation`
- `google_drive_read_operation`
- `google_drive_export_operation`
- new:
  - `gmail_attachment_draft_operation`

Acceptance criteria:

- Builder has one explicit policy source instead of embedding all family decisions directly in normalization logic

#### Task 1.2: Refactor normalization to consult Builder policy

Update:

- [D:\GitHub\Codex-RAGenius-System\ragenius_builder\flask_scaffold\skill_normalization.py](D:/GitHub/Codex-RAGenius-System/ragenius_builder/flask_scaffold/skill_normalization.py:1)

Changes:

- keep intent classification logic, but stop hard-coding as many family-level policy outcomes
- read:
  - policy class
  - auto-finalize
  - inferred tools
  - required permissions
from Builder policy defaults

Add new attachment-capable classification:

- `gmail_attachment_draft_operation`

Inferred from intent examples like:

- draft an email with attachments
- attach exported documents to a Gmail draft
- prepare a Gmail draft with files

Attachment-family normalization should generate:

- required tools:
  - `mcp.gmail.create_draft`
  - attachment-aware tool id if exposed separately, or the Gmail draft tool if attachments are part of its input contract
  - possibly `load_artifact` if the workflow resolves artifacts explicitly
- required permissions:
  - `external_api.write`
  - `artifact.read`

Acceptance criteria:

- Builder normalization decisions for the migrated families come from policy defaults
- attachment-capable Gmail draft skills normalize as `review_required`

#### Task 1.3: Expand Builder test coverage

Update:

- [D:\GitHub\Codex-RAGenius-System\ragenius_builder\flask_scaffold\tests\test_skill_management.py](D:/GitHub/Codex-RAGenius-System/ragenius_builder/flask_scaffold/tests/test_skill_management.py:1)

Add tests for:

- policy-backed normalization still works for existing Gmail/Drive families
- attachment-capable Gmail draft normalization produces:
  - `gmail_attachment_draft_operation`
  - `review_required`
  - attachment-aware required tools
  - `artifact.read`
  - `external_api.write`
- auto-finalization decisions reflect policy defaults rather than ad hoc conditionals

Acceptance criteria:

- Builder tests prove the first typed policy module is actually consulted

### Workstream 2: Execution-subsystem typed policy module

#### Task 2.1: Add execution policy types and seeded defaults

Create a runtime policy module, for example:

- [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\config\policy-config.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/config/policy-config.ts:1)

Define typed/default policy sections for:

- providers
- tools
- artifacts
- side effects
- attachments

Initial content should include:

- provider policy for:
  - `gmail`
  - `gdrive`
  - `gdocs`
- tool policy for:
  - `mcp.gmail.create_draft`
  - `mcp.gmail.send_draft`
  - `mcp.gmail.send_message`
  - `mcp.gdrive.search_files`
  - `mcp.gdrive.download_file_content`
  - `save_artifact`
  - `load_artifact`
- artifact policy:
  - app scope enforced
  - outbound-eligible artifact types
- attachment policy:
  - `artifact_only`
  - max attachment count
  - max bytes
  - allowed MIME types

Acceptance criteria:

- runtime has a typed policy object that can govern provider/tool/artifact behavior

#### Task 2.2: Project policy into runtime config

Update runtime config composition, likely across:

- [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\config\runtime-config.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/config/runtime-config.ts:1)
- [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\app.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/app.ts:1)

Goal:

- make policy available to:
  - `ToolEngine`
  - MCP provider
  - local artifact/load tool paths
  - workflow execution

Acceptance criteria:

- policy is a first-class runtime input, not just documentation

#### Task 2.3: Refactor runtime checks to consult policy

Apply policy to:

- provider allowlists
- tool confirmation requirements
- attachment source restrictions
- outbound capability rules

Likely touch points:

- [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\tools\providers\mcp-tool-provider.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/core/tools/providers/mcp-tool-provider.ts:1)
- [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\tools\tool-engine.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/core/tools/tool-engine.ts:1)
- permission/confirmation seam where appropriate

Acceptance criteria:

- at least one migrated provider family uses typed policy for meaningful runtime decisions

### Workstream 3: Gmail attachment-capable draft support

#### Task 3.1: Define the first runtime attachment contract

Use this contract:

- input:
  - `to`
  - `subject`
  - `body`
  - `artifactIds: string[]`
- attachment source mode:
  - `artifact_only`
- artifact eligibility:
  - must be app-scoped
  - must be outbound-eligible by artifact policy

Important rule:

- do not allow raw local file paths
- do not allow arbitrary Drive file ids directly

Acceptance criteria:

- one explicit attachment-capable contract exists that matches policy

#### Task 3.2: Add attachment-capable Gmail sample skill

Update:

- [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\skills\sample-skills.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/core/skills/sample-skills.ts:1)

Add sample skill:

- `gmail_create_draft_with_attachments`

Workflow shape:

1. `load_artifact` or repeated artifact resolution path
2. `service_call` to Gmail draft tool with attachment payload
3. `end`

If workflow semantics make repeated attachment resolution awkward, introduce a bounded internal packaging step in the runtime seam rather than widening the public contract.

Acceptance criteria:

- one sample attachment-capable Gmail draft skill exists and stays artifact-based

#### Task 3.3: Extend Gmail MCP provider contract handling

Update:

- [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\tools\providers\mcp-tool-provider.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/core/tools/providers/mcp-tool-provider.ts:1)

Changes:

- support the chosen Gmail draft input shape with attachments
- map attachment payload according to the MCP server contract
- keep this write path:
  - `external_api.write`
  - side-effecting
  - confirmation-gated

Important:

- the provider should not be responsible for arbitrary file reads
- it should receive already-approved artifact-derived attachment content

Acceptance criteria:

- Gmail draft creation can accept artifact-derived attachments through the provider seam

#### Task 3.4: Enforce attachment policy at runtime

Apply runtime checks for:

- artifact id source only
- app scope
- allowed artifact types
- allowed MIME types
- max attachment count
- max total bytes

Likely touch points:

- artifact load path
- workflow assembly path
- Gmail service-call preparation path

Acceptance criteria:

- attachment-capable Gmail draft execution fails closed when policy is violated

### Workstream 4: Tests and documentation

#### Task 4.1: Add runtime unit and integration tests

Update or add tests in:

- [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\tests\tools\mcp-tool-provider.test.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/tests/tools/mcp-tool-provider.test.ts:1)
- [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\tests\execution\permission-block.test.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/tests/execution/permission-block.test.ts:1)
- [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\tests\execution\execute-skill.test.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/tests/execution/execute-skill.test.ts:1)
- possibly local artifact tests if attachment loading needs new behavior

Add coverage for:

- policy-driven provider/tool decisions
- attachment-capable draft pending-confirmation
- confirm/resume success
- cross-app artifact denial
- disallowed MIME type denial
- too many attachments denial
- too-large attachment denial

Acceptance criteria:

- attachment-capable Gmail draft support is covered end to end

#### Task 4.2: Update documentation

Update:

- Builder and execution README/docs where relevant
- policy config docs
- Gmail attachment-capable behavior docs

Document:

- attachment source model
- policy-driven enforcement model
- first supported Gmail attachment path
- what remains out of scope

Acceptance criteria:

- the feature can be understood as a policy-governed artifact workflow, not an ad hoc provider trick

## Recommended Execution Order

1. Builder policy module and default policies
2. runtime policy module and default policies
3. migrate existing Gmail/Drive families to consult policy
4. add attachment-capable Gmail draft contract
5. add attachment policy enforcement
6. add tests
7. update docs

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

- Builder normalization remains green with policy-backed decisions
- runtime tests prove policy-backed provider/tool behavior
- Gmail attachment-capable draft flow works end to end with app-scoped artifacts
- cross-app leakage and raw-path attachment models remain blocked

## Expected Deliverables

- first typed Builder policy module
- first typed runtime policy module
- migrated policy-backed normalization/runtime checks
- first artifact-based Gmail attachment-capable draft support
- tests and docs

## Follow-On Recommendation

If this slice lands cleanly, the next logical follow-on is:

- `send_draft` with attachments already present on the draft

That keeps outbound-send behavior separate from the first attachment materialization slice while reusing the same policy model.
