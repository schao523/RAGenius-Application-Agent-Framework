# Google Docs MCP Read-Only Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first Google Docs MCP slice as a read-only provider family for architecture validation, using the existing remote HTTP MCP seam, Builder review-required normalization model, and `service_call` workflow path.

**Architecture:** `ragenius_execution_subsystem` already supports real HTTP Gmail MCP discovery/execution. This slice reuses that transport/provider pattern for a second provider family, `gdocs`, and registers one allowlisted read tool: `search_documents`. Builder adds a `google_docs_read_operation` template family that generates explicit `review_required` contracts. Runtime executes the Docs search/list tool through the existing `service_call` seam with `external_api.read` scope.

**Tech Stack:** Flask/Python (`ragenius_builder`), TypeScript/Fastify/Prisma (`ragenius_execution_subsystem`), Zod, MCP HTTP client, OAuth2 Bearer auth, existing MCP discovery routes.

---

## File Structure

### Builder

- Modify: `ragenius_builder/flask_scaffold/skill_normalization.py`
  - add `google_docs_read_operation` inference, schema synthesis, and review-required workflow generation
- Modify: `ragenius_builder/flask_scaffold/tests/test_skill_management.py`
  - add Google Docs read-only normalization coverage

### Execution subsystem

- Modify: `ragenius_execution_subsystem/src/core/tools/providers/mcp-tool-provider.ts`
  - map `search_documents` for the `gdocs` provider as a read-only Docs MCP tool
- Modify: `ragenius_execution_subsystem/src/core/skills/sample-skills.ts`
  - add `google_docs_search`
- Modify: `ragenius_execution_subsystem/src/config/mcp-config.ts`
  - no schema redesign required; extend tests/docs to cover the `gdocs` provider and allowlist

### Tests

- Modify: `ragenius_execution_subsystem/tests/tools/mcp-tool-provider.test.ts`
  - Google Docs search discovery and execution normalization coverage
- Modify: `ragenius_execution_subsystem/tests/execution/permission-block.test.ts`
  - missing token or allowlist failure coverage for Google Docs
- Modify: `ragenius_execution_subsystem/tests/execution/execute-skill.test.ts`
  - end-to-end Google Docs search execution coverage

### Docs

- Modify: `ragenius_execution_subsystem/README.md`
  - document Google Docs MCP config and read-only scope

---

## Task 1: Extend Builder normalization for Google Docs read-only contracts

**Files:**
- Modify: `ragenius_builder/flask_scaffold/skill_normalization.py`
- Modify: `ragenius_builder/flask_scaffold/tests/test_skill_management.py`

- [ ] **Step 1: Write the failing Google Docs normalization test**

Add a Builder test asserting a natural Docs search skill becomes a `review_required` Docs read contract:

```python
    def test_normalize_google_docs_search_skill_marks_review_required(self) -> None:
        markdown = "\n".join(
            [
                "---",
                "name: google-docs-search",
                "description: Search Google Docs documents.",
                "---",
                "",
                "## Inputs",
                "- query",
                "",
                "## Workflow",
                "1. Search Google Docs documents.",
            ]
        )

        from skill_normalization import normalize_skill_markdown

        draft = normalize_skill_markdown(markdown)

        self.assertEqual(draft["template_family"], "google_docs_read_operation")
        self.assertEqual(draft["policy_class"], "review_required")
        self.assertFalse(draft["auto_finalize"])
        self.assertEqual(draft["required_tools"], ["mcp.gdocs.search_documents"])
```

- [ ] **Step 2: Run the targeted test to verify it fails**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System
python -m unittest ragenius_builder.flask_scaffold.tests.test_skill_management.SkillManagementTests.test_normalize_google_docs_search_skill_marks_review_required
```

Expected:

```text
AssertionError: 'unsupported' != 'google_docs_read_operation'
```

- [ ] **Step 3: Implement Google Docs read inference**

Add:

- template family `google_docs_read_operation`
- `required_tools = ["mcp.gdocs.search_documents"]`
- `required_permissions = ["external_api.read"]`
- input schema for `query`
- output schema for Docs search results
- `service_call` workflow targeting `mcp.gdocs.search_documents`
- `policy_class = "review_required"`
- `auto_finalize = False`

- [ ] **Step 4: Run the targeted test to verify it passes**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System
python -m unittest ragenius_builder.flask_scaffold.tests.test_skill_management.SkillManagementTests.test_normalize_google_docs_search_skill_marks_review_required
```

Expected:

```text
OK
```

---

## Task 2: Extend MCP tool mapping for Google Docs `search_documents`

**Files:**
- Modify: `ragenius_execution_subsystem/src/core/tools/providers/mcp-tool-provider.ts`
- Modify: `ragenius_execution_subsystem/tests/tools/mcp-tool-provider.test.ts`

- [ ] **Step 1: Write the failing Google Docs provider tests**

Cover:

- allowlisted `search_documents` is discovered for provider `gdocs`
- mapped tool id is `mcp.gdocs.search_documents`
- tool is marked `side_effecting = false`
- tool permission scope is `external_api.read`
- execution normalizes Docs search result payload

- [ ] **Step 2: Run the targeted test to verify it fails**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- mcp-tool-provider.test.ts
```

Expected:

```text
AssertionError
```

- [ ] **Step 3: Implement Google Docs search tool mapping**

Update the MCP provider so:

- `search_documents` is recognized for the `gdocs` provider
- permission scope maps to `external_api.read`
- Docs search result is normalized into a stable `results[]` object
- allowlist enforcement still applies

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

---

## Task 3: Add the Google Docs sample skill

**Files:**
- Modify: `ragenius_execution_subsystem/src/core/skills/sample-skills.ts`

- [ ] **Step 1: Add `google_docs_search`**

Add a sample skill with:

- `id = "google_docs_search"`
- input schema requiring:
  - `query`
- output schema containing at least:
  - `results[]`
  - each result containing `id` and `title`
- required tool:
  - `mcp.gdocs.search_documents`
- required permission:
  - `external_api.read`
- workflow:
  - `service_call` to `mcp.gdocs.search_documents`

- [ ] **Step 2: Verify the sample skill is registered**

Run a targeted test or route-based verification through the execution tests after the next task.

---

## Task 4: Add Google Docs execution and failure-path coverage

**Files:**
- Modify: `ragenius_execution_subsystem/tests/execution/permission-block.test.ts`
- Modify: `ragenius_execution_subsystem/tests/execution/execute-skill.test.ts`

- [ ] **Step 1: Add a missing-token or allowlist failure test**

Add a route test covering at least one of:

- Docs provider configured without `GOOGLE_DOCS_MCP_ACCESS_TOKEN`
- non-allowlisted Docs tool not exposed

Expected failure:

- clean MCP provider/auth or allowlist error

- [ ] **Step 2: Add the end-to-end Google Docs read-only execution test**

Add a test that:

1. configures the `gdocs` provider with `search_documents` allowlisted
2. discovers Docs tools
3. executes `google_docs_search`
4. returns `200 completed`
5. verifies normalized Docs search results

- [ ] **Step 3: Run the targeted tests to verify they pass**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- permission-block.test.ts execute-skill.test.ts
```

Expected:

```text
# pass
```

---

## Task 5: Update Google Docs MCP documentation

**Files:**
- Modify: `ragenius_execution_subsystem/README.md`

- [ ] **Step 1: Add Google Docs provider config example**

Document a config example using:

- provider id `gdocs`
- remote HTTP base URL placeholder
- `GOOGLE_DOCS_MCP_ACCESS_TOKEN`
- `allowedToolNames: ["search_documents"]`

- [ ] **Step 2: Add a read-only Google Docs section**

Document:

- this is a read-only architecture-validation slice
- only `mcp.gdocs.search_documents` is in scope
- Builder marks Docs contracts `review_required`
- Docs content-read and write flows remain out of scope

---

## Task 6: Final verification

- [ ] **Step 1: Run Builder skill management tests**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System
python -m unittest ragenius_builder.flask_scaffold.tests.test_skill_management
```

Expected:

```text
OK
```

- [ ] **Step 2: Validate Prisma schema**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npx prisma validate
```

Expected:

```text
The schema at prisma/schema.prisma is valid
```

- [ ] **Step 3: Run focused Docs MCP test coverage**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- mcp-tool-provider.test.ts permission-block.test.ts execute-skill.test.ts
```

Expected:

```text
# pass
```

- [ ] **Step 4: Sanity check residual scope**

Verify:

- Docs support is read-only
- only `search_documents` is exposed
- no Docs content read or Docs write capability was added
- Builder still marks Docs MCP contracts `review_required`

---

## Completion Criteria

The implementation is complete when:

- Builder normalizes Docs search skills into explicit `review_required` contracts
- `mcp.gdocs.search_documents` is discovered and registered through the MCP allowlist
- `google_docs_search` is available as a sample skill
- Docs search executes successfully end to end
- Docs provider failure paths are covered cleanly
- docs reflect the new Google Docs read-only slice
- all listed verification commands pass
