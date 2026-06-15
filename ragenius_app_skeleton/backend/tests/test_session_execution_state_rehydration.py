from __future__ import annotations

from ragenius_app_skeleton.workflows.nodes.load_template_registry import (
    _sanitize_session_execution_state_for_rehydration,
)
from ragenius_app_skeleton.workflows.runtime_models import SessionExecutionState


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
