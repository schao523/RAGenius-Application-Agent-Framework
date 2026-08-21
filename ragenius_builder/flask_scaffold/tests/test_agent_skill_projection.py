from __future__ import annotations

import os
import json
import shutil
import sqlite3
import sys
import threading
import unittest
from pathlib import Path
from uuid import uuid4


SCAFFOLD_DIR = Path(__file__).resolve().parents[1]
if str(SCAFFOLD_DIR) not in sys.path:
    sys.path.insert(0, str(SCAFFOLD_DIR))
os.environ["RAGENIUS_BUILDER_DISABLE_GLOBAL_STORE"] = "1"

from agent_skill_projection import (  # noqa: E402
    build_agent_skill_projection,
    compute_agent_skill_projection_digest,
    synchronize_agent_skill_projection,
)
from storage import DatabaseStore  # noqa: E402


class FakeProjectionClient:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.payloads: list[dict] = []

    def publish_governance_projection(self, payload: dict) -> dict:
        self.payloads.append(payload)
        if self.response.get("echo_payload"):
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
        return self.response


class AgentSkillProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        root = Path.cwd() / "outputs" / "builder_agent_skill_tests" / f"projection_{uuid4().hex}"
        root.mkdir(parents=True, exist_ok=True)
        self.root = root
        self.db_path = root / "builder.db"
        self.store = DatabaseStore(self.db_path, storage_root=root, seed_data=False)

    def tearDown(self) -> None:
        self.store.close()
        shutil.rmtree(self.root, ignore_errors=True)

    def test_projection_builder_uses_one_consistent_governance_snapshot(self) -> None:
        class SnapshotOnlyStore:
            def read_agent_skill_projection_snapshot(self, builder_instance_id: str):
                self.builder_instance_id = builder_instance_id
                return {"local_revision": 1720000000000}, []

            def configure_agent_skill_projection(self, _builder_instance_id: str):
                raise AssertionError("projection state and items must not be read separately")

            def list_agent_skill_projection_items(self):
                raise AssertionError("projection state and items must not be read separately")

        store = SnapshotOnlyStore()

        projection = build_agent_skill_projection(store, "builder-atomic")

        self.assertEqual(store.builder_instance_id, "builder-atomic")
        self.assertEqual(projection["revision"], 1720000000000)
        self.assertEqual(projection["items"], [])

    def _populate(self) -> None:
        app = self.store.create_application(
            {
                "name": "Projection App",
                "slug": "projection-app",
                "description": "test",
                "starter_questions": [],
                "instructions": "# Test",
                "version": "v1",
            }
        )
        source = self.store.create_agent_skill_source(
            backend="openclaw_cli",
            source_kind="openclaw_agent_inventory",
            display_name="OpenClaw main",
            runtime_target_id="openclaw-main",
            protected_locator_ref="openclaw-source-ref-1",
            actor_id="admin-1",
        )
        skill = self.store.refresh_agent_skill_catalog(
            source_id=source["id"],
            actor_id="admin-1",
            candidates=[
                {
                    "agent_skill_id": "agent-skill-1",
                    "backend": "openclaw_cli",
                    "content_fingerprint": "sha256:v1:abc",
                    "description": "Summarize approved content.",
                    "direct_tool_dispatch": False,
                    "discovered_at": "2026-08-04T00:00:00.000Z",
                    "discovery_status": "available",
                    "display_name": "Summarizer",
                    "last_seen_at": "2026-08-04T00:00:00.000Z",
                    "missing_requirements": {"bins": [], "config": [], "env": [], "os": []},
                    "model_visible": True,
                    "provider_metadata": {},
                    "provider_skill_name": "summarizer",
                    "runtime_target_id": "openclaw-main",
                    "source_id": source["id"],
                    "source_kind": "openclaw_agent_inventory",
                    "source_label": "OpenClaw main",
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
            app_id=app["id"], agent_skill_id=skill["id"], created_by="admin-1"
        )

    def test_snapshot_revision_is_monotonic_and_digest_is_canonical(self) -> None:
        self._populate()
        first = build_agent_skill_projection(self.store, "builder-test")
        second = build_agent_skill_projection(self.store, "builder-test")

        self.assertEqual(first, second)
        self.assertRegex(first["digest"], r"^sha256:[a-f0-9]{64}$")
        previous_revision = first["revision"]
        source = self.store.list_agent_skill_sources()[0]
        self.store.update_agent_skill_source(
            source["id"], enabled=False, actor_id="admin-1"
        )
        changed = build_agent_skill_projection(self.store, "builder-test")
        self.assertGreater(changed["revision"], previous_revision)

    def test_interaction_policy_defaults_and_reviewed_change_round_trip(self) -> None:
        self._populate()
        autonomous = build_agent_skill_projection(self.store, "builder-test")
        self.assertEqual(
            autonomous["items"][0]["interaction_policy"],
            {
                "interaction_channel": "none",
                "interaction_requirement": "autonomous",
                "supported_interaction_types": [],
                "required_transport": "one_shot",
                "recovery_class": "not_resumable",
            },
        )

        skill = self.store.list_agent_skill_catalog()[0]
        self.store.approve_agent_skill(
            agent_skill_id=skill["id"],
            expected_fingerprint=skill["content_fingerprint"],
            approved_by="admin-1",
            interaction_policy={
                "interaction_requirement": "required",
                "supported_interaction_types": ["selection", "approval", "approval"],
                "required_transport": "interactive",
                "recovery_class": "turn_resumable",
            },
        )
        interactive = build_agent_skill_projection(self.store, "builder-test")

        self.assertNotEqual(interactive["digest"], autonomous["digest"])
        self.assertEqual(
            interactive["items"][0]["interaction_policy"],
            {
                "interaction_channel": "none",
                "interaction_requirement": "required",
                "supported_interaction_types": ["approval", "selection"],
                "required_transport": "interactive",
                "recovery_class": "turn_resumable",
            },
        )

    def test_chat_level_channel_is_explicitly_approved_and_projected(self) -> None:
        self._populate()
        skill = self.store.list_agent_skill_catalog()[0]
        self.store.approve_agent_skill(
            agent_skill_id=skill["id"],
            expected_fingerprint=skill["content_fingerprint"],
            approved_by="admin-1",
            interaction_policy={
                "interaction_channel": "chat_level",
                "interaction_requirement": "autonomous",
                "supported_interaction_types": [],
                "required_transport": "interactive",
                "recovery_class": "session_resumable",
            },
        )
        projection = build_agent_skill_projection(self.store, "builder-test")
        self.assertEqual(
            projection["items"][0]["interaction_policy"]["interaction_channel"],
            "chat_level",
        )

    def test_invalid_interaction_policy_is_rejected(self) -> None:
        self._populate()
        skill = self.store.list_agent_skill_catalog()[0]
        invalid = {
            "interaction_requirement": "required",
            "supported_interaction_types": ["approval"],
            "required_transport": "one_shot",
            "recovery_class": "not_resumable",
        }

        with self.assertRaisesRegex(ValueError, "AGENT_SKILL_INTERACTION_POLICY_INVALID"):
            self.store.approve_agent_skill(
                agent_skill_id=skill["id"],
                expected_fingerprint=skill["content_fingerprint"],
                approved_by="admin-1",
                interaction_policy=invalid,
            )

    def test_first_empty_snapshot_receives_a_real_monotonic_revision(self) -> None:
        snapshot = build_agent_skill_projection(self.store, "builder-test")

        self.assertGreater(snapshot["revision"], 0)
        self.assertEqual(
            self.store.get_agent_skill_projection_state()["sync_status"], "pending"
        )

    def test_digest_matches_execution_subsystem_canonicalization(self) -> None:
        payload = {
            "builder_instance_id": "builder-test",
            "revision": 42,
            "generated_at": "2026-08-04T00:00:00.000Z",
            "items": [
                {
                    "agent_skill_id": "skill-1",
                    "app_id": "app-1",
                    "approval_state": "approved",
                    "approved_fingerprint": "sha256:v1:abc",
                    "backend": "codex_cli",
                    "binding_enabled": True,
                    "current_fingerprint": "sha256:v1:abc",
                    "description": "Résumé",
                    "direct_tool_dispatch": False,
                    "display_name": "Research",
                    "model_visible": True,
                    "protected_locator_ref": "ref-1",
                    "provider_skill_name": "research",
                    "runtime_target_id": "codex-local",
                    "source_enabled": True,
                    "source_id": "source-1",
                    "user_invocable": True,
                }
            ],
        }

        self.assertEqual(
            compute_agent_skill_projection_digest(payload),
            "sha256:5fa095202ad39196ff7077e031d8e277df8eba14410841ce9aad4e749f5ccc48",
        )

    def test_acknowledgment_is_idempotent_and_requires_exact_echo(self) -> None:
        self._populate()
        client = FakeProjectionClient({"echo_payload": True})

        first = synchronize_agent_skill_projection(self.store, client, "builder-test")
        second = synchronize_agent_skill_projection(self.store, client, "builder-test")

        self.assertEqual(first["sync_status"], "synchronized")
        self.assertEqual(second["sync_status"], "synchronized")
        self.assertEqual(client.payloads[0], client.payloads[1])
        self.assertEqual(
            client.payloads[0]["items"][0]["provider_skill_reference"],
            "summarizer",
        )
        publication_actions = [
            event["action"]
            for event in self.store.list_agent_skill_audit_events(limit=20)
            if event["action"].startswith("agent_skill.publication_")
        ]
        self.assertEqual(publication_actions.count("agent_skill.publication_attempted"), 2)
        self.assertEqual(publication_actions.count("agent_skill.publication_succeeded"), 2)

    def test_failed_sync_remains_pending_and_retries_after_restart(self) -> None:
        self._populate()
        failed_client = FakeProjectionClient(
            {
                "ok": False,
                "status_code": 503,
                "body": {"error": {"code": "EXECUTION_SUBSYSTEM_UNAVAILABLE", "message": "offline"}},
            }
        )

        failed = synchronize_agent_skill_projection(
            self.store, failed_client, "builder-test"
        )
        failed_payload = failed_client.payloads[0]
        self.assertEqual(failed["sync_status"], "failed")
        self.store.close()
        self.store = DatabaseStore(self.db_path, storage_root=self.root, seed_data=False)

        retry_client = FakeProjectionClient({"echo_payload": True})
        retried = synchronize_agent_skill_projection(
            self.store, retry_client, "builder-test"
        )

        self.assertEqual(retried["sync_status"], "synchronized")
        self.assertEqual(retry_client.payloads[0], failed_payload)

    def test_existing_projection_state_table_gains_published_snapshot_column(self) -> None:
        legacy_path = self.root / "legacy.db"
        connection = sqlite3.connect(legacy_path)
        connection.execute(
            """
            CREATE TABLE agent_skill_projection_state (
                singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1),
                builder_instance_id TEXT,
                local_revision INTEGER NOT NULL DEFAULT 0,
                published_revision INTEGER,
                published_digest TEXT,
                sync_status TEXT NOT NULL DEFAULT 'synchronized',
                last_attempt_at TEXT,
                last_success_at TEXT,
                last_error_code TEXT,
                last_error_message TEXT
            )
            """
        )
        connection.execute(
            "INSERT INTO agent_skill_projection_state (singleton_id) VALUES (1)"
        )
        connection.commit()
        connection.close()

        upgraded = DatabaseStore(legacy_path, storage_root=self.root, seed_data=False)
        try:
            columns = {
                row["name"]
                for row in upgraded.conn.execute(
                    "PRAGMA table_info(agent_skill_projection_state)"
                )
            }
            self.assertIn("published_snapshot_json", columns)
            self.assertIsNone(
                upgraded.get_agent_skill_projection_state()["published_snapshot_json"]
            )
        finally:
            upgraded.close()

    def test_published_snapshot_round_trips_as_deterministic_compact_json(self) -> None:
        self._populate()
        projection = build_agent_skill_projection(self.store, "builder-test")
        snapshot = {
            "sources": [{"enabled": True, "source_id": "source-1"}],
            "skills": [
                {
                    "agent_skill_id": "skill-1",
                    "approval_state": "approved",
                    "approved_fingerprint": "sha256:v1:abc",
                    "current_fingerprint": "sha256:v1:abc",
                    "interaction_policy": {
                        "interaction_channel": "none",
                        "interaction_requirement": "autonomous",
                        "supported_interaction_types": [],
                        "required_transport": "one_shot",
                        "recovery_class": "not_resumable",
                    },
                    "provider_skill_reference": "summarizer",
                    "source_id": "source-1",
                }
            ],
            "bindings": [
                {"agent_skill_id": "skill-1", "app_id": "app-1", "enabled": True}
            ],
        }

        state = self.store.mark_agent_skill_projection_published(
            builder_instance_id="builder-test",
            revision=projection["revision"],
            digest=projection["digest"],
            redacted_snapshot=snapshot,
        )

        self.assertEqual(self.store.get_published_agent_skill_snapshot(), snapshot)
        self.assertEqual(
            state["published_snapshot_json"],
            json.dumps(snapshot, sort_keys=True, separators=(",", ":")),
        )

    def test_publication_acknowledgment_is_serialized_by_governance_lock(self) -> None:
        self._populate()
        projection = build_agent_skill_projection(self.store, "builder-test")
        completed = threading.Event()
        errors = []

        def acknowledge() -> None:
            try:
                self.store.mark_agent_skill_projection_published(
                    builder_instance_id="builder-test",
                    revision=projection["revision"],
                    digest=projection["digest"],
                    redacted_snapshot={"sources": [], "skills": [], "bindings": []},
                )
            except Exception as exc:
                errors.append(exc)
            finally:
                completed.set()

        with self.store._agent_skill_governance_lock:
            worker = threading.Thread(target=acknowledge)
            worker.start()
            self.assertFalse(completed.wait(0.1))
        worker.join(timeout=2)

        self.assertTrue(completed.is_set())
        self.assertEqual(errors, [])

    def test_malformed_or_unsafe_published_snapshot_is_rejected(self) -> None:
        with self.store.conn:
            self.store.conn.execute(
                """
                UPDATE agent_skill_projection_state
                SET published_snapshot_json = '{not-json'
                WHERE singleton_id = 1
                """
            )

        with self.assertRaisesRegex(ValueError, "PUBLISHED_SNAPSHOT_INVALID"):
            self.store.get_published_agent_skill_snapshot()

        with self.assertRaisesRegex(ValueError, "PUBLISHED_SNAPSHOT_INVALID"):
            self.store.mark_agent_skill_projection_published(
                builder_instance_id=None,
                revision=0,
                digest="sha256:test",
                redacted_snapshot={"protected_locator_ref": "secret-path"},
            )

    def test_failed_publication_retains_previous_published_snapshot(self) -> None:
        self._populate()
        projection = build_agent_skill_projection(self.store, "builder-test")
        snapshot = {"sources": [], "skills": [], "bindings": []}
        self.store.mark_agent_skill_projection_published(
            builder_instance_id="builder-test",
            revision=projection["revision"],
            digest=projection["digest"],
            redacted_snapshot=snapshot,
        )

        self.store.mark_agent_skill_projection_failed(
            code="EXECUTION_SUBSYSTEM_UNAVAILABLE", message="offline"
        )

        self.assertEqual(self.store.get_published_agent_skill_snapshot(), snapshot)
        self.assertEqual(
            self.store.get_agent_skill_projection_state()["published_revision"],
            projection["revision"],
        )


if __name__ == "__main__":
    unittest.main()
