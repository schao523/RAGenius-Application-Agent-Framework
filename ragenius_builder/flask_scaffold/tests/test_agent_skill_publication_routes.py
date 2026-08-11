from __future__ import annotations

import importlib
import os
import shutil
import sys
import unittest
from pathlib import Path
from uuid import uuid4


SCAFFOLD_DIR = Path(__file__).resolve().parents[1]
if str(SCAFFOLD_DIR) not in sys.path:
    sys.path.insert(0, str(SCAFFOLD_DIR))
os.environ["RAGENIUS_BUILDER_DISABLE_GLOBAL_STORE"] = "1"

from storage import DatabaseStore  # noqa: E402


class FakeExecutionClient:
    def __init__(self) -> None:
        self.reject = False
        self.payloads: list[dict] = []

    def get_source_options(self) -> dict:
        return {"ok": True, "status_code": 200, "body": {"items": []}}

    def publish_governance_projection(self, payload: dict) -> dict:
        self.payloads.append(payload)
        if self.reject:
            return {
                "ok": False,
                "status_code": 503,
                "body": {
                    "error": {
                        "code": "EXECUTION_SUBSYSTEM_UNAVAILABLE",
                        "message": "offline",
                    }
                },
            }
        return {
            "ok": True,
            "status_code": 200,
            "body": {
                "builder_instance_id": payload["builder_instance_id"],
                "revision": payload["revision"],
                "digest": payload["digest"],
            },
        }


class AgentSkillPublicationRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        root = Path.cwd() / "outputs" / "builder_agent_skill_tests" / f"publication_routes_{uuid4().hex}"
        root.mkdir(parents=True, exist_ok=True)
        self.root = root
        self.store = DatabaseStore(":memory:", storage_root=root, seed_data=False)
        app_record = self.store.create_application(
            {
                "name": "Route App",
                "slug": "route-app",
                "description": "test",
                "starter_questions": [],
                "instructions": "# Test",
                "version": "v1",
            }
        )
        source = self.store.create_agent_skill_source(
            backend="codex_cli",
            source_kind="codex_directory",
            display_name="Approved Codex",
            runtime_target_id="codex-local",
            protected_locator_ref="C:/secret/skills",
            actor_id="admin-1",
        )
        skill = self.store.refresh_agent_skill_catalog(
            source_id=source["id"],
            actor_id="admin-1",
            candidates=[
                {
                    "agent_skill_id": "route-skill-1",
                    "backend": "codex_cli",
                    "content_fingerprint": "sha256:v1:route",
                    "description": "Route test skill.",
                    "direct_tool_dispatch": False,
                    "discovered_at": "2026-08-04T00:00:00.000Z",
                    "discovery_status": "available",
                    "display_name": "Route Skill",
                    "last_seen_at": "2026-08-04T00:00:00.000Z",
                    "missing_requirements": {"bins": [], "config": [], "env": [], "os": []},
                    "model_visible": True,
                    "provider_metadata": {"token": "must-not-leak"},
                    "provider_skill_name": "route-skill",
                    "provider_skill_reference": "codex:route-skill",
                    "runtime_target_id": "codex-local",
                    "source_id": source["id"],
                    "source_kind": "codex_directory",
                    "source_label": "Approved Codex",
                    "user_invocable": True,
                }
            ],
        )[0]
        self.store.approve_agent_skill(
            agent_skill_id=skill["id"],
            expected_fingerprint=skill["content_fingerprint"],
            approved_by="admin-1",
        )
        self.store.create_app_agent_skill_binding(
            app_id=app_record["id"], agent_skill_id=skill["id"], created_by="admin-1"
        )
        self.execution_client = FakeExecutionClient()
        self.app_module = importlib.import_module("app")
        self.original_store = self.app_module.store
        self.original_factory = self.app_module._agent_skill_execution_client
        self.app_module.store = self.store
        self.app_module._agent_skill_execution_client = lambda: self.execution_client
        self.app_module.app.config["TESTING"] = True
        self.client = self.app_module.app.test_client()

    def tearDown(self) -> None:
        self.app_module._agent_skill_execution_client = self.original_factory
        self.app_module.store = self.original_store
        self.store.close()
        shutil.rmtree(self.root, ignore_errors=True)

    def test_preview_api_and_review_page_are_redacted_and_use_publication_language(self) -> None:
        api_response = self.client.get("/api/agent-skills/publication-preview")
        page_response = self.client.get("/agent-skills/publication-review")

        self.assertEqual(api_response.status_code, 200)
        self.assertEqual(page_response.status_code, 200)
        api_body = api_response.get_data(as_text=True)
        page_body = page_response.get_data(as_text=True)
        self.assertNotIn("C:/secret/skills", api_body + page_body)
        self.assertNotIn("must-not-leak", api_body + page_body)
        self.assertIn("Draft changes", page_body)
        self.assertIn("Publish revision", page_body)
        self.assertNotIn("synchronized", page_body.lower())

    def test_publication_api_rejects_stale_revision_without_calling_execution(self) -> None:
        revision = self.store.configure_agent_skill_projection(
            "builder-local-default"
        )["local_revision"]

        response = self.client.post(
            "/api/agent-skills/publications",
            json={"expected_local_revision": revision - 1},
            headers={"X-RAGenius-Admin-Id": "admin-route"},
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["error"]["code"], "PUBLICATION_REVISION_STALE")
        self.assertEqual(self.execution_client.payloads, [])

    def test_success_and_failure_keep_explicit_published_and_draft_states(self) -> None:
        revision = self.store.configure_agent_skill_projection(
            "builder-local-default"
        )["local_revision"]
        published = self.client.post(
            "/api/agent-skills/publications",
            json={"expected_local_revision": revision},
            headers={"X-Request-Id": "publish-ok"},
        )
        self.assertEqual(published.status_code, 200)
        self.assertEqual(published.get_json()["state"], "published")

        binding = self.store.list_app_agent_skill_bindings(
            self.store.list_applications()[0]["id"]
        )[0]
        self.store.update_app_agent_skill_binding(
            binding["id"], enabled=False, actor_id="admin-1"
        )
        previous_published_revision = self.store.get_agent_skill_projection_state()[
            "published_revision"
        ]
        self.execution_client.reject = True
        current_revision = self.store.get_agent_skill_projection_state()["local_revision"]
        failed = self.client.post(
            "/api/agent-skills/publications",
            json={"expected_local_revision": current_revision},
        )

        self.assertEqual(failed.status_code, 502)
        self.assertEqual(failed.get_json()["state"], "publish_failed")
        self.assertEqual(
            self.store.get_agent_skill_projection_state()["published_revision"],
            previous_published_revision,
        )

    def test_legacy_synchronize_delegates_and_is_marked_deprecated(self) -> None:
        response = self.client.post("/api/agent-skills/synchronize")

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["sync_status"], "synchronized")
        self.assertTrue(body["_meta"]["deprecated"])
        self.assertEqual(body["_meta"]["replacement"], "/api/agent-skills/publications")

    def test_catalog_links_to_review_instead_of_legacy_synchronize(self) -> None:
        response = self.client.get("/agent-skills")
        body = response.get_data(as_text=True)

        self.assertIn("Review &amp; Publish Changes", body)
        self.assertIn("/agent-skills/publication-review", body)
        self.assertNotIn("/agent-skills/synchronize", body)


if __name__ == "__main__":
    unittest.main()
