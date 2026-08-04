import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from workflows.nodes import load_template_registry


class LoadTemplateRegistryTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
