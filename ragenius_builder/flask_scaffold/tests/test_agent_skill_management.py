from __future__ import annotations

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


def candidate(*, fingerprint: str = "sha256:v1:first") -> dict:
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


if __name__ == "__main__":
    unittest.main()
