import unittest

from jsonschema.exceptions import ValidationError

from backend.schemas import (
    validate_adapter_json,
    validate_config_json,
    validate_evidence_item,
    validate_final_answer,
    validate_planner_output,
)


def make_valid_config_json():
    return {
        "meta": {"title": "Config", "domain_hint": "general", "version_hint": None, "author": None},
        "role": {"name": "assistant", "mission": ["help users"]},
        "goals": ["answer clearly"],
        "mode_detection": [{"mode": "default", "triggers": ["question"], "priority": 1}],
        "coverage_rules": ["stay in scope"],
        "retrieval_rules": ["retrieve relevant docs"],
        "style_rules": ["be concise"],
        "safety_rules": ["do not hallucinate"],
        "step_skeletons": [{"intent_or_mode": "qa", "steps": ["understand", "retrieve", "answer"]}],
        "modules": [{"name": "search", "triggers": ["lookup"], "behavior": None}],
        "controls_commands": [{"command": "/reset", "effect": "clear session"}],
    }


def make_valid_adapter_json():
    return {
        "domain": "general",
        "version": 1,
        "intent_overrides": [
            {
                "alias_intent": "qa",
                "triggers_from_config": ["question"],
                "maps_to_base_intent": "qa",
            }
        ],
        "step_skeleton_mapping": {
            "use_config_step_skeletons": True,
            "default_mode": "default",
            "step_waiting_policy": {"wait_for_user_each_step": False, "max_questions_per_turn": 3},
        },
        "info_type_to_tags": {"fact": ["policy"]},
        "retrieval_defaults": {"top_k_range": [1, 5], "language": "en"},
        "plugin_activation_rules_file": None,
        "llm_guardrails_append": ["be precise"],
    }


def make_valid_planner_output():
    return {
        "intentType": "qa",
        "confidence": 0.8,
        "steps": [{"id": "1", "title": "Retrieve", "goal": "Find evidence", "reasoning": None}],
        "infoTypes": ["fact"],
        "retrievalPlan": {"query_text": "policy", "top_k": 3, "filters": {}, "explanation": None},
        "systemInstructionSummary": {
            "fromConfigPdf": ["rule A"],
            "fromAdapter": ["rule B"],
            "fromTemplate": ["rule C"],
        },
        "normalizedQuery": "policy",
        "contextualQuery": "policy details",
    }


def make_valid_final_answer():
    return {
        "content": "Here is the answer.",
        "citations": [
            {
                "docId": "doc-1",
                "title": "Policy Doc",
                "snippet": "Relevant policy text.",
                "score": 0.92,
                "location": None,
                "version": None,
            }
        ],
        "missing_infoTypes": [],
    }


def make_valid_evidence_item():
    return {
        "doc_id": "doc-1",
        "title": "Policy Doc",
        "snippet": "Relevant policy text.",
        "score": 0.88,
        "metadata": {"section": "intro"},
        "version": None,
        "location": None,
        "chunk_id": None,
    }


class SchemaValidatorTests(unittest.TestCase):
    def test_validate_config_json_happy_path(self):
        validate_config_json(make_valid_config_json())

    def test_validate_config_json_missing_required(self):
        payload = make_valid_config_json()
        payload.pop("goals")
        with self.assertRaises(ValidationError):
            validate_config_json(payload)

    def test_validate_adapter_json_happy_path(self):
        validate_adapter_json(make_valid_adapter_json())

    def test_validate_adapter_json_invalid_waiting_policy(self):
        payload = make_valid_adapter_json()
        payload["step_skeleton_mapping"]["step_waiting_policy"]["max_questions_per_turn"] = 9
        with self.assertRaises(ValidationError):
            validate_adapter_json(payload)

    def test_validate_planner_output_happy_path(self):
        validate_planner_output(make_valid_planner_output())

    def test_validate_planner_output_invalid_confidence(self):
        payload = make_valid_planner_output()
        payload["confidence"] = 1.5
        with self.assertRaises(ValidationError):
            validate_planner_output(payload)

    def test_validate_final_answer_happy_path(self):
        validate_final_answer(make_valid_final_answer())

    def test_validate_final_answer_missing_citations(self):
        payload = make_valid_final_answer()
        payload.pop("citations")
        with self.assertRaises(ValidationError):
            validate_final_answer(payload)

    def test_validate_evidence_item_happy_path(self):
        validate_evidence_item(make_valid_evidence_item())

    def test_validate_evidence_item_missing_doc_id(self):
        payload = make_valid_evidence_item()
        payload.pop("doc_id")
        with self.assertRaises(ValidationError):
            validate_evidence_item(payload)


if __name__ == "__main__":
    unittest.main()

