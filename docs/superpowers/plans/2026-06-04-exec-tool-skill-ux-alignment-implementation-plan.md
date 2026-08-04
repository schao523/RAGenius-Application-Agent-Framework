# Exec Tool/Skill UX Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate direct runtime-tool execution from real skill execution, then replace raw `@exec key=value` memorization with a guided execution composer that uses runtime schemas.

**Architecture:** Keep `@exec` as the explicit execution namespace, but split it into `@exec tool`, `@exec skill`, and `@exec status`. `ragenius_app_skeleton` should stop treating hardcoded NotebookLM wrappers as “skills” in the user-facing contract and instead resolve either real runtime skills or explicitly allowlisted runtime tools. The frontend should add a schema-driven execution composer on top of the same runtime inventories so normal users do not need to remember command syntax.

**Tech Stack:** FastAPI, Python, React, Vitest, Pytest, TypeScript/Fastify, existing runtime inventory endpoints, existing Builder/runtime skill and tool registries.

---

## File Structure

**`ragenius_app_skeleton/backend/app/exec_router.py`**
- Parse `@exec tool`, `@exec skill`, and `@exec status`.
- Keep legacy alias handling temporarily.

**`ragenius_app_skeleton/backend/app/execution_intent_service.py`**
- Split policy metadata into real runtime skills vs direct tools.
- Remove hardcoded pseudo-skill ambiguity from user-facing routing.

**`ragenius_app_skeleton/backend/app/execution_subsystem_client.py`**
- Add runtime skill/tool inventory client methods.
- Add helper calls for tool execution if separate request shaping is needed.

**`ragenius_app_skeleton/backend/app/main.py`**
- Route `@exec tool` and `@exec skill` separately.
- Validate direct-tool execution against runtime inventory.
- Add execution-composer metadata endpoints for frontend use.

**`ragenius_app_skeleton/backend/tests/test_exec_router.py`**
- Cover parser behavior for `tool`, `skill`, `status`, async mode, and legacy compatibility.

**`ragenius_app_skeleton/backend/tests/test_execution_intent_service.py`**
- Cover policy classification for direct tools vs real skills.

**`ragenius_app_skeleton/backend/tests/test_chat_exec_routing.py`**
- Cover end-to-end app routing for `@exec tool`, `@exec skill`, and runtime mismatch failures.

**`ragenius_execution_subsystem/src/api/routes/tools.routes.ts`**
- Extend tool inventory for `exec_capable`, friendly label, argument schema, risk class.
- Add skill inventory endpoint for real runtime skills.

**`ragenius_execution_subsystem/src/core/skills/skill-registry.ts`**
- Surface skill inventory metadata for runtime API.

**`ragenius_execution_subsystem/tests/execution/execute-skill.test.ts`**
- Verify inventory endpoints and metadata shape.

**`ragenius_app_skeleton/frontend/src/App.jsx`**
- Add execution composer state, launchers, and submit flow.
- Keep raw `@exec` input path for advanced mode.

**`ragenius_app_skeleton/frontend/src/components/ExecutionComposer.jsx`**
- New guided composer for tool vs skill selection and schema-driven arguments.

**`ragenius_app_skeleton/frontend/src/components/ExecutionLaneStatusCard.jsx`**
- Add launch points into the composer and compact help text.

**`ragenius_app_skeleton/frontend/src/components/ExecutionComposer.test.jsx`**
- Test schema rendering, validation, and generated submit payloads.

**`ragenius_app_skeleton/frontend/src/App.test.jsx`**
- Test end-to-end composer behavior and legacy/raw-mode coexistence.

**`docs/2026-06-03-ragenius-content-execution-split-contract-v3.md`**
- Update routing section to reflect `@exec tool`, `@exec skill`, `@exec status`.

**`docs/superpowers/specs/` or app help markdown if desired**
- Add concise user-facing help for direct tool execution, skill execution, and composer behavior.

---

### Task 1: Split The `@exec` Command Contract

**Files:**
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\exec_router.py`
- Test: `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\tests\test_exec_router.py`

- [ ] **Step 1: Write the failing parser tests**

```python
from backend.app.exec_router import parse_exec_turn


def test_parse_exec_tool_with_adapter_tool_id():
    route = parse_exec_turn(
        '@exec tool adapter.notebooklm.generate_report '
        'notebookTitle=\"GPT Application Designer\"'
    )
    assert route.is_exec_turn is True
    assert route.command == "tool"
    assert route.tool_id == "adapter.notebooklm.generate_report"
    assert route.parsed_args["notebookTitle"] == "GPT Application Designer"


def test_parse_exec_skill_with_runtime_skill_id():
    route = parse_exec_turn('@exec skill notebooklm-video-generator notebookTitle=\"GPT Application Designer\"')
    assert route.is_exec_turn is True
    assert route.command == "skill"
    assert route.skill_id == "notebooklm-video-generator"


def test_parse_exec_status_keeps_existing_behavior():
    route = parse_exec_turn("@exec status execution_123")
    assert route.is_exec_turn is True
    assert route.command == "status"
    assert route.execution_id == "execution_123"


def test_parse_exec_legacy_wrapper_is_marked_legacy_skill():
    route = parse_exec_turn('@exec skill notebooklm_generate_video notebookTitle=\"GPT Application Designer\"')
    assert route.is_exec_turn is True
    assert route.command == "skill"
    assert route.skill_id == "notebooklm_generate_video"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest ragenius_app_skeleton/backend/tests/test_exec_router.py -q
```

Expected:
- FAIL because `ExecRouteDecision` does not yet carry `tool_id`
- FAIL because parser only supports `skill` and `status`

- [ ] **Step 3: Extend the router model and parser**

Update `ExecRouteDecision` and `parse_exec_turn()` in `exec_router.py` along these lines:

```python
class ExecRouteDecision(BaseModel):
    is_exec_turn: bool
    command: str | None = None
    execution_mode: str | None = None
    skill_id: str | None = None
    tool_id: str | None = None
    execution_id: str | None = None
    raw_args: str = ""
    parsed_args: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


if command == "tool":
    if not rest:
        return ExecRouteDecision(
            is_exec_turn=True,
            command="tool",
            execution_mode=execution_mode,
            error="Missing tool id. Use '@exec tool <tool_id> ...'.",
        )
    tool_parts = rest.split(maxsplit=1)
    tool_id = tool_parts[0]
    raw_args = tool_parts[1] if len(tool_parts) > 1 else ""
    parsed_args = _parse_key_value_args(raw_args)
    if execution_mode and "execution_mode" not in parsed_args:
        parsed_args["execution_mode"] = execution_mode
    return ExecRouteDecision(
        is_exec_turn=True,
        command="tool",
        execution_mode=execution_mode,
        tool_id=tool_id,
        raw_args=raw_args,
        parsed_args=parsed_args,
    )
```

Also update parser error messages to:

```python
"Missing execution command. Use '@exec tool <tool_id> ...', '@exec skill <skill_id> ...', or '@exec status <execution_id>'."
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
python -m pytest ragenius_app_skeleton/backend/tests/test_exec_router.py -q
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add ragenius_app_skeleton/backend/app/exec_router.py ragenius_app_skeleton/backend/tests/test_exec_router.py
git commit -m "feat: add exec tool routing syntax"
```

### Task 2: Expose Real Runtime Skill Inventory And Rich Tool Inventory

**Files:**
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\api\routes\tools.routes.ts`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\skills\skill-registry.ts`
- Test: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\tests\execution\execute-skill.test.ts`

- [ ] **Step 1: Write failing runtime inventory tests**

Add tests like:

```ts
it("returns runtime skill inventory for actual registered skills", async () => {
  const response = await app.inject({ method: "GET", url: "/v1/skills/inventory" });
  expect(response.statusCode).toBe(200);
  const payload = response.json();
  expect(payload.items.some((item: any) => item.skill_id === "notebooklm_generate_video")).toBe(true);
});

it("returns tool inventory with exec capability metadata", async () => {
  const response = await app.inject({ method: "GET", url: "/v1/tools/inventory" });
  const payload = response.json();
  const item = payload.items.find((row: any) => row.tool_id === "adapter.notebooklm.generate_video");
  expect(item.exec_capable).toBe(true);
  expect(item.exec_kind).toBe("tool");
  expect(item.input_schema).toBeDefined();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
npm test -- execute-skill.test.ts
```

Expected:
- FAIL because `/v1/skills/inventory` does not exist
- FAIL because tool inventory lacks `exec_capable` metadata

- [ ] **Step 3: Add inventory metadata**

Add a runtime skill inventory endpoint in `tools.routes.ts`:

```ts
app.get("/skills/inventory", async () => ({
  items: app.services.skillRegistry.list().map((skill) => ({
    skill_id: skill.id,
    name: skill.name,
    required_tools: skill.requiredTools,
    input_schema: skill.inputSchema ?? null,
    output_schema: skill.outputSchema ?? null,
    exec_capable: true,
    exec_kind: "skill",
  })),
}));
```

Extend `/tools/inventory` rows with:

```ts
{
  tool_id: tool.id,
  name: tool.name,
  family: tool.providerType,
  enabled: tool.enabled ?? true,
  exec_capable: Boolean(tool.enabled ?? true),
  exec_kind: "tool",
  input_schema: serializeSchema(tool.inputSchema),
  output_schema: serializeSchema(tool.outputSchema),
  risk_class: tool.sideEffecting ? "write" : "read_only",
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
npm test -- execute-skill.test.ts
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add ragenius_execution_subsystem/src/api/routes/tools.routes.ts ragenius_execution_subsystem/src/core/skills/skill-registry.ts ragenius_execution_subsystem/tests/execution/execute-skill.test.ts
git commit -m "feat: add runtime skill inventory and exec tool metadata"
```

### Task 3: Replace Hardcoded Pseudo-Skill Semantics In The App

**Files:**
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\execution_subsystem_client.py`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\execution_intent_service.py`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\main.py`
- Test: `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\tests\test_execution_intent_service.py`
- Test: `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\tests\test_chat_exec_routing.py`

- [ ] **Step 1: Write failing backend tests**

Add tests like:

```python
def test_exec_tool_uses_runtime_tool_inventory(client, monkeypatch):
    monkeypatch.setattr(
        "backend.app.main.execution_client.get_tool_inventory",
        lambda: {"items": [{"tool_id": "adapter.notebooklm.generate_report", "exec_capable": True, "enabled": True}]},
    )
    response = client.post(
        "/sessions/s1/chat",
        json={
            "app_id": "app-1",
            "user_id": "user-1",
            "user_query": '@exec tool adapter.notebooklm.generate_report notebookTitle=\"GPT Application Designer\" instructions=\"test\"',
        },
    )
    assert response.status_code == 200


def test_exec_skill_rejects_unknown_runtime_skill(client):
    response = client.post(
        "/sessions/s1/chat",
        json={
            "app_id": "app-1",
            "user_id": "user-1",
            "user_query": "@exec skill definitely_not_registered",
        },
    )
    assert response.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest ragenius_app_skeleton/backend/tests/test_execution_intent_service.py ragenius_app_skeleton/backend/tests/test_chat_exec_routing.py -q
```

Expected:
- FAIL because app still assumes hardcoded local pseudo-skill policy only

- [ ] **Step 3: Add runtime inventory client calls and routing split**

In `execution_subsystem_client.py`, add:

```python
def get_tool_inventory(self) -> dict[str, Any]:
    return self._json_request(path="/v1/tools/inventory", method="GET")


def get_skill_inventory(self) -> dict[str, Any]:
    return self._json_request(path="/v1/skills/inventory", method="GET")
```

In `main.py`, split execution handlers:

```python
if route.command == "tool":
    return _handle_exec_tool_turn(session_id=session_id, payload=payload, route=route)
if route.command == "skill":
    return _handle_exec_skill_turn(session_id=session_id, payload=payload, route=route)
```

For `_handle_exec_tool_turn`, validate against runtime tool inventory and submit through a minimal wrapper skill or direct tool execution contract already accepted by the subsystem. Keep legacy pseudo-skill ids temporarily via a compatibility map:

```python
LEGACY_EXEC_SKILL_TO_TOOL = {
    "notebooklm_generate_report": "adapter.notebooklm.generate_report",
    "notebooklm_generate_slide_deck": "adapter.notebooklm.generate_slide_deck",
    "notebooklm_generate_video": "adapter.notebooklm.generate_video",
}
```

In `execution_intent_service.py`, rename policy intent to reflect direct execution targets:

```python
def get_execution_target_policy(target_id: str, *, command_kind: str) -> dict[str, Any]:
    ...
```

Keep a compatibility adapter for existing tests while migrating callers.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
python -m pytest ragenius_app_skeleton/backend/tests/test_execution_intent_service.py ragenius_app_skeleton/backend/tests/test_chat_exec_routing.py -q
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add ragenius_app_skeleton/backend/app/execution_subsystem_client.py ragenius_app_skeleton/backend/app/execution_intent_service.py ragenius_app_skeleton/backend/app/main.py ragenius_app_skeleton/backend/tests/test_execution_intent_service.py ragenius_app_skeleton/backend/tests/test_chat_exec_routing.py
git commit -m "feat: align exec routing with runtime tools and skills"
```

### Task 4: Add A Guided Execution Composer In The Frontend

**Files:**
- Create: `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\components\ExecutionComposer.jsx`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\App.jsx`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\components\ExecutionLaneStatusCard.jsx`
- Test: `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\components\ExecutionComposer.test.jsx`
- Test: `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\App.test.jsx`

- [ ] **Step 1: Write the failing frontend tests**

Add tests like:

```jsx
it("renders tool and skill tabs from runtime inventories", async () => {
  render(<ExecutionComposer toolInventory={toolInventory} skillInventory={skillInventory} />);
  expect(screen.getByText("Tool")).toBeInTheDocument();
  expect(screen.getByText("Skill")).toBeInTheDocument();
  expect(screen.getByLabelText("Target")).toBeInTheDocument();
});

it("renders schema-driven fields and submits structured payload", async () => {
  const onSubmit = vi.fn();
  render(<ExecutionComposer toolInventory={toolInventory} skillInventory={skillInventory} onSubmit={onSubmit} />);
  await userEvent.selectOptions(screen.getByLabelText("Target"), "adapter.notebooklm.generate_video");
  await userEvent.type(screen.getByLabelText("notebookTitle"), "GPT Application Designer");
  await userEvent.type(screen.getByLabelText("instructions"), "Create a short intro video.");
  await userEvent.click(screen.getByRole("button", { name: "Run" }));
  expect(onSubmit).toHaveBeenCalledWith({
    commandKind: "tool",
    targetId: "adapter.notebooklm.generate_video",
    args: expect.objectContaining({
      notebookTitle: "GPT Application Designer",
      instructions: "Create a short intro video.",
    }),
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
npm test -- ExecutionComposer.test.jsx App.test.jsx
```

Expected:
- FAIL because component does not exist

- [ ] **Step 3: Build the composer**

Create `ExecutionComposer.jsx` with:

```jsx
export default function ExecutionComposer({
  mode,
  toolInventory,
  skillInventory,
  onSubmit,
  onClose,
}) {
  const [commandKind, setCommandKind] = useState("tool");
  const [targetId, setTargetId] = useState("");
  const [formState, setFormState] = useState({});
  const selected = useMemo(() => {
    const source = commandKind === "tool" ? toolInventory : skillInventory;
    return source.find((item) => (item.tool_id || item.skill_id) === targetId) || null;
  }, [commandKind, toolInventory, skillInventory, targetId]);
  ...
}
```

In `App.jsx`, load inventory once per app/session and open the composer from:
- a new “Run Tool or Skill” action
- existing execution-lane affordances

Submit through existing chat endpoint by generating raw `@exec` text for now:

```jsx
const command = commandKind === "tool"
  ? `@exec ${executionMode === "async" ? "async " : ""}tool ${targetId} ${serializedArgs}`
  : `@exec ${executionMode === "async" ? "async " : ""}skill ${targetId} ${serializedArgs}`;
```

This keeps backend changes minimal while delivering a non-manual UI.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
npm test -- ExecutionComposer.test.jsx App.test.jsx
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add ragenius_app_skeleton/frontend/src/components/ExecutionComposer.jsx ragenius_app_skeleton/frontend/src/components/ExecutionComposer.test.jsx ragenius_app_skeleton/frontend/src/components/ExecutionLaneStatusCard.jsx ragenius_app_skeleton/frontend/src/App.jsx ragenius_app_skeleton/frontend/src/App.test.jsx
git commit -m "feat: add guided exec composer"
```

### Task 5: Improve Discoverability, Help, And Backward Compatibility

**Files:**
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\main.py`
- Modify: `D:\GitHub\Codex-RAGenius-System\docs\2026-06-03-ragenius-content-execution-split-contract-v3.md`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\components\ExecutionLaneStatusCard.jsx`
- Test: `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\tests\test_chat_exec_routing.py`

- [ ] **Step 1: Write failing help/compatibility tests**

Add tests like:

```python
def test_legacy_notebooklm_exec_skill_returns_deprecation_hint(client):
    response = client.post(
        "/sessions/s1/chat",
        json={
            "app_id": "app-1",
            "user_id": "user-1",
            "user_query": '@exec skill notebooklm_generate_video notebookTitle=\"GPT\"',
        },
    )
    assert response.status_code in {200, 400}
    assert "tool" in response.json()["content"].lower() or "legacy" in response.json()["content"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest ragenius_app_skeleton/backend/tests/test_chat_exec_routing.py -q
```

Expected:
- FAIL because no deprecation/help hint is emitted

- [ ] **Step 3: Add help text and contract updates**

In `main.py`, add a compact helper payload for invalid/incomplete `@exec` requests:

```python
EXEC_HELP = {
    "commands": [
        "@exec tool <tool_id> key=value ...",
        "@exec skill <skill_id> key=value ...",
        "@exec status <execution_id>",
    ]
}
```

Update v3 contract sections to say:

```md
- `@exec tool ...` is for direct allowlisted runtime tool execution.
- `@exec skill ...` is for real registered runtime skills.
- legacy pseudo-skill wrappers may be supported temporarily for compatibility, but are not the target contract.
```

In `ExecutionLaneStatusCard.jsx`, add short help lines:

```jsx
<small>Use the execution composer for guided runs, or advanced commands like `@exec tool ...` and `@exec status ...`.</small>
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
python -m pytest ragenius_app_skeleton/backend/tests/test_chat_exec_routing.py -q
npm test -- App.test.jsx ExecutionLaneStatusCard.test.jsx
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add ragenius_app_skeleton/backend/app/main.py ragenius_app_skeleton/backend/tests/test_chat_exec_routing.py ragenius_app_skeleton/frontend/src/components/ExecutionLaneStatusCard.jsx ragenius_app_skeleton/frontend/src/App.test.jsx docs/2026-06-03-ragenius-content-execution-split-contract-v3.md
git commit -m "docs: clarify exec tool and skill contract"
```

### Task 6: Add Safe Chat-Selection Export As A Real Skill

**Files:**
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\skills\sample-skills.ts`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\tools\tool-registry.ts`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\main.py`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\App.jsx`
- Test: `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\tests\execution\execute-skill.test.ts`
- Test: `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\tests\test_chat_exec_routing.py`

- [ ] **Step 1: Write the failing export tests**

```python
def test_save_chat_selection_exports_to_controlled_directory(client):
    ...
    assert response.status_code == 200
    assert "saved_path" in response.json()["execution_override"]["submit_result"]["result"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest ragenius_app_skeleton/backend/tests/test_chat_exec_routing.py -q
npm test -- execute-skill.test.ts
```

Expected:
- FAIL because no export skill/tool exists

- [ ] **Step 3: Implement a scoped export capability**

Use a dedicated runtime skill such as:

```ts
{
  id: "save_chat_selection",
  requiredTools: ["local.session.export_to_file"],
}
```

Restrict destination to an app-owned export directory, for example:

```python
export_root = Path(__file__).resolve().parents[2] / "exports" / session_id
```

Avoid arbitrary absolute-path writes.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
python -m pytest ragenius_app_skeleton/backend/tests/test_chat_exec_routing.py -q
npm test -- execute-skill.test.ts
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add ragenius_execution_subsystem/src/core/skills/sample-skills.ts ragenius_execution_subsystem/src/core/tools/tool-registry.ts ragenius_app_skeleton/backend/app/main.py ragenius_app_skeleton/frontend/src/App.jsx ragenius_execution_subsystem/tests/execution/execute-skill.test.ts ragenius_app_skeleton/backend/tests/test_chat_exec_routing.py
git commit -m "feat: add safe chat export capability"
```

### Task 7: Improve User-Facing Fallback For Answer-Model Failures

**Files:**
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\answer.py`
- Test: `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_answer_node.py`

- [ ] **Step 1: Write the failing fallback test**

```python
def test_answer_llm_402_uses_user_facing_failure_message():
    state = {...}
    def failing_llm(*_args, **_kwargs):
        raise RuntimeError('LLM HTTP error 402: {"error":{"message":"Insufficient Balance"}}')
    result = run(state, llm_answer=failing_llm)
    assert "暫時不可用" in result["final_answer"]["content"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest ragenius_app_skeleton/tests/test_answer_node.py -q
```

Expected:
- FAIL because fallback still returns generic English text

- [ ] **Step 3: Add a provider-failure-safe fallback**

Change the fallback branch in `answer.py`:

```python
if "LLM HTTP error 402" in llm_error:
    final_answer = {
        "content": "目前回答模型暫時不可用，請稍後再試。",
        "citations": [],
        "missing_infoTypes": [],
    }
else:
    final_answer = _fallback_final_answer(context)
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
python -m pytest ragenius_app_skeleton/tests/test_answer_node.py -q
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add ragenius_app_skeleton/workflows/nodes/answer.py ragenius_app_skeleton/tests/test_answer_node.py
git commit -m "fix: improve answer model failure fallback"
```

## Self-Review

**Spec coverage**
- `@exec tool` vs `@exec skill` split: covered by Tasks 1, 2, 3, 5.
- Runtime/Builder mismatch between real skills and pseudo-skills: covered by Tasks 2 and 3.
- Better UX than raw memorized syntax: covered by Task 4.
- Keep raw `@exec` as advanced mode: covered by Tasks 1 and 5.
- Safe “save selected chat contents as a file”: covered by Task 6.
- Better user-facing fallback when a normal answer model fails: covered by Task 7.

**Placeholder scan**
- No `TODO`, `TBD`, or “implement later” placeholders remain.
- Every task has file paths, tests, commands, and concrete code snippets.

**Type consistency**
- Command kinds use `tool`, `skill`, `status` consistently.
- Runtime inventory names use `tool_id` and `skill_id` consistently.
- Composer submits `commandKind`, `targetId`, and schema-driven `args` consistently.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-04-exec-tool-skill-ux-alignment-implementation-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
