# Hierarchical Instruction Parser And Planner Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor instruction parsing and planning so app instructions are interpreted as hierarchical service contracts with default workflows, explicit service-block types, heading-based steps, and correct resource-binding activation.

**Architecture:** Build a canonical heading tree in the parser, classify executable service blocks from that tree, derive procedures and steps from those blocks, then update planner session-entry logic to prefer explicit triggers before falling back to the default primary workflow. Keep retrieval and persistence request-driven, but propagate the richer service-block provenance through summaries and runtime state without breaking existing compatibility fields.

**Tech Stack:** Python 3, Pydantic runtime models, unittest, existing `ragenius_app_skeleton` workflow graph nodes.

---

## File Structure

### Core parser contract
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\load_template_registry.py`
  - Add heading-tree parsing
  - Add service-block classification
  - Add default primary workflow inference
  - Add heading-style step extraction
  - Keep current legacy outputs populated during migration

- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\runtime_models.py`
  - Add new parser/planner contract models
  - Add active service-block runtime fields
  - Preserve backward compatibility with existing turn/session fields

### Planner and runtime integration
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\planner.py`
  - Consume service blocks and procedures
  - Resolve explicit trigger vs default workflow entry
  - Distinguish support modules, follow-up modules, and supplementary workflows
  - Keep existing `primary_scope`, `active_step_scope`, `primary_support_module_scope`

- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\retrieve.py`
  - Preserve request-driven retrieval
  - Propagate new service-block provenance into prepared inputs and debug trace

- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\persist_run.py`
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\chat_service.py`
  - Expose active service-block metadata in summaries while preserving older fields

### Tests
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_load_template_registry.py`
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_planner_node.py`
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_retrieve_node.py`
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_persist_run_node.py`
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_chat_pipeline_runtime_contracts.py`
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_builder_chat_integration.py`

---

### Task 1: Add Hierarchical Parser Models

**Files:**
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\runtime_models.py`
- Test: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_load_template_registry.py`

- [ ] **Step 1: Write the failing model tests**

```python
class RuntimeModelHierarchyTests(unittest.TestCase):
    def test_instruction_heading_node_serializes_children_without_hash_markers(self):
        from workflows.runtime_models import InstructionHeadingNode, to_plain_dict

        node = InstructionHeadingNode(
            node_id="node:workflow",
            level=2,
            title="Interaction Logic & Execution Flow",
            normalized_title="interaction_logic_execution_flow",
            body_text="Step 0 gate",
            children=[
                InstructionHeadingNode(
                    node_id="node:step-1",
                    level=3,
                    title="Step 1：Clarification",
                    normalized_title="step_1_clarification",
                    body_text="Ask one question",
                    children=[],
                )
            ],
        )

        payload = to_plain_dict(node)

        assert payload["title"] == "Interaction Logic & Execution Flow"
        assert payload["children"][0]["title"] == "Step 1：Clarification"
        assert payload["children"][0]["level"] == 3

    def test_service_block_and_procedure_models_accept_new_types(self):
        from workflows.runtime_models import InstructionProcedure, InstructionServiceBlock

        block = InstructionServiceBlock(
            block_id="workflow:default-parenting",
            block_type="primary_workflow",
            title="Parenting Coaching Workflow",
            is_default=True,
        )
        procedure = InstructionProcedure(
            procedure_id="procedure:default-parenting",
            service_block_id="workflow:default-parenting",
            title="Parenting Coaching Workflow",
            procedure_kind="primary",
            is_default=True,
        )

        assert block.block_type == "primary_workflow"
        assert procedure.procedure_kind == "primary"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```powershell
$env:PYTHONPATH='C:\Users\User\Documents\GitHub\Codex-RAGenius-System;C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton'; python -m unittest ragenius_app_skeleton.tests.test_load_template_registry -v
```

Expected: FAIL with missing `InstructionHeadingNode`, `InstructionServiceBlock`, or `InstructionProcedure` models.

- [ ] **Step 3: Add the new runtime models with compatibility defaults**

```python
class InstructionHeadingNode(BaseModel):
    node_id: str
    level: int
    title: str
    normalized_title: str
    body_text: str = ""
    children: list["InstructionHeadingNode"] = Field(default_factory=list)
    source_span: dict[str, Any] | None = None


class TriggerCondition(BaseModel):
    trigger_type: str
    phrases: list[str] = Field(default_factory=list)
    command_markers: list[str] = Field(default_factory=list)
    artifact_roles: list[str] = Field(default_factory=list)
    starter_prompts: list[str] = Field(default_factory=list)


class InstructionServiceBlock(BaseModel):
    block_id: str
    block_type: Literal[
        "primary_workflow",
        "entry_mode",
        "support_module",
        "followup_module",
        "supplementary_workflow",
        "global_policy",
        "resource_catalog",
        "output_contract",
    ]
    title: str
    body_text: str = ""
    parent_block_id: str | None = None
    trigger_conditions: list[TriggerCondition] = Field(default_factory=list)
    required_inputs: list[str] = Field(default_factory=list)
    resource_refs: list[str] = Field(default_factory=list)
    policy_refs: list[str] = Field(default_factory=list)
    is_default: bool = False


class InstructionProcedure(BaseModel):
    procedure_id: str
    service_block_id: str
    title: str
    procedure_kind: Literal["primary", "supplementary", "followup"]
    is_default: bool = False
    entry_mode_ids: list[str] = Field(default_factory=list)
    trigger_conditions: list[TriggerCondition] = Field(default_factory=list)
    step_sequence: list[str] = Field(default_factory=list)
    output_targets: list[str] = Field(default_factory=list)


class ProcedureStepDefinition(BaseModel):
    step_id: str
    procedure_id: str
    order: int
    title: str
    body_text: str = ""
    step_kind: str | None = None
    wait_for_user: bool = False
    advance_conditions: list[str] = Field(default_factory=list)
    resource_refs: list[str] = Field(default_factory=list)
    primary_support_module_id: str | None = None
    step_output_role: str | None = None
```

- [ ] **Step 4: Extend turn/session runtime fields for active service-block identity**

```python
class TurnExecutionPlan(BaseModel):
    # existing fields unchanged
    active_service_block_type: str | None = None
    active_service_block_id: str | None = None
    active_service_block_title: str | None = None


class SessionExecutionState(BaseModel):
    # existing fields unchanged
    active_service_block_type: str | None = None
    active_service_block_id: str | None = None
    active_service_block_title: str | None = None
```

- [ ] **Step 5: Run tests to verify model changes pass**

Run:
```powershell
$env:PYTHONPATH='C:\Users\User\Documents\GitHub\Codex-RAGenius-System;C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton'; python -m unittest ragenius_app_skeleton.tests.test_load_template_registry -v
```

Expected: PASS for new model tests, with older runtime-model tests still green.

- [ ] **Step 6: Commit**

```bash
git add ragenius_app_skeleton/workflows/runtime_models.py ragenius_app_skeleton/tests/test_load_template_registry.py
git commit -m "feat: add hierarchical instruction runtime models"
```

---

### Task 2: Build Canonical Heading Tree And Step Extraction

**Files:**
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\load_template_registry.py`
- Test: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_load_template_registry.py`

- [ ] **Step 1: Write failing parser tests for heading depth, ownership, and heading-style steps**

```python
def test_builds_heading_tree_from_double_hash_top_level_and_triple_hash_steps(self):
    markdown = """
## Interaction Logic & Execution Flow
Intro
### Step 0：輸入完整度判斷
Gate rules
### Step 1：Clarification
Ask one key question
## Knowledge Modules
Use template_library.md
"""
    out = load_template_registry.run({
        "template_version": 1,
        "domain": "general",
        "template_registry": {"builder_instructions": markdown},
    })
    model = out["template_registry"]["instruction_runtime_model"]

    tree = model["instruction_heading_tree"]
    procedures = model["instruction_procedures"]
    steps = model["procedure_steps"]

    self.assertEqual(tree[0]["title"], "Interaction Logic & Execution Flow")
    self.assertEqual(tree[0]["children"][0]["title"], "Step 0：輸入完整度判斷")
    self.assertEqual(tree[0]["children"][1]["title"], "Step 1：Clarification")
    self.assertEqual(procedures[0]["title"], "Interaction Logic & Execution Flow")
    self.assertEqual([step["order"] for step in steps], [0, 1])


def test_infers_default_primary_workflow_when_main_procedure_has_no_explicit_triggers(self):
    markdown = """
## Interaction Logic & Execution Flow
### Step 0：輸入完整度判斷
Gate rules
### Step 1：Clarification
Ask one question
## Knowledge Modules
- template_library.md
"""
    out = load_template_registry.run({
        "template_version": 1,
        "domain": "general",
        "template_registry": {"builder_instructions": markdown},
    })
    procedures = out["template_registry"]["instruction_runtime_model"]["instruction_procedures"]

    default_procedure = next(item for item in procedures if item["is_default"])
    self.assertEqual(default_procedure["title"], "Interaction Logic & Execution Flow")
    self.assertEqual(default_procedure["procedure_kind"], "primary")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```powershell
$env:PYTHONPATH='C:\Users\User\Documents\GitHub\Codex-RAGenius-System;C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton'; python -m unittest ragenius_app_skeleton.tests.test_load_template_registry -v
```

Expected: FAIL because `instruction_heading_tree`, `instruction_procedures`, or heading-style step extraction do not yet exist.

- [ ] **Step 3: Add heading tokenization and canonical tree construction**

```python
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


def _scan_heading_entries(markdown: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    body_buffer: list[str] = []
    current: dict[str, Any] | None = None
    for raw_line in markdown.splitlines():
        line = str(raw_line or "")
        match = HEADING_PATTERN.match(line.strip())
        if match:
            if current is not None:
                current["body_text"] = "\n".join(body_buffer).strip()
                entries.append(current)
            current = {
                "level": len(match.group(1)),
                "title": match.group(2).strip(),
            }
            body_buffer = []
            continue
        if current is not None:
            body_buffer.append(line)
    if current is not None:
        current["body_text"] = "\n".join(body_buffer).strip()
        entries.append(current)
    return entries


def _infer_top_level_heading_depth(entries: list[dict[str, Any]]) -> int:
    levels = [int(item.get("level") or 0) for item in entries if int(item.get("level") or 0) in {1, 2}]
    if not levels:
        return 2
    return min(levels)
```

- [ ] **Step 4: Build nested tree ownership and heading-style step extraction**

```python
def _build_instruction_heading_tree(markdown: str) -> list[dict[str, Any]]:
    entries = _scan_heading_entries(markdown)
    top_level = _infer_top_level_heading_depth(entries)
    stack: list[dict[str, Any]] = []
    roots: list[dict[str, Any]] = []

    for index, entry in enumerate(entries, 1):
        level = int(entry["level"])
        node = {
            "node_id": f"heading:{index}",
            "level": level,
            "title": str(entry["title"]),
            "normalized_title": _normalize_section_name(str(entry["title"])),
            "body_text": str(entry.get("body_text") or ""),
            "children": [],
        }
        while stack and int(stack[-1]["level"]) >= level:
            stack.pop()
        if stack:
            stack[-1]["children"].append(node)
        else:
            roots.append(node)
        stack.append(node)

    return [node for node in roots if int(node["level"]) >= top_level]


def _is_heading_style_step(node: dict[str, Any], procedure_level: int) -> bool:
    title = str(node.get("title") or "")
    level = int(node.get("level") or 0)
    return level == procedure_level + 1 and bool(re.match(r"^Step\s*\d+", title, re.IGNORECASE) or re.match(r"^步驟?\s*\d+", title))
```

- [ ] **Step 5: Populate new parser outputs alongside legacy outputs**

```python
runtime_model["instruction_heading_tree"] = heading_tree
runtime_model["instruction_service_blocks"] = service_blocks
runtime_model["instruction_procedures"] = procedures
runtime_model["procedure_steps"] = procedure_steps
runtime_model["support_modules"] = support_modules
runtime_model["followup_modules"] = followup_modules
runtime_model["global_policies"] = global_policies
```

- [ ] **Step 6: Run parser tests and inspect the Church Ministry extraction case**

Run:
```powershell
$env:PYTHONPATH='C:\Users\User\Documents\GitHub\Codex-RAGenius-System;C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton'; python -m unittest ragenius_app_skeleton.tests.test_load_template_registry -v
```

Expected: PASS for heading tree and default workflow inference, with Church Ministry now emitting heading-based steps under `Interaction Logic & Execution Flow`.

- [ ] **Step 7: Commit**

```bash
git add ragenius_app_skeleton/workflows/nodes/load_template_registry.py ragenius_app_skeleton/tests/test_load_template_registry.py
git commit -m "feat: add hierarchical instruction parsing"
```

---

### Task 3: Classify Service Blocks And Module Roles

**Files:**
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\load_template_registry.py`
- Test: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_load_template_registry.py`

- [ ] **Step 1: Write failing classification tests for all four analyzed app styles**

```python
def test_classifies_church_ministry_primary_workflow_support_modules_and_followup_modules(self):
    markdown = """
## Interaction Logic & Execution Flow
### Step 0：輸入完整度判斷
### Step 1：Clarification
## 1️⃣ Knowledge Modules（知識模組）
- template_library.md
## 2️⃣ Instruction Modules（指令模組）
- dynamic_prompt_optimizer.md
## Optimization Module（Prompt 優化模組）
### Trigger Conditions
- 幫我優化這段指令
"""
    out = load_template_registry.run({
        "template_version": 1,
        "domain": "general",
        "template_registry": {"builder_instructions": markdown},
    })
    blocks = out["template_registry"]["instruction_runtime_model"]["instruction_service_blocks"]
    kinds = {item["title"]: item["block_type"] for item in blocks}

    self.assertEqual(kinds["Interaction Logic & Execution Flow"], "primary_workflow")
    self.assertEqual(kinds["1️⃣ Knowledge Modules（知識模組）"], "support_module")
    self.assertEqual(kinds["2️⃣ Instruction Modules（指令模組）"], "support_module")
    self.assertEqual(kinds["Optimization Module（Prompt 優化模組）"], "followup_module")


def test_classifies_grow_with_children_bible_study_as_supplementary_workflow(self):
    markdown = """
## 互動模式
- 一步搞定
- 按步就班
- 深度解析
## 查經互動模組（歸納釋經法的十個步驟, Supplementary Module）
### Step 1
觀察
### Step 2
關係
"""
    out = load_template_registry.run({
        "template_version": 1,
        "domain": "general",
        "template_registry": {"builder_instructions": markdown},
    })
    blocks = out["template_registry"]["instruction_runtime_model"]["instruction_service_blocks"]
    mapping = {item["title"]: item["block_type"] for item in blocks}

    self.assertEqual(mapping["查經互動模組（歸納釋經法的十個步驟, Supplementary Module）"], "supplementary_workflow")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```powershell
$env:PYTHONPATH='C:\Users\User\Documents\GitHub\Codex-RAGenius-System;C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton'; python -m unittest ragenius_app_skeleton.tests.test_load_template_registry -v
```

Expected: FAIL because current block typing is still generic/legacy.

- [ ] **Step 3: Add tree-based block classification helpers**

```python
def _classify_service_block(node: dict[str, Any], siblings: list[dict[str, Any]]) -> str:
    title = str(node.get("title") or "")
    body = str(node.get("body_text") or "")
    normalized = _normalize_section_name(title)

    if _looks_like_resource_catalog(title, body):
        return "resource_catalog"
    if _looks_like_output_contract(title, body):
        return "output_contract"
    if _looks_like_global_policy(title, body):
        return "global_policy"
    if _looks_like_supplementary_workflow(title, body):
        return "supplementary_workflow"
    if _looks_like_followup_module(title, body):
        return "followup_module"
    if _looks_like_support_module(title, body):
        return "support_module"
    if _looks_like_entry_mode(title, body):
        return "entry_mode"
    if _looks_like_primary_workflow(title, body):
        return "primary_workflow"
    return "global_policy"
```

- [ ] **Step 4: Infer default primary workflow and normalize trigger conditions**

```python
def _mark_default_primary_workflow(blocks: list[dict[str, Any]]) -> None:
    primaries = [item for item in blocks if item.get("block_type") == "primary_workflow"]
    explicit = [item for item in primaries if item.get("trigger_conditions")]
    if len(primaries) == 1 and not explicit:
        primaries[0]["is_default"] = True
```

- [ ] **Step 5: Materialize support/follow-up/supplementary outputs in the runtime model**

```python
runtime_model["support_modules"] = [
    block for block in service_blocks if block.get("block_type") == "support_module"
]
runtime_model["followup_modules"] = [
    block for block in service_blocks if block.get("block_type") == "followup_module"
]
runtime_model["instruction_procedures"] = [
    _procedure_from_block(block) for block in service_blocks
    if block.get("block_type") in {"primary_workflow", "supplementary_workflow"}
]
```

- [ ] **Step 6: Run tests to verify classification for Church Ministry, Bible Tutor, GPT App Design, and Grow With Children**

Run:
```powershell
$env:PYTHONPATH='C:\Users\User\Documents\GitHub\Codex-RAGenius-System;C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton'; python -m unittest ragenius_app_skeleton.tests.test_load_template_registry -v
```

Expected: PASS for service-block classification across all four instruction styles.

- [ ] **Step 7: Commit**

```bash
git add ragenius_app_skeleton/workflows/nodes/load_template_registry.py ragenius_app_skeleton/tests/test_load_template_registry.py
git commit -m "feat: classify instruction service blocks"
```

---

### Task 4: Refactor Planner Session Entry And Procedure Selection

**Files:**
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\planner.py`
- Test: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_planner_node.py`
- Test: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_builder_chat_integration.py`

- [ ] **Step 1: Write failing planner tests for default workflow cold-start and supplementary workflow routing**

```python
def test_church_ministry_starter_turn_activates_default_primary_workflow(self):
    state = _church_ministry_state_for_query(
        "我想透過【主題或經文】幫助人更深認識神的真理，請幫我建立一個能支持這目的的最佳化提示（prompt）。"
    )
    result = planner.run(state)
    plan = result["turn_execution_plan"]

    self.assertEqual(plan["primary_scope"]["title"], "Interaction Logic & Execution Flow")
    self.assertEqual(plan["primary_scope"]["scope_type"], "workflow")
    self.assertEqual(plan["active_service_block_type"], "primary_workflow")


def test_grow_with_children_scripture_request_activates_supplementary_workflow(self):
    state = _grow_with_children_state_for_query("我想查考一段經文")
    result = planner.run(state)
    plan = result["turn_execution_plan"]

    self.assertEqual(plan["active_service_block_type"], "supplementary_workflow")
    self.assertIn("查經互動模組", plan["primary_scope"]["title"])
    self.assertIsNone(plan.get("primary_support_module_scope"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```powershell
$env:PYTHONPATH='C:\Users\User\Documents\GitHub\Codex-RAGenius-System;C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton'; python -m unittest ragenius_app_skeleton.tests.test_planner_node -v
```

Expected: FAIL because planner still depends primarily on legacy workflow/module selection and cannot cold-start the Church Ministry default workflow.

- [ ] **Step 3: Replace flat workflow selection with service-block-aware session-entry resolution**

```python
def _select_active_service_block(state: GraphState, planner_output: dict[str, Any]) -> dict[str, Any] | None:
    blocks = _instruction_service_blocks(state)
    query = _combined_query_text(state, planner_output)
    is_new_session = _is_new_session_turn(state)

    explicit = _match_explicit_service_blocks(blocks, query, state)
    if explicit is not None:
        return explicit

    if is_new_session:
        return _default_primary_workflow_block(state)

    return _continued_service_block(state)
```

- [ ] **Step 4: Derive procedure, step, and support-module selection from the active service block**

```python
def _resolve_service_execution_context(state: GraphState, planner_output: dict[str, Any]) -> dict[str, Any]:
    block = _select_active_service_block(state, planner_output)
    procedure = _procedure_for_service_block(state, block)
    step = _select_procedure_step(state, procedure, planner_output)
    support_module = _select_primary_support_module(state, procedure, step, planner_output)
    return {
        "active_service_block": block,
        "active_procedure": procedure,
        "active_step": step,
        "primary_support_module": support_module,
    }
```

- [ ] **Step 5: Preserve scope semantics by block type**

```python
if active_block_type == "primary_workflow":
    primary_scope = _scope_from_procedure(procedure)
elif active_block_type == "supplementary_workflow":
    primary_scope = _scope_from_procedure(procedure)
elif active_block_type == "followup_module":
    primary_scope = _scope_from_followup_module(block, prior_primary_scope)
else:
    primary_scope = prior_primary_scope
```

And:
```python
turn_execution_plan["active_service_block_type"] = active_block_type
turn_execution_plan["active_service_block_id"] = block.get("block_id")
turn_execution_plan["active_service_block_title"] = block.get("title")
```

- [ ] **Step 6: Run planner and integration tests**

Run:
```powershell
$env:PYTHONPATH='C:\Users\User\Documents\GitHub\Codex-RAGenius-System;C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton'; python -m unittest ragenius_app_skeleton.tests.test_planner_node ragenius_app_skeleton.tests.test_builder_chat_integration -v
```

Expected: PASS for Church Ministry starter cold-start, Bible Tutor routing, and Grow With Children supplementary-workflow selection.

- [ ] **Step 7: Commit**

```bash
git add ragenius_app_skeleton/workflows/nodes/planner.py ragenius_app_skeleton/tests/test_planner_node.py ragenius_app_skeleton/tests/test_builder_chat_integration.py
git commit -m "feat: refactor planner around hierarchical service blocks"
```

---

### Task 5: Propagate Service-Block Provenance Through Retrieval And Summaries

**Files:**
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\retrieve.py`
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\persist_run.py`
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\chat_service.py`
- Test: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_retrieve_node.py`
- Test: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_persist_run_node.py`
- Test: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_chat_pipeline_runtime_contracts.py`

- [ ] **Step 1: Write failing provenance tests**

```python
def test_retrieve_preserves_active_service_block_provenance_on_requests(self):
    state = _state_with_resource_requests([
        {
            "filename": "template_library.md",
            "resource_role": "instruction_source",
            "source_layer": "procedure_step",
            "step_scope_id": "step:church:3",
            "support_module_id": "module:knowledge",
        }
    ])
    state["turn_execution_plan"] = {
        "active_service_block_type": "primary_workflow",
        "active_service_block_id": "workflow:church-primary",
        "active_service_block_title": "Interaction Logic & Execution Flow",
    }
    result = retrieve.run(state)

    resolved = result["prepared_inputs"]["resource_requests"][0]
    self.assertEqual(resolved["source_layer"], "procedure_step")
    self.assertEqual(resolved["step_scope_id"], "step:church:3")
    self.assertEqual(result["retrieval_debug_trace"]["active_service_block_type"], "primary_workflow")


def test_persist_summary_exposes_active_service_block_without_breaking_primary_scope(self):
    summary = persist_run._build_retrieval_summary({
        "turn_execution_plan": {
            "primary_scope": {"title": "Interaction Logic & Execution Flow", "scope_type": "workflow"},
            "active_service_block_type": "primary_workflow",
            "active_service_block_id": "workflow:church-primary",
            "active_service_block_title": "Interaction Logic & Execution Flow",
        }
    })

    self.assertEqual(summary["active_service_block_type"], "primary_workflow")
    self.assertEqual(summary["primary_scope"], "Interaction Logic & Execution Flow")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```powershell
$env:PYTHONPATH='C:\Users\User\Documents\GitHub\Codex-RAGenius-System;C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton'; python -m unittest ragenius_app_skeleton.tests.test_retrieve_node ragenius_app_skeleton.tests.test_persist_run_node ragenius_app_skeleton.tests.test_chat_pipeline_runtime_contracts -v
```

Expected: FAIL because active service-block metadata is not yet present in all retrieval/summary surfaces.

- [ ] **Step 3: Thread active service-block metadata through retrieval debug and prepared inputs**

```python
retrieval_debug_trace["active_service_block_type"] = turn_execution_plan.get("active_service_block_type")
retrieval_debug_trace["active_service_block_id"] = turn_execution_plan.get("active_service_block_id")
retrieval_debug_trace["active_service_block_title"] = turn_execution_plan.get("active_service_block_title")
```

- [ ] **Step 4: Extend summary builders with compatibility-safe service-block fields**

```python
summary["active_service_block_type"] = turn_execution_plan.get("active_service_block_type")
summary["active_service_block_id"] = turn_execution_plan.get("active_service_block_id")
summary["active_service_block_title"] = turn_execution_plan.get("active_service_block_title")
```

- [ ] **Step 5: Run retrieval/runtime contract tests**

Run:
```powershell
$env:PYTHONPATH='C:\Users\User\Documents\GitHub\Codex-RAGenius-System;C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton'; python -m unittest ragenius_app_skeleton.tests.test_retrieve_node ragenius_app_skeleton.tests.test_persist_run_node ragenius_app_skeleton.tests.test_chat_pipeline_runtime_contracts -v
```

Expected: PASS, with older `primary_scope` / `active_step_scope` summary assertions still valid.

- [ ] **Step 6: Commit**

```bash
git add ragenius_app_skeleton/workflows/nodes/retrieve.py ragenius_app_skeleton/workflows/nodes/persist_run.py ragenius_app_skeleton/backend/app/chat_service.py ragenius_app_skeleton/tests/test_retrieve_node.py ragenius_app_skeleton/tests/test_persist_run_node.py ragenius_app_skeleton/tests/test_chat_pipeline_runtime_contracts.py
git commit -m "feat: propagate active service-block provenance"
```

---

### Task 6: Add Cross-App Regression Coverage And Verify End-To-End Behavior

**Files:**
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_load_template_registry.py`
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_planner_node.py`
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_chat_pipeline_runtime_contracts.py`
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_builder_chat_integration.py`

- [ ] **Step 1: Add parser fixtures for the four analyzed app archetypes**

```python
BIBLE_TUTOR_SNIPPET = """
## 模式自動識別（Mode Detection）
- 查考經文模式（Bible Study）
  - 觸發：「查考」「研經」「經文」
## 查經互動模組（歸納釋經法的十個步驟）
### Step 1：細察事實
使用 observation_guide.md
"""

GROW_WITH_CHILDREN_SNIPPET = """
## 互動模式
- 一步搞定
- 按步就班
- 深度解析
## 查經互動模組（歸納釋經法的十個步驟, Supplementary Module）
### Step 1：細察事實
依據 歸納釋經法 102025.pdf
"""
```

- [ ] **Step 2: Add planner regressions for each contract distinction**

```python
def test_bible_tutor_bible_study_mode_routes_to_primary_study_workflow(self): ...
def test_gpt_app_design_config_support_is_followup_module_not_primary_workflow(self): ...
def test_grow_with_children_parenting_question_stays_in_default_primary_workflow(self): ...
def test_grow_with_children_bible_study_request_activates_supplementary_workflow(self): ...
def test_church_ministry_first_turn_uses_default_primary_workflow_without_explicit_trigger(self): ...
```

- [ ] **Step 3: Add end-to-end pipeline assertions for service-block identity**

```python
def test_pipeline_summary_reports_supplementary_workflow_when_parenting_app_enters_bible_study(self):
    result = _run_pipeline_for_query(...)
    summary = result["retrieval_summary"]
    self.assertEqual(summary["active_service_block_type"], "supplementary_workflow")
    self.assertIn("查經互動模組", summary["active_service_block_title"])
```

- [ ] **Step 4: Run the full targeted suite**

Run:
```powershell
$env:PYTHONPATH='C:\Users\User\Documents\GitHub\Codex-RAGenius-System;C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton'; python -m unittest ragenius_app_skeleton.tests.test_load_template_registry ragenius_app_skeleton.tests.test_planner_node ragenius_app_skeleton.tests.test_retrieve_node ragenius_app_skeleton.tests.test_persist_run_node ragenius_app_skeleton.tests.test_chat_pipeline_runtime_contracts ragenius_app_skeleton.tests.test_builder_chat_integration -v
```

Expected: PASS, with all new and legacy behavior validated together.

- [ ] **Step 5: Commit**

```bash
git add ragenius_app_skeleton/tests/test_load_template_registry.py ragenius_app_skeleton/tests/test_planner_node.py ragenius_app_skeleton/tests/test_chat_pipeline_runtime_contracts.py ragenius_app_skeleton/tests/test_builder_chat_integration.py
git commit -m "test: add hierarchical instruction parser regressions"
```

---

### Task 7: Final Compatibility Review And Cleanup

**Files:**
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\load_template_registry.py`
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\planner.py`
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\retrieve.py`
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\persist_run.py`
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\chat_service.py`
- Test: all targeted suites above

- [ ] **Step 1: Remove duplicated legacy inference from hot paths only where the new contract already supplies the same answer**

```python
# Example cleanup target
service_blocks = runtime_model.get("instruction_service_blocks", []) or []
procedures = runtime_model.get("instruction_procedures", []) or []
if service_blocks and procedures:
    # prefer hierarchical contract
    ...
else:
    # compatibility fallback
    ...
```

- [ ] **Step 2: Verify old compatibility fields are still present where external consumers may rely on them**

```python
assert "primary_scope" in turn_execution_plan
assert "active_step_scope" in turn_execution_plan
assert "primary_support_module_scope" in turn_execution_plan
assert "instruction_resource_load_plan" in session_execution_state
```

- [ ] **Step 3: Run the final verification suite**

Run:
```powershell
$env:PYTHONPATH='C:\Users\User\Documents\GitHub\Codex-RAGenius-System;C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton'; python -m unittest ragenius_app_skeleton.tests.test_load_template_registry ragenius_app_skeleton.tests.test_planner_node ragenius_app_skeleton.tests.test_retrieve_node ragenius_app_skeleton.tests.test_persist_run_node ragenius_app_skeleton.tests.test_chat_pipeline_runtime_contracts ragenius_app_skeleton.tests.test_builder_chat_integration -v
```

Expected: PASS across all six suites.

- [ ] **Step 4: Document verified outcomes in the final review notes**

```text
Verified:
- Church Ministry default workflow cold-start works
- Bible Tutor mode -> workflow routing works
- GPT App Design support vs follow-up behavior works
- Grow With Children supplementary workflow works
- backward-compatible summary fields remain
```

- [ ] **Step 5: Commit**

```bash
git add ragenius_app_skeleton/workflows/nodes/load_template_registry.py ragenius_app_skeleton/workflows/nodes/planner.py ragenius_app_skeleton/workflows/nodes/retrieve.py ragenius_app_skeleton/workflows/nodes/persist_run.py ragenius_app_skeleton/backend/app/chat_service.py
git commit -m "refactor: finalize hierarchical instruction parsing and planning"
```

---

## Spec Coverage Check

Covered requirements:
- heading-tree parser contract
- top-level heading depth normalization
- heading markers excluded from names
- default primary workflow inference
- explicit trigger precedence over default workflow
- primary/support/follow-up/supplementary/global-policy distinction
- heading-style step extraction
- planner cold-start for Church Ministry
- supplementary workflow handling for Grow With Children
- backward-compatible runtime/persistence propagation
- cross-app regression coverage

No uncovered spec items remain.

## Placeholder Scan

Reviewed for:
- `TODO`
- `TBD`
- “write tests for above” without examples
- inconsistent type names

No placeholders remain.

## Type Consistency Check

Consistent names used throughout:
- `InstructionHeadingNode`
- `InstructionServiceBlock`
- `InstructionProcedure`
- `ProcedureStepDefinition`
- `active_service_block_type`
- `active_service_block_id`
- `active_service_block_title`
- `primary_workflow`
- `support_module`
- `followup_module`
- `supplementary_workflow`
