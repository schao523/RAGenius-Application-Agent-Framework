# NotebookLM Adapter And User-Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first-class NotebookLM adapter to RAGenius that supports existing-notebook access, NotebookLM Q&A, app-artifact source import, and phase-3 generation for slide decks, reports, and video through explicit Builder and runtime contracts.

**Architecture:** RAGenius will integrate NotebookLM through a local Python adapter seam rather than direct Node reimplementation. `ragenius_execution_subsystem` will own capability-shaped runtime tools and policy, while Builder will resolve author-facing `notebooklm.*` aliases into deterministic workflow families. The first implementation slice will use a Python bridge command seam that can later be lifted into a long-running local adapter service without changing the higher-level contracts.

**Tech Stack:** TypeScript/Node (`ragenius_execution_subsystem`), Python bridge wrapper around `notebooklm-py`, Flask Builder normalization/policy, Zod schemas, existing execution diagnostics and artifact store.

---

## File Structure

Planned runtime files:

- Create: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\tools\providers\notebooklm-adapter.ts`
- Create: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\tools\providers\notebooklm-bridge.ts`
- Create: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\tools\providers\notebooklm-types.ts`
- Create: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\scripts\notebooklm_bridge.py`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\tools\providers\adapter-tool-provider.ts`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\config\provider-config.ts`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\config\runtime-config.ts`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\config\policy-config.ts`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\skills\sample-skills.ts`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\README.md`

Planned Builder files:

- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_builder\flask_scaffold\skill_normalization.py`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_builder\flask_scaffold\policy.py`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_builder\flask_scaffold\app.py`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_builder\flask_scaffold\templates\skill_detail.html`

Planned tests:

- Create: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\tests\tools\notebooklm-adapter.test.ts`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\tests\tools\adapter-tool-provider.test.ts`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\tests\execution\execute-skill.test.ts`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\tests\config\runtime-config.test.ts`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_builder\flask_scaffold\tests\test_skill_management.py`

## Task 1: Add Typed NotebookLM Runtime Configuration

**Files:**
- Create: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\tools\providers\notebooklm-types.ts`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\config\provider-config.ts`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\config\runtime-config.ts`
- Test: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\tests\config\runtime-config.test.ts`

- [ ] **Step 1: Write the failing runtime-config test for NotebookLM provider config**

Add a test case to `runtime-config.test.ts` that expects:

```ts
assert.deepEqual(config.providers.notebooklm, {
  enabled: true,
  pythonCommand: "python",
  bridgeScript: "scripts/notebooklm_bridge.py",
  authMode: "env_json",
  profile: "default",
  allowedOperations: ["list_notebooks", "list_sources", "ask"],
  generationDefaults: {
    waitForCompletion: true,
    persistArtifacts: true
  }
});
```

- [ ] **Step 2: Run the runtime-config test to verify it fails**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- runtime-config.test.ts
```

Expected:

- FAIL because `providers.notebooklm` does not exist yet

- [ ] **Step 3: Define the NotebookLM provider config interfaces and env parsing**

Add a `NotebookLmProviderConfig` shape in `provider-config.ts` and include it in `ProviderRuntimeConfig`:

```ts
export interface NotebookLmProviderConfig {
  enabled: boolean;
  pythonCommand: string;
  bridgeScript: string;
  authMode: "env_json" | "profile" | "storage_path";
  profile?: string;
  storagePath?: string;
  allowedOperations: string[];
  generationDefaults: {
    waitForCompletion: boolean;
    persistArtifacts: boolean;
  };
}
```

Then include it in `buildProviderRuntimeConfig(env)` and surface it through `inspectRuntimeConfig(...)`.

- [ ] **Step 4: Run the runtime-config test to verify it passes**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- runtime-config.test.ts
```

Expected:

- PASS with NotebookLM config present in runtime diagnostics

- [ ] **Step 5: Commit**

```bash
git add ragenius_execution_subsystem/src/config/provider-config.ts ragenius_execution_subsystem/src/config/runtime-config.ts ragenius_execution_subsystem/tests/config/runtime-config.test.ts
git commit -m "feat: add typed notebooklm runtime config"
```

## Task 2: Add The NotebookLM Bridge Script Contract

**Files:**
- Create: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\scripts\notebooklm_bridge.py`
- Create: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\tools\providers\notebooklm-types.ts`
- Test: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\tests\tools\notebooklm-adapter.test.ts`

- [ ] **Step 1: Write the failing adapter test for bridge request/response normalization**

Add a test that expects a NotebookLM bridge response like:

```ts
const bridgeResponse = {
  ok: true,
  result: {
    notebooks: [
      { id: "nb_1", title: "Research", sources_count: 3 }
    ]
  }
};
```

to normalize into:

```ts
{
  notebooks: [
    { id: "nb_1", title: "Research", sources_count: 3 }
  ]
}
```

- [ ] **Step 2: Run the NotebookLM adapter test to verify it fails**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- notebooklm-adapter.test.ts
```

Expected:

- FAIL because the adapter and bridge do not exist yet

- [ ] **Step 3: Create the Python bridge script skeleton**

Create `scripts/notebooklm_bridge.py` with:

```python
import json
import sys

def main() -> int:
    payload = json.loads(sys.stdin.read() or "{}")
    operation = payload.get("operation")
    arguments = payload.get("arguments", {})
    response = {
        "ok": False,
        "error": {
            "code": "NOTEBOOKLM_BRIDGE_NOT_IMPLEMENTED",
            "message": f"Operation not implemented: {operation}",
            "details": {"arguments": arguments},
        },
    }
    sys.stdout.write(json.dumps(response))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

Also define shared TS types in `notebooklm-types.ts` for:

- `NotebookLmBridgeRequest`
- `NotebookLmBridgeResponse`
- `NotebookLmOperation`

- [ ] **Step 4: Run the adapter test to verify the bridge contract exists**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- notebooklm-adapter.test.ts
```

Expected:

- still FAIL on behavior, but fail against real bridge/adapter contract instead of missing files

- [ ] **Step 5: Commit**

```bash
git add ragenius_execution_subsystem/scripts/notebooklm_bridge.py ragenius_execution_subsystem/src/core/tools/providers/notebooklm-types.ts ragenius_execution_subsystem/tests/tools/notebooklm-adapter.test.ts
git commit -m "feat: scaffold notebooklm bridge contract"
```

## Task 3: Implement The First Real Adapter Execution Path

**Files:**
- Create: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\tools\providers\notebooklm-bridge.ts`
- Create: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\tools\providers\notebooklm-adapter.ts`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\tests\tools\notebooklm-adapter.test.ts`

- [ ] **Step 1: Write the failing test for `list_notebooks` execution through the bridge**

Add a test that stubs bridge execution and expects:

```ts
await adapter.execute(
  "list_notebooks",
  {},
  { appId: "app_001" }
)
```

to return:

```ts
{
  notebooks: [
    { id: "nb_1", title: "Research", sources_count: 3 }
  ]
}
```

- [ ] **Step 2: Run the NotebookLM adapter test to verify it fails**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- notebooklm-adapter.test.ts
```

Expected:

- FAIL because no NotebookLM adapter execution logic exists yet

- [ ] **Step 3: Implement the Node-side bridge runner and adapter wrapper**

Create a bridge runner in `notebooklm-bridge.ts` that:

- spawns the configured Python command
- writes request JSON to stdin
- reads response JSON from stdout
- maps transport failures into `AppError`

Create `notebooklm-adapter.ts` that:

- validates allowed operations
- calls the bridge runner
- normalizes successful results into runtime payloads
- normalizes bridge error payloads into RAGenius `AppError`s

- [ ] **Step 4: Run the NotebookLM adapter test to verify it passes**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- notebooklm-adapter.test.ts
```

Expected:

- PASS for `list_notebooks` bridge execution and error normalization

- [ ] **Step 5: Commit**

```bash
git add ragenius_execution_subsystem/src/core/tools/providers/notebooklm-bridge.ts ragenius_execution_subsystem/src/core/tools/providers/notebooklm-adapter.ts ragenius_execution_subsystem/tests/tools/notebooklm-adapter.test.ts
git commit -m "feat: add notebooklm bridge execution adapter"
```

## Task 4: Extend The Generic Adapter Provider For NotebookLM Tools

**Files:**
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\tools\providers\adapter-tool-provider.ts`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\tests\tools\adapter-tool-provider.test.ts`

- [ ] **Step 1: Write the failing adapter-provider test for `adapter.notebooklm.list_notebooks`**

Add a test that expects:

```ts
const result = await provider.execute(
  toolDefinition,
  {},
  { appId: "app_001" }
);
```

to dispatch through the NotebookLM adapter when the configured tool id is:

```ts
"adapter.notebooklm.list_notebooks"
```

- [ ] **Step 2: Run the adapter-provider test to verify it fails**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- adapter-tool-provider.test.ts
```

Expected:

- FAIL because `AdapterToolProvider` only handles hardcoded demo adapters today

- [ ] **Step 3: Refactor `AdapterToolProvider` to route NotebookLM tools cleanly**

Update `adapter-tool-provider.ts` to:

- preserve existing demo adapters
- detect the `adapter.notebooklm.*` tool family
- instantiate or receive a NotebookLM adapter executor
- reject disallowed tools with `ADAPTER_NOT_ALLOWED`
- reject unsupported NotebookLM operations with `ADAPTER_NOT_IMPLEMENTED`

Use a focused dispatcher pattern instead of adding more `if (tool.id === ...)` branches.

- [ ] **Step 4: Run the adapter-provider test to verify it passes**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- adapter-tool-provider.test.ts
```

Expected:

- PASS for NotebookLM adapter routing

- [ ] **Step 5: Commit**

```bash
git add ragenius_execution_subsystem/src/core/tools/providers/adapter-tool-provider.ts ragenius_execution_subsystem/tests/tools/adapter-tool-provider.test.ts
git commit -m "feat: route notebooklm tools through adapter provider"
```

## Task 5: Implement Phase-1 NotebookLM Operations

**Files:**
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\scripts\notebooklm_bridge.py`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\tools\providers\notebooklm-adapter.ts`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\tests\tools\notebooklm-adapter.test.ts`

- [ ] **Step 1: Write failing tests for `list_sources` and `ask`**

Add tests that expect:

```ts
await adapter.execute("list_sources", { notebookId: "nb_1" }, { appId: "app_001" })
```

to return:

```ts
{
  sources: [
    { id: "src_1", title: "Paper A", kind: "pdf", status: "ready" }
  ]
}
```

And:

```ts
await adapter.execute(
  "ask",
  { notebookId: "nb_1", question: "What are the themes?" },
  { appId: "app_001" }
)
```

to return:

```ts
{
  answer: "The main themes are ...",
  conversation_id: "conv_1",
  references: [{ source_id: "src_1", title: "Paper A" }]
}
```

- [ ] **Step 2: Run the adapter test to verify it fails**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- notebooklm-adapter.test.ts
```

Expected:

- FAIL because bridge operations are still unimplemented

- [ ] **Step 3: Implement `list_notebooks`, `list_sources`, and `ask` in the Python bridge**

Extend `notebooklm_bridge.py` to:

- create `NotebookLMClient.from_storage()`
- dispatch:
  - `list_notebooks`
  - `list_sources`
  - `ask`
- return normalized JSON only

Example dispatch shape:

```python
if operation == "list_notebooks":
    notebooks = await client.notebooks.list()
    return {"ok": True, "result": {"notebooks": [...]}}
```

- [ ] **Step 4: Run the adapter test to verify phase-1 operations pass**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- notebooklm-adapter.test.ts
```

Expected:

- PASS for phase-1 read-like NotebookLM operations

- [ ] **Step 5: Commit**

```bash
git add ragenius_execution_subsystem/scripts/notebooklm_bridge.py ragenius_execution_subsystem/src/core/tools/providers/notebooklm-adapter.ts ragenius_execution_subsystem/tests/tools/notebooklm-adapter.test.ts
git commit -m "feat: implement phase-one notebooklm operations"
```

## Task 6: Register NotebookLM Tool Definitions And Sample Skills

**Files:**
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\skills\sample-skills.ts`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\tests\execution\execute-skill.test.ts`

- [ ] **Step 1: Write the failing execution test for a sample NotebookLM ask skill**

Add a test skill like:

```ts
id: "notebooklm_existing_notebook_ask"
requiredTools: ["adapter.notebooklm.ask"]
requiredPermissions: ["external_api.read"]
```

with workflow:

```json
[
  {
    "id": "ask_notebooklm",
    "type": "tool_call",
    "toolId": "adapter.notebooklm.ask",
    "inputMapping": {
      "notebookId": "$.input.notebookId",
      "question": "$.input.question"
    },
    "outputMapping": {
      "answer": "$.output.answer",
      "references": "$.output.references"
    },
    "on": {
      "success": "end"
    }
  }
]
```

- [ ] **Step 2: Run the execution test to verify it fails**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- execute-skill.test.ts
```

Expected:

- FAIL because the tool definitions/sample skill are not registered yet

- [ ] **Step 3: Add sample NotebookLM skills and tool definitions**

Register sample skills for:

- `notebooklm_existing_notebook_ask`
- `notebooklm_list_notebook_sources`

Ensure tool definitions declare:

- provider type `adapter`
- permission scopes
- side-effecting flags
- Zod input/output schemas

- [ ] **Step 4: Run the execution test to verify it passes**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- execute-skill.test.ts
```

Expected:

- PASS for NotebookLM sample execution path

- [ ] **Step 5: Commit**

```bash
git add ragenius_execution_subsystem/src/core/skills/sample-skills.ts ragenius_execution_subsystem/tests/execution/execute-skill.test.ts
git commit -m "feat: add notebooklm sample skills"
```

## Task 7: Add Builder Alias Resolution And Template Families

**Files:**
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_builder\flask_scaffold\skill_normalization.py`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_builder\flask_scaffold\policy.py`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_builder\flask_scaffold\tests\test_skill_management.py`

- [ ] **Step 1: Write the failing Builder test for explicit `notebooklm.ask` normalization**

Add a test manifest that contains:

```yaml
required_tools:
  - notebooklm.ask
required_permissions:
  - external_api.read
```

and assert it normalizes to:

```python
normalized["required_tools"] == ["adapter.notebooklm.ask"]
normalized["template_family"] == "notebooklm_read_existing_notebook_operation"
```

- [ ] **Step 2: Run the Builder skill-management tests to verify failure**

Run:

```powershell
python -m unittest ragenius_builder.flask_scaffold.tests.test_skill_management
```

Expected:

- FAIL because NotebookLM aliases and template families do not exist yet

- [ ] **Step 3: Add NotebookLM alias and template-family support**

Extend `AUTHOR_TOOL_ALIAS_MAP`, `SAFE_TEMPLATE_TOOL_MAP`, and `DEFAULT_TEMPLATE_FAMILY_POLICY` with:

- `notebooklm.list_notebooks`
- `notebooklm.get_notebook`
- `notebooklm.list_sources`
- `notebooklm.ask`
- `notebooklm.add_source_text`
- `notebooklm.add_source_file`
- `notebooklm.add_source_url`
- `notebooklm.generate_slide_deck`
- `notebooklm.generate_report`
- `notebooklm.generate_video`

Create first template families:

- `notebooklm_read_existing_notebook_operation`
- `notebooklm_import_source_operation`
- `notebooklm_generation_operation`

- [ ] **Step 4: Run the Builder test suite to verify it passes**

Run:

```powershell
python -m unittest ragenius_builder.flask_scaffold.tests.test_skill_management
```

Expected:

- PASS with deterministic NotebookLM normalization coverage

- [ ] **Step 5: Commit**

```bash
git add ragenius_builder/flask_scaffold/skill_normalization.py ragenius_builder/flask_scaffold/policy.py ragenius_builder/flask_scaffold/tests/test_skill_management.py
git commit -m "feat: add notebooklm builder alias normalization"
```

## Task 8: Implement Phase-2 Source Import Through Artifact Boundary

**Files:**
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\scripts\notebooklm_bridge.py`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\tools\providers\notebooklm-adapter.ts`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\tests\tools\notebooklm-adapter.test.ts`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\tests\execution\execute-skill.test.ts`

- [ ] **Step 1: Write failing tests for `add_source_text` and `add_source_file`**

Add adapter tests that expect:

```ts
await adapter.execute(
  "add_source_text",
  { notebookId: "nb_1", title: "Notes", content: "Key points" },
  { appId: "app_001" }
)
```

and:

```ts
await adapter.execute(
  "add_source_file",
  { notebookId: "nb_1", artifactId: "artifact_123", title: "Deck Notes" },
  { appId: "app_001" }
)
```

to return normalized source summaries.

- [ ] **Step 2: Run the adapter and execution tests to verify failure**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- notebooklm-adapter.test.ts execute-skill.test.ts
```

Expected:

- FAIL because source import paths are not implemented

- [ ] **Step 3: Implement source import with artifact materialization**

Update the adapter path so:

- `add_source_text` calls the bridge directly
- `add_source_file` loads the app-scoped artifact
- materializes bridge-owned temporary upload content
- calls `client.sources.add_file(...)`
- cleans up temporary files after upload

Do not allow arbitrary local path input.

- [ ] **Step 4: Run tests to verify phase-2 import passes**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- notebooklm-adapter.test.ts execute-skill.test.ts
```

Expected:

- PASS for source import and artifact-boundary handling

- [ ] **Step 5: Commit**

```bash
git add ragenius_execution_subsystem/scripts/notebooklm_bridge.py ragenius_execution_subsystem/src/core/tools/providers/notebooklm-adapter.ts ragenius_execution_subsystem/tests/tools/notebooklm-adapter.test.ts ragenius_execution_subsystem/tests/execution/execute-skill.test.ts
git commit -m "feat: add notebooklm source import support"
```

## Task 9: Implement Phase-3 Generation And Artifact Persistence

**Files:**
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\scripts\notebooklm_bridge.py`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\tools\providers\notebooklm-adapter.ts`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\tests\tools\notebooklm-adapter.test.ts`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\tests\execution\execute-skill.test.ts`

- [ ] **Step 1: Write failing tests for slide deck, report, and video generation**

Add tests that expect:

```ts
await adapter.execute(
  "generate_slide_deck",
  { notebookId: "nb_1", instructions: "Make a concise deck" },
  { appId: "app_001" }
)
```

to return:

```ts
{
  task_id: "task_1",
  status: "completed",
  artifact_id: "artifact_456"
}
```

Repeat equivalent assertions for:

- `generate_report`
- `generate_video`

- [ ] **Step 2: Run the adapter and execution tests to verify failure**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- notebooklm-adapter.test.ts execute-skill.test.ts
```

Expected:

- FAIL because generation wait/download paths do not exist

- [ ] **Step 3: Implement generation wait, download, and artifact save**

Update the bridge and adapter so generation paths:

- call the corresponding `notebooklm-py` generation method
- wait for completion when policy/defaults require it
- download the resulting output
- save it using the existing artifact store
- return normalized generation metadata plus `artifact_id`

Initial generation coverage:

- `generate_slide_deck`
- `generate_report`
- `generate_video`

- [ ] **Step 4: Run tests to verify generation passes**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- notebooklm-adapter.test.ts execute-skill.test.ts
```

Expected:

- PASS with generated outputs persisted as app-scoped artifacts

- [ ] **Step 5: Commit**

```bash
git add ragenius_execution_subsystem/scripts/notebooklm_bridge.py ragenius_execution_subsystem/src/core/tools/providers/notebooklm-adapter.ts ragenius_execution_subsystem/tests/tools/notebooklm-adapter.test.ts ragenius_execution_subsystem/tests/execution/execute-skill.test.ts
git commit -m "feat: add notebooklm generation workflows"
```

## Task 10: Add Typed Policy, Review Visibility, And Diagnostics

**Files:**
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\config\policy-config.ts`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_builder\flask_scaffold\policy.py`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_builder\flask_scaffold\app.py`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_builder\flask_scaffold\templates\skill_detail.html`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_builder\flask_scaffold\tests\test_skill_management.py`

- [ ] **Step 1: Write the failing Builder review test for NotebookLM fallback/policy visibility**

Add a Builder test that expects a NotebookLM generation skill detail page to show:

- resolved NotebookLM tool ids
- required permissions
- policy class
- `review_required`

And, if generation defaults are exposed, show those policy expectations too.

- [ ] **Step 2: Run the Builder test suite to verify failure**

Run:

```powershell
python -m unittest ragenius_builder.flask_scaffold.tests.test_skill_management
```

Expected:

- FAIL because NotebookLM policy metadata is not surfaced yet

- [ ] **Step 3: Add NotebookLM policy entries and Builder review surface**

Update policy/config so:

- read-like NotebookLM operations map to `external_api.read`
- source import and generation map to `external_api.write`
- file import also maps to `artifact.read`
- generation persistence maps to `artifact.write`

Expose NotebookLM-capable tools and policy expectations in Builder review the same way Gmail/Drive contracts are surfaced today.

- [ ] **Step 4: Run Builder tests to verify they pass**

Run:

```powershell
python -m unittest ragenius_builder.flask_scaffold.tests.test_skill_management
```

Expected:

- PASS with NotebookLM review metadata visible

- [ ] **Step 5: Commit**

```bash
git add ragenius_execution_subsystem/src/config/policy-config.ts ragenius_builder/flask_scaffold/policy.py ragenius_builder/flask_scaffold/app.py ragenius_builder/flask_scaffold/templates/skill_detail.html ragenius_builder/flask_scaffold/tests/test_skill_management.py
git commit -m "feat: surface notebooklm policy and review metadata"
```

## Task 11: Document Runtime Setup And Operator Expectations

**Files:**
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\README.md`
- Modify: `D:\GitHub\Codex-RAGenius-System\docs\superpowers\specs\2026-06-02-notebooklm-adapter-and-user-workflow-integration-design.md` (only if clarification from implementation is needed)

- [ ] **Step 1: Write the failing documentation checklist**

Create a checklist in your working notes that the README must cover:

- NotebookLM is unofficial and adapter-backed
- `notebooklm-py` installation requirement
- supported auth env/config
- supported first-phase operations
- artifact boundary for file import
- generation outputs persisted as RAGenius artifacts

- [ ] **Step 2: Update the README with NotebookLM adapter setup**

Document:

- required Python/package prerequisites
- bridge script path
- env/config values
- supported adapter tool ids
- operational caveats around session auth and upstream drift

- [ ] **Step 3: Manually review the README section for ambiguity**

Check that the doc does not imply:

- official Google NotebookLM API support
- Builder secret storage
- arbitrary local path import

- [ ] **Step 4: Commit**

```bash
git add ragenius_execution_subsystem/README.md
git commit -m "docs: add notebooklm adapter setup and limits"
```

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
npm test -- runtime-config.test.ts adapter-tool-provider.test.ts notebooklm-adapter.test.ts execute-skill.test.ts
```

Manual verification:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
python scripts/notebooklm_bridge.py
```

Expected:

- bridge accepts JSON on stdin and returns structured JSON on stdout

Success criteria:

- Builder normalizes NotebookLM aliases deterministically
- runtime can list notebooks, list sources, and ask questions through the adapter
- artifact-backed source import works without arbitrary local path inputs
- slide deck, report, and video generation persist outputs as app-scoped artifacts
- policy and review surfaces remain explicit

## Expected Deliverables

- typed NotebookLM runtime config
- Python bridge contract and script
- Node-side NotebookLM adapter executor
- adapter-provider routing for NotebookLM tool ids
- phase-1, phase-2, and phase-3 NotebookLM capabilities
- Builder alias normalization and review policy surfaces
- runtime and operator documentation

## Follow-On Recommendation

If this plan lands cleanly, the next logical plan is:

- `ragenius_app` NotebookLM user-facing follow-up UX

That next slice should cover:

- notebook selection UX
- saved execution-result reuse
- generated artifact result cards
- user-friendly chaining from app-created artifacts into NotebookLM workflows
