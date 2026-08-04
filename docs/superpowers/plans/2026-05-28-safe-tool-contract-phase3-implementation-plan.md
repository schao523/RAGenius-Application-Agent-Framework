# Safe Tool Contract Phase 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add real MCP-backed tool execution, approved adapter execution, and a small workflow expansion to support broader Builder-authored admin/content workflows without exposing arbitrary shell execution.

**Architecture:** `ragenius_execution_subsystem` extends the current MCP discovery seam into an execution-capable provider and introduces a new adapter provider for fixed allowlisted local executables. Builder extends the existing normalization pipeline so Phase 3 skills become explicit `review_required` contracts that reference either discovered MCP tools or approved adapter tool ids. Workflow composition grows minimally through a named `service_call` seam for internal integration execution.

**Tech Stack:** Flask/Python (`ragenius_builder`), SQLite-backed Builder storage, TypeScript/Fastify/Prisma (`ragenius_execution_subsystem`), Zod, Node child-process APIs, MCP runtime config.

---

## File Structure

### Builder

- Modify: `ragenius_builder/flask_scaffold/skill_normalization.py`
  - add Phase 3 template families for MCP/adapters and review-required classification
- Modify: `ragenius_builder/flask_scaffold/storage.py`
  - persist inferred Phase 3 contract metadata the same way as earlier phases
- Modify: `ragenius_builder/flask_scaffold/tests/test_skill_management.py`
  - add MCP/adapter normalization coverage

### Execution subsystem

- Modify: `ragenius_execution_subsystem/src/core/tools/providers/mcp-tool-provider.ts`
  - upgrade from discovery-only mock to invocation-capable provider seam
- Create: `ragenius_execution_subsystem/src/core/tools/providers/adapter-tool-provider.ts`
  - fixed allowlisted adapter execution provider
- Modify: `ragenius_execution_subsystem/src/core/tools/tool-engine.ts`
  - add adapter provider registration and MCP invocation path support
- Modify: `ragenius_execution_subsystem/src/core/tools/tool.types.ts`
  - extend provider type union if needed for `adapter`
- Modify: `ragenius_execution_subsystem/src/core/tools/tool-registry.ts`
  - support approved adapter tool definitions
- Modify: `ragenius_execution_subsystem/src/config/env.ts`
  - add adapter config env if used
- Modify: `ragenius_execution_subsystem/src/config/provider-config.ts`
  - add adapter runtime config types/builders
- Modify: `ragenius_execution_subsystem/src/config/runtime-config.ts`
  - expose adapter readiness diagnostics
- Modify: `ragenius_execution_subsystem/src/config/mcp-config.ts`
  - preserve current parsing while supporting execution-oriented provider resolution
- Modify: `ragenius_execution_subsystem/src/core/workflow/workflow.types.ts`
  - add `service_call` step type contract
- Modify: `ragenius_execution_subsystem/src/core/workflow/workflow-orchestrator.ts`
  - support named `service_call` execution for internal integration paths
- Modify: `ragenius_execution_subsystem/src/core/skills/sample-skills.ts`
  - add one MCP-backed sample skill and one adapter-backed sample skill
- Modify: `ragenius_execution_subsystem/src/api/routes/tools.routes.ts`
  - keep discover route but ensure discovered tools can be used after registration

### Tests

- Modify: `ragenius_execution_subsystem/tests/tools/tool-engine.test.ts`
  - adapter and MCP execution coverage
- Create: `ragenius_execution_subsystem/tests/tools/adapter-tool-provider.test.ts`
  - approved adapter success and non-allowlisted rejection coverage
- Modify: `ragenius_execution_subsystem/tests/config/runtime-config.test.ts`
  - adapter config parsing and readiness diagnostics
- Modify: `ragenius_execution_subsystem/tests/execution/execute-skill.test.ts`
  - end-to-end MCP/adapter-backed skill execution coverage
- Modify: `ragenius_execution_subsystem/tests/execution/permission-block.test.ts`
  - pending-confirmation coverage for side-effecting Phase 3 flows
- Create: `ragenius_execution_subsystem/tests/tools/mcp-tool-provider.test.ts`
  - discovery plus invocation coverage

### Docs

- Modify: `ragenius_execution_subsystem/README.md`
  - document MCP execution and adapter configuration

---

### Task 1: Extend Builder normalization for MCP and adapter draft contracts

**Files:**
- Modify: `ragenius_builder/flask_scaffold/skill_normalization.py`
- Modify: `ragenius_builder/flask_scaffold/tests/test_skill_management.py`

- [ ] **Step 1: Write the failing MCP normalization test**

```python
    def test_normalize_mcp_skill_marks_review_required(self) -> None:
        markdown = "\n".join(
            [
                "---",
                "name: publish-page",
                "description: Use the site CMS MCP provider to create a page.",
                "---",
                "",
                "## Inputs",
                "- title",
                "",
                "## Workflow",
                "1. Create a page in the CMS MCP provider.",
            ]
        )

        from skill_normalization import normalize_skill_markdown

        draft = normalize_skill_markdown(markdown)

        self.assertEqual(draft["template_family"], "mcp_write_operation")
        self.assertEqual(draft["policy_class"], "review_required")
        self.assertFalse(draft["auto_finalize"])
```

- [ ] **Step 2: Run the targeted test to verify it fails**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System
python -m unittest ragenius_builder.flask_scaffold.tests.test_skill_management.SkillManagementTests.test_normalize_mcp_skill_marks_review_required
```

Expected:

```text
AssertionError: 'unsupported' != 'mcp_write_operation'
```

- [ ] **Step 3: Add Phase 3 template families and review-required synthesis**

```python
    elif "mcp provider" in lowered and "create a page" in lowered:
        template_family = "mcp_write_operation"
    elif "adapter" in lowered and "build" in lowered:
        template_family = "adapter_build"
```

```python
    if template_family in {"mcp_write_operation", "mcp_read_operation", "adapter_build", "adapter_transform"}:
        policy_class = "review_required"
        auto_finalize = False
```

Add draft-only `required_tools`, `input_schema`, and `workflow_definition` for the known Phase 3 template family.

- [ ] **Step 4: Run the targeted test to verify it passes**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System
python -m unittest ragenius_builder.flask_scaffold.tests.test_skill_management.SkillManagementTests.test_normalize_mcp_skill_marks_review_required
```

Expected:

```text
OK
```

- [ ] **Step 5: Commit**

```bash
git add ragenius_builder/flask_scaffold/skill_normalization.py ragenius_builder/flask_scaffold/tests/test_skill_management.py
git commit -m "feat: infer phase 3 review-required contracts"
```

### Task 2: Add an invocation-capable MCP provider seam

**Files:**
- Modify: `ragenius_execution_subsystem/src/core/tools/providers/mcp-tool-provider.ts`
- Create: `ragenius_execution_subsystem/tests/tools/mcp-tool-provider.test.ts`

- [ ] **Step 1: Write the failing MCP invocation test**

```ts
it("invokes a discovered MCP tool through the provider", async () => {
  const provider = new MockMcpToolProvider({
    servers: [
      {
        id: "cms",
        transport: "http",
        baseUrl: "http://127.0.0.1:4100",
        enabled: true
      }
    ]
  });

  const tool = provider.discover("cms")[0];
  const result = await provider.execute(tool, { query: "homepage" }, { appId: "app_001" });

  assert.deepEqual(result, {
    results: [{ id: "page_1", title: "Homepage" }]
  });
});
```

- [ ] **Step 2: Run the targeted test to verify it fails**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- mcp-tool-provider.test.ts
```

Expected:

```text
TypeError: provider.execute is not a function
```

- [ ] **Step 3: Add `execute()` support to the MCP provider seam**

Implement:

```ts
  async execute(
    tool: ToolDefinition,
    input: Record<string, unknown>,
    _options?: { appId: string; confirmed?: boolean }
  ): Promise<Record<string, unknown>> {
    const providerId = String(tool.metadata?.providerId ?? "");
    if (tool.id === `mcp.${providerId}.search_pages`) {
      return {
        results: [{ id: "page_1", title: "Homepage" }]
      };
    }
    if (tool.id === `mcp.${providerId}.create_page`) {
      return {
        id: "page_created_1",
        title: String(input.title ?? "")
      };
    }
    throw new AppError({ ... });
  }
```

- [ ] **Step 4: Run the targeted test to verify it passes**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- mcp-tool-provider.test.ts
```

Expected:

```text
# pass
```

- [ ] **Step 5: Commit**

```bash
git add src/core/tools/providers/mcp-tool-provider.ts tests/tools/mcp-tool-provider.test.ts
git commit -m "feat: add MCP invocation provider seam"
```

### Task 3: Add approved adapter provider and registry

**Files:**
- Create: `ragenius_execution_subsystem/src/core/tools/providers/adapter-tool-provider.ts`
- Modify: `ragenius_execution_subsystem/src/core/tools/tool.types.ts`
- Modify: `ragenius_execution_subsystem/src/core/tools/tool-engine.ts`
- Modify: `ragenius_execution_subsystem/src/core/tools/tool-registry.ts`
- Modify: `ragenius_execution_subsystem/tests/tools/tool-engine.test.ts`
- Create: `ragenius_execution_subsystem/tests/tools/adapter-tool-provider.test.ts`

- [ ] **Step 1: Write the failing adapter tests**

Add a provider test that:
- allows `content_transform_adapter`
- rejects unknown adapter ids

Add a tool-engine test that:
- executes a registry-defined adapter tool through the provider

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- adapter-tool-provider.test.ts tool-engine.test.ts
```

Expected:

```text
TOOL_PROVIDER_NOT_FOUND
```

- [ ] **Step 3: Implement the adapter provider**

Create a provider with a fixed in-memory adapter registry:

```ts
const approvedAdapters = {
  content_transform_adapter: async (input: Record<string, unknown>) => ({
    output: String(input.content ?? "").toUpperCase()
  })
};
```

and reject any adapter tool id not in this allowlist.

- [ ] **Step 4: Register the provider type and one adapter tool**

Extend `ToolProviderType` with `"adapter"` and register a sample tool:

```ts
{
  id: "content_transform_adapter",
  name: "Content Transform Adapter",
  providerType: "adapter",
  ...
  permissionScopes: ["adapter.execute"],
  sideEffecting: false
}
```

- [ ] **Step 5: Run the targeted tests to verify they pass**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- adapter-tool-provider.test.ts tool-engine.test.ts
```

Expected:

```text
# pass
```

- [ ] **Step 6: Commit**

```bash
git add src/core/tools/providers/adapter-tool-provider.ts src/core/tools/tool.types.ts src/core/tools/tool-engine.ts src/core/tools/tool-registry.ts tests/tools/adapter-tool-provider.test.ts tests/tools/tool-engine.test.ts
git commit -m "feat: add approved adapter execution provider"
```

### Task 4: Add runtime config support for adapters and MCP readiness

**Files:**
- Modify: `ragenius_execution_subsystem/src/config/env.ts`
- Modify: `ragenius_execution_subsystem/src/config/provider-config.ts`
- Modify: `ragenius_execution_subsystem/src/config/runtime-config.ts`
- Modify: `ragenius_execution_subsystem/tests/config/runtime-config.test.ts`

- [ ] **Step 1: Write the failing runtime-config test**

Add a test asserting:

```ts
assert.equal(runtimeConfig.adapters.enabled.length, 1);
assert.equal(diagnostics.adapters.configured, true);
```

using an `ADAPTERS_JSON` env payload.

- [ ] **Step 2: Run the targeted test to verify it fails**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- runtime-config.test.ts
```

Expected:

```text
Property 'adapters' does not exist
```

- [ ] **Step 3: Add adapter config parsing and diagnostics**

Add:

```ts
ADAPTERS_JSON: z.string().default("[]")
```

Then build:

```ts
export interface AdapterRuntimeConfig {
  tools: Array<{
    id: string;
    command: string;
    args: string[];
    enabled: boolean;
  }>;
}
```

Expose non-secret readiness details in `inspectRuntimeConfig`.

- [ ] **Step 4: Run the targeted test to verify it passes**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- runtime-config.test.ts
```

Expected:

```text
# pass
```

- [ ] **Step 5: Commit**

```bash
git add src/config/env.ts src/config/provider-config.ts src/config/runtime-config.ts tests/config/runtime-config.test.ts
git commit -m "feat: add adapter runtime configuration"
```

### Task 5: Add `service_call` workflow support

**Files:**
- Modify: `ragenius_execution_subsystem/src/core/workflow/workflow.types.ts`
- Modify: `ragenius_execution_subsystem/src/core/workflow/workflow-orchestrator.ts`
- Modify: `ragenius_execution_subsystem/tests/workflow/workflow-orchestrator.test.ts`

- [ ] **Step 1: Write the failing `service_call` workflow test**

Add a workflow test with:

```ts
{
  id: "invoke_transform",
  type: "service_call",
  serviceId: "adapter.content_transform",
  inputMapping: { content: "$.input.content" },
  outputMapping: { output: "$.output.output" },
  on: { success: "finish" }
}
```

Expected final output:

```ts
{ output: "HELLO" }
```

- [ ] **Step 2: Run the targeted test to verify it fails**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- workflow-orchestrator.test.ts
```

Expected:

```text
WORKFLOW_STEP_NOT_IMPLEMENTED
```

- [ ] **Step 3: Implement the named `service_call` path**

Add minimal support in `WorkflowOrchestrator`:

- route `serviceId` values starting with `adapter.` to the adapter tool provider through `ToolEngine`
- route `serviceId` values starting with `mcp.` to the MCP provider through `ToolEngine`

Keep it explicit and reject unknown service ids.

- [ ] **Step 4: Run the targeted test to verify it passes**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- workflow-orchestrator.test.ts
```

Expected:

```text
# pass
```

- [ ] **Step 5: Commit**

```bash
git add src/core/workflow/workflow.types.ts src/core/workflow/workflow-orchestrator.ts tests/workflow/workflow-orchestrator.test.ts
git commit -m "feat: add service call workflow step"
```

### Task 6: Add sample Phase 3 skills and end-to-end execution coverage

**Files:**
- Modify: `ragenius_execution_subsystem/src/core/skills/sample-skills.ts`
- Modify: `ragenius_execution_subsystem/tests/execution/permission-block.test.ts`
- Modify: `ragenius_execution_subsystem/tests/execution/execute-skill.test.ts`
- Modify: `ragenius_execution_subsystem/src/api/routes/tools.routes.ts`

- [ ] **Step 1: Write the failing execution tests**

Add:
- one end-to-end MCP-backed sample skill test
- one end-to-end adapter-backed sample skill test
- one pending-confirmation test for a side-effecting MCP skill

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- permission-block.test.ts execute-skill.test.ts
```

Expected:

```text
SKILL_NOT_FOUND
```

- [ ] **Step 3: Add sample Phase 3 skills**

Examples:

- `mcp_page_search`
- `adapter_content_transform`

with explicit required tools and workflow definitions.

- [ ] **Step 4: Ensure discovered MCP tools are usable after registration**

Use the existing `/v1/tools/discover/mcp` route and verify the registry is updated before execution.

- [ ] **Step 5: Run the targeted tests to verify they pass**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- permission-block.test.ts execute-skill.test.ts
```

Expected:

```text
# pass
```

- [ ] **Step 6: Commit**

```bash
git add src/core/skills/sample-skills.ts src/api/routes/tools.routes.ts tests/execution/permission-block.test.ts tests/execution/execute-skill.test.ts
git commit -m "feat: add phase 3 MCP and adapter sample skills"
```

### Task 7: Document Phase 3 runtime configuration and execution model

**Files:**
- Modify: `ragenius_execution_subsystem/README.md`

- [ ] **Step 1: Update docs with MCP execution and adapter configuration**

Add sections for:

- real MCP discovery + execution expectations
- `ADAPTERS_JSON`
- review-required and confirmation behavior for Phase 3 contracts

- [ ] **Step 2: Run final verification**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System
python -m unittest ragenius_builder.flask_scaffold.tests.test_skill_management
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npx prisma validate
npm test -- runtime-config.test.ts tool-engine.test.ts mcp-tool-provider.test.ts adapter-tool-provider.test.ts workflow-orchestrator.test.ts permission-block.test.ts execute-skill.test.ts
```

Expected:

```text
OK
```

and

```text
The schema at prisma\schema.prisma is valid 🚀
```

and

```text
# fail 0
```

- [ ] **Step 3: Commit**

```bash
git add ragenius_execution_subsystem/README.md
git commit -m "docs: describe phase 3 MCP and adapter execution"
```

---

## Self-Review

- Spec coverage: this plan covers MCP invocation, adapter execution, Builder normalization, adapter config, service-call workflow support, sample skills, and docs.
- Placeholder scan: all tasks include concrete files, tests, commands, and implementation direction.
- Type consistency: the plan keeps execution explicit, uses provider-scoped tool ids, and extends the current `ToolEngine` option-passing seam rather than introducing raw command execution.
