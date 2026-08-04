# Safe Tool Contract Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first safe Builder normalization path plus Phase 1 runtime tool support so natural `SKILL.md` uploads can become explicit, executable contracts for safe admin/content workflows.

**Architecture:** Builder gains a normalization module that parses natural skill markdown, classifies it into supported safe template families, synthesizes explicit contract metadata, and persists that metadata into published skill definitions. `ragenius_execution_subsystem` gains a small set of safe tool definitions and provider implementations that fit its current `ToolEngine` and `SkillDefinition` interfaces. Execution remains explicit: Builder finalizes contracts first, runtime executes only the finalized contract.

**Tech Stack:** Flask/Python (`ragenius_builder`), SQLite-backed Builder storage, TypeScript/Fastify/Prisma (`ragenius_execution_subsystem`), Zod, PostgreSQL.

---

## File Structure

### Builder

- Create: `ragenius_builder/flask_scaffold/skill_normalization.py`
  - Builder-only normalization, template classification, contract synthesis, and finalization-policy helpers
- Modify: `ragenius_builder/flask_scaffold/storage.py`
  - invoke normalization during skill import and publish normalized metadata into stored skill version metadata
- Modify: `ragenius_builder/flask_scaffold/app.py`
  - surface normalized policy/finalization details in existing skill detail and test flows if useful
- Modify: `ragenius_builder/flask_scaffold/tests/test_skill_management.py`
  - extend the existing `SkillManagementTests` class with normalization and persisted-contract tests

### Execution subsystem

- Modify: `ragenius_execution_subsystem/src/core/tools/tool-registry.ts`
  - register Phase 1 safe core tools using the current `ToolDefinition` contract
- Modify: `ragenius_execution_subsystem/src/core/tools/providers/local-tool-provider.ts`
  - replace the current local provider placeholder interface with a concrete provider class implementing `execute(tool, input)`
- Create: `ragenius_execution_subsystem/src/core/tools/providers/file-policy.ts`
  - allowed-root and bounded-read enforcement helper for local file tools
- Create: `ragenius_execution_subsystem/src/core/tools/providers/artifact-store.ts`
  - app-scoped artifact persistence helper
- Modify: `ragenius_execution_subsystem/src/core/tools/providers/rag-adapter-provider.ts`
  - extend the current mock/provider to support `retrieve_documents` and `search_metadata` while keeping retrieval logic owned by `rag_subsystem`
- Modify: `ragenius_execution_subsystem/src/core/tools/tool-engine.ts`
  - wire the concrete local provider and keep the current `execute(tool, input)` provider contract intact
- Modify: `ragenius_execution_subsystem/src/config/env.ts`
  - add env vars for allowed roots and artifact storage
- Modify: `ragenius_execution_subsystem/src/config/provider-config.ts`
  - add policy/runtime config types for file tools and artifact store
- Modify: `ragenius_execution_subsystem/src/config/runtime-config.ts`
  - expose safe tool configuration in the runtime config
- Modify: `ragenius_execution_subsystem/src/api/routes/health.routes.ts`
  - expose non-secret readiness details for file-tool and artifact-store configuration
- Modify: `ragenius_execution_subsystem/src/core/skills/sample-skills.ts`
  - add a sample `file_inventory` skill that matches the Phase 1 contract shape for end-to-end verification

### Tests

- Modify: `ragenius_execution_subsystem/tests/tools/tool-engine.test.ts`
  - assert registry and engine behavior for the new Phase 1 tools using Node `assert`
- Create: `ragenius_execution_subsystem/tests/tools/file-policy.test.ts`
  - allowed-root and rejection coverage
- Create: `ragenius_execution_subsystem/tests/tools/local-tool-provider.test.ts`
  - read/list/save/load artifact behavior coverage
- Modify: `ragenius_execution_subsystem/tests/tools/rag-adapter.test.ts`
  - retrieval and metadata-search behavior under the current provider style
- Modify: `ragenius_execution_subsystem/tests/config/runtime-config.test.ts`
  - env parsing for file-tool and artifact-store config
- Modify: `ragenius_execution_subsystem/tests/execution/execute-skill.test.ts`
  - end-to-end execution of the sample normalized safe contract using `ExecutionEngine`

### Docs

- Modify: `ragenius_execution_subsystem/README.md`
  - document new Phase 1 safe tools and required env vars

---

### Task 1: Add Builder normalization module and first draft classifier

**Files:**
- Create: `ragenius_builder/flask_scaffold/skill_normalization.py`
- Modify: `ragenius_builder/flask_scaffold/tests/test_skill_management.py`

- [ ] **Step 1: Write the failing Builder normalization test inside `SkillManagementTests`**

```python
    def test_normalize_safe_read_skill_builds_file_inspection_draft(self) -> None:
        markdown = "\n".join(
            [
                "---",
                "name: file-inventory",
                "description: Inspect a workspace path and save a summary report.",
                "---",
                "",
                "# File Inventory",
                "",
                "## Inputs",
                "- path",
                "",
                "## Workflow",
                "1. List files under the target path.",
                "2. Save a report artifact.",
            ]
        )

        from skill_normalization import normalize_skill_markdown

        draft = normalize_skill_markdown(markdown)

        self.assertEqual(draft["template_family"], "file_inspection_report")
        self.assertEqual(draft["policy_class"], "safe_read")
        self.assertEqual(draft["candidate_tools"], ["list_files", "save_artifact"])
```

- [ ] **Step 2: Run the targeted test to verify it fails**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System
python -m unittest ragenius_builder.flask_scaffold.tests.test_skill_management.SkillManagementTests.test_normalize_safe_read_skill_builds_file_inspection_draft
```

Expected:

```text
ModuleNotFoundError: No module named 'skill_normalization'
```

- [ ] **Step 3: Create the normalization module using the existing `storage.py` frontmatter parser**

```python
from __future__ import annotations

from typing import Any, Dict

from storage import DatabaseStore


SAFE_TEMPLATE_TOOL_MAP = {
    "file_inspection_report": ["list_files", "save_artifact"],
    "retrieval_report": ["retrieve_documents", "save_artifact"],
    "metadata_search_report": ["search_metadata", "save_artifact"],
}


def normalize_skill_markdown(markdown: str) -> Dict[str, Any]:
    manifest = DatabaseStore._normalize_skill_manifest(
        DatabaseStore._parse_skill_manifest(markdown)
    )
    lowered = markdown.lower()

    if "list files" in lowered or "inspect a workspace path" in lowered:
        template_family = "file_inspection_report"
    elif "retrieve" in lowered and "documents" in lowered:
        template_family = "retrieval_report"
    elif "metadata" in lowered:
        template_family = "metadata_search_report"
    else:
        template_family = "unsupported"

    candidate_tools = SAFE_TEMPLATE_TOOL_MAP.get(template_family, [])
    policy_class = "safe_read" if candidate_tools else "unsupported"
    return {
        "name": str(manifest.get("name", "")).strip(),
        "description": str(manifest.get("description", "")).strip(),
        "template_family": template_family,
        "candidate_tools": candidate_tools,
        "policy_class": policy_class,
        "confidence": 0.95 if candidate_tools else 0.0,
    }
```

- [ ] **Step 4: Run the targeted test to verify it passes**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System
python -m unittest ragenius_builder.flask_scaffold.tests.test_skill_management.SkillManagementTests.test_normalize_safe_read_skill_builds_file_inspection_draft
```

Expected:

```text
OK
```

- [ ] **Step 5: Commit**

```bash
git add ragenius_builder/flask_scaffold/skill_normalization.py ragenius_builder/flask_scaffold/tests/test_skill_management.py
git commit -m "feat: add builder skill normalization classifier"
```

### Task 2: Extend Builder normalization to synthesize explicit Phase 1 contracts

**Files:**
- Modify: `ragenius_builder/flask_scaffold/skill_normalization.py`
- Modify: `ragenius_builder/flask_scaffold/tests/test_skill_management.py`

- [ ] **Step 1: Write the failing finalized-contract test in `SkillManagementTests`**

```python
    def test_normalize_safe_read_skill_generates_finalized_contract(self) -> None:
        markdown = "\n".join(
            [
                "---",
                "name: retrieval-summary",
                "description: Retrieve relevant app documents and save a summary artifact.",
                "---",
                "",
                "## Inputs",
                "- query",
            ]
        )

        from skill_normalization import normalize_skill_markdown

        draft = normalize_skill_markdown(markdown)

        self.assertTrue(draft["auto_finalize"])
        self.assertEqual(draft["required_tools"], ["retrieve_documents", "save_artifact"])
        self.assertEqual(
            draft["workflow_definition"]["steps"][0]["toolId"],
            "retrieve_documents",
        )
        self.assertEqual(draft["input_schema"]["required"], ["query"])
```

- [ ] **Step 2: Run the targeted test to verify it fails**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System
python -m unittest ragenius_builder.flask_scaffold.tests.test_skill_management.SkillManagementTests.test_normalize_safe_read_skill_generates_finalized_contract
```

Expected:

```text
KeyError: 'auto_finalize'
```

- [ ] **Step 3: Add input-schema, output-schema, workflow, permissions, and auto-finalization synthesis**

```python
def _input_schema_for(template_family: str) -> Dict[str, Any]:
    if template_family == "retrieval_report":
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "top_k": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                    "default": 5,
                },
            },
            "required": ["query"],
        }
    return {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    }


def _output_schema_for() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "artifact_id": {"type": "string"},
        },
        "required": ["artifact_id"],
    }


def _workflow_for(template_family: str) -> Dict[str, Any]:
    if template_family == "retrieval_report":
        return {
            "steps": [
                {
                    "id": "retrieve_documents",
                    "type": "tool_call",
                    "toolId": "retrieve_documents",
                    "inputMapping": {
                        "query": "$.input.query",
                        "top_k": "$.input.top_k",
                    },
                    "outputMapping": {"items": "$.output.items"},
                    "on": {"success": "save_report"},
                },
                {
                    "id": "save_report",
                    "type": "tool_call",
                    "toolId": "save_artifact",
                    "inputMapping": {
                        "artifact_type": "retrieval_report",
                        "name": "retrieval-summary",
                        "content": "$.steps.retrieve_documents.output.items",
                    },
                    "outputMapping": {"artifact_id": "$.output.artifact_id"},
                    "on": {"success": "finish"},
                },
                {"id": "finish", "type": "end"},
            ]
        }

    return {
        "steps": [
            {
                "id": "list_files",
                "type": "tool_call",
                "toolId": "list_files",
                "inputMapping": {"path": "$.input.path"},
                "outputMapping": {"entries": "$.output.entries"},
                "on": {"success": "save_report"},
            },
            {
                "id": "save_report",
                "type": "tool_call",
                "toolId": "save_artifact",
                "inputMapping": {
                    "artifact_type": "file_inventory",
                    "name": "file-inventory",
                    "content": "$.steps.list_files.output.entries",
                },
                "outputMapping": {"artifact_id": "$.output.artifact_id"},
                "on": {"success": "finish"},
            },
            {"id": "finish", "type": "end"},
        ]
    }
```

```python
    required_tools = candidate_tools
    auto_finalize = policy_class == "safe_read" and template_family != "unsupported"
    required_permissions = (
        ["filesystem.read", "artifact.write"]
        if template_family == "file_inspection_report"
        else ["rag.read", "artifact.write"]
    )
    return {
        "name": str(manifest.get("name", "")).strip(),
        "description": str(manifest.get("description", "")).strip(),
        "template_family": template_family,
        "candidate_tools": candidate_tools,
        "required_tools": required_tools,
        "required_permissions": required_permissions if auto_finalize else [],
        "input_schema": _input_schema_for(template_family) if auto_finalize else {},
        "output_schema": _output_schema_for() if auto_finalize else {},
        "workflow_definition": _workflow_for(template_family) if auto_finalize else {},
        "policy_class": policy_class,
        "confidence": 0.95 if candidate_tools else 0.0,
        "auto_finalize": auto_finalize,
    }
```

- [ ] **Step 4: Run the Builder normalization tests**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System
python -m unittest ragenius_builder.flask_scaffold.tests.test_skill_management.SkillManagementTests.test_normalize_safe_read_skill_builds_file_inspection_draft ragenius_builder.flask_scaffold.tests.test_skill_management.SkillManagementTests.test_normalize_safe_read_skill_generates_finalized_contract
```

Expected:

```text
OK
```

- [ ] **Step 5: Commit**

```bash
git add ragenius_builder/flask_scaffold/skill_normalization.py ragenius_builder/flask_scaffold/tests/test_skill_management.py
git commit -m "feat: synthesize phase 1 builder skill contracts"
```

### Task 3: Persist normalized contract metadata through Builder import and publish

**Files:**
- Modify: `ragenius_builder/flask_scaffold/storage.py`
- Modify: `ragenius_builder/flask_scaffold/app.py`
- Modify: `ragenius_builder/flask_scaffold/tests/test_skill_management.py`

- [ ] **Step 1: Write the failing persisted-contract test in `SkillManagementTests`**

```python
    def test_import_skill_package_stores_normalized_contract_metadata(self) -> None:
        src = self._tmpdir / "safe_skill_src"
        src.mkdir(parents=True, exist_ok=True)
        (src / "SKILL.md").write_text(
            "\n".join(
                [
                    "---",
                    "name: file-inventory",
                    "description: Inspect a workspace path and save a summary report.",
                    "---",
                    "",
                    "# File Inventory",
                ]
            ),
            encoding="utf-8",
        )
        archive_path = self._tmpdir / "file_inventory.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.write(src / "SKILL.md", "SKILL.md")

        store = DatabaseStore(
            ":memory:",
            storage_root=self._tmpdir / "builder_storage",
            seed_data=False,
        )
        try:
            imported = store.import_skill_package(
                archive_path=archive_path,
                storage_root=self._tmpdir / "managed_skills",
                scope="managed",
                import_source="upload",
            )
            published = store.publish_skill_version(imported["version"]["id"])
            payload = store.get_published_skill_definition(
                skill_id=imported["skill"]["id"],
                version=published["version"],
            )
        finally:
            store.close()

        self.assertEqual(payload["required_tools"], ["list_files", "save_artifact"])
        self.assertEqual(payload["workflow_definition"]["steps"][0]["toolId"], "list_files")
```

- [ ] **Step 2: Run the targeted test to verify it fails**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System
python -m unittest ragenius_builder.flask_scaffold.tests.test_skill_management.SkillManagementTests.test_import_skill_package_stores_normalized_contract_metadata
```

Expected:

```text
FAIL: [] != ['list_files', 'save_artifact']
```

- [ ] **Step 3: Invoke normalization during skill import and merge the generated metadata into stored skill version metadata**

```python
from skill_normalization import normalize_skill_markdown
```

```python
markdown = skill_md_path.read_text(encoding="utf-8")
manifest = self._normalize_skill_manifest(self._parse_skill_manifest(markdown))
normalized_contract = normalize_skill_markdown(markdown)

metadata = {
    "description": manifest.get("description", ""),
    "required_tools": normalized_contract.get(
        "required_tools",
        manifest.get("required_tools", []),
    ),
    "required_permissions": normalized_contract.get(
        "required_permissions",
        manifest.get("required_permissions", []),
    ),
    "workflow_definition": normalized_contract.get("workflow_definition", {}),
    "input_schema": normalized_contract.get("input_schema", {}),
    "output_schema": normalized_contract.get("output_schema", {}),
    "policy_class": normalized_contract.get("policy_class", "unsupported"),
    "auto_finalize": bool(normalized_contract.get("auto_finalize", False)),
}
```

```python
state = "draft"
if not metadata["auto_finalize"] and not manifest.get("required_tools"):
    state = "review"
```

- [ ] **Step 4: Surface normalized policy in the skill detail flow without changing core Builder routing**

```python
published = store.get_published_skill_definition(skill_id=skill_id)
normalized_policy = (published or {}).get("metadata", {}).get("policy_class")
```

- [ ] **Step 5: Run the full Builder skill management suite**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System
python -m unittest ragenius_builder.flask_scaffold.tests.test_skill_management
```

Expected:

```text
OK
```

- [ ] **Step 6: Commit**

```bash
git add ragenius_builder/flask_scaffold/storage.py ragenius_builder/flask_scaffold/app.py ragenius_builder/flask_scaffold/tests/test_skill_management.py
git commit -m "feat: persist normalized builder skill contracts"
```

### Task 4: Register Phase 1 safe core tools in the execution subsystem

**Files:**
- Modify: `ragenius_execution_subsystem/src/core/tools/tool-registry.ts`
- Modify: `ragenius_execution_subsystem/tests/tools/tool-engine.test.ts`

- [ ] **Step 1: Write the failing registry test using Node `assert`**

```ts
it("registers phase 1 safe core tools", () => {
  const registry = new ToolRegistry();

  assert.equal(registry.get("read_file").id, "read_file");
  assert.equal(registry.get("list_files").id, "list_files");
  assert.equal(registry.get("retrieve_documents").id, "retrieve_documents");
  assert.equal(registry.get("search_metadata").id, "search_metadata");
  assert.equal(registry.get("save_artifact").id, "save_artifact");
  assert.equal(registry.get("load_artifact").id, "load_artifact");
});
```

- [ ] **Step 2: Run the targeted test to verify it fails**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- tool-engine.test.ts
```

Expected:

```text
TOOL_NOT_FOUND
```

- [ ] **Step 3: Register the new tools using the current `ToolDefinition` contract**

```ts
{
  id: "read_file",
  name: "Read File",
  providerType: "local",
  inputSchema: z.object({
    path: z.string().min(1),
    encoding: z.string().optional(),
    max_bytes: z.number().int().positive().max(1_000_000).optional(),
  }),
  outputSchema: z.object({
    path: z.string(),
    content: z.string(),
    truncated: z.boolean(),
    size_bytes: z.number().int().nonnegative(),
  }),
  permissionScopes: ["filesystem.read"],
  timeoutMs: 2_000,
  sideEffecting: false,
  enabled: true,
  metadata: { safePhase: 1, policyClass: "safe_read" },
},
{
  id: "save_artifact",
  name: "Save Artifact",
  providerType: "local",
  inputSchema: z.object({
    artifact_type: z.string().min(1),
    name: z.string().min(1),
    content: z.unknown(),
    format: z.string().optional(),
  }),
  outputSchema: z.object({
    artifact_id: z.string(),
    path: z.string(),
    artifact_type: z.string(),
  }),
  permissionScopes: ["artifact.write"],
  timeoutMs: 2_000,
  sideEffecting: false,
  enabled: true,
  metadata: { safePhase: 1, policyClass: "artifact_safe" },
}
```

- [ ] **Step 4: Run the registry test**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- tool-engine.test.ts
```

Expected:

```text
PASS
```

- [ ] **Step 5: Commit**

```bash
git add ragenius_execution_subsystem/src/core/tools/tool-registry.ts ragenius_execution_subsystem/tests/tools/tool-engine.test.ts
git commit -m "feat: register phase 1 safe core tools"
```

### Task 5: Replace the local provider placeholder with a concrete safe file/artifact provider

**Files:**
- Create: `ragenius_execution_subsystem/src/core/tools/providers/file-policy.ts`
- Create: `ragenius_execution_subsystem/src/core/tools/providers/artifact-store.ts`
- Modify: `ragenius_execution_subsystem/src/core/tools/providers/local-tool-provider.ts`
- Modify: `ragenius_execution_subsystem/src/config/env.ts`
- Modify: `ragenius_execution_subsystem/src/config/provider-config.ts`
- Modify: `ragenius_execution_subsystem/src/config/runtime-config.ts`
- Modify: `ragenius_execution_subsystem/tests/config/runtime-config.test.ts`
- Create: `ragenius_execution_subsystem/tests/tools/file-policy.test.ts`
- Create: `ragenius_execution_subsystem/tests/tools/local-tool-provider.test.ts`

- [ ] **Step 1: Write the failing file-policy test**

```ts
it("rejects reads outside configured allowed roots", () => {
  const policy = new FilePolicy({
    allowedRoots: ["D:/GitHub/Codex-RAGenius-System/docs"],
    maxReadBytes: 4096,
  });

  assert.throws(
    () => policy.resolveReadablePath("C:/Windows/System32/drivers/etc/hosts"),
    (error: unknown) =>
      error instanceof AppError &&
      error.code === "FILESYSTEM_PATH_NOT_ALLOWED"
  );
});
```

- [ ] **Step 2: Write the failing local-provider test against the actual `execute(tool, input)` contract**

```ts
it("reads a text file within an allowed root", async () => {
  const provider = new PhaseOneLocalToolProvider(
    new FilePolicy({
      allowedRoots: ["D:/GitHub/Codex-RAGenius-System"],
      maxReadBytes: 4096,
    }),
    new ArtifactStore("D:/GitHub/Codex-RAGenius-System/outputs/test-artifacts")
  );

  const result = await provider.execute(
    {
      id: "read_file",
      name: "Read File",
      providerType: "local",
      inputSchema: z.object({ path: z.string() }),
      outputSchema: z.object({
        path: z.string(),
        content: z.string(),
        truncated: z.boolean(),
        size_bytes: z.number(),
      }),
      permissionScopes: ["filesystem.read"],
      sideEffecting: false,
    },
    {
      path: "D:/GitHub/Codex-RAGenius-System/README.md",
    }
  );

  assert.match(result.path, /README\.md$/);
  assert.equal(typeof result.content, "string");
});
```

- [ ] **Step 3: Run the targeted tests to verify they fail**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- file-policy.test.ts local-tool-provider.test.ts runtime-config.test.ts
```

Expected:

```text
Cannot find module './file-policy'
```

- [ ] **Step 4: Implement `FilePolicy`, `ArtifactStore`, and a concrete `PhaseOneLocalToolProvider`**

```ts
export class FilePolicy {
  constructor(
    private readonly config: { allowedRoots: string[]; maxReadBytes: number }
  ) {}

  resolveReadablePath(inputPath: string): string {
    const resolved = path.resolve(inputPath);
    const allowed = this.config.allowedRoots.some((root) =>
      resolved.startsWith(path.resolve(root))
    );
    if (!allowed) {
      throw new AppError({
        code: "FILESYSTEM_PATH_NOT_ALLOWED",
        message: "File path is outside allowed roots.",
        errorClass: "permission",
        httpStatus: 403,
        recoverable: true,
      });
    }
    return resolved;
  }
}
```

```ts
export class PhaseOneLocalToolProvider {
  readonly providerType = "local" as const;

  constructor(
    private readonly filePolicy: FilePolicy,
    private readonly artifactStore: ArtifactStore
  ) {}

  async execute(
    tool: ToolDefinition,
    input: Record<string, unknown>
  ): Promise<Record<string, unknown>> {
    if (tool.id === "read_file") {
      const resolved = this.filePolicy.resolveReadablePath(String(input.path ?? ""));
      const raw = await fs.readFile(resolved, "utf-8");
      const maxBytes = Number(input.max_bytes ?? 65536);
      const content = raw.slice(0, maxBytes);
      return {
        path: resolved,
        content,
        truncated: raw.length > content.length,
        size_bytes: Buffer.byteLength(raw, "utf-8"),
      };
    }

    throw new AppError({
      code: "LOCAL_TOOL_NOT_IMPLEMENTED",
      message: "Local tool is not implemented.",
      errorClass: "tool",
      httpStatus: 502,
      details: { tool_id: tool.id },
      recoverable: false,
    });
  }
}
```

- [ ] **Step 5: Add env/runtime config entries**

```ts
FILESYSTEM_ALLOWED_ROOTS: z.string().default(""),
FILESYSTEM_MAX_READ_BYTES: z.coerce.number().int().positive().default(65536),
ARTIFACT_STORAGE_ROOT: z.string().default("storage/artifacts"),
```

```ts
fileTools: {
  allowedRoots: splitCsv(env.FILESYSTEM_ALLOWED_ROOTS),
  maxReadBytes: env.FILESYSTEM_MAX_READ_BYTES,
},
artifactStore: {
  rootDir: env.ARTIFACT_STORAGE_ROOT,
},
```

- [ ] **Step 6: Run the targeted tests**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- file-policy.test.ts local-tool-provider.test.ts runtime-config.test.ts
```

Expected:

```text
PASS
```

- [ ] **Step 7: Commit**

```bash
git add ragenius_execution_subsystem/src/core/tools/providers/file-policy.ts ragenius_execution_subsystem/src/core/tools/providers/artifact-store.ts ragenius_execution_subsystem/src/core/tools/providers/local-tool-provider.ts ragenius_execution_subsystem/src/config/env.ts ragenius_execution_subsystem/src/config/provider-config.ts ragenius_execution_subsystem/src/config/runtime-config.ts ragenius_execution_subsystem/tests/config/runtime-config.test.ts ragenius_execution_subsystem/tests/tools/file-policy.test.ts ragenius_execution_subsystem/tests/tools/local-tool-provider.test.ts
git commit -m "feat: add phase 1 local file and artifact providers"
```

### Task 6: Extend the current rag adapter provider for retrieval and metadata search

**Files:**
- Modify: `ragenius_execution_subsystem/src/core/tools/providers/rag-adapter-provider.ts`
- Modify: `ragenius_execution_subsystem/tests/tools/rag-adapter.test.ts`

- [ ] **Step 1: Write the failing metadata-search adapter test**

```ts
it("returns metadata-only rows for search_metadata", async () => {
  const provider = new MockRagAdapterProvider();
  const result = await provider.execute(
    {
      id: "search_metadata",
      name: "Search Metadata",
      providerType: "rag_adapter",
      inputSchema: z.object({ query: z.string() }),
      outputSchema: z.object({
        items: z.array(
          z.object({
            document_id: z.string(),
            title: z.string(),
            tags: z.array(z.string()),
          })
        ),
      }),
      permissionScopes: ["rag.read"],
      sideEffecting: false,
    },
    {
      query: "guide",
      limit: 5,
    }
  );

  assert.equal(Array.isArray(result.items), true);
  assert.equal(result.items[0]?.document_id, "doc-metadata-1");
});
```

- [ ] **Step 2: Run the targeted test to verify it fails**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- rag-adapter.test.ts
```

Expected:

```text
RAG_TOOL_NOT_IMPLEMENTED
```

- [ ] **Step 3: Extend the current mock/provider without changing its `execute(tool, input)` signature**

```ts
if (tool.id === "retrieve_documents" || tool.id === "rag_retrieval_tool") {
  return {
    items: [
      {
        title: "RAG Overview",
        content: `Context for query: ${String(input.query)}`,
        metadata: {
          topK: input.top_k ?? input.topK ?? 3,
        },
      },
    ],
  };
}

if (tool.id === "search_metadata") {
  return {
    items: [
      {
        document_id: "doc-metadata-1",
        title: `Metadata result for ${String(input.query)}`,
        tags: [],
      },
    ],
  };
}
```

- [ ] **Step 4: Run the rag adapter tests**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- rag-adapter.test.ts
```

Expected:

```text
PASS
```

- [ ] **Step 5: Commit**

```bash
git add ragenius_execution_subsystem/src/core/tools/providers/rag-adapter-provider.ts ragenius_execution_subsystem/tests/tools/rag-adapter.test.ts
git commit -m "feat: add phase 1 retrieval and metadata tools"
```

### Task 7: Wire providers into `ToolEngine` and verify a normalized sample skill end to end

**Files:**
- Modify: `ragenius_execution_subsystem/src/core/tools/tool-engine.ts`
- Modify: `ragenius_execution_subsystem/src/api/routes/health.routes.ts`
- Modify: `ragenius_execution_subsystem/src/core/skills/sample-skills.ts`
- Modify: `ragenius_execution_subsystem/tests/execution/execute-skill.test.ts`

- [ ] **Step 1: Write the failing file-inventory execution test using `ExecutionEngine`**

```ts
it("executes a normalized file inventory contract", async () => {
  const engine = new ExecutionEngine();

  const result = await engine.execute({
    request_type: "execute_skill",
    app_id: "app_file_inventory",
    session_id: "session-1",
    skill_id: "file_inventory",
    input: {
      path: "D:/GitHub/Codex-RAGenius-System/docs",
    },
    execution_options: {
      dry_run: false,
      require_confirmation: false,
    },
  });

  assert.equal(result.status, "completed");
  assert.equal(result.result_type, "json");
  assert.ok((result.result as { artifact_id?: string }).artifact_id);
});
```

- [ ] **Step 2: Run the targeted test to verify it fails**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- execute-skill.test.ts
```

Expected:

```text
SKILL_NOT_FOUND or TOOL_PROVIDER_NOT_FOUND
```

- [ ] **Step 3: Add the sample skill and wire the concrete local provider into `ToolEngine`**

```ts
{
  id: "file_inventory",
  name: "File Inventory",
  version: "1.0.0",
  description: "Inspect a path and save an inventory artifact.",
  inputSchema: z.object({
    path: z.string().min(1),
  }),
  outputSchema: z.object({
    artifact_id: z.string(),
  }),
  requiredTools: ["list_files", "save_artifact"],
  requiredPermissions: ["filesystem.read", "artifact.write"],
  workflowDefinition: {
    steps: [
      {
        id: "list_files",
        type: "tool_call",
        toolId: "list_files",
        inputMapping: { path: "$.input.path" },
        outputMapping: { entries: "$.output.entries" },
        on: { success: "save_report" },
      },
      {
        id: "save_report",
        type: "tool_call",
        toolId: "save_artifact",
        inputMapping: {
          artifact_type: "file_inventory",
          name: "inventory-report",
          content: "$.steps.list_files.output.entries",
        },
        outputMapping: { artifact_id: "$.output.artifact_id" },
        on: { success: "finish" },
      },
      { id: "finish", type: "end" },
    ],
  },
  enabled: true,
  resultType: "json",
}
```

```ts
this.providers = {
  api: new MockApiToolProvider(buildProviderRuntimeConfig(getEnv())),
  mcp: new MockMcpToolProvider(),
  rag_adapter: new MockRagAdapterProvider(),
  local: new PhaseOneLocalToolProvider(
    new FilePolicy(buildRuntimeConfig(getEnv()).fileTools),
    new ArtifactStore(buildRuntimeConfig(getEnv()).artifactStore.rootDir)
  ),
  ...providers,
};
```

- [ ] **Step 4: Expose non-secret readiness details for file-tool and artifact-store configuration**

```ts
assert.equal(response.json().checks.runtime_config.fileTools.configured, true);
assert.equal(response.json().checks.runtime_config.artifactStore.configured, true);
```

- [ ] **Step 5: Run the end-to-end tests**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- execute-skill.test.ts tool-engine.test.ts
```

Expected:

```text
PASS
```

- [ ] **Step 6: Commit**

```bash
git add ragenius_execution_subsystem/src/core/tools/tool-engine.ts ragenius_execution_subsystem/src/api/routes/health.routes.ts ragenius_execution_subsystem/src/core/skills/sample-skills.ts ragenius_execution_subsystem/tests/execution/execute-skill.test.ts
git commit -m "feat: execute normalized phase 1 sample skills"
```

### Task 8: Document and verify the Phase 1 operator workflow

**Files:**
- Modify: `ragenius_execution_subsystem/README.md`

- [ ] **Step 1: Document the safe Phase 1 tools and runtime env vars**

```md
## Phase 1 Safe Core Tools

The execution subsystem supports these Builder-normalized safe tools:

- `read_file`
- `list_files`
- `retrieve_documents`
- `search_metadata`
- `save_artifact`
- `load_artifact`

### Required environment variables

```env
FILESYSTEM_ALLOWED_ROOTS=D:/GitHub/Codex-RAGenius-System/docs,D:/GitHub/Codex-RAGenius-System/ragenius_builder/flask_scaffold/instructions
FILESYSTEM_MAX_READ_BYTES=65536
ARTIFACT_STORAGE_ROOT=storage/artifacts
```
```

- [ ] **Step 2: Run the full targeted verification suite**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System
python -m unittest ragenius_builder.flask_scaffold.tests.test_skill_management

cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- runtime-config.test.ts file-policy.test.ts local-tool-provider.test.ts rag-adapter.test.ts tool-engine.test.ts execute-skill.test.ts
npx prisma validate
```

Expected:

```text
All targeted Builder and execution-subsystem tests pass.
Prisma schema validation passes.
```

- [ ] **Step 3: Commit**

```bash
git add ragenius_execution_subsystem/README.md
git commit -m "docs: document phase 1 safe tool workflow"
```

## Self-Review

### Spec coverage

- Builder normalization pipeline: Tasks 1-3
- Auto-finalization policy and explicit contract synthesis: Tasks 2-3
- Safe core runtime tool registry: Task 4
- Local file/artifact policy enforcement: Task 5
- Retrieval and metadata support without moving retrieval logic: Task 6
- End-to-end execution of a normalized contract: Task 7
- Operator/runtime documentation: Task 8

No Phase 1 spec area is left without a task.

### Placeholder scan

- No `TODO`, `TBD`, or "implement later" placeholders remain.
- Each code step contains concrete code.
- Each verification step contains exact commands and expected outcomes.

### Type consistency

- Builder contract fields consistently use:
  - `required_tools`
  - `required_permissions`
  - `input_schema`
  - `output_schema`
  - `workflow_definition`
- Runtime skill fields consistently use:
  - `requiredTools`
  - `requiredPermissions`
  - `inputSchema`
  - `outputSchema`
  - `workflowDefinition`
- Runtime provider interfaces consistently use:
  - `execute(tool, input)`

