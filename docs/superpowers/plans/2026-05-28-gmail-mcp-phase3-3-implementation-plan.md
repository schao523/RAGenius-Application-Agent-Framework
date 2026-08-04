# Gmail MCP Phase 3.3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the Gmail MCP slice from draft creation to the first controlled outbound send path, `send_draft`, using the existing review-required Builder contract model and the persisted runtime confirmation/resume lifecycle.

**Architecture:** `ragenius_execution_subsystem` already supports real HTTP Gmail MCP discovery, read-only Gmail tools, and confirmation-gated `create_draft`. Phase 3.3 extends the Gmail allowlist and tool mapping to include `send_draft` as a side-effecting MCP tool with `external_api.write` scope. Builder adds a `gmail_send_draft_operation` template family that generates explicit `review_required` contracts. Runtime executes the outbound send only after confirmation and persists the execution lifecycle through the existing execution store.

**Tech Stack:** Flask/Python (`ragenius_builder`), TypeScript/Fastify/Prisma (`ragenius_execution_subsystem`), Zod, MCP HTTP client, OAuth2 Bearer auth, existing confirmation/persistence routes.

---

## File Structure

### Builder

- Modify: `ragenius_builder/flask_scaffold/skill_normalization.py`
  - add `gmail_send_draft_operation` inference, schema synthesis, and review-required workflow generation
- Modify: `ragenius_builder/flask_scaffold/tests/test_skill_management.py`
  - add Gmail send-draft normalization coverage

### Execution subsystem

- Modify: `ragenius_execution_subsystem/src/core/tools/providers/mcp-tool-provider.ts`
  - map `send_draft` as a side-effecting Gmail MCP tool and preserve allowlist enforcement
- Modify: `ragenius_execution_subsystem/src/core/skills/sample-skills.ts`
  - add `gmail_send_draft`
- Modify: `ragenius_execution_subsystem/src/config/mcp-config.ts`
  - no schema redesign required; extend tests/docs to cover `send_draft` in allowlists

### Tests

- Modify: `ragenius_execution_subsystem/tests/tools/mcp-tool-provider.test.ts`
  - Gmail send-draft discovery and execution normalization coverage
- Modify: `ragenius_execution_subsystem/tests/execution/permission-block.test.ts`
  - pending-confirmation coverage for Gmail draft send
- Modify: `ragenius_execution_subsystem/tests/execution/execute-skill.test.ts`
  - confirm/resume end-to-end Gmail draft send coverage

### Docs

- Modify: `ragenius_execution_subsystem/README.md`
  - document Gmail send-draft allowlisting and confirmation-gated outbound behavior

---

## Task 1: Extend Builder normalization for Gmail send-draft contracts

**Files:**
- Modify: `ragenius_builder/flask_scaffold/skill_normalization.py`
- Modify: `ragenius_builder/flask_scaffold/tests/test_skill_management.py`

- [ ] **Step 1: Write the failing Gmail send-draft normalization test**

Add a Builder test asserting a natural send-draft skill becomes a `review_required` Gmail send contract:

```python
    def test_normalize_gmail_send_draft_skill_marks_review_required(self) -> None:
        markdown = "\n".join(
            [
                "---",
                "name: gmail-send-draft",
                "description: Send an existing Gmail draft.",
                "---",
                "",
                "## Inputs",
                "- draftId",
                "",
                "## Workflow",
                "1. Send the Gmail draft.",
            ]
        )

        from skill_normalization import normalize_skill_markdown

        draft = normalize_skill_markdown(markdown)

        self.assertEqual(draft["template_family"], "gmail_send_draft_operation")
        self.assertEqual(draft["policy_class"], "review_required")
        self.assertFalse(draft["auto_finalize"])
        self.assertEqual(draft["required_tools"], ["mcp.gmail.send_draft"])
```

- [ ] **Step 2: Run the targeted test to verify it fails**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System
python -m unittest ragenius_builder.flask_scaffold.tests.test_skill_management.SkillManagementTests.test_normalize_gmail_send_draft_skill_marks_review_required
```

Expected:

```text
AssertionError: 'unsupported' != 'gmail_send_draft_operation'
```

- [ ] **Step 3: Implement Gmail send-draft inference**

Add:

- template family `gmail_send_draft_operation`
- `required_tools = ["mcp.gmail.send_draft"]`
- `required_permissions = ["external_api.write"]`
- input schema for `draftId`
- output schema for sent result metadata
- `service_call` workflow targeting `mcp.gmail.send_draft`
- `policy_class = "review_required"`
- `auto_finalize = False`

- [ ] **Step 4: Run the targeted test to verify it passes**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System
python -m unittest ragenius_builder.flask_scaffold.tests.test_skill_management.SkillManagementTests.test_normalize_gmail_send_draft_skill_marks_review_required
```

Expected:

```text
OK
```

---

## Task 2: Extend Gmail MCP tool mapping for `send_draft`

**Files:**
- Modify: `ragenius_execution_subsystem/src/core/tools/providers/mcp-tool-provider.ts`
- Modify: `ragenius_execution_subsystem/tests/tools/mcp-tool-provider.test.ts`

- [ ] **Step 1: Write the failing Gmail send-draft provider tests**

Cover:

- allowlisted `send_draft` is discovered for Gmail
- mapped tool id is `mcp.gmail.send_draft`
- tool is marked `side_effecting = true`
- tool permission scope is `external_api.write`
- execution normalizes sent result payload

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

- [ ] **Step 3: Implement Gmail send-draft tool mapping**

Update the MCP provider so:

- `send_draft` is recognized as side-effecting
- permission scopes map to `external_api.write`
- send execution result is normalized into a structured object
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

## Task 3: Add the Gmail send-draft sample skill

**Files:**
- Modify: `ragenius_execution_subsystem/src/core/skills/sample-skills.ts`

- [ ] **Step 1: Add `gmail_send_draft`**

Add a sample skill with:

- `id = "gmail_send_draft"`
- input schema requiring:
  - `draftId`
- output schema containing at least:
  - `id`
  - optional `threadId`
  - `status`
- required tool:
  - `mcp.gmail.send_draft`
- required permission:
  - `external_api.write`
- workflow:
  - `service_call` to `mcp.gmail.send_draft`

- [ ] **Step 2: Verify the sample skill is registered**

Run a targeted test or route-based verification through the existing execution tests after the next task.

---

## Task 4: Add pending-confirmation coverage for Gmail draft send

**Files:**
- Modify: `ragenius_execution_subsystem/tests/execution/permission-block.test.ts`

- [ ] **Step 1: Write the failing pending-confirmation test**

Add a route test that:

1. configures Gmail MCP with `allowedToolNames: ["search_messages", "create_draft", "send_draft"]`
2. discovers Gmail tools
3. executes `gmail_send_draft`
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

- [ ] **Step 3: Ensure confirmation gating works through the Gmail send path**

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

## Task 5: Add confirm/resume end-to-end Gmail send execution coverage

**Files:**
- Modify: `ragenius_execution_subsystem/tests/execution/execute-skill.test.ts`

- [ ] **Step 1: Write the failing end-to-end Gmail send execution test**

Add a test that:

1. configures Gmail MCP with `send_draft` allowlisted
2. discovers Gmail tools
3. executes `gmail_send_draft`
4. receives `pending_confirmation`
5. confirms the execution
6. verifies completion with a normalized sent result

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

- [ ] **Step 3: Ensure the Gmail send path completes after confirmation**

Use the existing execution confirm/resume seam. The confirmed path should call:

- `mcp.gmail.send_draft`

and return a stable normalized result like:

```json
{
  "id": "sent-message-1",
  "threadId": "thread-1",
  "status": "sent"
}
```

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

## Task 6: Update Gmail send-draft documentation

**Files:**
- Modify: `ragenius_execution_subsystem/README.md`

- [ ] **Step 1: Extend the Gmail MCP allowlist example**

Update the Gmail runtime config example to include:

- `send_draft`

- [ ] **Step 2: Add a Phase 3.3 Gmail send section**

Document:

- `mcp.gmail.send_draft`
- Builder `review_required`
- runtime `external_api.write`
- `pending_confirmation` before outbound delivery
- confirm/resume completion behavior
- explicit note that direct `send_message` remains out of scope

---

## Task 7: Final verification

- [ ] **Step 1: Run Builder normalization tests**

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

- [ ] **Step 3: Run focused Gmail MCP test coverage**

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

- Gmail outbound support is limited to `send_draft`
- direct `send_message` is still not exposed
- Builder still marks Gmail send contracts `review_required`

---

## Completion Criteria

The implementation is complete when:

- Builder normalizes Gmail send-draft skills into explicit `review_required` contracts
- Gmail `send_draft` is discovered and registered through the MCP allowlist
- `gmail_send_draft` is available as a sample skill
- execution becomes `pending_confirmation` before send
- confirmed execution resumes and returns a normalized sent result
- docs reflect the new Gmail outbound slice
- all listed verification commands pass
