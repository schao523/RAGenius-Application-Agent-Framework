import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from workflows.nodes import load_template_registry


class LoadTemplateRegistryTests(unittest.TestCase):
    def test_build_instruction_runtime_model_extracts_declared_module_orchestration(self):
        runtime_model = load_template_registry._build_instruction_runtime_model(
            """
## 模組調度規則（Module Orchestration）
Assistant 必須：
1. 根據語意自動選擇模組
2. 不依賴 Starter 才能啟動
3. 必要時主動建議模組
4. 可組合多模組

任務對應模組:
• 模糊想法 → Use Case Writing Support Module
• 架構設計 → MODULE_GENERATOR Module
• 資源問題 → RESOURCE_MANIFEST_SUPPORT Module
• 模組資源 → RESOURCE_BINDING Module
• 設定問題 → Configuration Support Module
• 互動問題 → Interaction Mode Support Module
• 測試 → Testing & Optimization Support Module

## 應用場景撰寫支持模組 (Use Case Writing Support Module)
Handle unclear ideas.

## MODULE_GENERATOR Module
Design modules.

## RESOURCE_MANIFEST_SUPPORT Module
Design resources.

## RESOURCE_BINDING Module
Bind resources.

## 配置實現支持模組 (Configuration Support Module)
Configure the application.

## 互動模式支持模組 (Interaction Mode Support Module)
Design interaction.

## 測試與優化支持模組 (Testing & Optimization Support Module)
Test the application.
""".strip()
        )

        orchestration = runtime_model["module_orchestration"]
        self.assertEqual(orchestration["selection_mode"], "semantic")
        self.assertFalse(orchestration["starter_required"])
        self.assertTrue(orchestration["assistant_suggestion_allowed"])
        self.assertTrue(orchestration["allow_multi_module"])
        self.assertEqual(
            [item["task_pattern"] for item in orchestration["task_module_mappings"]],
            ["模糊想法", "架構設計", "資源問題", "模組資源", "設定問題", "互動問題", "測試"],
        )
        self.assertEqual(
            [item["target_module_id"] for item in orchestration["task_module_mappings"]],
            [
                "support_module:應用場景撰寫支持模組_use_case_writing_support_module",
                "support_module:module_generator_module",
                "support_module:resource_manifest_support_module",
                "support_module:resource_binding_module",
                "followup_module:配置實現支持模組_configuration_support_module",
                "support_module:互動模式支持模組_interaction_mode_support_module",
                "followup_module:測試與優化支持模組_testing_optimization_support_module",
            ],
        )
        followup_titles = {
            item["title"] for item in runtime_model["followup_modules"]
        }
        self.assertNotIn("模組調度規則（Module Orchestration）", followup_titles)

    def test_build_instruction_runtime_model_does_not_infer_orchestration_from_body_mentions(self):
        runtime_model = load_template_registry._build_instruction_runtime_model(
            """
## General Support Module
This module may coordinate with Configuration Support Module and
Testing & Optimization Support Module.
""".strip()
        )

        self.assertIsNone(runtime_model["module_orchestration"])
        service_block = runtime_model["instruction_service_blocks"][0]
        self.assertEqual(service_block["block_type"], "support_module")

    def test_build_instruction_runtime_model_keeps_stepwise_support_module_procedure_steps(self):
        runtime_model = load_template_registry._build_instruction_runtime_model(
            """
## 查經互動模組
1. 細察事實
使用資源： Resource/ observation_guide.md

2. 認清關係
使用資源： Resource/ identify_relationships_guide.md

## 釋經支援模組（八種合法處境）
使用資源： Resource/ 合法處境補充材料.pdf
""".strip(),
            document_registry=load_template_registry._build_builder_document_registry(
                [
                    {"id": "doc-1", "filename": "observation_guide.md", "status": "ready"},
                    {"id": "doc-2", "filename": "identify_relationships_guide.md", "status": "ready"},
                    {"id": "doc-3", "filename": "合法處境補充材料.pdf", "status": "ready"},
                ]
            ),
        )

        service_blocks = runtime_model.get("instruction_service_blocks", [])
        support_module_block = next(
            item
            for item in service_blocks
            if isinstance(item, dict) and str(item.get("block_id") or "").strip() == "support_module:查經互動模組"
        )
        self.assertEqual(support_module_block.get("block_type"), "support_module")

        procedures = runtime_model.get("instruction_procedures", [])
        support_module_procedure = next(
            item
            for item in procedures
            if isinstance(item, dict)
            and str(item.get("service_block_id") or "").strip() == "support_module:查經互動模組"
        )
        self.assertEqual(
            str(support_module_procedure.get("procedure_id") or "").strip(),
            "procedure:support_module_查經互動模組",
        )

        procedure_steps = [
            item
            for item in runtime_model.get("procedure_steps", [])
            if isinstance(item, dict)
            and str(item.get("procedure_id") or "").strip() == "procedure:support_module_查經互動模組"
        ]
        self.assertEqual(
            [str(item.get("title") or "").strip() for item in procedure_steps],
            ["細察事實", "認清關係"],
        )
        self.assertEqual(
            [list(item.get("resource_refs") or []) for item in procedure_steps],
            [["observation_guide.md"], ["identify_relationships_guide.md"]],
        )

        support_modules = runtime_model.get("support_modules", [])
        bible_study_support_module = next(
            item
            for item in support_modules
            if str(item.get("module_id") or "").strip() == "查經互動模組"
        )
        self.assertEqual(
            list(bible_study_support_module.get("resource_ids") or []),
            [],
        )

        instruction_blocks = runtime_model.get("instruction_blocks", [])
        support_scope = next(
            item
            for item in instruction_blocks
            if isinstance(item, dict) and str(item.get("block_id") or "").strip() == "support:查經互動模組"
        )
        self.assertEqual(list(support_scope.get("referenced_resources") or []), [])
        support_module_scope = next(
            item
            for item in instruction_blocks
            if isinstance(item, dict) and str(item.get("block_id") or "").strip() == "support_module:查經互動模組"
        )
        self.assertEqual(list(support_module_scope.get("referenced_resources") or []), [])
        first_step_scope = next(
            item
            for item in instruction_blocks
            if isinstance(item, dict) and str(item.get("block_id") or "").strip() == "step:support_module_查經互動模組:1"
        )
        self.assertEqual(list(first_step_scope.get("referenced_resources") or []), ["observation_guide.md"])

    def test_support_module_uses_numbered_interaction_flow_instead_of_activation_rules(self):
        runtime_model = load_template_registry._build_instruction_runtime_model(
            """
## 應用場景撰寫支持模組 (Use Case Writing Support Module)
目的: 將模糊想法轉化為清晰的應用場景。
啟動規則:
在以下情況啟動：
1. 使用者點擊 Starter Question
2. 使用者主動請求協助
3. Assistant 判斷描述模糊
互動流程:
1. 確認方向
2. 收集要素
3. Brainstorm
參考：use_case_brainstorm_guide.md
4. 結構化
5. 精煉
""".strip(),
            document_registry=load_template_registry._build_builder_document_registry(
                [
                    {
                        "id": "doc-use-case",
                        "filename": "use_case_brainstorm_guide.md",
                        "status": "ready",
                    }
                ]
            ),
        )

        procedure = next(
            item
            for item in runtime_model["instruction_procedures"]
            if item["service_block_id"]
            == "support_module:應用場景撰寫支持模組_use_case_writing_support_module"
        )
        steps = [
            item
            for item in runtime_model["procedure_steps"]
            if item["procedure_id"] == procedure["procedure_id"]
        ]

        self.assertEqual([item["title"] for item in steps], ["確認方向", "收集要素", "Brainstorm", "結構化", "精煉"])
        self.assertEqual(len(procedure["step_sequence"]), len(set(procedure["step_sequence"])))
        self.assertEqual(steps[2]["resource_refs"], ["use_case_brainstorm_guide.md"])

    def test_build_instruction_runtime_model_extracts_heading_steps_for_followup_modules(self):
        runtime_model = load_template_registry._build_instruction_runtime_model(
            """
## Optimization Module（Prompt 優化模組）
### 【Purpose】
Improve an existing prompt.

### 【Execution Flow】
#### Step 0：Input Check
Ask for the prompt when it is missing.

#### Step 1：Evaluate
Use Optimization Strategy Library.md.

## Tool Selection Module（Compact）
### Trigger
Only run when the user requests tool recommendations.

### Step 1：Determine Execution Type
Determine the execution environment internally.

### Step 2：Select Tools
Use suite_tool_mapping.md.
""".strip(),
            document_registry=load_template_registry._build_builder_document_registry(
                [
                    {"id": "doc-1", "filename": "Optimization Strategy Library.md", "status": "ready"},
                    {"id": "doc-2", "filename": "suite_tool_mapping.md", "status": "ready"},
                ]
            ),
        )

        procedures_by_block = {
            item["service_block_id"]: item
            for item in runtime_model["instruction_procedures"]
        }
        steps_by_procedure = {}
        for step in runtime_model["procedure_steps"]:
            steps_by_procedure.setdefault(step["procedure_id"], []).append(step)

        optimization = procedures_by_block[
            "followup_module:optimization_module_prompt_優化模組"
        ]
        tool_selection = procedures_by_block[
            "followup_module:tool_selection_module_compact"
        ]
        self.assertEqual(
            [step["title"] for step in steps_by_procedure[optimization["procedure_id"]]],
            ["Input Check", "Evaluate"],
        )
        self.assertEqual(
            [step["title"] for step in steps_by_procedure[tool_selection["procedure_id"]]],
            ["Determine Execution Type", "Select Tools"],
        )
        self.assertEqual(
            steps_by_procedure[optimization["procedure_id"]][1]["resource_refs"],
            ["Optimization Strategy Library.md"],
        )
        self.assertEqual(
            steps_by_procedure[tool_selection["procedure_id"]][1]["resource_refs"],
            ["suite_tool_mapping.md"],
        )

    def test_generic_phase_bindings_omit_inert_entries_and_keep_operational_bindings(self):
        runtime_model = load_template_registry._build_instruction_runtime_model(
            """
## Step 1: Clarification
Ask one question and wait for the user.

## Step 2: Reference Guidance
Use workflow_guide.md.

## Export Command
Run /export_prompt when the user requests an export.

## Artifact Review Gate
If the required upload is missing, stop before continuing.
""".strip(),
            document_registry=load_template_registry._build_builder_document_registry(
                [
                    {
                        "id": "doc-workflow",
                        "filename": "workflow_guide.md",
                        "status": "ready",
                    }
                ]
            ),
        )

        bindings_by_title = {
            binding["title"]: binding
            for binding in runtime_model["phase_resource_bindings"]
        }

        self.assertNotIn("Step 1: Clarification", bindings_by_title)
        self.assertEqual(
            bindings_by_title["Step 2: Reference Guidance"]["filenames"],
            ["workflow_guide.md"],
        )
        self.assertEqual(
            bindings_by_title["Export Command"]["trigger_type"],
            "command_trigger",
        )
        self.assertEqual(
            bindings_by_title["Artifact Review Gate"]["artifact_contract"]["mode"],
            "requires_artifact",
        )

    def test_resource_catalog_canonicalizes_unique_filename_fragments_and_legacy_aliases(self):
        runtime_model = load_template_registry._build_instruction_runtime_model(
            """
## 資源 (Resources)
- Nasty, brutish, and short.pdf：parenting reference.
- 歸納釋經法 102025.pdf：Bible study reference.

## 查經支援模組 (Bible Study Support Module)
必須根據 Resource《歸納釋經法.pdf》引導學員。
""".strip(),
            document_registry=load_template_registry._build_builder_document_registry(
                [
                    {
                        "id": "doc-parenting",
                        "filename": "Nasty, brutish, and short.pdf",
                        "status": "ready",
                    },
                    {
                        "id": "doc-bible-study",
                        "filename": "歸納釋經法 102025.pdf",
                        "status": "ready",
                    },
                ]
            ),
        )

        catalog = runtime_model["instruction_resources"]
        filenames = {item["filename"] for item in catalog}
        self.assertEqual(
            filenames,
            {"Nasty, brutish, and short.pdf", "歸納釋經法 102025.pdf"},
        )
        self.assertTrue(all(item.get("document_id") for item in catalog))

    def test_builder_document_resolution_does_not_guess_ambiguous_containment_alias(self):
        registry = load_template_registry._build_builder_document_registry(
            [
                {"id": "doc-2024", "filename": "歸納釋經法 2024.pdf", "status": "ready"},
                {"id": "doc-2025", "filename": "歸納釋經法 2025.pdf", "status": "ready"},
            ]
        )

        self.assertIsNone(
            load_template_registry._resolve_builder_document(
                "歸納釋經法.pdf",
                registry,
            )
        )

    def test_support_module_uses_numbered_core_tasks_instead_of_trigger_conditions(self):
        runtime_model = load_template_registry._build_instruction_runtime_model(
            """
## 互動模式支持模組 (Interaction Mode Support Module)
觸發條件（Trigger Conditions）:
1. 使用者點擊 Starter Question
2. 使用者主動請求
3. Assistant 判斷互動方式不清楚
核心任務:
1. 互動模式識別
2. 任務對齊
3. 設計候選互動模式
參考：interaction_patterns_guide.md
""".strip(),
            document_registry=load_template_registry._build_builder_document_registry(
                [{"id": "doc-patterns", "filename": "interaction_patterns_guide.md", "status": "ready"}]
            ),
        )

        procedure = next(
            item
            for item in runtime_model["instruction_procedures"]
            if item["service_block_id"]
            == "support_module:互動模式支持模組_interaction_mode_support_module"
        )
        steps = [
            item
            for item in runtime_model["procedure_steps"]
            if item["procedure_id"] == procedure["procedure_id"]
        ]

        self.assertEqual([item["title"] for item in steps], ["互動模式識別", "任務對齊", "設計候選互動模式"])
        self.assertEqual(steps[2]["resource_refs"], ["interaction_patterns_guide.md"])

    def test_support_module_uses_numbered_usage_principles_instead_of_reference_categories(self):
        runtime_model = load_template_registry._build_instruction_runtime_model(
            """
## 釋經支援模組（Exegesis Support Module — 八種合法處境）
八種合法處境（Legal Contexts Overview）
1. 文本上下文
2. 經文互涉
3. 史地文化背景
4. 文學與文法
5. 相同神學主題
6. 相同文體
7. 人物生平
8. 救恩歷史
使用原則
1. 根據問題挑選 1–2 種處境
2. 提出與該處境對應的觀察問題
3. 引導學員觀察與思考
4. 明確說明引用來源
""".strip()
        )

        procedure = next(
            item
            for item in runtime_model["instruction_procedures"]
            if item["service_block_id"]
            == "support_module:釋經支援模組_exegesis_support_module_八種合法處境"
        )
        steps = [
            item
            for item in runtime_model["procedure_steps"]
            if item["procedure_id"] == procedure["procedure_id"]
        ]

        self.assertEqual(
            [item["title"] for item in steps],
            [
                "根據問題挑選 1–2 種處境",
                "提出與該處境對應的觀察問題",
                "引導學員觀察與思考",
                "明確說明引用來源",
            ],
        )
        self.assertEqual(len(procedure["step_sequence"]), 4)
        self.assertEqual(len(procedure["step_sequence"]), len(set(procedure["step_sequence"])))

    def test_run_preserves_replayed_session_execution_state(self):
        state = {
            "domain": "general",
            "template_version": 1,
            "workflow_progress": {
                "workflow_id": "interaction_logic_execution_flow",
                "workflow_title": "Interaction Logic & Execution Flow",
                "step_order": 2,
                "step_title": "Workflow Execution",
            },
            "session_execution_state": {
                "active_execution_mode": "bundled",
                "bundled_execution_completed": True,
                "active_module_queue": ["step:routing", "followup_module:optimization_module"],
                "primary_support_module_id": "step:routing",
                "primary_support_module_title": None,
                "active_service_block_id": "primary_workflow:interaction_logic_execution_flow",
                "active_service_block_type": "primary_workflow",
            },
            "template_registry": {
                "builder_instructions": "# Mission\n- Test\n",
            },
        }

        out = load_template_registry.run(state)
        session_state = out["session_execution_state"]

        self.assertEqual(session_state["active_execution_mode"], "bundled")
        self.assertTrue(session_state["bundled_execution_completed"])
        self.assertEqual(
            session_state["active_module_queue"],
            ["step:routing", "followup_module:optimization_module"],
        )
        self.assertEqual(session_state["primary_support_module_id"], "step:routing")
        self.assertEqual(
            session_state["active_service_block_id"],
            "primary_workflow:interaction_logic_execution_flow",
        )
        self.assertEqual(session_state["active_service_block_type"], "primary_workflow")

    def test_run_reconciles_same_scope_activation_title_during_rehydration(self):
        state = {
            "domain": "general",
            "template_version": 1,
            "workflow_progress": {
                "workflow_id": "workflow:design",
                "workflow_title": "Design Workflow",
                "step_order": 1,
                "step_title": "Clarification",
            },
            "session_execution_state": {
                "active_step_order": 1,
                "active_step_title": "Clarification",
                "active_step_scope_id": "step:design:1",
                "procedure_step_activation": {
                    "step_scope_id": "step:design:1",
                    "step_scope_type": "step",
                    "step_order": 1,
                    "step_title": "Step 1: Clarification",
                    "resource_ids": ["clarification-guide"],
                    "primary_support_module_id": None,
                },
            },
            "template_registry": {
                "builder_instructions": "# Mission\n- Test\n",
            },
        }

        out = load_template_registry.run(state)
        session_state = out["session_execution_state"]

        self.assertEqual(session_state["active_step_title"], "Clarification")
        self.assertEqual(
            session_state["procedure_step_activation"]["step_title"],
            "Clarification",
        )
        self.assertEqual(
            session_state["procedure_step_activation"]["resource_ids"],
            ["clarification-guide"],
        )


if __name__ == "__main__":
    unittest.main()
