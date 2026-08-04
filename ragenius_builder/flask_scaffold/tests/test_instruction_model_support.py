from __future__ import annotations

import hashlib
import importlib
import json
import os
import shutil
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4


SCAFFOLD_DIR = Path(__file__).resolve().parents[1]
if str(SCAFFOLD_DIR) not in sys.path:
    sys.path.insert(0, str(SCAFFOLD_DIR))
os.environ["RAGENIUS_BUILDER_DISABLE_GLOBAL_STORE"] = "1"
TEST_TMP_ROOT = Path.cwd() / "outputs" / "builder_instruction_model_tests"
TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)

from instruction_model_adapter import InstructionModelAdapter  # noqa: E402
from storage import DatabaseStore  # noqa: E402


def _sample_payload(content: str = "# Hello", version: str = "v1") -> dict:
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return {
        "compiled_status": "ready",
        "compiled_at": "2026-06-15T01:02:03Z",
        "instruction_source_hash": digest,
        "instruction_source_version": version,
        "instruction_uri": "instructions/app-1/instructions.md",
        "parser_contract_version": "instruction-parser-2026-05-18-v3",
        "binding_logic_version": "binding-logic-2026-05-07-v1",
        "compiled_contract": {
            "instruction_runtime_model": {
                "primary_service_mode": "guided_workflow",
                "default_workflow_id": "workflow.main",
                "instruction_service_blocks": [{"id": "workflow.main", "role": "primary"}],
                "instruction_procedures": [
                    {"id": "proc.main", "procedure_steps": [{"id": "step.one"}]}
                ],
                "instruction_resources": [{"id": "res.one", "role": "reference"}],
                "global_policies": ["Use uploaded docs first."],
            }
        },
        "semantic_compile": {"attached": True, "valid": True},
    }


def _create_app(store: DatabaseStore, instructions: str = "# Hello") -> dict:
    suffix = uuid4().hex
    return store.create_application(
        {
            "name": f"Instruction Model Test App {suffix}",
            "slug": f"instruction-model-test-app-{suffix}",
            "description": "App for instruction model support tests.",
            "starter_questions": ["one", "two", "three", "four"],
            "instructions": instructions,
            "version": "v1",
        }
    )


@contextmanager
def _temporary_directory():
    tmpdir = TEST_TMP_ROOT / f"case_{uuid4().hex}"
    tmpdir.mkdir(parents=True, exist_ok=True)
    try:
        yield str(tmpdir)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


class InstructionModelAdapterTests(unittest.TestCase):
    def test_returns_unconfigured_when_snapshot_root_missing(self):
        adapter = InstructionModelAdapter(snapshot_root=None)

        result = adapter.get_latest_instruction_model(
            app_id="app-1",
            current_instruction={
                "content": "# Hello",
                "version": "v1",
                "uri": "instructions/app-1/instructions.md",
            },
        )

        self.assertEqual(result["status"], "missing")
        self.assertEqual(result["source_kind"], "unconfigured")
        self.assertEqual(result["freshness"], "unknown")
        self.assertEqual(result["payload"], None)
        self.assertEqual(result["errors"], [])

    def test_loads_understanding_json_from_snapshot_folder(self):
        with _temporary_directory() as tmp:
            root = Path(tmp)
            app_dir = root / "app-1"
            app_dir.mkdir()
            content = "# Hello"
            payload = _sample_payload(content)
            (app_dir / "understanding.json").write_text(json.dumps(payload), encoding="utf-8")
            adapter = InstructionModelAdapter(snapshot_root=root)

            result = adapter.get_latest_instruction_model(
                app_id="app-1",
                current_instruction={
                    "content": content,
                    "version": "v1",
                    "uri": "instructions/app-1/instructions.md",
                },
            )

            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["source_kind"], "filesystem_snapshot")
            self.assertEqual(result["freshness"], "current")
            self.assertEqual(result["payload"]["compiled_status"], "ready")
            self.assertEqual(result["summary"]["service_block_count"], 1)
            self.assertEqual(result["summary"]["procedure_count"], 1)
            self.assertEqual(result["summary"]["procedure_step_count"], 1)
            self.assertEqual(result["summary"]["resource_count"], 1)

    def test_builds_display_model_with_procedure_steps_and_resource_names(self):
        with _temporary_directory() as tmp:
            root = Path(tmp)
            app_dir = root / "app-1"
            app_dir.mkdir()
            content = "# Hello"
            payload = _sample_payload(content)
            payload["compiled_contract"]["instruction_runtime_model"] = {
                "instruction_service_blocks": [
                    {"block_id": "primary_workflow:main", "title": "Main Workflow"}
                ],
                "instruction_procedures": [
                    {
                        "procedure_id": "procedure:main",
                        "title": "Main Procedure",
                        "step_sequence": ["step:main:1", "step:main:2"],
                    }
                ],
                "procedure_steps": [
                    {
                        "step_id": "step:main:1",
                        "procedure_id": "procedure:main",
                        "order": 1,
                        "title": "First Runtime Step",
                        "execution_mode": "bundled",
                        "body_text": "Use the first compiled step.",
                    },
                    {
                        "step_id": "step:main:2",
                        "procedure_id": "procedure:main",
                        "order": 2,
                        "title": "Second Runtime Step",
                        "execution_mode": "interactive",
                        "body_text": "Use the second compiled step.",
                    },
                ],
                "instruction_resources": [
                    {
                        "resource_id": "guide_one",
                        "title": "資源 (Resources)",
                        "filename": "guide_one.md",
                        "document_id": "doc-1",
                        "file_status": "ready",
                    },
                    {
                        "resource_id": "guide_two",
                        "title": "資源 (Resources)",
                        "filename": "guide_two.md",
                        "document_id": "doc-2",
                        "file_status": "ready",
                    },
                ],
            }
            (app_dir / "understanding.json").write_text(json.dumps(payload), encoding="utf-8")
            adapter = InstructionModelAdapter(snapshot_root=root)

            result = adapter.get_latest_instruction_model(
                app_id="app-1",
                current_instruction={
                    "content": content,
                    "version": "v1",
                    "uri": "instructions/app-1/instructions.md",
                },
            )

            procedures = result["display_model"]["procedures"]
            resources = result["display_model"]["resources"]
            self.assertEqual(procedures[0]["title"], "Main Procedure")
            self.assertEqual([step["title"] for step in procedures[0]["steps"]], ["First Runtime Step", "Second Runtime Step"])
            self.assertEqual(resources[0]["label"], "資源 (Resources) - guide_one.md")
            self.assertEqual(resources[1]["label"], "資源 (Resources) - guide_two.md")

    def test_builds_display_steps_from_runtime_embedded_module_fields_when_canonical_steps_are_absent(self):
        with _temporary_directory() as tmp:
            root = Path(tmp)
            app_dir = root / "app-1"
            app_dir.mkdir()
            content = "# Hello"
            payload = _sample_payload(content)
            payload["compiled_contract"]["instruction_runtime_model"] = {
                "instruction_procedures": [
                    {
                        "procedure_id": "primary_workflow:方法流程",
                        "service_block_id": "primary_workflow:方法流程",
                        "title": "方法流程",
                    },
                    {
                        "procedure_id": "procedure:配置實現支持模組_configuration_support_module",
                        "service_block_id": "配置實現支持模組_configuration_support_module",
                        "title": "配置實現支持模組 (Configuration Support Module)",
                    },
                ],
                "procedure_steps": [],
                "instruction_blocks": [
                    {
                        "block_id": "step:方法流程:1",
                        "block_type": "step",
                        "title": "需求分析與設計",
                        "body_text": "Step 1: 問應用場景",
                        "linked_workflow": "方法流程",
                        "linked_step_order": 1,
                    },
                    {
                        "block_id": "step:方法流程:2",
                        "block_type": "step",
                        "title": "功能配置實現",
                        "body_text": "Step 1: 生成 System Prompt 草稿",
                        "linked_workflow": "方法流程",
                        "linked_step_order": 2,
                    },
                ],
                "followup_modules": [
                    {
                        "module_id": "followup_module:配置實現支持模組_configuration_support_module",
                        "block_id": "followup_module:配置實現支持模組_configuration_support_module",
                        "title": "配置實現支持模組 (Configuration Support Module)",
                        "tasks": [
                            {"order": 1, "title": "逐項檢查", "items": ["System Instructions"]},
                            {"order": 2, "title": "提出修訂方案", "items": ["Prompt Patches"]},
                        ],
                    }
                ],
            }
            (app_dir / "understanding.json").write_text(json.dumps(payload), encoding="utf-8")
            adapter = InstructionModelAdapter(snapshot_root=root)

            result = adapter.get_latest_instruction_model(
                app_id="app-1",
                current_instruction={
                    "content": content,
                    "version": "v1",
                    "uri": "instructions/app-1/instructions.md",
                },
            )

            procedures = result["display_model"]["procedures"]
            self.assertEqual([step["title"] for step in procedures[0]["steps"]], ["需求分析與設計", "功能配置實現"])
            self.assertEqual([step["title"] for step in procedures[1]["steps"]], ["逐項檢查", "提出修訂方案"])
            self.assertEqual(procedures[0]["steps_source"], "instruction_blocks")
            self.assertEqual(procedures[1]["steps_source"], "embedded_module_fields")

    def test_matches_followup_module_step_sequence_when_module_ids_have_suffix_variants(self):
        with _temporary_directory() as tmp:
            root = Path(tmp)
            app_dir = root / "app-1"
            app_dir.mkdir()
            content = "# Hello"
            payload = _sample_payload(content)
            payload["compiled_contract"]["instruction_runtime_model"] = {
                "instruction_procedures": [
                    {
                        "procedure_id": "procedure:followup_module_optimization_module",
                        "service_block_id": "followup_module:optimization_module",
                        "title": "Optimization Module（Prompt 優化模組）",
                    }
                ],
                "procedure_steps": [],
                "followup_modules": [
                    {
                        "module_id": "followup_module:optimization_module_prompt_優化模組",
                        "title": "Optimization Module（Prompt 優化模組）",
                    },
                    {
                        "module_id": "followup_module:optimization_module",
                        "title": "Optimization Module（Prompt 優化模組）",
                        "step_sequence": [
                            {
                                "order": 0,
                                "step_id": "followup:optimization:input_check",
                                "title": "Step 0：Input Check",
                                "description": "請提供要優化的 Prompt。",
                                "execution_mode": "interactive",
                            },
                            {
                                "order": 1,
                                "step_id": "followup:optimization:dual_evaluation",
                                "title": "Step 1：Dual Evaluation",
                                "description": "雙軸評估。",
                                "execution_mode": "bundled",
                            },
                        ],
                    },
                ],
            }
            (app_dir / "understanding.json").write_text(json.dumps(payload), encoding="utf-8")
            adapter = InstructionModelAdapter(snapshot_root=root)

            result = adapter.get_latest_instruction_model(
                app_id="app-1",
                current_instruction={
                    "content": content,
                    "version": "v1",
                    "uri": "instructions/app-1/instructions.md",
                },
            )

            procedure = result["display_model"]["procedures"][0]
            self.assertEqual(procedure["steps_source"], "embedded_module_fields")
            self.assertEqual([step["title"] for step in procedure["steps"]], ["Step 0：Input Check", "Step 1：Dual Evaluation"])

    def test_marks_snapshot_stale_when_hash_differs(self):
        with _temporary_directory() as tmp:
            root = Path(tmp)
            app_dir = root / "app-1"
            app_dir.mkdir()
            payload = {
                "compiled_status": "ready",
                "instruction_source_hash": "old-hash",
                "instruction_source_version": "v1",
                "compiled_contract": {"instruction_runtime_model": {}},
            }
            (app_dir / "understanding.json").write_text(json.dumps(payload), encoding="utf-8")
            adapter = InstructionModelAdapter(snapshot_root=root)

            result = adapter.get_latest_instruction_model(
                app_id="app-1",
                current_instruction={
                    "content": "# Changed",
                    "version": "v1",
                    "uri": "instructions/app-1/instructions.md",
                },
            )

            self.assertEqual(result["freshness"], "stale")
            self.assertIn("hash", result["freshness_reason"])

    def test_invalid_json_returns_error_without_payload(self):
        with _temporary_directory() as tmp:
            root = Path(tmp)
            app_dir = root / "app-1"
            app_dir.mkdir()
            (app_dir / "understanding.json").write_text("{invalid-json", encoding="utf-8")
            adapter = InstructionModelAdapter(snapshot_root=root)

            result = adapter.get_latest_instruction_model(
                app_id="app-1",
                current_instruction={
                    "content": "# Hello",
                    "version": "v1",
                    "uri": "instructions/app-1/instructions.md",
                },
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["payload"], None)
            self.assertTrue(result["errors"])


class InstructionModelBuilderRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = TEST_TMP_ROOT / f"case_{uuid4().hex}"
        self.tmpdir.mkdir(parents=True, exist_ok=True)
        self.store = DatabaseStore(":memory:", storage_root=self.tmpdir / "builder_store", seed_data=False)
        self.app_module = importlib.import_module("app")
        self.original_store = self.app_module.store
        self.original_snapshot_root = os.environ.get("RAGENIUS_INSTRUCTION_MODEL_SNAPSHOT_ROOT")
        self.original_default_snapshot_root = getattr(
            self.app_module,
            "_DEFAULT_INSTRUCTION_MODEL_SNAPSHOT_ROOT",
            None,
        )
        self.app_module.store = self.store
        self.app_module.app.config["TESTING"] = True

    def tearDown(self):
        self.app_module.store = self.original_store
        if self.original_default_snapshot_root is None and hasattr(
            self.app_module,
            "_DEFAULT_INSTRUCTION_MODEL_SNAPSHOT_ROOT",
        ):
            delattr(self.app_module, "_DEFAULT_INSTRUCTION_MODEL_SNAPSHOT_ROOT")
        else:
            self.app_module._DEFAULT_INSTRUCTION_MODEL_SNAPSHOT_ROOT = self.original_default_snapshot_root
        if self.original_snapshot_root is None:
            os.environ.pop("RAGENIUS_INSTRUCTION_MODEL_SNAPSHOT_ROOT", None)
        else:
            os.environ["RAGENIUS_INSTRUCTION_MODEL_SNAPSHOT_ROOT"] = self.original_snapshot_root
        self.store.close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _client(self):
        return self.app_module.app.test_client()

    def test_instruction_model_api_returns_snapshot(self):
        created = _create_app(self.store)
        snapshot_root = self.tmpdir / "snapshots"
        app_dir = snapshot_root / created["id"]
        app_dir.mkdir(parents=True)
        payload = _sample_payload("# Hello")
        (app_dir / "understanding.json").write_text(json.dumps(payload), encoding="utf-8")
        os.environ["RAGENIUS_INSTRUCTION_MODEL_SNAPSHOT_ROOT"] = str(snapshot_root)

        response = self._client().get(f"/api/apps/{created['id']}/instruction-model")

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["app_id"], created["id"])
        self.assertEqual(body["status"], "ready")
        self.assertIn("summary", body)
        self.assertIn("payload", body)

    def test_instruction_model_api_uses_default_snapshot_root_when_env_is_unset(self):
        created = _create_app(self.store)
        snapshot_root = self.tmpdir / "default_snapshots"
        app_dir = snapshot_root / created["id"]
        app_dir.mkdir(parents=True)
        payload = _sample_payload("# Hello")
        (app_dir / "understanding.json").write_text(json.dumps(payload), encoding="utf-8")
        os.environ.pop("RAGENIUS_INSTRUCTION_MODEL_SNAPSHOT_ROOT", None)
        self.app_module._DEFAULT_INSTRUCTION_MODEL_SNAPSHOT_ROOT = snapshot_root

        response = self._client().get(f"/api/apps/{created['id']}/instruction-model")

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["status"], "ready")
        self.assertEqual(body["source_kind"], "filesystem_snapshot")
        self.assertIn(str(snapshot_root), body["source_path"])

    def test_instruction_model_api_returns_404_for_missing_app(self):
        response = self._client().get("/api/apps/missing-app/instruction-model")

        self.assertEqual(response.status_code, 404)

    def test_instruction_model_api_does_not_allow_post(self):
        created = _create_app(self.store)

        response = self._client().post(f"/api/apps/{created['id']}/instruction-model")

        self.assertEqual(response.status_code, 405)

    def test_instruction_config_page_has_runtime_model_modes(self):
        created = _create_app(self.store)

        response = self._client().get(f"/apps/{created['id']}/config?tab=instructions")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Runtime Model", body)
        self.assertIn("Markdown Preview", body)
        self.assertIn("Raw JSON", body)
        self.assertIn('name="content"', body)
        self.assertIn("Save Instructions", body)

    def test_instruction_config_post_still_updates_file_backed_instructions(self):
        created = _create_app(self.store)

        response = self._client().post(
            f"/apps/{created['id']}/config?tab=instructions",
            data={
                "content": "# Updated",
                "version": "v2",
                "uri": f"instructions/{created['id']}/instructions.md",
            },
        )

        self.assertEqual(response.status_code, 200)
        updated = self.store.get_instructions(created["id"])
        self.assertEqual(updated["content"], "# Updated")
        self.assertEqual(updated["version"], "v2")

    def test_settings_config_post_still_updates_settings(self):
        created = _create_app(self.store)

        response = self._client().post(
            f"/apps/{created['id']}/config?tab=settings",
            data={
                "config_settings": '{"llm": {"provider": "test"}}',
                "config_schema": '{"type": "object", "properties": {"llm": {"type": "object"}}}',
            },
        )

        self.assertEqual(response.status_code, 200)
        settings = self.store.get_settings(created["id"])
        self.assertIn('"provider": "test"', settings["config_settings"])

    def test_unrelated_builder_routes_still_render_without_server_errors(self):
        created = _create_app(self.store)
        routes = [
            f"/apps/{created['id']}/config?tab=instructions",
            f"/apps/{created['id']}/config?tab=settings",
            f"/apps/{created['id']}/docs",
            f"/apps/{created['id']}/search",
            "/skills",
        ]

        for route in routes:
            response = self._client().get(route)
            self.assertLess(response.status_code, 500, route)

    def test_existing_instruction_and_settings_apis_still_work(self):
        created = _create_app(self.store)
        client = self._client()

        self.assertEqual(client.get(f"/api/apps/{created['id']}/instructions").status_code, 200)
        self.assertEqual(client.get(f"/api/apps/{created['id']}/settings").status_code, 200)
        patch_response = client.patch(
            f"/api/apps/{created['id']}/instructions",
            json={
                "content": "# API Updated",
                "version": "v3",
                "uri": f"instructions/{created['id']}/instructions.md",
            },
        )
        self.assertEqual(patch_response.status_code, 200)
        updated = self.store.get_instructions(created["id"])
        self.assertEqual(updated["content"], "# API Updated")
