from __future__ import annotations

from ragenius_app_skeleton.workflows.nodes.load_template_registry import (
    _sanitize_session_execution_state_for_rehydration,
)
from ragenius_app_skeleton.workflows.runtime_models import SessionExecutionState
from ragenius_app_skeleton.backend.app.chat_repos import SessionRepo


def test_rehydration_drops_stale_support_module_activation_for_previous_step():
    state = {
        "active_step_scope_id": "step:identify_relationships",
        "primary_support_module_id": "support_module:bible-study",
        "primary_support_module_title": "Bible Study",
        "primary_support_module_activation": {
            "support_module_id": "support_module:bible-study",
            "support_module_title": "Bible Study",
            "resource_ids": [],
            "step_scope_id": "step:observation",
        },
    }

    sanitized = _sanitize_session_execution_state_for_rehydration(state, {})

    assert "primary_support_module_activation" not in sanitized
    hydrated = SessionExecutionState(**sanitized)
    assert hydrated.active_step_scope_id == "step:identify_relationships"
    assert hydrated.primary_support_module_id == "support_module:bible-study"


def test_rehydration_keeps_matching_support_module_activation():
    state = {
        "active_step_scope_id": "step:observation",
        "primary_support_module_id": "support_module:bible-study",
        "primary_support_module_title": "Bible Study",
        "primary_support_module_activation": {
            "support_module_id": "support_module:bible-study",
            "support_module_title": "Bible Study",
            "resource_ids": [],
            "step_scope_id": "step:observation",
        },
    }

    sanitized = _sanitize_session_execution_state_for_rehydration(state, {})

    assert sanitized["primary_support_module_activation"]["step_scope_id"] == "step:observation"
    hydrated = SessionExecutionState(**sanitized)
    assert hydrated.active_step_scope_id == "step:observation"


def test_interactive_execution_lane_rehydrates_without_prompt_or_provider_handle(tmp_path):
    db_path = tmp_path / "runtime_state.db"
    repo = SessionRepo(db_path=db_path)
    repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )
    repo.set_runtime_state("session-1", {
        "session_lane_state": {
            "execution_lane": {
                "latest_execution_id": "execution_1",
                "latest_interaction_id": "interaction_1",
                "latest_interaction_type": "approval",
                "latest_interaction_state": "pending",
                "latest_interaction_version": 2,
                "latest_interaction_expires_at": "2026-08-13T12:00:00Z",
                "last_event_sequence": 9,
            }
        }
    })

    rehydrated = SessionRepo(db_path=db_path).get_runtime_state("session-1")
    lane = rehydrated["session_lane_state"]["execution_lane"]

    assert lane["latest_interaction_id"] == "interaction_1"
    assert lane["last_event_sequence"] == 9
    assert "prompt" not in lane
    assert not any("provider" in key for key in lane)
