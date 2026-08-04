# Gmail MCP Phase 3.2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the Gmail MCP slice from read-only discovery/execution to the first safe write action, `create_draft`, using the existing review-required Builder contract model and the persisted runtime confirmation/resume lifecycle.

**Architecture:** `ragenius_execution_subsystem` already has a real HTTP MCP seam and Gmail read-only tool registration. Phase 3.2 extends the Gmail allowlist and tool mapping to include `create_draft` as a side-effecting MCP tool with `external_api.write` scope. Builder adds a `gmail_draft_operation` template family that generates explicit `review_required` contracts. Runtime executes the draft tool only after confirmation and persists the execution lifecycle through the existing execution store.

**Tech Stack:** Flask/Python (`ragenius_builder`), TypeScript/Fastify/Prisma (`ragenius_execution_subsystem`), Zod, MCP HTTP client, OAuth2 Bearer auth, existing confirmation/persistence routes.

---

## File Structure

### Builder

- Modify: `ragenius_builder/flask_scaffold/skill_normalization.py`
  - add `gmail_draft_operation` inference, schema synthesis, and review-required workflow generation
- Modify: `ragenius_builder/flask_scaffold/tests/test_skill_management.py`
  - add Gmail draft normalization coverage

### Execution subsystem

- Modify: `ragenius_execution_subsystem/src/core/tools/providers/mcp-tool-provider.ts`
  - map `create_draft` as a side-effecting Gmail MCP tool and preserve allowlist enforcement
- Modify: `ragenius_execution_subsystem/src/core/skills/sample-skills.ts`
  - add `gmail_create_draft`
- Modify: `ragenius_execution_subsystem/src/config/mcp-config.ts`
  - no schema redesign required; extend tests/docs to cover `create_draft` in allowlists

### Tests

- Modify: `ragenius_execution_subsystem/tests/tools/mcp-tool-provider.test.ts`
  - Gmail draft discovery and execution normalization coverage
- Modify: `ragenius_execution_subsystem/tests/execution/permission-block.test.ts`
  - pending-confirmation coverage for Gmail draft creation
- Modify: `ragenius_execution_subsystem/tests/execution/execute-skill.test.ts`
  - confirm/resume end-to-end Gmail draft execution coverage

### Docs

- Modify: `ragenius_execution_subsystem/README.md`
  - document Gmail draft allowlisting and confirmation-gated write behavior

---

## Task 1: Extend Builder normalization for Gmail draft contracts

**Files:**
- Modify: `ragenius_builder/flask_scaffold/skill_normalization.py`
- Modify: `ragenius_builder/flask_scaffold/tests/test_skill_management.py`

- [ ] **Step 1: Write the failing Gmail draft normalization test**

Add a Builder test asserting a natural draft skill becomes a `review_required` Gmail draft contract:

```python
    def test_normalize_gmail_draft_skill_marks_review_required(self) -> None:
        markdown = "\n".join(
            [
                "---",
                "name: gmail-create-draft",
                "description: Create a draft email in Gmail.",
                "---",
                "",
                "## Inputs",
                "- to",
                "- subject",
                "- body",
                "",
                "## Workflow",
                "1. Create a Gmail draft.",
            ]
        )

        from skill_normalization import normalize_skill_markdown

        draft = normalize_skill_markdown(markdown)

        self.assertEqual(draft["template_family"], "gmail_draft_operation")
        self.assertEqual(draft["policy_class"], "review_required")
        self.assertFalse(draft["auto_finalize"])
        self.assertEqual(draft["required_tools"], ["mcp.gmail.create_draft"])
```

- [ ] **Step 2: Run the targeted test to verify it fails**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System
python -m unittest ragenius_builder.flask_scaffold.tests.test_skill_management.SkillManagementTests.test_normalize_gmail_draft_skill_marks_review_required
```

Expected:

```text
AssertionError: 'unsupported' != 'gmail_draft_operation'
```

- [ ] **Step 3: Implement Gmail draft inference**

Add:

- template family `gmail_draft_operation`
- `required_tools = ["mcp.gmail.create_draft"]`
- `required_permissions = ["external_api.write"]`
- input schema for `to`, `subject`, `body`
- output schema for draft result metadata
- `service_call` workflow targeting `mcp.gmail.create_draft`
- `policy_class = "review_required"`
- `auto_finalize = False`

- [ ] **Step 4: Run the targeted test to verify it passes**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System
python -m unittest ragenius_builder.flask_scaffold.tests.test_skill_management.SkillManagementTests.test_normalize_gmail_draft_skill_marks_review_required
```

Expected:

```text
OK
```

---

## Task 2: Extend Gmail MCP tool mapping for `create_draft`

**Files:**
- Modify: `ragenius_execution_subsystem/src/core/tools/providers/mcp-tool-provider.ts`
- Modify: `ragenius_execution_subsystem/tests/tools/mcp-tool-provider.test.ts`

- [ ] **Step 1: Write the failing Gmail draft provider tests**

Cover:

- allowlisted `create_draft` is discovered for Gmail
- mapped tool id is `mcp.gmail.create_draft`
- tool is marked `side_effecting = true`
- tool permission scope is `external_api.write`
- execution normalizes draft result payload

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

- [ ] **Step 3: Implement Gmail draft tool mapping**

Update the MCP provider so:

- `create_draft` is recognized as side-effecting
- permission scopes map to `external_api.write`
- draft execution result is normalized into a structured object
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

## Task 3: Add the Gmail draft sample skill

**Files:**
- Modify: `ragenius_execution_subsystem/src/core/skills/sample-skills.ts`

- [ ] **Step 1: Add `gmail_create_draft`**

Add a sample skill with:

- `id = "gmail_create_draft"`
- input schema requiring:
  - `to`
  - `subject`
  - `body`
- output schema containing at least:
  - `id`
  - optional `threadId`
  - `status`
- required tool:
  - `mcp.gmail.create_draft`
- required permission:
  - `external_api.write`
- workflow:
  - `service_call` to `mcp.gmail.create_draft`

- [ ] **Step 2: Verify the sample skill is registered**

Run a targeted test or route-based verification through the existing execution tests after the next task.

---

## Task 4: Add pending-confirmation coverage for Gmail draft creation

**Files:**
- Modify: `ragenius_execution_subsystem/tests/execution/permission-block.test.ts`

- [ ] **Step 1: Write the failing pending-confirmation test**

Add a route test that:

1. configures Gmail MCP with `allowedToolNames: ["search_messages", "create_draft"]`
2. discovers Gmail tools
3. executes `gmail_create_draft`
4. asserts the response is `202 pending_confirmation`

- [ ] **Step 2: Run the targeted test to verify it fails**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- permission-block.test.ts
```

Expected:

```text
SKILL_NOT_FOUND
```

or

```text
AssertionError
```

- [ ] **Step 3: Ensure confirmation gating works through the Gmail draft path**

No new confirmation mechanism should be invented. Reuse the existing:

- permission engine `require_confirmation`
- persisted execution record
- `POST /v1/executions/:execution_id/confirm`

- [ ] **Step 4: Run the targeted test to verify it passes**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- permission-block.test.ts
```

Expected:

```text
# pass
```

---

## Task 5: Add confirmed Gmail draft execution coverage

**Files:**
- Modify: `ragenius_execution_subsystem/tests/execution/execute-skill.test.ts`

- [ ] **Step 1: Write the failing Gmail draft confirm/resume test**

Add a full route test that:

1. mocks Gmail MCP HTTP responses for:
   - `initialize`
   - `notifications/initialized`
   - `tools/list`
   - `tools/call` returning draft metadata
2. configures Gmail MCP with `create_draft` allowlisted
3. discovers tools
4. executes `gmail_create_draft`
5. receives `pending_confirmation`
6. confirms the execution
7. receives `completed`

- [ ] **Step 2: Run the targeted test to verify it fails**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- execute-skill.test.ts
```

Expected:

```text
AssertionError
```

- [ ] **Step 3: Implement any missing Gmail draft result normalization**

If needed, normalize MCP `structuredContent` into the sample skill’s output schema.

- [ ] **Step 4: Run the targeted test to verify it passes**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- execute-skill.test.ts
```

Expected:

```text
# pass
```

---

## Task 6: Document Gmail draft write scope and confirmation rules

**Files:**
- Modify: `ragenius_execution_subsystem/README.md`

- [ ] **Step 1: Update Gmail MCP docs**

Add:

- `create_draft` to the Gmail allowlist example
- explicit note that Gmail draft creation is confirmation-gated
- explicit note that send message is still out of scope

- [ ] **Step 2: Run final verification**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System
python -m unittest ragenius_builder.flask_scaffold.tests.test_skill_management
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npx prisma validate
npm test -- mcp-tool-provider.test.ts permission-block.test.ts execute-skill.test.ts
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

---

## Self-Review

- Scope check: this plan adds only Gmail draft creation, not sending.
- Safety check: the design preserves Builder review plus runtime confirmation.
- Boundary check: secrets remain in `ragenius_execution_subsystem`; Builder still publishes explicit contracts only.
- Placeholder scan: tasks include concrete files, tests, commands, and expected outcomes.
