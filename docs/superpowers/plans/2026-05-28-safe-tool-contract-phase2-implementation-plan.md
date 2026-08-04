# Safe Tool Contract Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add review-gated mutation contracts to Builder and bounded `write_file` / `patch_file` execution support to `ragenius_execution_subsystem`.

**Architecture:** Builder extends the Phase 1 normalization path to classify mutation-oriented natural skills into explicit `review_required` contracts, but never auto-finalizes them. `ragenius_execution_subsystem` extends the existing local provider and policy/config seams with bounded write and patch support, then routes those tools through the existing permission and confirmation lifecycle.

**Tech Stack:** Flask/Python (`ragenius_builder`), SQLite-backed Builder storage, TypeScript/Fastify/Prisma (`ragenius_execution_subsystem`), Zod, Node filesystem APIs.

---

## File Structure

### Builder

- Modify: `ragenius_builder/flask_scaffold/skill_normalization.py`
  - add mutation template classification, mutation schemas/workflows, and review-required finalization rules
- Modify: `ragenius_builder/flask_scaffold/storage.py`
  - persist mutation contract metadata and ensure mutation skills land in review state instead of auto-finalize
- Modify: `ragenius_builder/flask_scaffold/tests/test_skill_management.py`
  - extend `SkillManagementTests` with mutation normalization and persistence tests

### Execution subsystem

- Modify: `ragenius_execution_subsystem/src/core/tools/tool-registry.ts`
  - register `write_file` and `patch_file`
- Modify: `ragenius_execution_subsystem/src/core/tools/providers/file-policy.ts`
  - add mutation-root and existing-file validation helpers
- Modify: `ragenius_execution_subsystem/src/core/tools/providers/local-tool-provider.ts`
  - implement `write_file` and `patch_file`
- Modify: `ragenius_execution_subsystem/src/config/env.ts`
  - add mutation env vars
- Modify: `ragenius_execution_subsystem/src/config/provider-config.ts`
  - add mutation runtime config types/builders
- Modify: `ragenius_execution_subsystem/src/config/runtime-config.ts`
  - expose mutation config and readiness diagnostics
- Modify: `ragenius_execution_subsystem/src/core/skills/sample-skills.ts`
  - add one sample normalized mutation skill
- Modify: `ragenius_execution_subsystem/src/core/execution/result-normalizer.ts`
  - keep confirmation response and logs clear for mutation-oriented flows if needed
- Modify: `ragenius_execution_subsystem/src/api/routes/health.routes.ts`
  - expose non-secret mutation readiness details if diagnostics shape changes

### Tests

- Modify: `ragenius_execution_subsystem/tests/tools/file-policy.test.ts`
  - mutation-root validation coverage
- Modify: `ragenius_execution_subsystem/tests/tools/local-tool-provider.test.ts`
  - write and patch success/failure coverage
- Modify: `ragenius_execution_subsystem/tests/tools/tool-engine.test.ts`
  - registry and app-context coverage for mutation tools
- Modify: `ragenius_execution_subsystem/tests/config/runtime-config.test.ts`
  - mutation env parsing and diagnostics
- Modify: `ragenius_execution_subsystem/tests/execution/permission-block.test.ts`
  - pending-confirmation and confirmed execution behavior for mutation tools
- Modify: `ragenius_execution_subsystem/tests/execution/execute-skill.test.ts`
  - end-to-end execution of a normalized mutation contract

### Docs

- Modify: `ragenius_execution_subsystem/README.md`
  - document mutation tool config and confirmation requirements

---

### Task 1: Extend Builder normalization for mutation templates

**Files:**
- Modify: `ragenius_builder/flask_scaffold/skill_normalization.py`
- Modify: `ragenius_builder/flask_scaffold/tests/test_skill_management.py`

- [ ] **Step 1: Write the failing mutation-normalization test**

```python
    def test_normalize_mutation_skill_marks_review_required(self) -> None:
        markdown = "\n".join(
            [
                "---",
                "name: patch-homepage-copy",
                "description: Update the homepage markdown copy and save the result.",
                "---",
                "",
                "## Inputs",
                "- path",
                "- patch",
                "",
                "## Workflow",
                "1. Read the existing file.",
                "2. Apply a patch to the file.",
            ]
        )

        from skill_normalization import normalize_skill_markdown

        draft = normalize_skill_markdown(markdown)

        self.assertEqual(draft["template_family"], "content_patch")
        self.assertEqual(draft["policy_class"], "review_required")
        self.assertFalse(draft["auto_finalize"])
        self.assertEqual(
            draft["required_tools"],
            ["read_file", "patch_file", "save_artifact"],
        )
```

- [ ] **Step 2: Run the targeted test to verify it fails**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System
python -m unittest ragenius_builder.flask_scaffold.tests.test_skill_management.SkillManagementTests.test_normalize_mutation_skill_marks_review_required
```

Expected:

```text
AssertionError: 'unsupported' != 'content_patch'
```

- [ ] **Step 3: Add mutation template classification and workflow/schema synthesis**

```python
    if "apply a patch" in lowered or "patch the file" in lowered:
        template_family = "content_patch"
    elif "replace the file" in lowered or "write the updated file" in lowered:
        template_family = "content_replace"
```

```python
def _input_schema_for(template_family: str) -> Dict[str, Any]:
    if template_family == "content_patch":
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "patch": {"type": "string"},
            },
            "required": ["path", "patch"],
        }
    if template_family == "content_replace":
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        }
```

```python
def _workflow_for(template_family: str) -> Dict[str, Any]:
    if template_family == "content_patch":
        return {
            "steps": [
                {
                    "id": "read_file",
                    "type": "tool_call",
                    "toolId": "read_file",
                    "inputMapping": {"path": "$.input.path"},
                    "outputMapping": {"content": "$.output.content"},
                    "on": {"success": "apply_patch"},
                },
                {
                    "id": "apply_patch",
                    "type": "tool_call",
                    "toolId": "patch_file",
                    "inputMapping": {
                        "path": "$.input.path",
                        "patch": "$.input.patch",
                        "format": "unified_diff",
                    },
                    "outputMapping": {
                        "path": "$.output.path",
                        "updated": "$.output.updated",
                        "summary": "$.output.summary",
                    },
                    "on": {"success": "save_report"},
                },
                {
                    "id": "save_report",
                    "type": "tool_call",
                    "toolId": "save_artifact",
                    "inputMapping": {
                        "artifact_type": "mutation_report",
                        "name": "patch-result",
                        "content": "$.steps.apply_patch.output",
                    },
                    "outputMapping": {"artifact_id": "$.output.artifact_id"},
                    "on": {"success": "finish"},
                },
                {"id": "finish", "type": "end"},
            ]
        }
```

```python
    if template_family in {"content_patch", "content_replace"}:
        required_tools = SAFE_TEMPLATE_TOOL_MAP[template_family]
        required_permissions = ["filesystem.read", "filesystem.patch", "artifact.write"]
        policy_class = "review_required"
        auto_finalize = False
```

- [ ] **Step 4: Run the targeted test to verify it passes**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System
python -m unittest ragenius_builder.flask_scaffold.tests.test_skill_management.SkillManagementTests.test_normalize_mutation_skill_marks_review_required
```

Expected:

```text
OK
```

- [ ] **Step 5: Commit**

```bash
git add ragenius_builder/flask_scaffold/skill_normalization.py ragenius_builder/flask_scaffold/tests/test_skill_management.py
git commit -m "feat: classify mutation skills as review-required"
```

### Task 2: Persist mutation contracts in Builder review state

**Files:**
- Modify: `ragenius_builder/flask_scaffold/storage.py`
- Modify: `ragenius_builder/flask_scaffold/tests/test_skill_management.py`

- [ ] **Step 1: Write the failing storage test**

```python
    def test_import_skill_package_keeps_mutation_contract_in_review_state(self) -> None:
        archive_path = self._create_skill_archive(
            "patch-homepage-copy",
            "\n".join(
                [
                    "---",
                    "name: patch-homepage-copy",
                    "description: Apply a patch to an existing markdown file.",
                    "---",
                    "",
                    "1. Read the file.",
                    "2. Apply a patch to the file.",
                ]
            ),
        )

        imported = self.store.import_skill_package(archive_path, "managed")

        self.assertEqual(imported["version_state"], "review")
        skill = self.store.get_skill(imported["skill_id"])
        version = skill["versions"][0]
        self.assertEqual(version["metadata"]["policy_class"], "review_required")
        self.assertEqual(version["metadata"]["workflow_definition"]["steps"][1]["toolId"], "patch_file")
```

- [ ] **Step 2: Run the targeted test to verify it fails**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System
python -m unittest ragenius_builder.flask_scaffold.tests.test_skill_management.SkillManagementTests.test_import_skill_package_keeps_mutation_contract_in_review_state
```

Expected:

```text
AssertionError: 'draft' != 'review'
```

- [ ] **Step 3: Update import-state handling for normalized mutation contracts**

```python
        version_state = "draft"
        normalized_policy_class = metadata_json.get("policy_class")
        if normalized_policy_class == "review_required":
            version_state = "review"
        elif not metadata_json.get("auto_finalize") and not metadata_json.get(
            "required_tools"
        ):
            version_state = "review"
```

- [ ] **Step 4: Run the targeted test to verify it passes**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System
python -m unittest ragenius_builder.flask_scaffold.tests.test_skill_management.SkillManagementTests.test_import_skill_package_keeps_mutation_contract_in_review_state
```

Expected:

```text
OK
```

- [ ] **Step 5: Commit**

```bash
git add ragenius_builder/flask_scaffold/storage.py ragenius_builder/flask_scaffold/tests/test_skill_management.py
git commit -m "feat: persist mutation contracts in review state"
```

### Task 3: Add failing runtime tests for mutation root policy and write behavior

**Files:**
- Modify: `ragenius_execution_subsystem/tests/tools/file-policy.test.ts`
- Modify: `ragenius_execution_subsystem/tests/tools/local-tool-provider.test.ts`

- [ ] **Step 1: Add the failing file-policy mutation test**

```ts
  it("rejects writes outside configured mutation roots", async () => {
    const policy = new FilePolicy({
      allowedRoots: ["D:/GitHub/Codex-RAGenius-System"],
      mutationRoots: ["D:/GitHub/Codex-RAGenius-System/docs"],
      maxReadBytes: 4096,
      maxWriteBytes: 8192,
      maxPatchBytes: 8192
    });

    assert.throws(
      () => policy.resolveWritablePath("D:/GitHub/Codex-RAGenius-System/README.md"),
      /FILESYSTEM_PATH_NOT_ALLOWED/
    );
  });
```

- [ ] **Step 2: Add the failing local-provider mutation tests**

```ts
  it("writes a text file only within mutation roots", async () => {
    const tempRoot = createArtifactRoot();
    const targetPath = path.join(tempRoot, "content.md");
    await fs.writeFile(targetPath, "before", "utf-8");

    const provider = new PhaseOneLocalToolProvider(
      new FilePolicy({
        allowedRoots: [tempRoot],
        mutationRoots: [tempRoot],
        maxReadBytes: 4096,
        maxWriteBytes: 4096,
        maxPatchBytes: 4096
      }),
      new ArtifactStore(createArtifactRoot())
    );

    const result = await provider.execute(
      writeFileToolDefinition,
      { path: targetPath, content: "after" },
      { appId: "app_alpha" }
    );

    assert.equal(result.updated, true);
    assert.equal(await fs.readFile(targetPath, "utf-8"), "after");
  });
```

```ts
  it("applies a unified diff patch within mutation roots", async () => {
    const tempRoot = createArtifactRoot();
    const targetPath = path.join(tempRoot, "content.md");
    await fs.writeFile(targetPath, "alpha\nbeta\n", "utf-8");

    const provider = new PhaseOneLocalToolProvider(
      new FilePolicy({
        allowedRoots: [tempRoot],
        mutationRoots: [tempRoot],
        maxReadBytes: 4096,
        maxWriteBytes: 4096,
        maxPatchBytes: 4096
      }),
      new ArtifactStore(createArtifactRoot())
    );

    const result = await provider.execute(
      patchFileToolDefinition,
      {
        path: targetPath,
        patch: "@@ -1,2 +1,2 @@\n alpha\n-beta\n+gamma\n"
      },
      { appId: "app_alpha" }
    );

    assert.equal(result.updated, true);
    assert.match(String(result.summary), /patched/i);
    assert.equal(await fs.readFile(targetPath, "utf-8"), "alpha\ngamma\n");
  });
```

- [ ] **Step 3: Run the targeted tests to verify they fail**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- file-policy.test.ts local-tool-provider.test.ts
```

Expected:

```text
TypeError: policy.resolveWritablePath is not a function
```

and

```text
LOCAL_TOOL_NOT_IMPLEMENTED
```

- [ ] **Step 4: Commit the failing tests checkpoint**

```bash
git add tests/tools/file-policy.test.ts tests/tools/local-tool-provider.test.ts
git commit -m "test: add mutation policy and local provider coverage"
```

### Task 4: Implement bounded mutation-root policy and local mutation tools

**Files:**
- Modify: `ragenius_execution_subsystem/src/core/tools/providers/file-policy.ts`
- Modify: `ragenius_execution_subsystem/src/core/tools/providers/local-tool-provider.ts`

- [ ] **Step 1: Add mutation-root resolution helpers**

```ts
  resolveWritablePath(rawPath: string): string {
    const resolved = path.resolve(rawPath);
    const allowed = this.config.mutationRoots.some((root) =>
      resolved.startsWith(path.resolve(root))
    );
    if (!allowed) {
      throw new AppError({
        code: "FILESYSTEM_PATH_NOT_ALLOWED",
        message: "Filesystem path is outside configured mutation roots.",
        errorClass: "permission",
        httpStatus: 403,
        details: { path: resolved },
        recoverable: false,
        suggestedAction: "Use a path within the configured mutation roots."
      });
    }
    return resolved;
  }
```

```ts
  async assertExistingWritableTextFile(rawPath: string): Promise<string> {
    const resolved = this.resolveWritablePath(rawPath);
    const stat = await fs.stat(resolved);
    if (!stat.isFile()) {
      throw new AppError({
        code: "FILESYSTEM_TARGET_INVALID",
        message: "Mutation target must be an existing file.",
        errorClass: "validation",
        httpStatus: 400,
        details: { path: resolved },
        recoverable: true,
        suggestedAction: "Provide an existing text file path."
      });
    }
    return resolved;
  }
```

- [ ] **Step 2: Implement `write_file`**

```ts
    if (tool.id === "write_file") {
      const resolved = await this.filePolicy.assertExistingWritableTextFile(
        String(input.path ?? "")
      );
      const content = String(input.content ?? "");
      await fs.writeFile(resolved, content, "utf-8");
      return {
        path: resolved,
        bytes_written: Buffer.byteLength(content, "utf-8"),
        updated: true
      };
    }
```

- [ ] **Step 3: Implement `patch_file` with bounded unified-diff replacement**

```ts
    if (tool.id === "patch_file") {
      const resolved = await this.filePolicy.assertExistingWritableTextFile(
        String(input.path ?? "")
      );
      const patch = String(input.patch ?? "");
      const raw = await fs.readFile(resolved, "utf-8");
      const next = applyUnifiedDiff(raw, patch);
      await fs.writeFile(resolved, next, "utf-8");
      return {
        path: resolved,
        updated: true,
        summary: "Patched file successfully."
      };
    }
```

- [ ] **Step 4: Run the targeted tests to verify they pass**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- file-policy.test.ts local-tool-provider.test.ts
```

Expected:

```text
# pass
```

- [ ] **Step 5: Commit**

```bash
git add src/core/tools/providers/file-policy.ts src/core/tools/providers/local-tool-provider.ts tests/tools/file-policy.test.ts tests/tools/local-tool-provider.test.ts
git commit -m "feat: add bounded local write and patch tools"
```

### Task 5: Register mutation tools and runtime config

**Files:**
- Modify: `ragenius_execution_subsystem/src/core/tools/tool-registry.ts`
- Modify: `ragenius_execution_subsystem/src/config/env.ts`
- Modify: `ragenius_execution_subsystem/src/config/provider-config.ts`
- Modify: `ragenius_execution_subsystem/src/config/runtime-config.ts`
- Modify: `ragenius_execution_subsystem/tests/config/runtime-config.test.ts`
- Modify: `ragenius_execution_subsystem/tests/tools/tool-engine.test.ts`

- [ ] **Step 1: Add the failing config and registry tests**

```ts
  it("parses mutation roots and write limits from env", () => {
    const runtimeConfig = buildRuntimeConfig(
      getEnv({
        DATABASE_URL: "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
        FILESYSTEM_ALLOWED_ROOTS: "D:/workspace",
        FILESYSTEM_MUTATION_ROOTS: "D:/workspace/content",
        FILESYSTEM_MAX_WRITE_BYTES: "8192",
        FILESYSTEM_MAX_PATCH_BYTES: "4096"
      })
    );

    assert.deepEqual(runtimeConfig.fileTools.mutationRoots, ["D:/workspace/content"]);
    assert.equal(runtimeConfig.fileTools.maxWriteBytes, 8192);
    assert.equal(runtimeConfig.fileTools.maxPatchBytes, 4096);
  });
```

```ts
  it("registers mutation tools in the registry", () => {
    const registry = new ToolRegistry();
    assert.equal(registry.get("write_file").id, "write_file");
    assert.equal(registry.get("patch_file").id, "patch_file");
  });
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- runtime-config.test.ts tool-engine.test.ts
```

Expected:

```text
AssertionError
```

- [ ] **Step 3: Add env parsing and tool definitions**

```ts
FILESYSTEM_MUTATION_ROOTS: z.string().optional(),
FILESYSTEM_MAX_WRITE_BYTES: z.coerce.number().int().positive().default(65536),
FILESYSTEM_MAX_PATCH_BYTES: z.coerce.number().int().positive().default(32768),
```

```ts
export interface FileToolRuntimeConfig {
  allowedRoots: string[];
  mutationRoots: string[];
  maxReadBytes: number;
  maxWriteBytes: number;
  maxPatchBytes: number;
}
```

```ts
    this.register({
      id: "write_file",
      name: "Write File",
      providerType: "local",
      inputSchema: z.object({
        path: z.string().min(1),
        content: z.string(),
        encoding: z.string().optional(),
        if_exists: z.literal("overwrite").optional()
      }),
      outputSchema: z.object({
        path: z.string(),
        bytes_written: z.number().int().nonnegative(),
        updated: z.boolean()
      }),
      permissionScopes: ["filesystem.write"],
      sideEffecting: true,
      metadata: { safePhase: 2, policyClass: "mutation" }
    });
```

- [ ] **Step 4: Run the targeted tests to verify they pass**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- runtime-config.test.ts tool-engine.test.ts
```

Expected:

```text
# pass
```

- [ ] **Step 5: Commit**

```bash
git add src/core/tools/tool-registry.ts src/config/env.ts src/config/provider-config.ts src/config/runtime-config.ts tests/config/runtime-config.test.ts tests/tools/tool-engine.test.ts
git commit -m "feat: register mutation tools and runtime config"
```

### Task 6: Enforce confirmation flow for mutation execution

**Files:**
- Modify: `ragenius_execution_subsystem/tests/execution/permission-block.test.ts`
- Modify: `ragenius_execution_subsystem/src/core/skills/sample-skills.ts`
- Modify: `ragenius_execution_subsystem/tests/execution/execute-skill.test.ts`

- [ ] **Step 1: Add the failing pending-confirmation test for a mutation skill**

```ts
  it("returns pending confirmation before executing a mutation skill", async () => {
    const engine = new ExecutionEngine({
      permissionEngine: new PermissionEngine([
        {
          appId: "app_writer",
          toolId: "write_file",
          scope: "filesystem.write",
          mode: "require_confirmation"
        }
      ])
    });

    const result = await engine.execute({
      request_type: "execute_skill",
      app_id: "app_writer",
      session_id: "sess_writer",
      skill_id: "content_replace",
      input: {
        path: "D:/GitHub/Codex-RAGenius-System/docs/test.md",
        content: "updated"
      }
    });

    assert.equal(result.status, "pending_confirmation");
  });
```

- [ ] **Step 2: Run the targeted test to verify it fails**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- permission-block.test.ts execute-skill.test.ts
```

Expected:

```text
SKILL_NOT_FOUND
```

- [ ] **Step 3: Add a sample normalized mutation skill and confirmed execution test**

```ts
export const contentReplaceSkill: SkillDefinition = {
  id: "content_replace",
  name: "Content Replace",
  version: "1.0.0",
  description: "Replace file content within configured mutation roots.",
  inputSchema: z.object({
    path: z.string().min(1),
    content: z.string()
  }),
  outputSchema: z.object({
    path: z.string(),
    bytes_written: z.number().int().nonnegative(),
    updated: z.boolean()
  }),
  requiredTools: ["write_file"],
  requiredPermissions: ["filesystem.write"],
  workflowDefinition: {
    steps: [
      {
        id: "write_file",
        type: "tool_call",
        toolId: "write_file",
        inputMapping: {
          path: "$.input.path",
          content: "$.input.content"
        },
        outputMapping: {
          path: "$.output.path",
          bytes_written: "$.output.bytes_written",
          updated: "$.output.updated"
        },
        on: { success: "finish" }
      },
      { id: "finish", type: "end" }
    ]
  },
  enabled: true,
  resultType: "json"
};
```

```ts
  it("executes a confirmed mutation skill within allowed roots", async () => {
    const tempRoot = "D:/GitHub/Codex-RAGenius-System/outputs/test-mutation-runtime";
    await fs.mkdir(tempRoot, { recursive: true });
    const targetPath = path.join(tempRoot, "content.md");
    await fs.writeFile(targetPath, "before", "utf-8");

    const runtimeConfig = buildRuntimeConfig(
      getEnv({
        DATABASE_URL: "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
        FILESYSTEM_ALLOWED_ROOTS: tempRoot,
        FILESYSTEM_MUTATION_ROOTS: tempRoot,
        FILESYSTEM_MAX_WRITE_BYTES: "4096",
        FILESYSTEM_MAX_PATCH_BYTES: "4096",
        ARTIFACT_STORAGE_ROOT: "D:/GitHub/Codex-RAGenius-System/outputs/test-artifacts-runtime",
        MCP_SERVERS_JSON: "[]"
      })
    );

    const engine = new ExecutionEngine({
      permissionEngine: new PermissionEngine([
        {
          appId: "app_writer",
          toolId: "write_file",
          scope: "filesystem.write",
          mode: "require_confirmation"
        }
      ]),
      toolEngine: createAppServices({}, runtimeConfig).toolEngine
    });

    const pending = await engine.execute({
      request_type: "execute_skill",
      app_id: "app_writer",
      session_id: "sess_writer",
      skill_id: "content_replace",
      input: { path: targetPath, content: "after" }
    });
    assert.equal(pending.status, "pending_confirmation");
  });
```

- [ ] **Step 4: Run the targeted tests to verify they pass**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- permission-block.test.ts execute-skill.test.ts
```

Expected:

```text
# pass
```

- [ ] **Step 5: Commit**

```bash
git add src/core/skills/sample-skills.ts tests/execution/permission-block.test.ts tests/execution/execute-skill.test.ts
git commit -m "feat: gate mutation skills behind confirmation"
```

### Task 7: Document Phase 2 mutation configuration and workflow expectations

**Files:**
- Modify: `ragenius_execution_subsystem/README.md`

- [ ] **Step 1: Add the failing docs expectation as a checklist in the diff**

```md
## Phase 2 Mutation Tools

- `write_file`
- `patch_file`

Required env vars:

- `FILESYSTEM_MUTATION_ROOTS`
- `FILESYSTEM_MAX_WRITE_BYTES`
- `FILESYSTEM_MAX_PATCH_BYTES`

Mutation executions are confirmation-gated and should be published from Builder as `review_required` contracts.
```

- [ ] **Step 2: Apply the README update**

Insert the section above beneath the Phase 1 safe tools documentation and update any sample env block to include:

```env
FILESYSTEM_MUTATION_ROOTS=D:/GitHub/Codex-RAGenius-System/content
FILESYSTEM_MAX_WRITE_BYTES=65536
FILESYSTEM_MAX_PATCH_BYTES=32768
```

- [ ] **Step 3: Run the targeted verification**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npx prisma validate
npm test -- runtime-config.test.ts file-policy.test.ts local-tool-provider.test.ts tool-engine.test.ts permission-block.test.ts execute-skill.test.ts
```

Expected:

```text
The schema at prisma\schema.prisma is valid 🚀
```

and

```text
# fail 0
```

- [ ] **Step 4: Commit**

```bash
git add ragenius_execution_subsystem/README.md
git commit -m "docs: document phase 2 mutation tool configuration"
```

---

## Self-Review

- Spec coverage: this plan covers Builder mutation classification/review state, runtime mutation tools, runtime config, confirmation flow, sample mutation contract execution, and docs.
- Placeholder scan: no `TODO`, `TBD`, or hand-wavy “add validation” steps are left without concrete code/tests.
- Type consistency: the plan uses the existing Builder normalization seam and the current execution-subsystem `ToolEngine` provider contract with `options.appId`.
