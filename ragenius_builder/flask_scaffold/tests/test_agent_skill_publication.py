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

from agent_skill_publication import (  # noqa: E402
    PublicationRevisionStale,
    build_publication_preview,
    publish_agent_skill_revision,
)
from storage import DatabaseStore  # noqa: E402


class FakePublicationClient:
    def __init__(self, mode: str = "echo") -> None:
        self.mode = mode
        self.payloads: list[dict] = []

    def publish_governance_projection(self, payload: dict) -> dict:
        self.payloads.append(payload)
        if self.mode == "raise":
            raise TimeoutError("execution timed out")
        if self.mode == "reject":
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
        if self.mode == "mismatch":
            return {
                "ok": True,
                "status_code": 200,
                "body": {
                    "builder_instance_id": payload["builder_instance_id"],
                    "revision": payload["revision"],
                    "digest": "sha256:wrong",
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


class AgentSkillPublicationTests(unittest.TestCase):
    def setUp(self) -> None:
        root = Path.cwd() / "outputs" / "builder_agent_skill_tests" / f"publication_{uuid4().hex}"
        root.mkdir(parents=True, exist_ok=True)
        self.root = root
        self.store = DatabaseStore(root / "builder.db", storage_root=root, seed_data=False)
        self.ids = self._populate()

    def tearDown(self) -> None:
        self.store.close()
        shutil.rmtree(self.root, ignore_errors=True)

    def _populate(self) -> dict[str, str]:
        app = self.store.create_application(
            {
                "name": "Publication App",
                "slug": "publication-app",
                "description": "test",
                "starter_questions": [],
                "instructions": "# Test",
                "version": "v1",
            }
        )
        source = self.store.create_agent_skill_source(
            backend="codex_cli",
            source_kind="codex_directory",
            display_name="Codex approved",
            runtime_target_id="codex-local",
            protected_locator_ref="protected-secret-path",
            actor_id="admin-1",
        )
        skill = self.store.refresh_agent_skill_catalog(
            source_id=source["id"],
            actor_id="admin-1",
            candidates=[
                {
                    "agent_skill_id": "agent-skill-1",
                    "backend": "codex_cli",
                    "content_fingerprint": "sha256:v1:abc",
                    "description": "Create a report.",
                    "direct_tool_dispatch": False,
                    "discovered_at": "2026-08-04T00:00:00.000Z",
                    "discovery_status": "available",
                    "display_name": "Reporter",
                    "last_seen_at": "2026-08-04T00:00:00.000Z",
                    "missing_requirements": {"bins": [], "config": [], "env": [], "os": []},
                    "model_visible": True,
                    "provider_metadata": {"raw_provider_output": "must-not-leak"},
                    "provider_skill_name": "reporter",
                    "provider_skill_reference": "codex:reporter",
                    "runtime_target_id": "codex-local",
                    "source_id": source["id"],
                    "source_kind": "codex_directory",
                    "source_label": "Codex approved",
                    "user_invocable": True,
                }
            ],
        )[0]
        self.store.approve_agent_skill(
            agent_skill_id=skill["id"],
            expected_fingerprint=skill["content_fingerprint"],
            approved_by="admin-1",
        )
        binding = self.store.create_app_agent_skill_binding(
            app_id=app["id"], agent_skill_id=skill["id"], created_by="admin-1"
        )
        return {
            "app_id": app["id"],
            "source_id": source["id"],
            "skill_id": skill["id"],
            "binding_id": binding["id"],
        }

    def _publish_current(self, client: FakePublicationClient | None = None) -> dict:
        client = client or FakePublicationClient()
        revision = self.store.configure_agent_skill_projection("builder-test")["local_revision"]
        return publish_agent_skill_revision(
            store=self.store,
            execution_client=client,
            builder_instance_id="builder-test",
            expected_local_revision=revision,
            actor_id="admin-1",
            correlation_id="correlation-initial",
        )

    def test_initial_preview_is_a_redacted_deterministic_full_replacement(self) -> None:
        first = build_publication_preview(
            store=self.store, builder_instance_id="builder-test"
        )
        second = build_publication_preview(
            store=self.store, builder_instance_id="builder-test"
        )

        self.assertEqual(first, second)
        self.assertFalse(first["baseline_available"])
        self.assertTrue(first["full_replacement"])
        self.assertEqual(first["state"], "draft_changes")
        self.assertEqual(first["changes"]["affected_apps"], [self.ids["app_id"]])
        serialized = str(first)
        self.assertNotIn("protected-secret-path", serialized)
        self.assertNotIn("raw_provider_output", serialized)

    def test_successful_publication_persists_baseline_and_no_change_preview(self) -> None:
        result = self._publish_current()
        preview = build_publication_preview(
            store=self.store, builder_instance_id="builder-test"
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["state"], "published")
        self.assertTrue(preview["baseline_available"])
        self.assertFalse(preview["full_replacement"])
        self.assertEqual(preview["state"], "published")
        self.assertEqual(preview["changes"]["sources"], [])
        self.assertEqual(preview["changes"]["approvals"], [])
        self.assertEqual(preview["changes"]["bindings"], [])
        self.assertIsNotNone(self.store.get_published_agent_skill_snapshot())
        events = self.store.list_agent_skill_audit_events(limit=10)
        publication_events = [
            event for event in events if event["action"].startswith("agent_skill.publication_")
        ]
        self.assertEqual(
            [event["action"] for event in reversed(publication_events)],
            ["agent_skill.publication_attempted", "agent_skill.publication_succeeded"],
        )
        self.assertTrue(
            all(event["actor_id"] == "admin-1" for event in publication_events)
        )
        self.assertTrue(
            all(event["correlation_id"] == "correlation-initial" for event in publication_events)
        )

    def test_preview_classifies_source_approval_and_binding_changes(self) -> None:
        self._publish_current()
        self.store.update_agent_skill_source(
            self.ids["source_id"], enabled=False, actor_id="admin-1"
        )
        self.store.revoke_agent_skill(
            agent_skill_id=self.ids["skill_id"], actor_id="admin-1"
        )
        self.store.update_app_agent_skill_binding(
            self.ids["binding_id"], enabled=False, actor_id="admin-1"
        )

        preview = build_publication_preview(
            store=self.store, builder_instance_id="builder-test"
        )

        self.assertEqual(preview["state"], "draft_changes")
        self.assertEqual(
            [(item["source_id"], item["change"]) for item in preview["changes"]["sources"]],
            [(self.ids["source_id"], "changed")],
        )
        self.assertEqual(
            [(item["agent_skill_id"], item["change"]) for item in preview["changes"]["approvals"]],
            [(self.ids["skill_id"], "changed")],
        )
        self.assertEqual(
            [(item["app_id"], item["agent_skill_id"], item["change"]) for item in preview["changes"]["bindings"]],
            [(self.ids["app_id"], self.ids["skill_id"], "changed")],
        )
        self.assertEqual(preview["changes"]["affected_apps"], [self.ids["app_id"]])

    def test_binding_removal_is_reported_in_stable_order(self) -> None:
        second_app = self.store.create_application(
            {
                "name": "Another App",
                "slug": "another-app",
                "description": "test",
                "starter_questions": [],
                "instructions": "# Test",
                "version": "v1",
            }
        )
        second_binding = self.store.create_app_agent_skill_binding(
            app_id=second_app["id"],
            agent_skill_id=self.ids["skill_id"],
            created_by="admin-1",
        )
        self._publish_current()
        self.store.delete_app_agent_skill_binding(
            second_binding["id"], actor_id="admin-1"
        )
        self.store.delete_app_agent_skill_binding(
            self.ids["binding_id"], actor_id="admin-1"
        )

        preview = build_publication_preview(
            store=self.store, builder_instance_id="builder-test"
        )

        self.assertEqual(
            [item["app_id"] for item in preview["changes"]["bindings"]],
            sorted([self.ids["app_id"], second_app["id"]]),
        )
        self.assertTrue(
            all(item["change"] == "removed" for item in preview["changes"]["bindings"])
        )

    def test_stale_review_is_rejected_before_execution_call(self) -> None:
        client = FakePublicationClient()
        current = self.store.configure_agent_skill_projection("builder-test")["local_revision"]

        with self.assertRaises(PublicationRevisionStale) as raised:
            publish_agent_skill_revision(
                store=self.store,
                execution_client=client,
                builder_instance_id="builder-test",
                expected_local_revision=current - 1,
                actor_id="admin-1",
                correlation_id="correlation-stale",
            )

        self.assertEqual(raised.exception.code, "PUBLICATION_REVISION_STALE")
        self.assertEqual(client.payloads, [])

    def test_transport_failure_retains_last_acknowledged_revision_and_snapshot(self) -> None:
        self._publish_current()
        before_state = self.store.get_agent_skill_projection_state()
        before_snapshot = self.store.get_published_agent_skill_snapshot()
        self.store.update_app_agent_skill_binding(
            self.ids["binding_id"], enabled=False, actor_id="admin-1"
        )

        result = self._publish_current(FakePublicationClient("reject"))

        after = self.store.get_agent_skill_projection_state()
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "EXECUTION_SUBSYSTEM_UNAVAILABLE")
        self.assertEqual(after["published_revision"], before_state["published_revision"])
        self.assertEqual(self.store.get_published_agent_skill_snapshot(), before_snapshot)

    def test_concurrent_governance_edit_remains_draft_after_reviewed_revision_is_accepted(self) -> None:
        store = self.store
        binding_id = self.ids["binding_id"]

        class EditingPublicationClient(FakePublicationClient):
            def publish_governance_projection(self, payload: dict) -> dict:
                store.update_app_agent_skill_binding(
                    binding_id, enabled=False, actor_id="admin-concurrent"
                )
                return super().publish_governance_projection(payload)

        reviewed_revision = self.store.configure_agent_skill_projection("builder-test")[
            "local_revision"
        ]
        result = publish_agent_skill_revision(
            store=self.store,
            execution_client=EditingPublicationClient(),
            builder_instance_id="builder-test",
            expected_local_revision=reviewed_revision,
            actor_id="admin-1",
            correlation_id="correlation-concurrent",
        )

        state = self.store.get_agent_skill_projection_state()
        preview = build_publication_preview(
            store=self.store, builder_instance_id="builder-test"
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["state"], "draft_changes")
        self.assertEqual(state["published_revision"], reviewed_revision)
        self.assertGreater(state["local_revision"], reviewed_revision)
        self.assertEqual(state["sync_status"], "pending")
        self.assertEqual(preview["state"], "draft_changes")
        self.assertEqual(preview["counts"]["binding_changes"], 1)

    def test_exception_and_ack_mismatch_are_bounded_failures(self) -> None:
        for mode, code in (
            ("raise", "EXECUTION_SUBSYSTEM_UNAVAILABLE"),
            ("mismatch", "AGENT_SKILL_PROJECTION_ACK_MISMATCH"),
        ):
            with self.subTest(mode=mode):
                result = self._publish_current(FakePublicationClient(mode))
                self.assertFalse(result["ok"])
                self.assertEqual(result["error"]["code"], code)
                self.assertIsNone(
                    self.store.get_agent_skill_projection_state()["published_revision"]
                )

    def test_source_toggle_and_publication_audit_are_revisioned_bounded_and_redacted(self) -> None:
        self.store.update_agent_skill_source(
            self.ids["source_id"],
            enabled=False,
            actor_id="admin-audit",
            correlation_id="correlation-toggle",
        )
        revision = self.store.get_agent_skill_projection_state()["local_revision"]
        self._publish_current()

        events = self.store.list_agent_skill_audit_events(limit=50)
        toggle = next(
            event for event in events if event["action"] == "agent_skill_source.updated"
        )
        self.assertEqual(toggle["actor_id"], "admin-audit")
        self.assertEqual(toggle["correlation_id"], "correlation-toggle")
        self.assertEqual(toggle["after"]["local_revision"], revision)

        publication_events = [
            event for event in events if event["action"].startswith("agent_skill.publication_")
        ]
        self.assertTrue(publication_events)
        self.assertTrue(all("counts" in event["after"] for event in publication_events))
        self.assertTrue(all("outcome" in event["after"] for event in publication_events))
        serialized = str(publication_events)
        for forbidden in (
            "protected-secret-path",
            "raw_provider_output",
            "token",
            "credential",
        ):
            self.assertNotIn(forbidden, serialized)


if __name__ == "__main__":
    unittest.main()
