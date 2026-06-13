# Gmail MCP Phase 3.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one real Gmail MCP integration path to `ragenius_execution_subsystem` over remote HTTP with OAuth2 Bearer auth, limited to read-only discovery and execution first, while keeping Builder-generated Gmail contracts explicit and `review_required`.

**Architecture:** `ragenius_execution_subsystem` adds a real HTTP MCP client seam beneath the existing MCP provider boundary, configured through `MCP_SERVERS_JSON` and `GMAIL_MCP_ACCESS_TOKEN`. Gmail discovery remains explicit through `/v1/tools/discover/mcp`, but discovered tools are filtered through a local allowlist before registration. Builder extends Phase 3 normalization with a narrow Gmail read-only template family that produces explicit draft contracts but never auto-finalizes them. The first end-to-end skill uses `service_call` to invoke a discovered Gmail read tool.

**Tech Stack:** Flask/Python (`ragenius_builder`), TypeScript/Fastify/Prisma (`ragenius_execution_subsystem`), Zod, HTTP fetch, OAuth2 Bearer auth, MCP lifecycle (`initialize`, `notifications/initialized`, `tools/list`, `tools/call`).

---

## File Structure

### Builder

- Modify: `ragenius_builder/flask_scaffold/skill_normalization.py`
  - add `gmail_read_operation` inference and review-required draft synthesis
- Modify: `ragenius_builder/flask_scaffold/tests/test_skill_management.py`
  - add Gmail read-only normalization coverage

### Execution subsystem

- Create: `ragenius_execution_subsystem/src/core/tools/providers/mcp-http-client.ts`
  - real MCP HTTP lifecycle client for `initialize`, `tools/list`, and `tools/call`
- Modify: `ragenius_execution_subsystem/src/core/tools/providers/mcp-tool-provider.ts`
  - replace mock execution path with real HTTP MCP invocation for configured HTTP providers
- Modify: `ragenius_execution_subsystem/src/config/mcp-config.ts`
  - extend runtime config with optional allowlist metadata for HTTP providers
- Modify: `ragenius_execution_subsystem/src/config/provider-config.ts`
  - add Gmail-specific MCP allowlist builder if kept here
- Modify: `ragenius_execution_subsystem/src/config/runtime-config.ts`
  - expose Gmail/MCP readiness diagnostics
- Modify: `ragenius_execution_subsystem/src/core/tools/tool-registry.ts`
  - support registering discovered Gmail tools with explicit metadata
- Modify: `ragenius_execution_subsystem/src/core/skills/sample-skills.ts`
  - add one Gmail read-only sample skill
- Modify: `ragenius_execution_subsystem/src/app.ts`
  - wire real MCP provider config into app services if needed

### Tests

- Create: `ragenius_execution_subsystem/tests/tools/mcp-http-client.test.ts`
  - lifecycle, auth header, session header, discovery, and call coverage
- Modify: `ragenius_execution_subsystem/tests/tools/mcp-tool-provider.test.ts`
  - real discovery mapping, allowlist filtering, and execution coverage
- Modify: `ragenius_execution_subsystem/tests/config/runtime-config.test.ts`
  - Gmail/MCP diagnostics coverage
- Modify: `ragenius_execution_subsystem/tests/execution/execute-skill.test.ts`
  - end-to-end Gmail read-only skill execution coverage
- Modify: `ragenius_execution_subsystem/tests/execution/permission-block.test.ts`
  - provider-not-configured / auth-missing failure coverage if routed here

### Docs

- Modify: `ragenius_execution_subsystem/README.md`
  - document Gmail MCP config, auth env, allowlist behavior, and read-only first scope

---

## Task 1: Extend Builder normalization for Gmail read-only draft contracts

**Files:**
- Modify: `ragenius_builder/flask_scaffold/skill_normalization.py`
- Modify: `ragenius_builder/flask_scaffold/tests/test_skill_management.py`

- [ ] **Step 1: Write the failing Gmail normalization test**

Add a Builder test asserting a natural Gmail skill becomes a `review_required` draft:

```python
    def test_normalize_gmail_read_skill_marks_review_required(self) -> None:
        markdown = "\n".join(
            [
                "---",
                "name: gmail-message-search",
                "description: Search Gmail messages through the Gmail MCP provider.",
                "---",
                "",
                "## Inputs",
                "- query",
                "",
                "## Workflow",
                "1. Search Gmail messages.",
            ]
        )

        from skill_normalization import normalize_skill_markdown

        draft = normalize_skill_markdown(markdown)

        self.assertEqual(draft["template_family"], "gmail_read_operation")
        self.assertEqual(draft["policy_class"], "review_required")
        self.assertFalse(draft["auto_finalize"])
        self.assertIn("mcp.gmail.", draft["required_tools"][0])
```

- [ ] **Step 2: Run the targeted test to verify it fails**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System
python -m unittest ragenius_builder.flask_scaffold.tests.test_skill_management.SkillManagementTests.test_normalize_gmail_read_skill_marks_review_required
```

Expected:

```text
AssertionError: 'unsupported' != 'gmail_read_operation'
```

- [ ] **Step 3: Add Gmail read-only inference**

Implement:

- template family: `gmail_read_operation`
- known required tool placeholder: one explicit Gmail MCP read tool id, e.g. `mcp.gmail.search_messages`
- `required_permissions = ["external_api.read"]`
- explicit input schema requiring `query`
- explicit `service_call` workflow targeting the Gmail tool id
- `policy_class = "review_required"`
- `auto_finalize = False`

- [ ] **Step 4: Run the targeted test to verify it passes**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System
python -m unittest ragenius_builder.flask_scaffold.tests.test_skill_management.SkillManagementTests.test_normalize_gmail_read_skill_marks_review_required
```

Expected:

```text
OK
```

---

## Task 2: Add a real HTTP MCP client seam

**Files:**
- Create: `ragenius_execution_subsystem/src/core/tools/providers/mcp-http-client.ts`
- Create: `ragenius_execution_subsystem/tests/tools/mcp-http-client.test.ts`

- [ ] **Step 1: Write failing HTTP MCP client tests**

Add tests for:

- `initialize` sends `Authorization: Bearer <token>`
- `tools/list` returns parsed tool definitions
- `tools/call` returns normalized result payload
- optional `Mcp-Session-Id` returned by the server is reused on subsequent calls

Use mocked `fetch` responses rather than live Gmail traffic.

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- mcp-http-client.test.ts
```

Expected:

```text
Cannot find module
```

- [ ] **Step 3: Implement the HTTP MCP lifecycle client**

Implement a small client with:

- `initialize()`
- `notifyInitialized()`
- `listTools()`
- `callTool(name, arguments)`

Rules:

- include `Authorization: Bearer ...` when `authToken` is configured
- use JSON-RPC request bodies
- preserve server session header if present
- surface protocol and transport failures as structured runtime errors

- [ ] **Step 4: Run the targeted tests to verify they pass**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- mcp-http-client.test.ts
```

Expected:

```text
# pass
```

---

## Task 3: Upgrade the MCP provider from mock execution to real Gmail-capable discovery and calls

**Files:**
- Modify: `ragenius_execution_subsystem/src/core/tools/providers/mcp-tool-provider.ts`
- Modify: `ragenius_execution_subsystem/tests/tools/mcp-tool-provider.test.ts`

- [ ] **Step 1: Write failing provider tests for allowlisted Gmail discovery**

Cover:

- discovery maps Gmail MCP `tools/list` output into `ToolDefinition[]`
- only allowlisted Gmail read tools are returned
- execution routes `tools/call` through the real client
- missing/disabled provider fails closed

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- mcp-tool-provider.test.ts
```

Expected:

```text
AssertionError
```

- [ ] **Step 3: Implement Gmail-aware discovery and execution**

Requirements:

- use the new HTTP MCP client for `transport === "http"`
- on discovery:
  - initialize provider session
  - request `tools/list`
  - filter tool names through a local allowlist
  - map registered ids to `mcp.gmail.<tool_name>`
- on execution:
  - resolve provider id from `tool.metadata.providerId`
  - call the real MCP tool name through `tools/call`
  - normalize `structuredContent` first, then fall back to `content`

- [ ] **Step 4: Run the targeted tests to verify they pass**

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

## Task 4: Extend runtime config for Gmail provider allowlisting and readiness

**Files:**
- Modify: `ragenius_execution_subsystem/src/config/mcp-config.ts`
- Modify: `ragenius_execution_subsystem/src/config/provider-config.ts`
- Modify: `ragenius_execution_subsystem/src/config/runtime-config.ts`
- Modify: `ragenius_execution_subsystem/tests/config/runtime-config.test.ts`

- [ ] **Step 1: Write the failing runtime-config test**

Add a test asserting:

- Gmail provider can be configured from `MCP_SERVERS_JSON`
- auth token resolution works through `GMAIL_MCP_ACCESS_TOKEN`
- non-secret diagnostics report Gmail as configured

- [ ] **Step 2: Run the targeted test to verify it fails**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- runtime-config.test.ts
```

Expected:

```text
AssertionError
```

- [ ] **Step 3: Add Gmail/MCP readiness diagnostics**

Expose enough non-secret state to verify:

- provider id present
- transport is `http`
- auth token is configured
- allowlist is configured

Do not expose raw token values.

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

---

## Task 5: Add one Gmail read-only sample skill and end-to-end execution coverage

**Files:**
- Modify: `ragenius_execution_subsystem/src/core/skills/sample-skills.ts`
- Modify: `ragenius_execution_subsystem/tests/execution/execute-skill.test.ts`

- [ ] **Step 1: Write the failing end-to-end Gmail execution test**

Add a test for a sample skill such as:

- `gmail_message_search`

The test should:

1. configure the Gmail MCP provider
2. discover tools through `POST /v1/tools/discover/mcp`
3. execute the sample skill
4. assert normalized JSON results are returned

- [ ] **Step 2: Run the targeted test to verify it fails**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- execute-skill.test.ts
```

Expected:

```text
SKILL_NOT_FOUND
```

- [ ] **Step 3: Add the Gmail read-only sample skill**

Sample contract:

- `id = "gmail_message_search"`
- input: `{ query: string }`
- output: normalized message/thread search results
- required tool: `mcp.gmail.search_messages`
- required permission: `external_api.read`
- workflow: `service_call` to the discovered Gmail tool

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

## Task 6: Add auth/config failure coverage for the Gmail MCP path

**Files:**
- Modify: `ragenius_execution_subsystem/tests/execution/permission-block.test.ts`

- [ ] **Step 1: Write failing failure-path tests**

Cover:

- Gmail provider disabled or missing
- Gmail provider configured but token missing
- non-allowlisted discovered Gmail tool is not exposed through the registry

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- permission-block.test.ts
```

Expected:

```text
AssertionError
```

- [ ] **Step 3: Implement the failure-path handling**

Ensure the runtime returns structured errors such as:

- `MCP_PROVIDER_NOT_FOUND`
- `MCP_PROVIDER_AUTH_FAILED`
- `MCP_TOOL_NOT_ALLOWED`

- [ ] **Step 4: Run the targeted tests to verify they pass**

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

## Task 7: Document Gmail MCP configuration and verification flow

**Files:**
- Modify: `ragenius_execution_subsystem/README.md`

- [ ] **Step 1: Update docs**

Add:

- Gmail MCP `MCP_SERVERS_JSON` example
- `GMAIL_MCP_ACCESS_TOKEN` env usage
- read-only-first scope
- explicit note that write Gmail operations are out of scope for Phase 3.1
- discovery and execution verification flow

- [ ] **Step 2: Run final verification**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System
python -m unittest ragenius_builder.flask_scaffold.tests.test_skill_management
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npx prisma validate
npm test -- runtime-config.test.ts mcp-http-client.test.ts mcp-tool-provider.test.ts workflow-orchestrator.test.ts permission-block.test.ts execute-skill.test.ts
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

- Scope check: this plan is intentionally narrow and only covers one real Gmail read-only MCP slice.
- Boundary check: secrets remain in `ragenius_execution_subsystem`; Builder only normalizes explicit draft contracts.
- Safety check: no Gmail write operations are introduced here.
- Placeholder scan: all tasks include concrete files, tests, commands, and acceptance expectations.
