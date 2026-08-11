from __future__ import annotations

import os
import shutil
import sys
import unittest
import importlib
import sqlite3
from pathlib import Path
from uuid import uuid4


SCAFFOLD_DIR = Path(__file__).resolve().parents[1]
if str(SCAFFOLD_DIR) not in sys.path:
    sys.path.insert(0, str(SCAFFOLD_DIR))
os.environ["RAGENIUS_BUILDER_DISABLE_GLOBAL_STORE"] = "1"

from storage import DatabaseStore  # noqa: E402


def candidate(
    *,
    fingerprint: str = "sha256:v1:first",
    provider_reference: str = "research-paper-finder",
) -> dict:
    return {
        "agent_skill_id": "agent-skill-provider-id",
        "backend": "codex_cli",
        "content_fingerprint": fingerprint,
        "description": "Use the approved research workflow.",
        "direct_tool_dispatch": False,
        "discovered_at": "2026-08-04T00:00:00.000Z",
        "discovery_status": "available",
        "display_name": "Research Papers",
        "last_seen_at": "2026-08-04T00:00:00.000Z",
        "missing_requirements": {"bins": [], "config": [], "env": [], "os": []},
        "model_visible": True,
        "provider_metadata": {"manifest": "SKILL.md"},
        "provider_skill_name": "research-paper-finder",
        "provider_skill_reference": provider_reference,
        "runtime_target_id": "codex-local-default",
        "source_id": "ignored-provider-source-id",
        "source_kind": "codex_directory",
        "source_label": "Approved Codex skills",
        "user_invocable": True,
    }


class AgentSkillManagementTests(unittest.TestCase):
    def setUp(self) -> None:
        root = Path.cwd() / "outputs" / "builder_agent_skill_tests" / f"case_{uuid4().hex}"
        root.mkdir(parents=True, exist_ok=True)
        self.root = root
        self.store = DatabaseStore(":memory:", storage_root=root, seed_data=False)

    def tearDown(self) -> None:
        self.store.close()
        shutil.rmtree(self.root, ignore_errors=True)

    def _source(self) -> dict:
        return self.store.create_agent_skill_source(
            backend="codex_cli",
            source_kind="codex_directory",
            display_name="Approved Codex skills",
            runtime_target_id="codex-local-default",
            protected_locator_ref="codex-source-ref-1",
            precedence=10,
            actor_id="admin-1",
        )

    def _app(self) -> dict:
        return self.store.create_application(
            {
                "name": f"Agent Skill App {uuid4().hex}",
                "slug": f"agent-skill-app-{uuid4().hex}",
                "description": "test",
                "starter_questions": [],
                "instructions": "# Test",
                "version": "v1",
            }
        )

    def test_creates_separate_agent_skill_governance_tables(self) -> None:
        tables = {
            row["name"]
            for row in self.store.conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

        self.assertTrue(
            {
                "agent_skill_sources",
                "agent_skill_catalog",
                "agent_skill_approvals",
                "app_agent_skill_bindings",
                "agent_skill_audit_events",
                "agent_skill_projection_state",
            }.issubset(tables)
        )

    def test_catalog_refresh_preserves_identity_and_marks_changed_fingerprint(self) -> None:
        source = self._source()
        first = self.store.refresh_agent_skill_catalog(
            source_id=source["id"], candidates=[candidate()], actor_id="admin-1"
        )[0]
        self.store.approve_agent_skill(
            agent_skill_id=first["id"],
            expected_fingerprint=first["content_fingerprint"],
            approved_by="admin-1",
        )

        changed = self.store.refresh_agent_skill_catalog(
            source_id=source["id"],
            candidates=[candidate(fingerprint="sha256:v1:changed")],
            actor_id="admin-1",
        )[0]

        self.assertEqual(changed["id"], first["id"])
        self.assertEqual(changed["governance_state"], "changed_pending_review")

    def test_catalog_identity_uses_canonical_reference_not_manifest_name(self) -> None:
        source = self._source()
        first = candidate(provider_reference="plugin-a:research-paper-finder")
        second = candidate(provider_reference="plugin-b:research-paper-finder")
        second["agent_skill_id"] = "agent-skill-provider-id-2"

        refreshed = self.store.refresh_agent_skill_catalog(
            source_id=source["id"],
            candidates=[first, second],
            actor_id="admin-1",
        )

        self.assertEqual(len(refreshed), 2)
        self.assertEqual(
            {item["provider_skill_reference"] for item in refreshed},
            {
                "plugin-a:research-paper-finder",
                "plugin-b:research-paper-finder",
            },
        )

    def test_existing_catalog_is_backfilled_during_sqlite_migration(self) -> None:
        db_path = self.root / "legacy-builder.db"
        connection = sqlite3.connect(db_path)
        connection.executescript(
            """
            CREATE TABLE agent_skill_sources (
                id TEXT PRIMARY KEY,
                backend TEXT NOT NULL,
                source_kind TEXT NOT NULL,
                display_name TEXT NOT NULL,
                runtime_target_id TEXT NOT NULL,
                protected_locator_ref TEXT NOT NULL,
                precedence INTEGER NOT NULL DEFAULT 100,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(backend, runtime_target_id, protected_locator_ref)
            );
            CREATE TABLE agent_skill_catalog (
                id TEXT PRIMARY KEY,
                backend TEXT NOT NULL,
                runtime_target_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                provider_skill_name TEXT NOT NULL,
                display_name TEXT NOT NULL,
                description TEXT NOT NULL,
                content_fingerprint TEXT NOT NULL,
                discovery_status TEXT NOT NULL,
                model_visible INTEGER NOT NULL,
                user_invocable INTEGER NOT NULL,
                direct_tool_dispatch INTEGER NOT NULL,
                missing_requirements_json TEXT NOT NULL,
                provider_metadata_json TEXT NOT NULL,
                discovered_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(backend, runtime_target_id, source_id, provider_skill_name)
            );
            INSERT INTO agent_skill_sources VALUES (
              'source-1','codex_cli','codex_directory','Legacy','codex-local',
              'legacy-ref',100,1,'2026-08-01','2026-08-01'
            );
            INSERT INTO agent_skill_catalog VALUES (
              'skill-1','codex_cli','codex-local','source-1','legacy-skill',
              'Legacy Skill','Legacy','sha256:v1:legacy','available',1,1,0,
              '{}','{}','2026-08-01','2026-08-01','2026-08-01'
            );
            """
        )
        connection.close()

        migrated_store = DatabaseStore(db_path, storage_root=self.root, seed_data=False)
        try:
            migrated = migrated_store.get_agent_skill_catalog_item("skill-1")
            self.assertEqual(
                migrated["provider_skill_reference"],
                migrated["provider_skill_name"],
            )
            migrated_store.approve_agent_skill(
                agent_skill_id="skill-1",
                expected_fingerprint="sha256:v1:legacy",
                approved_by="admin-1",
            )
            app = migrated_store.create_application(
                {
                    "name": f"Migrated App {uuid4().hex}",
                    "slug": f"migrated-app-{uuid4().hex}",
                    "description": "migration verification",
                    "starter_questions": [],
                    "instructions": "# Migrated",
                    "version": "v1",
                }
            )
            binding = migrated_store.create_app_agent_skill_binding(
                app_id=app["id"],
                agent_skill_id="skill-1",
                created_by="admin-1",
            )
            self.assertEqual(binding["agent_skill_id"], "skill-1")
            self.assertEqual(
                migrated_store.conn.execute("PRAGMA foreign_key_check").fetchall(),
                [],
            )
        finally:
            migrated_store.close()

    def test_approval_uses_compare_and_set_fingerprint(self) -> None:
        source = self._source()
        skill = self.store.refresh_agent_skill_catalog(
            source_id=source["id"], candidates=[candidate()], actor_id="admin-1"
        )[0]

        with self.assertRaisesRegex(ValueError, "AGENT_SKILL_FINGERPRINT_CHANGED"):
            self.store.approve_agent_skill(
                agent_skill_id=skill["id"],
                expected_fingerprint="sha256:v1:stale",
                approved_by="admin-1",
            )

    def test_binding_is_unique_and_runtime_mutations_are_audited(self) -> None:
        source = self._source()
        app = self._app()
        skill = self.store.refresh_agent_skill_catalog(
            source_id=source["id"], candidates=[candidate()], actor_id="admin-1"
        )[0]
        self.store.approve_agent_skill(
            agent_skill_id=skill["id"],
            expected_fingerprint=skill["content_fingerprint"],
            approved_by="admin-1",
        )
        first = self.store.create_app_agent_skill_binding(
            app_id=app["id"], agent_skill_id=skill["id"], created_by="admin-1"
        )
        second = self.store.create_app_agent_skill_binding(
            app_id=app["id"], agent_skill_id=skill["id"], created_by="admin-1"
        )

        self.assertEqual(second["id"], first["id"])
        self.assertEqual(len(self.store.list_app_agent_skill_bindings(app["id"])), 1)
        actions = {event["action"] for event in self.store.list_agent_skill_audit_events()}
        self.assertIn("agent_skill_source.created", actions)
        self.assertIn("agent_skill.approved", actions)
        self.assertIn("app_agent_skill_binding.created", actions)
        self.assertEqual(
            self.store.get_agent_skill_projection_state()["sync_status"], "pending"
        )

    def test_catalog_views_and_source_impact_are_deterministic(self) -> None:
        source = self._source()
        app_b = self._app()
        app_a = self._app()
        first = self.store.refresh_agent_skill_catalog(
            source_id=source["id"], candidates=[candidate()], actor_id="admin-1"
        )[0]
        self.store.approve_agent_skill(
            agent_skill_id=first["id"], expected_fingerprint=first["content_fingerprint"],
            approved_by="admin-1",
        )
        self.store.create_app_agent_skill_binding(
            app_id=app_b["id"], agent_skill_id=first["id"], created_by="admin-1",
        )
        self.store.create_app_agent_skill_binding(
            app_id=app_a["id"], agent_skill_id=first["id"], created_by="admin-1",
        )

        self.assertEqual(len(self.store.list_agent_skill_catalog_view(view="active")), 1)
        self.assertEqual(
            len(self.store.list_agent_skill_catalog_view(view="source", source_id=source["id"])), 1
        )
        self.store.update_agent_skill_source(source["id"], actor_id="admin-1", enabled=False)
        self.assertEqual(self.store.list_agent_skill_catalog_view(view="active"), [])
        disabled = self.store.list_agent_skill_catalog_view(view="disabled")
        self.assertEqual(disabled[0]["governance_state"], "source_disabled")

        impact = self.store.get_agent_skill_source_impact(source["id"])
        self.assertEqual(impact["discovered_skill_count"], 1)
        self.assertEqual(impact["approved_current_fingerprint_count"], 1)
        self.assertEqual(impact["enabled_binding_count"], 2)
        self.assertEqual(
            impact["affected_apps"],
            sorted(
                [{"id": app_a["id"], "name": app_a["name"]}, {"id": app_b["id"], "name": app_b["name"]}],
                key=lambda item: (item["name"].casefold(), item["id"]),
            ),
        )


class FakeAgentSkillExecutionClient:
    def __init__(self) -> None:
        self.discovery_calls: list[dict] = []
        self.projection_payloads: list[dict] = []

    def get_source_options(self) -> dict:
        return {
            "ok": True,
            "status_code": 200,
            "body": {
                "items": [
                    {
                        "backend": "codex_cli",
                        "display_name": "Configured Codex skills",
                        "protected_locator_ref": "codex-source-ref-1",
                        "precedence": 10,
                        "runtime_target_id": "codex-local-default",
                        "source_kind": "codex_directory",
                    }
                ]
            },
        }

    def discover(self, payload: dict) -> dict:
        self.discovery_calls.append(payload)
        item = candidate(provider_reference="superpowers:research-paper-finder")
        item["source_id"] = payload["source_id"]
        return {
            "ok": True,
            "status_code": 200,
            "body": {
                "backend": payload["backend"],
                "complete": True,
                "discovered_at": "2026-08-04T00:00:00.000Z",
                "errors": [],
                "items": [item],
                "runtime_target_id": payload["runtime_target_id"],
                "source_id": payload["source_id"],
            },
        }

    def publish_governance_projection(self, payload: dict) -> dict:
        self.projection_payloads.append(payload)
        return {
            "ok": True,
            "status_code": 200,
            "body": {
                "builder_instance_id": payload["builder_instance_id"],
                "revision": payload["revision"],
                "digest": payload["digest"],
                "idempotent": False,
            },
        }


class AgentSkillAdminRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_admin_token = os.environ.get("RAGENIUS_BUILDER_ADMIN_TOKEN")
        os.environ["RAGENIUS_BUILDER_ADMIN_TOKEN"] = "route-admin-secret"
        root = Path.cwd() / "outputs" / "builder_agent_skill_tests" / f"routes_{uuid4().hex}"
        root.mkdir(parents=True, exist_ok=True)
        self.root = root
        self.store = DatabaseStore(":memory:", storage_root=root, seed_data=False)
        self.app_record = self.store.create_application(
            {
                "name": "Agent Skill Route App",
                "slug": "agent-skill-route-app",
                "description": "test",
                "starter_questions": [],
                "instructions": "# Test",
                "version": "v1",
            }
        )
        self.execution_client = FakeAgentSkillExecutionClient()
        self.app_module = importlib.import_module("app")
        self.original_store = self.app_module.store
        self.app_module.store = self.store
        self.original_factory = getattr(self.app_module, "_agent_skill_execution_client", None)
        self.app_module._agent_skill_execution_client = lambda: self.execution_client
        self.app_module.app.config["TESTING"] = True
        self.client = self.app_module.app.test_client()

    def tearDown(self) -> None:
        if self.original_factory is None:
            delattr(self.app_module, "_agent_skill_execution_client")
        else:
            self.app_module._agent_skill_execution_client = self.original_factory
        self.app_module.store = self.original_store
        self.store.close()
        shutil.rmtree(self.root, ignore_errors=True)
        if self.original_admin_token is None:
            os.environ.pop("RAGENIUS_BUILDER_ADMIN_TOKEN", None)
        else:
            os.environ["RAGENIUS_BUILDER_ADMIN_TOKEN"] = self.original_admin_token

    def _create_and_discover(self) -> tuple[dict, dict]:
        created_response = self.client.post(
            "/api/agent-skill-sources",
            json={
                "backend": "codex_cli",
                "source_kind": "codex_directory",
                "display_name": "Approved Codex skills",
                "runtime_target_id": "codex-local-default",
                "protected_locator_ref": "codex-source-ref-1",
                "precedence": 999,
            },
        )
        self.assertEqual(created_response.status_code, 201)
        source = created_response.get_json()
        discovered_response = self.client.post(
            f"/api/agent-skill-sources/{source['id']}/discover"
        )
        self.assertEqual(discovered_response.status_code, 200)
        skill = discovered_response.get_json()["items"][0]
        return source, skill

    def test_source_creation_uses_configured_option_and_redacts_locator(self) -> None:
        source, _ = self._create_and_discover()

        self.assertNotIn("protected_locator_ref", source)
        self.assertEqual(source["precedence"], 10)
        page = self.client.get("/agent-skills")
        body = page.get_data(as_text=True)
        self.assertEqual(page.status_code, 200)
        self.assertIn("Agent Skills", body)
        self.assertIn("Approved Codex skills", body)
        self.assertIn("superpowers:research-paper-finder", body)
        self.assertNotIn("codex-source-ref-1", body)
        self.assertNotIn("C:\\", body)

    def test_plugin_inventory_source_kind_is_supported(self) -> None:
        source = self.store.create_agent_skill_source(
            backend="codex_cli",
            source_kind="codex_plugin_inventory",
            display_name="Approved Codex plugins",
            runtime_target_id="codex-local-default",
            protected_locator_ref="codex-plugin-root-1",
            precedence=20,
            actor_id="admin-1",
        )

        self.assertEqual(source["source_kind"], "codex_plugin_inventory")

    def test_source_update_rejects_client_precedence_override(self) -> None:
        source, _ = self._create_and_discover()

        rejected = self.client.patch(
            f"/api/agent-skill-sources/{source['id']}",
            json={"precedence": 999},
        )
        accepted = self.client.patch(
            f"/api/agent-skill-sources/{source['id']}",
            json={"precedence": 10, "display_name": "Renamed source"},
        )

        self.assertEqual(rejected.status_code, 422)
        self.assertEqual(accepted.status_code, 200)
        stored = self.store.get_agent_skill_source(source["id"])
        self.assertEqual(stored["precedence"], 10)
        self.assertEqual(stored["display_name"], "Renamed source")

    def test_approval_binding_and_synchronization_flow(self) -> None:
        _, skill = self._create_and_discover()
        stale = self.client.post(
            f"/api/agent-skills/{skill['id']}/approve",
            json={"expected_fingerprint": "sha256:v1:stale"},
        )
        approved = self.client.post(
            f"/api/agent-skills/{skill['id']}/approve",
            json={"expected_fingerprint": skill["content_fingerprint"]},
        )
        bound = self.client.post(
            f"/api/apps/{self.app_record['id']}/agent-skill-bindings",
            json={"agent_skill_id": skill["id"]},
        )
        pending_page = self.client.get(f"/agent-skills/{skill['id']}")
        synchronized = self.client.post(
            "/api/agent-skills/synchronize",
            headers={"Authorization": "Bearer route-admin-secret"},
        )

        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.get_json()["error"]["code"], "AGENT_SKILL_FINGERPRINT_CHANGED")
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(bound.status_code, 201)
        self.assertIn("Pending synchronization", pending_page.get_data(as_text=True))
        self.assertEqual(synchronized.status_code, 200)
        self.assertEqual(synchronized.get_json()["sync_status"], "synchronized")
        self.assertEqual(len(self.execution_client.projection_payloads), 1)

    def test_agent_skill_mutations_do_not_accept_get(self) -> None:
        _, skill = self._create_and_discover()

        self.assertEqual(
            self.client.get(f"/api/agent-skills/{skill['id']}/approve").status_code,
            405,
        )
        self.assertEqual(self.client.get("/api/agent-skills/synchronize").status_code, 405)

    def test_app_detail_keeps_executable_and_agent_skills_distinct(self) -> None:
        _, skill = self._create_and_discover()
        self.client.post(
            f"/api/agent-skills/{skill['id']}/approve",
            json={"expected_fingerprint": skill["content_fingerprint"]},
        )
        self.client.post(
            f"/api/apps/{self.app_record['id']}/agent-skill-bindings",
            json={"agent_skill_id": skill["id"]},
        )

        response = self.client.get(f"/apps/{self.app_record['id']}")
        body = response.get_data(as_text=True)

        self.assertIn("Agent Skill Bindings", body)
        self.assertIn("Research Papers", body)
        self.assertIn("Skills", body)

    def test_gui_can_disable_sources_and_unbind_agent_skills(self) -> None:
        source, skill = self._create_and_discover()
        self.client.post(
            f"/api/agent-skills/{skill['id']}/approve",
            json={"expected_fingerprint": skill["content_fingerprint"]},
        )
        binding = self.client.post(
            f"/api/apps/{self.app_record['id']}/agent-skill-bindings",
            json={"agent_skill_id": skill["id"]},
        ).get_json()

        source_page = self.client.get("/agent-skills").get_data(as_text=True)
        detail_page = self.client.get(f"/agent-skills/{skill['id']}").get_data(as_text=True)
        disabled = self.client.post(
            f"/agent-skill-sources/{source['id']}/toggle",
            data={"enabled": "false"},
        )
        unbound = self.client.post(
            f"/agent-skills/{skill['id']}/bindings/{binding['id']}/delete"
        )

        self.assertIn("Disable source", source_page)
        self.assertIn("Unbind", detail_page)
        self.assertEqual(disabled.status_code, 302)
        self.assertFalse(self.store.get_agent_skill_source(source["id"])["enabled"])
        self.assertEqual(unbound.status_code, 302)
        self.assertEqual(self.store.list_app_agent_skill_bindings(self.app_record["id"]), [])

    def test_source_tabs_retain_disabled_history_and_disable_review_is_compare_and_set(self) -> None:
        source, skill = self._create_and_discover()
        self.client.post(
            f"/api/agent-skills/{skill['id']}/approve",
            json={"expected_fingerprint": skill["content_fingerprint"]},
        )
        self.client.post(
            f"/api/apps/{self.app_record['id']}/agent-skill-bindings",
            json={"agent_skill_id": skill["id"]},
        )
        revision = self.store.get_agent_skill_projection_state()["local_revision"]

        source_tab = self.client.get(f"/agent-skills?catalog_view=source:{source['id']}")
        review = self.client.get(f"/agent-skill-sources/{source['id']}/disable-review")
        stale = self.client.post(
            f"/agent-skill-sources/{source['id']}/toggle",
            data={"enabled": "false", "expected_local_revision": revision - 1},
        )
        disabled = self.client.post(
            f"/agent-skill-sources/{source['id']}/toggle",
            data={"enabled": "false", "expected_local_revision": revision},
        )
        disabled_page = self.client.get("/agent-skills?catalog_view=disabled")

        self.assertEqual(source_tab.status_code, 200)
        self.assertIn('aria-current="page"', source_tab.get_data(as_text=True))
        self.assertIn("Research Papers", source_tab.get_data(as_text=True))
        self.assertIn("Disable source in draft", review.get_data(as_text=True))
        self.assertIn(self.app_record["name"], review.get_data(as_text=True))
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(disabled.status_code, 302)
        self.assertIn("source_disabled", disabled_page.get_data(as_text=True))
        rejected = self.client.post(
            f"/agent-skills/{skill['id']}/approve",
            data={"expected_fingerprint": skill["content_fingerprint"]},
        )
        self.assertEqual(rejected.status_code, 422)


if __name__ == "__main__":
    unittest.main()
