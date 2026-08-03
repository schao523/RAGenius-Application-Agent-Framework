import json
import os
import sqlite3
import sys
import unittest
import uuid
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

TEST_RUNTIME_ROOT = Path(__file__).resolve().parent / "_tmp" / "builder_chat_runtime"
TEST_RUNTIME_STATE_DB = TEST_RUNTIME_ROOT / "runtime_state.db"
TEST_RUNTIME_UPLOADS_DIR = TEST_RUNTIME_ROOT / "session_uploads"
os.environ["RAGENIUS_APP_STATE_DB"] = str(TEST_RUNTIME_STATE_DB)
os.environ["RAGENIUS_APP_UPLOADS_DIR"] = str(TEST_RUNTIME_UPLOADS_DIR)

import backend.app.main as backend_main
from backend.app.chat_repos import ChatRepo, SessionRepo
from backend.app.rag_runtime import reset_rag_store

# main may already be imported during full-suite collection, so replace its
# process-global repositories before importing their aliases below.
backend_main.session_repo = SessionRepo(TEST_RUNTIME_STATE_DB)
backend_main.chat_repo = ChatRepo(TEST_RUNTIME_STATE_DB)

from backend.app.main import (
    app,
    chat_repo,
    ingestion_repo,
    instruction_understanding_repo,
    planner_repo,
    retrieval_repo,
    session_repo,
)
from backend.app.instruction_understanding_service import compile_instruction_understanding


def _create_builder_db(base_dir: str) -> tuple[str, str]:
    root = Path(base_dir)
    if root.exists():
        for path in sorted(root.glob("**/*"), reverse=True):
            try:
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            except PermissionError:
                pass

    db_path = Path(base_dir) / "rag_app.db"
    instructions_dir = Path(base_dir) / "instructions" / "app-1"
    instructions_dir.mkdir(parents=True, exist_ok=True)
    instructions_path = instructions_dir / "instructions.md"
    instructions_path.write_text(
        "# Mission\n- Answer from uploaded knowledge.\n# Style\n- Be calm.\n# Safety\n- Do not fabricate.\n\n"
        "## Mode Detection\n"
        "â€¢ Bible Study\n"
        "  o Trigger: query includes ã€ŒæŸ¥è€ƒã€ ã€Œç ”ç¶“ã€ ã€Œç¶“æ–‡ã€\n"
        "  o Start full workflow: æŸ¥ç¶“äº’å‹•æ¨¡çµ„\n\n"
        "## æŸ¥ç¶“äº’å‹•æ¨¡çµ„\n"
        "1. ç´°å¯Ÿäº‹å¯¦ (Observation)\n"
        "ä½¿ç”¨è³‡æºï¼š Resource/ observation_guide.md\n"
        "2. èªæ¸…é—œä¿‚ (Identify Relationships)\n"
        "ä½¿ç”¨è³‡æºï¼š Resource/ identify_relation_guide.md\n",
        encoding="utf-8",
    )
    uploads_dir = Path(base_dir) / "storage" / "uploads" / "app-1"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    doc_path = uploads_dir / "doc-1_jesus.txt"
    doc_path.write_text(
        "Jesus is central to Christian faith. This builder-managed document contains enough words to survive "
        "chunking and quality filtering, so retrieval should return a grounded snippet about Jesus and his role.",
        encoding="utf-8",
    )

    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE applications (id TEXT PRIMARY KEY, name TEXT NOT NULL, slug TEXT NOT NULL UNIQUE, description TEXT, starter_questions TEXT, updated_at TEXT)"
    )
    conn.execute(
        "CREATE TABLE instructions (app_id TEXT PRIMARY KEY, content TEXT, uri TEXT, version TEXT, updated_at TEXT)"
    )
    conn.execute(
        "CREATE TABLE settings (app_id TEXT PRIMARY KEY, config_settings TEXT, config_schema TEXT, updated_at TEXT)"
    )
    conn.execute(
        "CREATE TABLE documents (id TEXT PRIMARY KEY, app_id TEXT NOT NULL, filename TEXT NOT NULL, mime_type TEXT, size_bytes INTEGER, language TEXT, tags TEXT, file_path TEXT, status TEXT, error_message TEXT, uploaded_at TEXT)"
    )
    conn.execute(
        "INSERT INTO applications (id, name, slug, description, starter_questions, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("app-1", "Bible Helper", "bible-helper", "desc", json.dumps(["q1", "q2", "q3", "q4"]), "2026-04-25T00:00:00"),
    )
    conn.execute(
        "INSERT INTO instructions (app_id, content, uri, version, updated_at) VALUES (?, ?, ?, ?, ?)",
        ("app-1", "# stale", "instructions/app-1/instructions.md", "v1", "2026-04-25T00:00:00"),
    )
    conn.execute(
        "INSERT INTO settings (app_id, config_settings, config_schema, updated_at) VALUES (?, ?, ?, ?)",
        (
            "app-1",
            json.dumps({"embedding_model": "text-embedding-3-small", "language": "zh"}),
            json.dumps({"type": "object"}),
            "2026-04-25T00:00:00",
        ),
    )
    conn.execute(
        "INSERT INTO documents (id, app_id, filename, mime_type, size_bytes, language, tags, file_path, status, error_message, uploaded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "doc-1",
            "app-1",
            "jesus.txt",
            "text/plain",
            len(doc_path.read_text(encoding='utf-8')),
            "en",
            json.dumps(["bible"]),
            str(doc_path),
            "pending",
            None,
            "2026-04-25T00:00:00",
        ),
    )
    conn.commit()
    conn.close()
    return str(db_path), str(instructions_path)


class BuilderChatIntegrationTests(unittest.TestCase):
    def setUp(self):
        ingestion_repo.reset()
        session_repo.reset()
        chat_repo.reset()
        if hasattr(instruction_understanding_repo, "reset"):
            instruction_understanding_repo.reset()
        planner_repo.reset()
        retrieval_repo.reset()
        reset_rag_store()
        self.client = TestClient(app)
        self.tmp_root = Path(__file__).resolve().parent / "_tmp" / "builder_chat" / str(uuid.uuid4())
        self.tmp_root.mkdir(parents=True, exist_ok=True)

    def test_runtime_state_is_isolated_from_user_session_storage(self):
        self.assertEqual(session_repo._db.db_path, TEST_RUNTIME_STATE_DB.resolve())
        self.assertEqual(session_repo._db.uploads_dir, TEST_RUNTIME_UPLOADS_DIR.resolve())
        self.assertNotEqual(
            session_repo._db.db_path,
            (Path(__file__).resolve().parents[1] / "backend" / ".state" / "runtime_state.db").resolve(),
        )

    def tearDown(self):
        if self.tmp_root.exists():
            for path in sorted(self.tmp_root.glob("**/*"), reverse=True):
                try:
                    if path.is_file():
                        path.unlink()
                    elif path.is_dir():
                        path.rmdir()
                except PermissionError:
                    pass

    def test_chat_uses_builder_app_context_by_app_id(self):
        db_path, instructions_path = _create_builder_db(str(self.tmp_root))
        captured = {}

        def fake_run_chat_pipeline(state, **kwargs):
            captured["state"] = state
            return {"content": "builder-backed answer", "citations": [], "missing_infoTypes": []}

        with mock.patch.dict(os.environ, {"RAGENIUS_BUILDER_DB": db_path}, clear=False):
            with mock.patch("backend.app.main.run_chat_pipeline", side_effect=fake_run_chat_pipeline):
                response = self.client.post(
                    "/sessions/s-builder/chat",
                    json={
                        "user_id": "u1",
                        "app_id": "app-1",
                        "user_query": "Who is Jesus?",
                        "template_version": 1,
                    },
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["content"], "builder-backed answer")
        self.assertEqual(captured["state"]["collection_id"], "app-1")
        self.assertEqual(captured["state"]["config_json"]["meta"]["builder_settings"]["language"], "zh")
        self.assertEqual(
            captured["state"]["config_json"]["meta"]["llm_settings"]["models"]["planner"],
            "deepseek-v4-pro",
        )
        self.assertIn("Answer from uploaded knowledge.", captured["state"]["config_json"]["role"]["mission"])
        self.assertEqual(captured["state"]["adapter_json"]["domain"], "bible-helper")
        self.assertIn("Do not fabricate.", captured["state"]["adapter_json"]["llm_guardrails_append"])
        self.assertTrue(Path(instructions_path).exists())

    def test_builder_document_ingest_then_chat_retrieves_uploaded_text(self):
        db_path, _ = _create_builder_db(str(self.tmp_root))
        vector_store_path = str(self.tmp_root / "rag_vector_store.json")

        with mock.patch.dict(
            os.environ,
            {
                "RAGENIUS_BUILDER_DB": db_path,
                "RAG_VECTOR_STORE_BACKEND": "json",
                "RAG_VECTOR_STORE_PATH": vector_store_path,
                "RAG_EMBEDDING_BACKEND": "hash",
            },
            clear=False,
        ):
            reset_rag_store()
            ingest = self.client.post(
                "/apps/app-1/documents/ingest",
                headers={"x-role": "admin"},
                json={"document_ids": ["doc-1"]},
            )
            self.assertEqual(ingest.status_code, 200)
            run_id = ingest.json()["run_id"]

            status = self.client.get(f"/apps/app-1/ingestion_runs/{run_id}", headers={"x-role": "admin"})
            self.assertEqual(status.status_code, 200)
            self.assertEqual(status.json()["status"], "success")

            chat = self.client.post(
                "/sessions/s-builder-doc/chat",
                json={
                    "user_id": "u1",
                    "app_id": "app-1",
                    "user_query": "Who is Jesus?",
                    "template_version": 1,
                },
            )
            messages = self.client.get(
                "/sessions/s-builder-doc/messages?app_id=app-1&user_id=u1"
            )

        self.assertEqual(chat.status_code, 200)
        body = chat.json()
        self.assertTrue(body["citations"])
        self.assertNotEqual(body["citations"][0]["snippet"], "No snippet")
        self.assertIn("Jesus", body["citations"][0]["snippet"])
        self.assertIn("retrieval_summary", body)
        self.assertIn("turn_execution_plan", body)
        self.assertIn("session_execution_state", body)
        self.assertIn("primary_action_type", body["retrieval_summary"])
        self.assertIn("knowledge_retrieved_count", body["retrieval_summary"])
        self.assertIn("template_retrieved_count", body["retrieval_summary"])
        self.assertIn("template_titles", body["retrieval_summary"])
        self.assertIn("output_artifact_targets", body["retrieval_summary"])
        live_diagnostics = body["retrieval_summary"]["task_model_diagnostics"]
        self.assertGreaterEqual(live_diagnostics["turn_token_accounting"]["call_count"], 1)
        self.assertTrue(live_diagnostics["context_optimization"]["calls"])

        self.assertEqual(messages.status_code, 200)
        persisted_assistant = [
            message for message in messages.json()["messages"] if message.get("role") == "assistant"
        ][-1]
        persisted_diagnostics = persisted_assistant["retrievalSummary"]["task_model_diagnostics"]
        self.assertEqual(
            persisted_diagnostics["turn_token_accounting"],
            live_diagnostics["turn_token_accounting"],
        )

    def test_chat_route_surfaces_bundled_direct_markdown_sources_in_retrieval_summary(self):
        db_path, _ = _create_builder_db(str(self.tmp_root))

        class FakeGraph:
            def invoke(self, state):
                return {
                    "final_answer": {"content": "bundled result", "citations": [], "missing_infoTypes": []},
                    "raw_evidence": [
                        {
                            "doc_id": "doc-knowledge-1",
                            "title": "Micah Notes",
                            "retrieval_domain": "knowledge_source",
                        }
                    ],
                    "retrieval_debug_trace": {
                        "route": {},
                        "domains": {
                            "instruction_source": {"route": {}, "executed_queries": [], "attempt_count": 0},
                            "knowledge_source": {"route": {}, "executed_queries": [], "attempt_count": 1},
                            "output_template": {"route": {}, "executed_queries": [], "attempt_count": 0},
                            "session_upload": {"route": {}, "executed_queries": [], "attempt_count": 0},
                        },
                    },
                    "turn_execution_plan": {
                        "resource_requests": [
                            {"filename": "Ministry_Prompt_Framework.md", "resource_role": "instruction_source"},
                            {"filename": "delivery_package_template.md", "resource_role": "output_template"},
                        ],
                        "actions": [],
                    },
                    "session_execution_state": {
                        "active_execution_mode": "bundled",
                        "active_bundled_step_ids": [
                            "step:interaction_logic_execution_flow:2",
                            "step:interaction_logic_execution_flow:3",
                        ],
                        "bundled_entry_step_id": "step:interaction_logic_execution_flow:2",
                    },
                    "instruction_resource_context": [
                        {
                            "filename": "Ministry_Prompt_Framework.md",
                            "load_strategy": "direct_load",
                            "source_kind": "markdown",
                            "section_titles": ["Generate the Ministry Prompt Draft"],
                        }
                    ],
                    "template_resource_context": [
                        {
                            "filename": "delivery_package_template.md",
                            "load_strategy": "direct_load",
                            "source_kind": "markdown",
                            "section_titles": ["Finalize the Delivery Package"],
                        }
                    ],
                }

        with mock.patch.dict(os.environ, {"RAGENIUS_BUILDER_DB": db_path}, clear=False):
            with mock.patch("backend.app.chat_service._graph", return_value=FakeGraph()):
                response = self.client.post(
                    "/sessions/s-bundled-summary/chat",
                    json={
                        "user_id": "u1",
                        "app_id": "app-1",
                        "user_query": "Continue with the confirmed ministry details.",
                        "template_version": 1,
                    },
                )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["content"], "bundled result")
        self.assertEqual(body["retrieval_summary"]["knowledge_retrieved_count"], 1)
        self.assertEqual(body["retrieval_summary"]["instruction_retrieved_count"], 1)
        self.assertEqual(body["retrieval_summary"]["template_retrieved_count"], 1)
        self.assertIn("Ministry_Prompt_Framework.md", body["retrieval_summary"]["instruction_titles"])
        self.assertIn("delivery_package_template.md", body["retrieval_summary"]["template_titles"])
        self.assertEqual(body["retrieval_summary"]["active_execution_mode"], "bundled")
        self.assertEqual(
            body["retrieval_summary"]["bundled_entry_step_id"],
            "step:interaction_logic_execution_flow:2",
        )
        self.assertTrue(body["bundled_execution"]["enabled"])
        self.assertEqual(body["bundled_execution"]["active_execution_mode"], "bundled")
        self.assertEqual(
            body["bundled_execution"]["bundled_entry_step_id"],
            "step:interaction_logic_execution_flow:2",
        )

    def test_builder_instruction_endpoint_returns_derived_runtime_contract(self):
        db_path, _ = _create_builder_db(str(self.tmp_root))

        with mock.patch.dict(os.environ, {"RAGENIUS_BUILDER_DB": db_path}, clear=False):
            seeded = self.client.post(
                "/apps/app-1/instruction-understanding/recompile",
                headers={"x-role": "admin"},
            )
            self.assertEqual(seeded.status_code, 200)
            instructions = self.client.get("/apps/app-1/instructions", headers={"x-role": "admin"})

        self.assertEqual(instructions.status_code, 200)
        self.assertEqual(instructions.json()["runtime_source"], "builder")
        self.assertIn("Answer from uploaded knowledge.", instructions.json()["instructions"]["content"])
        self.assertIn("meta", instructions.json()["derived_config_json"])
        self.assertIn("domain", instructions.json()["derived_adapter_json"])
        self.assertEqual(instructions.json()["instruction_understanding_status"]["cache_status"], "hot")
        self.assertEqual(instructions.json()["instruction_understanding_status"]["compiled_status"], "ready")
        self.assertIn("instruction_understanding_preview", instructions.json())
        self.assertEqual(
            instructions.json()["instruction_understanding_preview"]["compiled_status"],
            "ready",
        )

    def test_builder_runtime_endpoint_includes_instruction_understanding_status(self):
        db_path, _ = _create_builder_db(str(self.tmp_root))

        with mock.patch.dict(os.environ, {"RAGENIUS_BUILDER_DB": db_path}, clear=False):
            seeded = self.client.post(
                "/apps/app-1/instruction-understanding/recompile",
                headers={"x-role": "admin"},
            )
            self.assertEqual(seeded.status_code, 200)
            runtime = self.client.get("/apps/app-1/runtime", headers={"x-role": "admin"})

        self.assertEqual(runtime.status_code, 200)
        payload = runtime.json()
        self.assertEqual(payload["runtime_source"], "builder")
        self.assertEqual(payload["instruction_understanding_status"]["cache_status"], "hot")
        self.assertEqual(payload["instruction_understanding_status"]["compiled_status"], "ready")
        self.assertIn("compiled_instruction_understanding", payload["template_registry_keys"])
        self.assertIn("instruction_understanding_status", payload["template_registry_keys"])
        self.assertIn("instruction_understanding_preview", payload)
        self.assertEqual(payload["instruction_understanding_preview"]["compiled_status"], "ready")
        self.assertIn("planner_mode", payload)
        self.assertIn("instruction_understanding_mode", payload)

    def test_chat_state_includes_planner_and_instruction_understanding_modes(self):
        db_path, _ = _create_builder_db(str(self.tmp_root))
        captured = {}
        conn = sqlite3.connect(db_path)
        conn.execute(
            "UPDATE settings SET config_settings = ? WHERE app_id = ?",
            (
                json.dumps(
                    {
                        "embedding_model": "text-embedding-3-small",
                        "language": "zh",
                        "planner_mode": "hybrid_shadow",
                        "instruction_understanding_mode": "hybrid_active",
                    }
                ),
                "app-1",
            ),
        )
        conn.commit()
        conn.close()

        def fake_run_chat_pipeline(state, **kwargs):
            captured["state"] = state
            return {"content": "ok", "citations": [], "missing_infoTypes": []}

        with mock.patch.dict(os.environ, {"RAGENIUS_BUILDER_DB": db_path}, clear=False):
            with mock.patch("backend.app.main.run_chat_pipeline", side_effect=fake_run_chat_pipeline):
                response = self.client.post(
                    "/sessions/s-mode/chat",
                    json={
                        "user_id": "u1",
                        "app_id": "app-1",
                        "user_query": "test mode state",
                        "template_version": 1,
                    },
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["state"]["planner_mode"], "hybrid_shadow")
        self.assertEqual(captured["state"]["instruction_understanding_mode"], "hybrid_active")

    def test_builder_nested_llm_settings_are_consumed_and_partial_models_merge_with_defaults(self):
        db_path, _ = _create_builder_db(str(self.tmp_root))
        captured = {}
        conn = sqlite3.connect(db_path)
        conn.execute(
            "UPDATE settings SET config_settings = ? WHERE app_id = ?",
            (
                json.dumps(
                    {
                        "language": "zh",
                        "llm": {
                            "provider": "deepseek",
                            "models": {
                                "planner": "deepseek-reasoner",
                                "adapter_generation": "deepseek-reasoner",
                            },
                            "temperature": {
                                "planner": 0.55,
                            },
                        },
                    }
                ),
                "app-1",
            ),
        )
        conn.commit()
        conn.close()

        def fake_run_chat_pipeline(state, **kwargs):
            captured["state"] = state
            return {"content": "ok", "citations": [], "missing_infoTypes": []}

        with mock.patch.dict(os.environ, {"RAGENIUS_BUILDER_DB": db_path}, clear=False):
            with mock.patch("backend.app.main.run_chat_pipeline", side_effect=fake_run_chat_pipeline):
                response = self.client.post(
                    "/sessions/s-llm-contract/chat",
                    json={
                        "user_id": "u1",
                        "app_id": "app-1",
                        "user_query": "test nested llm config",
                        "template_version": 1,
                    },
                )

        self.assertEqual(response.status_code, 200)
        llm_settings = captured["state"]["config_json"]["meta"]["llm_settings"]
        self.assertEqual(llm_settings["provider"], "deepseek")
        self.assertEqual(llm_settings["models"]["planner"], "deepseek-reasoner")
        self.assertEqual(llm_settings["models"]["adapter_generation"], "deepseek-reasoner")
        self.assertEqual(llm_settings["models"]["answer_generation"], "deepseek-v4-flash")
        self.assertEqual(llm_settings["temperature"]["planner"], 0.55)
        self.assertEqual(llm_settings["temperature"]["answer_generation"], 0.2)

    def test_chat_route_replays_prior_runtime_state_into_next_turn(self):
        db_path, _ = _create_builder_db(str(self.tmp_root))
        captured = {}

        runtime_state = {
            "workflow_progress": {
                "workflow_id": "interaction_logic_execution_flow",
                "workflow_title": "Interaction Logic & Execution Flow",
                "step_order": 2,
                "step_title": "æ ¸å¿ƒæµç¨‹ï¼ˆWorkflow Executionï¼‰",
            },
            "session_execution_state": {
                "primary_scope_id": "workflow:interaction_logic_execution_flow",
                "primary_scope_type": "workflow",
                "primary_scope_title": "Interaction Logic & Execution Flow",
                "active_execution_mode": "bundled",
                "bundled_execution_completed": True,
                "active_module_queue": ["followup_module:optimization_module"],
                "primary_support_module_id": "followup_module:optimization_module",
                "primary_support_module_title": "Optimization Module",
            },
            "intermediate_outputs": [],
            "assembly_state": {},
        }

        def fake_run_chat_pipeline(state, **kwargs):
            captured["state"] = state
            return {"content": "ok", "citations": [], "missing_infoTypes": []}

        with mock.patch.dict(os.environ, {"RAGENIUS_BUILDER_DB": db_path}, clear=False):
            session_repo.get_or_create(
                "s-followup-replay",
                collection_id="app-1",
                user_id="u1",
                title=None,
                config_version=1,
                adapter_version=1,
                template_version=1,
            )
            updated = session_repo.set_runtime_state("s-followup-replay", runtime_state)
            self.assertIsNotNone(updated)
            with mock.patch("backend.app.main.run_chat_pipeline", side_effect=fake_run_chat_pipeline):
                response = self.client.post(
                    "/sessions/s-followup-replay/chat",
                    json={
                        "user_id": "u1",
                        "app_id": "app-1",
                        "user_query": "è«‹å¹«æˆ‘å„ªåŒ–é€™å€‹ prompt",
                        "template_version": 1,
                    },
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            captured["state"]["workflow_progress"]["workflow_id"],
            "interaction_logic_execution_flow",
        )
        self.assertEqual(
            captured["state"]["session_execution_state"]["primary_support_module_id"],
            "followup_module:optimization_module",
        )
        self.assertEqual(
            captured["state"]["session_execution_state"]["active_module_queue"],
            ["followup_module:optimization_module"],
        )
        self.assertTrue(captured["state"]["session_execution_state"]["bundled_execution_completed"])

    def test_instruction_understanding_detail_route_returns_compiled_and_review_payload(self):
        db_path, _ = _create_builder_db(str(self.tmp_root))

        with mock.patch.dict(os.environ, {"RAGENIUS_BUILDER_DB": db_path}, clear=False):
            seeded = self.client.post(
                "/apps/app-1/instruction-understanding/recompile",
                headers={"x-role": "admin"},
            )
            self.assertEqual(seeded.status_code, 200)
            detail = self.client.get("/apps/app-1/instruction-understanding", headers={"x-role": "admin"})

        self.assertEqual(detail.status_code, 200)
        payload = detail.json()
        self.assertEqual(payload["app_id"], "app-1")
        self.assertIn("compiled", payload)
        self.assertIn("review", payload)
        self.assertIn("status", payload)
        self.assertIsInstance(payload["compiled"], dict)
        self.assertEqual(payload["compiled"]["compiled_status"], "ready")
        self.assertEqual(payload["status"]["compiled_status"], "ready")

    def test_instruction_understanding_detail_route_is_read_only(self):
        db_path, _ = _create_builder_db(str(self.tmp_root))

        with mock.patch.dict(os.environ, {"RAGENIUS_BUILDER_DB": db_path}, clear=False):
            with mock.patch(
                "backend.app.main.prepare_instruction_understanding",
                side_effect=AssertionError("prepare should not be called"),
            ):
                detail = self.client.get("/apps/app-1/instruction-understanding", headers={"x-role": "admin"})

        self.assertEqual(detail.status_code, 200)
        payload = detail.json()
        self.assertEqual(payload["app_id"], "app-1")
        self.assertIn("compiled", payload)
        self.assertIn("review", payload)
        self.assertIn("status", payload)

    def test_instruction_understanding_review_route_returns_409_without_reviewer(self):
        db_path, _ = _create_builder_db(str(self.tmp_root))

        with mock.patch.dict(os.environ, {"RAGENIUS_BUILDER_DB": db_path}, clear=False):
            self.client.get("/apps/app-1/instructions", headers={"x-role": "admin"})
            with mock.patch("backend.app.main.build_instruction_understanding_reviewer", return_value=None):
                response = self.client.post(
                    "/apps/app-1/instruction-understanding/review",
                    headers={"x-role": "admin"},
                )

        self.assertEqual(response.status_code, 409)
        self.assertIn("reviewer", response.json()["detail"].lower())

    def test_instruction_understanding_approve_route_returns_payload(self):
        db_path, _ = _create_builder_db(str(self.tmp_root))
        fake_result = {
            "record": {"compiled_status": "ready"},
            "review": {"review_status": "reviewed"},
            "approval": {"approval_status": "approved"},
        }
        with mock.patch.dict(os.environ, {"RAGENIUS_BUILDER_DB": db_path}, clear=False):
            with mock.patch(
                "backend.app.main.approve_instruction_understanding_findings",
                return_value=fake_result,
            ):
                response = self.client.post(
                    "/apps/app-1/instruction-understanding/approve-findings",
                    headers={"x-role": "admin"},
                    json={"approved_findings": [{"id": "f1"}], "approver": "tester"},
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["app_id"], "app-1")
        self.assertEqual(payload["approval"]["approval_status"], "approved")

    def test_instruction_understanding_revise_route_returns_409_without_reviser(self):
        db_path, _ = _create_builder_db(str(self.tmp_root))
        with mock.patch.dict(os.environ, {"RAGENIUS_BUILDER_DB": db_path}, clear=False):
            with mock.patch("backend.app.main.build_instruction_understanding_reviser", return_value=None):
                response = self.client.post(
                    "/apps/app-1/instruction-understanding/revise",
                    headers={"x-role": "admin"},
                )
        self.assertEqual(response.status_code, 409)
        self.assertIn("reviser", response.json()["detail"].lower())

    def test_instruction_understanding_recompile_route_returns_detail_and_refreshes_record(self):
        db_path, _ = _create_builder_db(str(self.tmp_root))

        def fake_compiler(_context):
            return {
                "app_semantic_model": {
                    "primary_service_mode": "single_default_workflow",
                    "default_workflow_id": "workflow:default",
                    "service_blocks": [
                        {
                            "block_id": "workflow:default",
                            "block_type": "primary_workflow",
                            "title": "Interaction Logic & Execution Flow",
                            "is_default": True,
                        }
                    ],
                    "procedures": [],
                    "procedure_steps": [],
                    "role_profiles": [],
                    "routing_rules": [],
                    "clarification_gate_rules": [],
                }
            }

        with mock.patch.dict(os.environ, {"RAGENIUS_BUILDER_DB": db_path}, clear=False):
            with mock.patch("backend.app.main.build_instruction_understanding_compiler", return_value=fake_compiler):
                seeded = self.client.post(
                    "/apps/app-1/instruction-understanding/recompile",
                    headers={"x-role": "admin"},
                )
                self.assertEqual(seeded.status_code, 200)
                before = self.client.get("/apps/app-1/instruction-understanding", headers={"x-role": "admin"})
                recompiled = self.client.post(
                    "/apps/app-1/instruction-understanding/recompile",
                    headers={"x-role": "admin"},
                )

        self.assertEqual(before.status_code, 200)
        self.assertEqual(recompiled.status_code, 200)
        before_payload = before.json()
        recompiled_payload = recompiled.json()
        self.assertEqual(recompiled_payload["app_id"], "app-1")
        self.assertEqual(recompiled_payload["status"]["compiled_status"], "ready")
        self.assertEqual(recompiled_payload["cache_status"], "recompiled")
        self.assertNotEqual(
            before_payload["compiled"]["id"],
            recompiled_payload["compiled"]["id"],
        )

    def test_instruction_understanding_recompile_route_keeps_last_valid_active_record_when_new_attempt_is_invalid(self):
        db_path, _ = _create_builder_db(str(self.tmp_root))

        def valid_compiler(_context):
            return {
                "app_semantic_model": {
                    "primary_service_mode": "single_default_workflow",
                    "default_workflow_id": "workflow:default",
                    "service_blocks": [
                        {
                            "block_id": "workflow:default",
                            "block_type": "primary_workflow",
                            "title": "Interaction Logic & Execution Flow",
                            "is_default": True,
                        }
                    ],
                    "procedures": [],
                    "procedure_steps": [],
                    "role_profiles": [],
                    "routing_rules": [],
                    "clarification_gate_rules": [],
                }
            }

        with mock.patch.dict(os.environ, {"RAGENIUS_BUILDER_DB": db_path}, clear=False):
            with mock.patch("backend.app.main.build_instruction_understanding_compiler", return_value=valid_compiler):
                first = self.client.post(
                    "/apps/app-1/instruction-understanding/recompile",
                    headers={"x-role": "admin"},
                )
            self.assertEqual(first.status_code, 200)
            first_payload = first.json()

            with mock.patch("backend.app.main.build_instruction_understanding_compiler", return_value=lambda _context: {}):
                second = self.client.post(
                    "/apps/app-1/instruction-understanding/recompile",
                    headers={"x-role": "admin"},
                )

        self.assertEqual(second.status_code, 200)
        second_payload = second.json()
        self.assertEqual(second_payload["compiled"]["id"], first_payload["compiled"]["id"])
        self.assertEqual(second_payload["compiled"]["metadata"]["publish_status"], "active")

    def test_instruction_understanding_recompile_route_reports_compile_required_when_invalid_attempt_has_no_prior_valid_model(self):
        db_path, _ = _create_builder_db(str(self.tmp_root))

        with mock.patch.dict(os.environ, {"RAGENIUS_BUILDER_DB": db_path}, clear=False):
            with mock.patch("backend.app.main.build_instruction_understanding_compiler", return_value=lambda _context: {}):
                recompiled = self.client.post(
                    "/apps/app-1/instruction-understanding/recompile",
                    headers={"x-role": "admin"},
                )
                detail = self.client.get("/apps/app-1/instruction-understanding", headers={"x-role": "admin"})
                instructions = self.client.get("/apps/app-1/instructions", headers={"x-role": "admin"})

        self.assertEqual(recompiled.status_code, 200)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(instructions.status_code, 200)

        recompiled_payload = recompiled.json()
        detail_payload = detail.json()
        instructions_payload = instructions.json()

        self.assertIsNone(recompiled_payload["compiled"])
        self.assertEqual(recompiled_payload["attempt_record"]["metadata"]["publish_status"], "diagnostic_only")
        self.assertIsNotNone(recompiled_payload["latest_attempt"]["id"])

        self.assertIsNone(detail_payload["compiled"])
        self.assertIsNotNone(detail_payload["latest_attempt"]["id"])

        preview = instructions_payload["instruction_understanding_preview"]
        self.assertIsNone(preview["compiled_id"])
        self.assertTrue(preview["compile_required"])
        self.assertIsNotNone(preview["latest_attempt_id"])
        self.assertFalse(preview["latest_attempt_semantic_compile_valid"])

    def test_instruction_and_runtime_get_routes_are_read_only_when_compiled_data_exists(self):
        db_path, _ = _create_builder_db(str(self.tmp_root))

        with mock.patch.dict(os.environ, {"RAGENIUS_BUILDER_DB": db_path}, clear=False):
            seeded = self.client.post(
                "/apps/app-1/instruction-understanding/recompile",
                headers={"x-role": "admin"},
            )
            self.assertEqual(seeded.status_code, 200)
            compiled_id = seeded.json()["compiled"]["id"]

            with mock.patch(
                "backend.app.main.prepare_instruction_understanding",
                side_effect=AssertionError("prepare should not be called"),
            ):
                instructions = self.client.get("/apps/app-1/instructions", headers={"x-role": "admin"})
                runtime = self.client.get("/apps/app-1/runtime", headers={"x-role": "admin"})

        self.assertEqual(instructions.status_code, 200)
        self.assertEqual(runtime.status_code, 200)
        self.assertEqual(instructions.json()["instruction_understanding_preview"]["compiled_id"], compiled_id)
        self.assertEqual(runtime.json()["instruction_understanding_preview"]["compiled_id"], compiled_id)
        self.assertEqual(instructions.json()["instruction_understanding_status"]["compiled_status"], "ready")
        self.assertEqual(runtime.json()["instruction_understanding_status"]["compiled_status"], "ready")

    def test_instruction_get_route_reports_compile_required_when_compiled_data_is_missing(self):
        db_path, _ = _create_builder_db(str(self.tmp_root))

        with mock.patch.dict(os.environ, {"RAGENIUS_BUILDER_DB": db_path}, clear=False):
            with mock.patch(
                "backend.app.main.prepare_instruction_understanding",
                side_effect=AssertionError("prepare should not be called"),
            ) as prepare_mock:
                response = self.client.get("/apps/app-1/instructions", headers={"x-role": "admin"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(prepare_mock.call_count, 0)
        payload = response.json()
        self.assertIsNone(payload["instruction_understanding_status"].get("compiled_status"))
        self.assertIsNone(payload["instruction_understanding_preview"]["compiled_id"])
        self.assertTrue(payload["instruction_understanding_preview"]["compile_required"])

    def test_instruction_get_route_rehydrates_compiled_data_from_snapshot_after_repo_reset(self):
        db_path, _ = _create_builder_db(str(self.tmp_root))

        def fake_compiler(_context):
            return {
                "app_semantic_model": {
                    "primary_service_mode": "single_default_workflow",
                    "default_workflow_id": "workflow:default",
                    "service_blocks": [
                        {
                            "block_id": "workflow:default",
                            "block_type": "primary_workflow",
                            "title": "Interaction Logic & Execution Flow",
                            "is_default": True,
                        }
                    ],
                    "procedures": [],
                    "procedure_steps": [],
                    "role_profiles": [],
                    "routing_rules": [],
                    "clarification_gate_rules": [],
                }
            }

        with mock.patch.dict(os.environ, {"RAGENIUS_BUILDER_DB": db_path}, clear=False):
            with mock.patch("backend.app.main.build_instruction_understanding_compiler", return_value=fake_compiler):
                seeded = self.client.post(
                    "/apps/app-1/instruction-understanding/recompile",
                    headers={"x-role": "admin"},
                )
            self.assertEqual(seeded.status_code, 200)
            compiled_id = seeded.json()["compiled"]["id"]
            instruction_understanding_repo.reset()

            with mock.patch(
                "backend.app.main.prepare_instruction_understanding",
                side_effect=AssertionError("prepare should not be called"),
            ):
                response = self.client.get("/apps/app-1/instructions", headers={"x-role": "admin"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["instruction_understanding_preview"]["compiled_id"], compiled_id)
        self.assertEqual(payload["instruction_understanding_status"]["compiled_status"], "ready")
        self.assertFalse(payload["instruction_understanding_preview"]["compile_required"])

    def test_instruction_understanding_review_route_runs_reviewer_and_returns_review_payload(self):
        db_path, _ = _create_builder_db(str(self.tmp_root))

        def fake_reviewer(compiled_record):
            self.assertEqual(compiled_record["compiled_status"], "ready")
            return {
                "review_status": "reviewed_with_warnings",
                "review_confidence": 0.67,
                "review_findings": {"warnings": ["ambiguous workflow trigger"]},
                "review_summary_md": "# Review\n\nWarning.\n",
                "review_recommendations": {"next_step": "inspect"},
            }

        with mock.patch.dict(os.environ, {"RAGENIUS_BUILDER_DB": db_path}, clear=False):
            seeded = self.client.post(
                "/apps/app-1/instruction-understanding/recompile",
                headers={"x-role": "admin"},
            )
            self.assertEqual(seeded.status_code, 200)
            with mock.patch("backend.app.main.build_instruction_understanding_reviewer", return_value=fake_reviewer):
                response = self.client.post(
                    "/apps/app-1/instruction-understanding/review",
                    headers={"x-role": "admin"},
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["review"]["review_status"], "reviewed_with_warnings")
        self.assertEqual(payload["status"]["review_status"], "reviewed_with_warnings")
        self.assertEqual(payload["compiled"]["compiled_status"], "ready")

    def test_instruction_get_route_surfaces_semantic_compile_flags_when_compiler_is_available(self):
        db_path, _ = _create_builder_db(str(self.tmp_root))

        def fake_compiler(context):
            self.assertIn("structural_candidate_graph", context)
            return {
                "app_semantic_model": {
                    "primary_service_mode": "single_default_workflow",
                    "default_workflow_id": "workflow:default",
                    "global_app_contract": {"mission": "Help users design prompts"},
                    "interaction_logic_blocks": [],
                    "role_profiles": [],
                    "routing_rules": [],
                    "module_orchestration": None,
                    "service_blocks": [
                        {
                            "block_id": "workflow:default",
                            "block_type": "primary_workflow",
                            "title": "Interaction Logic & Execution Flow",
                            "is_default": True,
                        }
                    ],
                    "procedures": [],
                    "procedure_steps": [],
                    "clarification_gate_rules": [],
                    "resource_bindings": [],
                    "semantic_warnings": [],
                    "semantic_confidence": 0.9,
                }
            }

        with mock.patch.dict(os.environ, {"RAGENIUS_BUILDER_DB": db_path}, clear=False):
            with mock.patch("backend.app.main.build_instruction_understanding_compiler", return_value=fake_compiler):
                seeded = self.client.post(
                    "/apps/app-1/instruction-understanding/recompile",
                    headers={"x-role": "admin"},
                )
                self.assertEqual(seeded.status_code, 200)
                response = self.client.get("/apps/app-1/instructions", headers={"x-role": "admin"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["instruction_understanding_status"]["compiled_status"], "ready")
        self.assertTrue(payload["instruction_understanding_preview"]["semantic_compile_attached"])
        self.assertTrue(payload["instruction_understanding_preview"]["semantic_compile_valid"])

    def test_instruction_get_route_surfaces_stale_semantic_compiler_status(self):
        db_path, instructions_path = _create_builder_db(str(self.tmp_root))
        compile_root = self.tmp_root / "semantic_stale"
        compile_root.mkdir(parents=True, exist_ok=True)
        with mock.patch.dict(os.environ, {"RAGENIUS_BUILDER_DB": db_path}, clear=False):
            builder_store = backend_main.get_builder_store()
            compile_instruction_understanding(
                app_id="app-1",
                instruction_text=Path(instructions_path).read_text(encoding="utf-8"),
                instruction_uri="instructions/app-1/instructions.md",
                instruction_source_version=3,
                documents=builder_store.list_documents("app-1"),
                repo=instruction_understanding_repo,
                snapshot_root=compile_root,
                semantic_compiler=lambda _context: {
                    "app_semantic_model": {
                        "primary_service_mode": "single_default_workflow",
                        "default_workflow_id": "workflow:default",
                        "service_blocks": [
                            {
                                "block_id": "workflow:default",
                                "block_type": "primary_workflow",
                                "title": "Interaction Logic & Execution Flow",
                                "is_default": True,
                            }
                        ],
                        "procedures": [],
                        "procedure_steps": [],
                        "role_profiles": [],
                        "routing_rules": [],
                        "clarification_gate_rules": [],
                    }
                },
                semantic_compiler_version="semantic-v1",
            )

        def fake_compiler(_context):
            return {}

        with mock.patch.dict(os.environ, {"RAGENIUS_BUILDER_DB": db_path}, clear=False):
            with mock.patch("backend.app.main.build_instruction_understanding_compiler", return_value=fake_compiler):
                response = self.client.get("/apps/app-1/instructions", headers={"x-role": "admin"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["instruction_understanding_status"]["cache_status"], "stale_semantic_compiler")
        self.assertIn(
            "semantic_compiler_version",
            payload["instruction_understanding_status"]["stale_reasons"],
        )

    def test_legacy_collection_endpoints_are_removed(self):
        response = self.client.get("/collections/app-1/config/latest", headers={"x-role": "admin"})
        self.assertEqual(response.status_code, 404)

    def test_session_workflow_status_and_advance_endpoint(self):
        db_path, _ = _create_builder_db(str(self.tmp_root))

        with mock.patch.dict(os.environ, {"RAGENIUS_BUILDER_DB": db_path}, clear=False):
            session_repo.get_or_create(
                "s-workflow",
                collection_id="app-1",
                user_id="u1",
                config_version=1,
                adapter_version=1,
                template_version=1,
            )
            session_repo.set_workflow_progress(
                "s-workflow",
                {
                    "workflow_id": "bible_study",
                    "workflow_title": "Bible Study",
                    "step_order": 1,
                    "step_title": "ç´°å¯Ÿäº‹å¯¦ (Observation)",
                    "resource_file": "observation_guide.md",
                },
            )

            list_response = self.client.get("/apps/app-1/sessions?user_id=u1")
            messages_response = self.client.get("/sessions/s-workflow/messages?app_id=app-1&user_id=u1")
            advance_response = self.client.post(
                "/sessions/s-workflow/workflow/advance",
                json={"app_id": "app-1", "user_id": "u1"},
            )

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(messages_response.status_code, 200)
        self.assertEqual(advance_response.status_code, 200)
        sessions = list_response.json()["sessions"]
        self.assertEqual(sessions[0]["workflow_status"]["current_step"]["order"], 1)
        self.assertEqual(sessions[0]["workflow_status"]["next_step"]["order"], 2)
        self.assertEqual(messages_response.json()["workflow_status"]["current_step"]["resource_file"], "observation_guide.md")
        self.assertEqual(advance_response.json()["workflow_status"]["current_step"]["order"], 2)
        self.assertIsNone(advance_response.json()["workflow_status"]["next_step"])

    def test_session_workflow_routes_do_not_force_prepare_side_effects(self):
        db_path, _ = _create_builder_db(str(self.tmp_root))

        with mock.patch.dict(os.environ, {"RAGENIUS_BUILDER_DB": db_path}, clear=False):
            session_repo.get_or_create(
                "s-workflow-readonly",
                collection_id="app-1",
                user_id="u1",
                config_version=1,
                adapter_version=1,
                template_version=1,
            )
            session_repo.set_workflow_progress(
                "s-workflow-readonly",
                {
                    "workflow_id": "bible_study",
                    "workflow_title": "Bible Study",
                    "step_order": 1,
                    "step_title": "Ã§Â´Â°Ã¥Â¯Å¸Ã¤Âºâ€¹Ã¥Â¯Â¦ (Observation)",
                    "resource_file": "observation_guide.md",
                },
            )

            with mock.patch(
                "backend.app.main.prepare_instruction_understanding",
                side_effect=AssertionError("prepare should not be called"),
            ):
                list_response = self.client.get("/apps/app-1/sessions?user_id=u1")
                messages_response = self.client.get("/sessions/s-workflow-readonly/messages?app_id=app-1&user_id=u1")
                advance_response = self.client.post(
                    "/sessions/s-workflow-readonly/workflow/advance",
                    json={"app_id": "app-1", "user_id": "u1"},
                )

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(messages_response.status_code, 200)
        self.assertEqual(advance_response.status_code, 200)
        self.assertEqual(list_response.json()["sessions"][0]["workflow_status"]["current_step"]["order"], 1)
        self.assertEqual(messages_response.json()["workflow_status"]["current_step"]["resource_file"], "observation_guide.md")
        self.assertEqual(advance_response.json()["workflow_status"]["current_step"]["order"], 2)

    def test_session_messages_workflow_status_prefers_latest_assistant_runtime_snapshot(self):
        db_path, _ = _create_builder_db(str(self.tmp_root))

        with mock.patch.dict(os.environ, {"RAGENIUS_BUILDER_DB": db_path}, clear=False):
            session_repo.get_or_create(
                "s-bundled-stale",
                collection_id="app-1",
                user_id="u1",
                config_version=1,
                adapter_version=1,
                template_version=1,
            )
            session_repo.set_workflow_progress(
                "s-bundled-stale",
                {
                    "workflow_id": "bible_study",
                    "workflow_title": "Bible Study",
                    "step_order": 1,
                    "step_title": "Observation",
                    "resource_file": "observation_guide.md",
                },
            )
            chat_repo.append(
                "s-bundled-stale",
                "assistant",
                "Generated bundled answer",
                retrieval_summary={
                    "primary_scope": {
                        "scope_id": "workflow:bible_study",
                        "scope_type": "workflow",
                        "title": "Bible Study",
                    },
                    "active_step_scope": {
                        "scope_id": "step:bible_study:1",
                        "scope_type": "step",
                        "title": "Observation",
                        "step_order": 1,
                    },
                    "session_execution_state": {
                        "execution_status": "guiding",
                        "active_execution_mode": "bundled",
                        "primary_scope_id": "workflow:bible_study",
                        "primary_scope_type": "workflow",
                        "primary_scope_title": "Bible Study",
                        "active_step_scope_id": "step:bible_study:1",
                        "active_step_order": 1,
                        "active_step_title": "Observation",
                        "bundled_execution_completed": True,
                    },
                },
            )

            messages_response = self.client.get("/sessions/s-bundled-stale/messages?app_id=app-1&user_id=u1")

        self.assertEqual(messages_response.status_code, 200)
        workflow_status = messages_response.json()["workflow_status"]
        self.assertEqual(workflow_status["workflow_id"], "bible_study")
        self.assertEqual(workflow_status["current_step"]["order"], 1)
        self.assertTrue(workflow_status["bundled_execution_completed"])
        self.assertEqual(workflow_status["active_execution_mode"], "bundled")
        self.assertIsNone(workflow_status["next_step"])

    def test_session_messages_workflow_status_uses_last_usable_assistant_runtime_state(self):
        db_path, _ = _create_builder_db(str(self.tmp_root))

        with mock.patch.dict(os.environ, {"RAGENIUS_BUILDER_DB": db_path}, clear=False):
            session_repo.get_or_create(
                "s-runtime-history",
                collection_id="app-1",
                user_id="u1",
                config_version=1,
                adapter_version=1,
                template_version=1,
            )
            chat_repo.append(
                "s-runtime-history",
                "assistant",
                "Step-guided question",
                retrieval_summary={
                    "primary_scope": {
                        "scope_id": "workflow:bible_study",
                        "scope_type": "workflow",
                        "title": "Bible Study",
                    },
                    "active_step_scope": {
                        "scope_id": "step:bible_study:2",
                        "scope_type": "step",
                        "title": "Identify Relationships",
                        "step_order": 2,
                    },
                    "session_execution_state": {
                        "execution_status": "guiding",
                        "primary_scope_id": "workflow:bible_study",
                        "primary_scope_type": "workflow",
                        "primary_scope_title": "Bible Study",
                        "active_step_scope_id": "step:bible_study:2",
                        "active_step_order": 2,
                        "active_step_title": "Identify Relationships",
                    },
                },
            )
            chat_repo.append(
                "s-runtime-history",
                "assistant",
                "Final answer without scope metadata",
                retrieval_summary={
                    "session_execution_state": {
                        "execution_status": "answering",
                    }
                },
            )

            messages_response = self.client.get("/sessions/s-runtime-history/messages?app_id=app-1&user_id=u1")

        self.assertEqual(messages_response.status_code, 200)
        workflow_status = messages_response.json()["workflow_status"]
        self.assertEqual(workflow_status["workflow_id"], "bible_study")
        self.assertEqual(workflow_status["current_step"]["order"], 2)
        self.assertEqual(workflow_status["current_step"]["title"], "Identify Relationships")

    def test_session_messages_preserve_distinct_workflow_status_for_each_assistant_turn(self):
        db_path, _ = _create_builder_db(str(self.tmp_root))

        with mock.patch.dict(os.environ, {"RAGENIUS_BUILDER_DB": db_path}, clear=False):
            session_repo.get_or_create(
                "s-turn-history",
                collection_id="app-1",
                user_id="u1",
                config_version=1,
                adapter_version=1,
                template_version=1,
            )
            for order, title in ((1, "Observation"), (2, "Identify Relationships")):
                chat_repo.append(
                    "s-turn-history",
                    "assistant",
                    f"Turn {order}",
                    retrieval_summary={
                        "workflow_progress": {
                            "workflow_id": "bible_study",
                            "workflow_title": "Bible Study",
                            "step_order": order,
                            "step_title": title,
                        },
                        "session_execution_state": {
                            "execution_status": "guiding",
                            "primary_scope_id": "workflow:bible_study",
                            "primary_scope_type": "workflow",
                            "primary_scope_title": "Bible Study",
                            "active_step_scope_id": f"step:bible_study:{order}",
                            "active_step_order": order,
                            "active_step_title": title,
                        },
                    },
                )

            messages_response = self.client.get("/sessions/s-turn-history/messages?app_id=app-1&user_id=u1")

        self.assertEqual(messages_response.status_code, 200)
        messages = messages_response.json()["messages"]
        self.assertEqual(messages[0]["workflow_status"]["current_step"]["order"], 1)
        self.assertEqual(messages[0]["workflow_status"]["current_step"]["title"], "Observation")
        self.assertEqual(messages[1]["workflow_status"]["current_step"]["order"], 2)
        self.assertEqual(messages[1]["workflow_status"]["current_step"]["title"], "Identify Relationships")

    def test_session_messages_workflow_status_surfaces_active_followup_module_scope(self):
        db_path, _ = _create_builder_db(str(self.tmp_root))

        with mock.patch.dict(os.environ, {"RAGENIUS_BUILDER_DB": db_path}, clear=False):
            session_repo.get_or_create(
                "s-followup-runtime",
                collection_id="app-1",
                user_id="u1",
                title="Followup runtime session",
                config_version=1,
                adapter_version=1,
                template_version=1,
            )
            chat_repo.append(
                "s-followup-runtime",
                "assistant",
                "Optimization followup",
                retrieval_summary={
                    "primary_scope": {
                        "scope_id": "workflow:interaction_logic_execution_flow",
                        "scope_type": "workflow",
                        "title": "Interaction Logic & Execution Flow",
                    },
                    "session_execution_state": {
                        "primary_scope_id": "workflow:interaction_logic_execution_flow",
                        "primary_scope_type": "workflow",
                        "primary_scope_title": "Interaction Logic & Execution Flow",
                        "active_service_block_id": "followup_module:optimization_module",
                        "active_service_block_type": "followup_module",
                        "active_service_block_title": "Optimization Module",
                        "execution_status": "guiding",
                        "bundled_execution_completed": True,
                        "active_execution_mode": None,
                    },
                },
            )

            messages_response = self.client.get("/sessions/s-followup-runtime/messages?app_id=app-1&user_id=u1")

        self.assertEqual(messages_response.status_code, 200)
        workflow_status = messages_response.json()["workflow_status"]
        self.assertEqual(workflow_status["workflow_id"], "interaction_logic_execution_flow")
        self.assertEqual(workflow_status["current_step"]["title"], "Optimization Module")
        self.assertIsNone(workflow_status["current_step"]["order"])
        self.assertEqual(workflow_status["active_service_block_type"], "followup_module")
        self.assertEqual(workflow_status["active_service_block_id"], "followup_module:optimization_module")
        self.assertEqual(workflow_status["active_service_block_title"], "Optimization Module")
        self.assertIsNone(workflow_status["next_step"])

    def test_session_messages_workflow_status_shows_life_application_for_life_guidance_starter(self):
        db_path, _ = _create_builder_db(str(self.tmp_root))

        with mock.patch.dict(os.environ, {"RAGENIUS_BUILDER_DB": db_path}, clear=False):
            session_repo.get_or_create(
                "s-life-application-runtime",
                collection_id="app-1",
                user_id="u1",
                title="Life application runtime session",
                config_version=1,
                adapter_version=1,
                template_version=1,
            )
            chat_repo.append(
                "s-life-application-runtime",
                "assistant",
                "Life application starter",
                retrieval_summary={
                    "session_execution_state": {
                        "selected_routing_rule_id": "route_to_life_application",
                        "active_mode": "mode_life_application",
                        "active_workflow": "\u751f\u6d3b\u61c9\u7528\u6a21\u5f0f\uff08Life Application\uff09",
                        "active_step_title": "\u751f\u6d3b\u61c9\u7528\u6a21\u5f0f\uff08Life Application\uff09",
                        "primary_scope_id": "mode_life_application",
                        "primary_scope_type": "mode",
                        "primary_scope_title": "\u751f\u6d3b\u61c9\u7528\u6a21\u5f0f\uff08Life Application\uff09",
                        "execution_status": "guiding",
                        "workflow_progress": {},
                    },
                },
            )

            messages_response = self.client.get(
                "/sessions/s-life-application-runtime/messages?app_id=app-1&user_id=u1"
            )

        self.assertEqual(messages_response.status_code, 200)
        workflow_status = messages_response.json()["workflow_status"]
        self.assertIsNone(workflow_status["workflow_id"])
        self.assertEqual(
            workflow_status["workflow_title"],
            "\u751f\u6d3b\u61c9\u7528\u6a21\u5f0f\uff08Life Application\uff09",
        )
        self.assertIsNone(workflow_status["current_step"]["order"])
        self.assertEqual(
            workflow_status["current_step"]["title"],
            "\u751f\u6d3b\u61c9\u7528\u6a21\u5f0f\uff08Life Application\uff09",
        )

    def test_session_messages_workflow_status_shows_parenting_route_when_role_target_should_bind_workflow(self):
        db_path, _ = _create_builder_db(str(self.tmp_root))

        with mock.patch.dict(os.environ, {"RAGENIUS_BUILDER_DB": db_path}, clear=False):
            session_repo.get_or_create(
                "s-parenting-runtime",
                collection_id="app-1",
                user_id="u1",
                title="Parenting runtime session",
                config_version=1,
                adapter_version=1,
                template_version=1,
            )
            chat_repo.append(
                "s-parenting-runtime",
                "assistant",
                "Parenting role route",
                retrieval_summary={
                    "session_execution_state": {
                        "active_role_id": "role:consultant",
                        "selected_routing_rule_id": "route:consultant",
                        "active_mode": "3x1\u5efa\u8b70\u6e05\u55ae\u6cd5",
                        "active_workflow": "3x1 \u5efa\u8b70\u6e05\u55ae\u6d41\u7a0b",
                        "active_step_order": 1,
                        "active_step_title": "\u63d0\u4f9b\u4e09\u500b\u5efa\u8b70\u8207\u4e00\u500b\u7acb\u5373\u884c\u52d5",
                        "active_service_block_type": "primary_workflow",
                        "active_service_block_id": "workflow:3x1\u5efa\u8b70\u6e05\u55ae\u6cd5",
                        "active_service_block_title": "3x1 \u5efa\u8b70\u6e05\u55ae\u6d41\u7a0b",
                        "primary_scope_id": "workflow:3x1\u5efa\u8b70\u6e05\u55ae\u6cd5",
                        "primary_scope_type": "workflow",
                        "primary_scope_title": "3x1 \u5efa\u8b70\u6e05\u55ae\u6d41\u7a0b",
                        "active_step_scope_id": "step:consultant:1",
                        "execution_status": "answering",
                        "workflow_progress": {
                            "workflow_id": "3x1\u5efa\u8b70\u6e05\u55ae\u6cd5",
                            "workflow_title": "3x1 \u5efa\u8b70\u6e05\u55ae\u6d41\u7a0b",
                            "step_order": 1,
                            "step_title": "\u63d0\u4f9b\u4e09\u500b\u5efa\u8b70\u8207\u4e00\u500b\u7acb\u5373\u884c\u52d5",
                        },
                    },
                },
            )

            messages_response = self.client.get("/sessions/s-parenting-runtime/messages?app_id=app-1&user_id=u1")

        self.assertEqual(messages_response.status_code, 200)
        workflow_status = messages_response.json()["workflow_status"]
        self.assertEqual(
            workflow_status.get("workflow_id"),
            "3x1\u5efa\u8b70\u6e05\u55ae\u6cd5",
        )
        self.assertEqual(
            workflow_status.get("workflow_title"),
            "3x1 \u5efa\u8b70\u6e05\u55ae\u6d41\u7a0b",
        )
        current_step = workflow_status.get("current_step") or {}
        self.assertEqual(current_step.get("order"), 1)
        self.assertEqual(
            current_step.get("title"),
            "\u63d0\u4f9b\u4e09\u500b\u5efa\u8b70\u8207\u4e00\u500b\u7acb\u5373\u884c\u52d5",
        )

    def test_session_messages_workflow_status_shows_optimization_module_when_optimization_turn_is_active(self):
        db_path, _ = _create_builder_db(str(self.tmp_root))

        with mock.patch.dict(os.environ, {"RAGENIUS_BUILDER_DB": db_path}, clear=False):
            session_repo.get_or_create(
                "s-optimization-runtime",
                collection_id="app-1",
                user_id="u1",
                title="Optimization runtime session",
                config_version=1,
                adapter_version=1,
                template_version=1,
            )
            chat_repo.append(
                "s-optimization-runtime",
                "assistant",
                "Optimization turn",
                retrieval_summary={
                    "session_execution_state": {
                        "primary_scope_id": "workflow:interaction_logic_execution_flow",
                        "primary_scope_type": "workflow",
                        "primary_scope_title": "Interaction Logic & Execution Flow",
                        "active_mode": "interaction_logic_execution_flow",
                        "active_workflow": "Interaction Logic & Execution Flow",
                        "active_step_title": "Optimization Module",
                        "active_service_block_type": "followup_module",
                        "active_service_block_id": "followup_module:optimization_module",
                        "active_service_block_title": "Optimization Module",
                        "primary_support_module_id": "followup_module:optimization_module",
                        "primary_support_module_title": "Optimization Module",
                        "execution_status": "answering",
                        "workflow_progress": {
                            "workflow_id": "interaction_logic_execution_flow",
                            "workflow_title": "Interaction Logic & Execution Flow",
                            "step_title": "Optimization Module",
                        },
                    },
                },
            )

            messages_response = self.client.get("/sessions/s-optimization-runtime/messages?app_id=app-1&user_id=u1")

        self.assertEqual(messages_response.status_code, 200)
        workflow_status = messages_response.json()["workflow_status"]
        self.assertEqual(workflow_status["workflow_id"], "interaction_logic_execution_flow")
        self.assertEqual(workflow_status["current_step"]["title"], "Optimization Module")
        self.assertIsNone(workflow_status["current_step"]["order"])
        self.assertEqual(workflow_status["active_service_block_type"], "followup_module")
        self.assertEqual(workflow_status["active_service_block_id"], "followup_module:optimization_module")
        self.assertEqual(workflow_status["active_service_block_title"], "Optimization Module")

    def test_session_messages_workflow_status_shows_core_workflow_when_bundled_step_two_is_active(self):
        db_path, _ = _create_builder_db(str(self.tmp_root))

        with mock.patch.dict(os.environ, {"RAGENIUS_BUILDER_DB": db_path}, clear=False):
            session_repo.get_or_create(
                "s-core-workflow-runtime",
                collection_id="app-1",
                user_id="u1",
                title="Core workflow runtime session",
                config_version=1,
                adapter_version=1,
                template_version=1,
            )
            chat_repo.append(
                "s-core-workflow-runtime",
                "assistant",
                "Core workflow turn",
                retrieval_summary={
                    "session_execution_state": {
                        "primary_scope_id": "workflow:interaction_logic_execution_flow",
                        "primary_scope_type": "workflow",
                        "primary_scope_title": "Interaction Logic & Execution Flow",
                        "active_mode": "interaction_logic_execution_flow",
                        "active_workflow": "Interaction Logic & Execution Flow",
                        "active_step_order": 2,
                        "active_step_title": "Core Workflow",
                        "active_execution_mode": "bundled",
                        "active_step_scope_id": "step:core_workflow_execution",
                        "execution_status": "guiding",
                        "workflow_progress": {
                            "workflow_id": "interaction_logic_execution_flow",
                            "workflow_title": "Interaction Logic & Execution Flow",
                            "step_order": 2,
                            "step_title": "Core Workflow",
                        },
                    },
                },
            )

            messages_response = self.client.get("/sessions/s-core-workflow-runtime/messages?app_id=app-1&user_id=u1")

        self.assertEqual(messages_response.status_code, 200)
        workflow_status = messages_response.json()["workflow_status"]
        self.assertEqual(workflow_status["workflow_id"], "interaction_logic_execution_flow")
        self.assertEqual(workflow_status["current_step"]["order"], 2)
        self.assertEqual(workflow_status["current_step"]["title"], "Core Workflow")
        self.assertEqual(workflow_status["active_execution_mode"], "bundled")

    def test_session_messages_surface_configured_and_latest_turn_task_models(self):
        db_path, _ = _create_builder_db(str(self.tmp_root))

        with mock.patch.dict(os.environ, {"RAGENIUS_BUILDER_DB": db_path}, clear=False):
            session_repo.get_or_create(
                "s-model-diagnostics",
                collection_id="app-1",
                user_id="u1",
                title="Model diagnostics session",
                config_version=1,
                adapter_version=1,
                template_version=1,
            )
            chat_repo.append(
                "s-model-diagnostics",
                "assistant",
                "Model-aware answer",
                retrieval_summary={
                    "task_model_diagnostics": {
                        "configured_task_models": {
                            "planner": {
                                "provider": "deepseek",
                                "model": "deepseek-v4-pro",
                                "temperature": 0.1,
                            },
                            "answer_generation": {
                                "provider": "deepseek",
                                "model": "deepseek-v4-flash",
                                "temperature": 0.2,
                            },
                        },
                        "selected_task_models": {
                            "planner": {
                                "provider": "deepseek",
                                "model": "deepseek-v4-pro",
                                "temperature": 0.1,
                                "selected_source": "builder_task_model",
                            },
                            "answer_generation": {
                                "provider": "deepseek",
                                "model": "deepseek-v4-flash",
                                "temperature": 0.2,
                                "selected_source": "builder_task_model",
                            },
                        },
                    }
                },
            )

            response = self.client.get("/sessions/s-model-diagnostics/messages?app_id=app-1&user_id=u1")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("model_diagnostics", body)
        self.assertEqual(
            body["model_diagnostics"]["configured_task_models"]["planner"]["model"],
            "deepseek-v4-pro",
        )
        self.assertEqual(
            body["model_diagnostics"]["latest_turn_task_models"]["answer_generation"]["model"],
            "deepseek-v4-flash",
        )
        db_path, _ = _create_builder_db(str(self.tmp_root))

        with mock.patch.dict(os.environ, {"RAGENIUS_BUILDER_DB": db_path}, clear=False):
            session_repo.get_or_create(
                "s-support-runtime",
                collection_id="app-1",
                user_id="u1",
                title="Support runtime session",
                config_version=1,
                adapter_version=1,
                template_version=1,
            )
            chat_repo.append(
                "s-support-runtime",
                "assistant",
                "Bible study module activated",
                retrieval_summary={
                    "primary_scope": {
                        "scope_id": "interaction_logic_block:mode_bible_study",
                        "scope_type": "response_logic",
                        "title": "æŸ¥è€ƒç¶“æ–‡æ¨¡å¼",
                    },
                    "active_step_scope": {
                        "scope_id": "step:support_module:bible_study:1",
                        "scope_type": "step",
                        "title": "ç´°å¯Ÿäº‹å¯¦",
                        "step_order": 1,
                    },
                    "session_execution_state": {
                        "primary_scope_id": "interaction_logic_block:mode_bible_study",
                        "primary_scope_type": "response_logic",
                        "primary_scope_title": "æŸ¥è€ƒç¶“æ–‡æ¨¡å¼",
                        "active_service_block_id": "support_module:bible_study",
                        "active_service_block_type": "support_module",
                        "active_service_block_title": "æŸ¥ç¶“äº’å‹•æ¨¡çµ„",
                        "primary_support_module_id": "support_module:bible_study",
                        "primary_support_module_title": "æŸ¥ç¶“äº’å‹•æ¨¡çµ„",
                        "active_step_scope_id": "step:support_module:bible_study:1",
                        "active_step_order": 1,
                        "active_step_title": "ç´°å¯Ÿäº‹å¯¦",
                        "execution_status": "guiding",
                    },
                },
            )

            messages_response = self.client.get("/sessions/s-support-runtime/messages?app_id=app-1&user_id=u1")

        self.assertEqual(messages_response.status_code, 200)
        workflow_status = messages_response.json()["workflow_status"]
        self.assertIsNone(workflow_status["workflow_id"])
        self.assertEqual(workflow_status["current_step"]["order"], 1)
        self.assertEqual(workflow_status["current_step"]["title"], "ç´°å¯Ÿäº‹å¯¦")
        self.assertEqual(workflow_status["active_service_block_type"], "support_module")
        self.assertEqual(workflow_status["active_service_block_id"], "support_module:bible_study")
        self.assertEqual(workflow_status["active_service_block_title"], "æŸ¥ç¶“äº’å‹•æ¨¡çµ„")

    def test_session_upload_endpoint_and_chat_state_include_uploaded_artifact(self):
        db_path, _ = _create_builder_db(str(self.tmp_root))
        captured = {"calls": []}

        def fake_run_chat_pipeline(state, **kwargs):
            captured["calls"].append(state)
            return {
                "content": "artifact analysis",
                "citations": [],
                "missing_infoTypes": [],
                "retrieval_summary": {"session_upload_retrieved_count": 1},
                "turn_execution_plan": {"turn_intent": "analyze_upload", "actions": [{"action_type": "respond_to_user"}]},
                "session_execution_state": {"active_session_upload_ids": state.get("session_upload_event_ids", [])},
            }

        with mock.patch.dict(os.environ, {"RAGENIUS_BUILDER_DB": db_path}, clear=False):
            with mock.patch("backend.app.main.run_chat_pipeline", side_effect=fake_run_chat_pipeline):
                upload_response = self.client.post(
                    "/sessions/s-upload/uploads",
                    data={"app_id": "app-1", "user_id": "u1"},
                    files={"file": ("artifact.md", b"# Draft\nUploaded artifact", "text/markdown")},
                )
                self.assertEqual(upload_response.status_code, 200)
                self.assertTrue(upload_response.json()["upload"]["has_text_content"])
                self.assertEqual(upload_response.json()["content"], "artifact analysis")
                self.assertEqual(upload_response.json()["retrieval_summary"]["session_upload_retrieved_count"], 1)
                self.assertEqual(upload_response.json()["turn_execution_plan"]["turn_intent"], "analyze_upload")
                self.assertEqual(captured["calls"][0]["turn_input_type"], "session_upload")
                self.assertEqual(captured["calls"][0]["pending_upload_analysis"], True)
                self.assertEqual(captured["calls"][0]["session_upload_event_ids"], [upload_response.json()["upload"]["id"]])
                self.assertEqual(len(captured["calls"][0]["session_uploads"]), 1)

            list_response = self.client.get("/sessions/s-upload/uploads?app_id=app-1&user_id=u1")
            self.assertEqual(list_response.status_code, 200)
            self.assertEqual(len(list_response.json()["uploads"]), 1)

            chat_calls = {}

            def fake_chat_pipeline(state, **kwargs):
                chat_calls["state"] = state
                return {"content": "artifact analysis", "citations": [], "missing_infoTypes": []}

            with mock.patch("backend.app.main.run_chat_pipeline", side_effect=fake_chat_pipeline):
                chat_response = self.client.post(
                    "/sessions/s-upload/chat",
                    json={
                        "user_id": "u1",
                        "app_id": "app-1",
                        "user_query": "Analyze this uploaded artifact",
                        "template_version": 1,
                    },
                )

        self.assertEqual(chat_response.status_code, 200)
        self.assertEqual(chat_response.json()["content"], "artifact analysis")
        self.assertEqual(len(chat_calls["state"]["session_uploads"]), 1)
        self.assertEqual(chat_calls["state"]["session_uploads"][0]["filename"], "artifact.md")

    def test_chat_route_does_not_auto_prepare_instruction_understanding_on_cache_miss(self):
        db_path, _ = _create_builder_db(str(self.tmp_root))

        captured = {}

        def fake_chat_pipeline(state, **kwargs):
            captured["state"] = state
            return {"content": "ok", "citations": [], "missing_infoTypes": []}

        with mock.patch.dict(os.environ, {"RAGENIUS_BUILDER_DB": db_path}, clear=False):
            instruction_understanding_repo.reset()
            with mock.patch(
                "backend.app.main.prepare_instruction_understanding",
                side_effect=AssertionError("chat should not auto-prepare instruction understanding"),
            ):
                with mock.patch("backend.app.main.run_chat_pipeline", side_effect=fake_chat_pipeline):
                    response = self.client.post(
                        "/sessions/s-no-auto-prepare/chat",
                        json={
                            "user_id": "u1",
                            "app_id": "app-1",
                            "user_query": "Test chat request",
                            "template_version": 1,
                        },
                    )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["content"], "ok")
        template_registry = captured["state"]["template_registry"]
        self.assertEqual(template_registry["compiled_instruction_understanding"], {})

    def test_bible_tutor_three_turn_flow_via_api(self):
        db_path, instructions_path = _create_builder_db(str(self.tmp_root))
        Path(instructions_path).write_text(
            """
## è§’è‰²å®šä½
ä½ æ˜¯ä¸€ä½å°ˆæ¥­è–ç¶“å°Žå¸«ã€‚

## ä¸»è¦ç›®æ¨™
1. å¾ªåºæ¼¸é€²å¸¶é ˜å­¸å“¡æŸ¥ç¶“

## æ•™å°Žé¢¨æ ¼
- ä»¥æå•å¼•å°Žå­¸ç¿’

## æ¨¡å¼è‡ªå‹•è­˜åˆ¥ï¼ˆMode Detectionï¼‰
â€¢ æŸ¥è€ƒç¶“æ–‡æ¨¡å¼ï¼ˆBible Studyï¼‰
  o è§¸ç™¼ï¼šè¼¸å…¥å«ã€ŒæŸ¥è€ƒã€ã€Œç ”ç¶“ã€ã€Œç¶“æ–‡ã€ç­‰å­—ã€‚
  o å›žæ‡‰ï¼šã€Œå¥½çš„ï¼Œæˆ‘å€‘ä¸€èµ·ç”¨æ­¸ç´é‡‹ç¶“æ³•æŸ¥è€ƒç¶“æ–‡ã€‚è«‹å•æƒ³å¾žå“ªä¸€æ®µé–‹å§‹ï¼Ÿã€
  o å•Ÿå‹•å®Œæ•´åæ­¥æ­¸ç´é‡‹ç¶“æµç¨‹: æŸ¥ç¶“äº’å‹•æ¨¡çµ„ã€‚

## æŸ¥ç¶“äº’å‹•æ¨¡çµ„ï¼ˆæ­¸ç´é‡‹ç¶“æ³•çš„åå€‹æ­¥é©Ÿï¼‰
1. ç´°å¯Ÿäº‹å¯¦ (Observation)
ç›®çš„ï¼š å¹«åŠ©å­¸å“¡è§€å¯Ÿç¶“æ–‡çš„å…·é«”ç´°ç¯€ã€‚
ä½¿ç”¨è³‡æºï¼š Resource/ observation_guide.md
æ“ä½œï¼š
â€¢ ä¾è³‡æºä¹‹è§€å¯Ÿé …ç›®ç”¢å‡º 1â€“3 é¡Œï¼Œç­‰å¾…å›žæ‡‰å¾Œå†æŽ¨é€²ã€‚
""".strip(),
            encoding="utf-8",
        )
        guide_dir = self.tmp_root / "instructions" / "app-1"
        guide_path = guide_dir / "observation_guide.md"
        guide_path.write_text(
            "# Observation\nAsk 1-3 observation questions about people, actions, repeated words, and commands.",
            encoding="utf-8",
        )

        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO documents (id, app_id, filename, mime_type, size_bytes, language, tags, file_path, status, error_message, uploaded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "doc-guide",
                "app-1",
                "observation_guide.md",
                "text/markdown",
                len(guide_path.read_text(encoding='utf-8')),
                "zh",
                json.dumps(["instruction"]),
                str(guide_path),
                "ready",
                None,
                "2026-04-25T00:00:00",
            ),
        )
        conn.commit()
        conn.close()

        def fake_task_callable(state, task_name):
            if task_name == "planner":
                return lambda _prompt, _tools, context: {
                    "intentType": "qa",
                    "confidence": 0.95,
                    "steps": [{"id": "1", "title": "Guide the learner", "goal": "Advance Bible study", "reasoning": None}],
                    "infoTypes": ["fact"],
                    "retrievalPlan": {
                        "query_text": str(context.get("user_query") or ""),
                        "top_k": 3,
                        "filters": {"app_id": str(context.get("collection_id") or "")},
                        "explanation": None,
                    },
                    "systemInstructionSummary": {"fromConfigPdf": [], "fromAdapter": [], "fromTemplate": []},
                    "normalizedQuery": str(context.get("user_query") or ""),
                    "contextualQuery": str(context.get("user_query") or ""),
                }
            if task_name == "answer_generation":
                def _answer(_prompt, _tools, context):
                    block = context.get("selected_instruction_block", {}) if isinstance(context.get("selected_instruction_block"), dict) else {}
                    block_type = str(block.get("block_type") or "")
                    query = str(context.get("planner_output", {}).get("normalizedQuery") or "")
                    if block_type == "step" and "ææ‘©å¤ªå‰æ›¸" in query:
                        return {
                            "content": "æˆ‘å€‘å…ˆå¾žè§€å¯Ÿé–‹å§‹ã€‚é€™æ®µç¶“æ–‡ä¸­ï¼Œä¿ç¾…å‘½ä»¤ææ‘©å¤ªè¦åšå“ªäº›äº‹ï¼Ÿ",
                            "citations": [],
                            "missing_infoTypes": [],
                        }
                    if block_type == "step":
                        return {
                            "content": "å¾ˆå¥½ã€‚å†è§€å¯Ÿä¸€ä¸‹ï¼Œé€™æ®µç¶“æ–‡å°ææ‘©å¤ªçš„æ¦œæ¨£æå‡ºäº†å“ªäº›å…·é«”é¢å‘ï¼Ÿ",
                            "citations": [],
                            "missing_infoTypes": [],
                        }
                    return {
                        "content": "Here is the answer based on available evidence.",
                        "citations": [],
                        "missing_infoTypes": [],
                    }
                return _answer
            return None

        def fake_retrieve(_query_text, _top_k, _filters):
            return {"results": [], "debug_trace": {"route": {"model": "knowledge"}}}

        def fake_task_binding(state, task_name):
            selected = fake_task_callable(state, task_name)
            return {
                "callable": selected,
                "diagnostics": {
                    "task_name": task_name,
                    "selected_source": "test-override" if selected is not None else "unconfigured",
                    "configured_model": None,
                },
            }

        with mock.patch.dict(os.environ, {"RAGENIUS_BUILDER_DB": db_path}, clear=False):
            with mock.patch("backend.app.chat_service.maybe_build_task_callable", side_effect=fake_task_callable):
                with mock.patch("backend.app.chat_service.build_task_binding", side_effect=fake_task_binding):
                    with mock.patch("workflows.nodes.retrieve._default_retrieve", side_effect=fake_retrieve):
                        starter = self.client.post(
                            "/sessions/s-bible-flow/chat",
                            json={
                                "user_id": "u1",
                                "app_id": "app-1",
                                "user_query": "æˆ‘æƒ³æŸ¥è€ƒä¸€æ®µç¶“æ–‡",
                                "template_version": 1,
                            },
                        )
                        passage = self.client.post(
                            "/sessions/s-bible-flow/chat",
                            json={
                                "user_id": "u1",
                                "app_id": "app-1",
                                "user_query": "ææ‘©å¤ªå‰æ›¸ 4:11-16",
                                "template_version": 1,
                            },
                        )
                        followup = self.client.post(
                            "/sessions/s-bible-flow/chat",
                            json={
                                "user_id": "u1",
                                "app_id": "app-1",
                                "user_query": "ä¿ç¾…å…ˆå©å’ææ‘©å¤ªè¦æ•™å°Žå’Œå‹¸å‹‰äºº",
                                "template_version": 1,
                            },
                        )
                        messages = self.client.get("/sessions/s-bible-flow/messages?app_id=app-1&user_id=u1")

        self.assertEqual(starter.status_code, 200)
        self.assertTrue(str(starter.json()["content"]).strip())
        self.assertEqual(starter.json()["retrieval_summary"]["instruction_block_type"], "mode")
        self.assertEqual(starter.json()["retrieval_summary"]["instruction_retrieved_count"], 0)

        self.assertEqual(passage.status_code, 200)
        self.assertEqual(passage.json()["retrieval_summary"]["instruction_block_type"], "step")
        self.assertEqual(
            passage.json()["retrieval_summary"]["instruction_resource_context_summary"][0]["filename"],
            "observation_guide.md",
        )
        passage_instruction_files = {
            str(item.get("filename") or "").strip()
            for item in passage.json()["retrieval_summary"]["instruction_resource_context_summary"]
            if str(item.get("filename") or "").strip()
        }
        self.assertEqual(passage_instruction_files, {"observation_guide.md"})
        self.assertEqual(passage.json()["session_execution_state"]["active_step_order"], 1)
        self.assertIn("æˆ‘å€‘å…ˆå¾žè§€å¯Ÿé–‹å§‹", passage.json()["content"])
        self.assertEqual(passage.json()["turn_execution_plan"]["turn_intent"], "start")
        self.assertEqual(passage.json()["turn_execution_plan"]["primary_scope"]["scope_type"], "workflow")
        self.assertEqual(
            passage.json()["retrieval_summary"]["active_step_scope"]["scope_type"],
            "step",
        )

        self.assertEqual(followup.status_code, 200)
        self.assertEqual(followup.json()["retrieval_summary"]["instruction_block_type"], "step")
        self.assertEqual(followup.json()["session_execution_state"]["active_step_order"], 1)
        self.assertTrue(str(followup.json()["content"]).strip())
        self.assertEqual(followup.json()["turn_execution_plan"]["turn_intent"], "answer_prior_questions")

        self.assertEqual(messages.status_code, 200)
        body = messages.json()
        self.assertGreaterEqual(len(body["messages"]), 6)
        self.assertEqual(body["workflow_status"]["current_step"]["order"], 1)
        assistant_messages = [item for item in body["messages"] if item.get("role") == "assistant"]
        first_summary = assistant_messages[0].get("retrievalSummary") or assistant_messages[0].get("retrieval_summary") or {}
        second_summary = assistant_messages[1].get("retrievalSummary") or assistant_messages[1].get("retrieval_summary") or {}
        self.assertEqual(first_summary["instruction_block_type"], "mode")
        self.assertEqual(
            second_summary["instruction_resource_context_summary"][0]["filename"],
            "observation_guide.md",
        )
        self.assertEqual(
            {
                str(item.get("filename") or "").strip()
                for item in second_summary.get("instruction_resource_context_summary", [])
                if str(item.get("filename") or "").strip()
            },
            {"observation_guide.md"},
        )


if __name__ == "__main__":
    unittest.main()
