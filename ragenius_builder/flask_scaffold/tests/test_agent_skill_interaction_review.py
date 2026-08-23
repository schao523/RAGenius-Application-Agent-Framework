from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCAFFOLD_DIR = Path(__file__).resolve().parents[1]
if str(SCAFFOLD_DIR) not in sys.path:
    sys.path.insert(0, str(SCAFFOLD_DIR))

from agent_skill_interaction_review import (  # noqa: E402
    build_agent_skill_interaction_recommendation,
    interaction_policy_from_form,
)


class AgentSkillInteractionRecommendationTests(unittest.TestCase):
    def test_recommends_openclaw_chat_level_only_with_explicit_interaction_evidence(self) -> None:
        recommendation = build_agent_skill_interaction_recommendation(
            {
                "backend": "openclaw_cli",
                "display_name": "TaskFlow",
                "provider_skill_name": "taskflow",
                "provider_skill_reference": "taskflow",
                "description": "Show the draft and wait for the user to confirm before continuing.",
                "provider_metadata": {},
            }
        )

        self.assertEqual(recommendation["recommended_channel"], "chat_level")
        self.assertEqual(recommendation["confidence"], "medium")
        self.assertIn("wait for the user", recommendation["evidence"])
        self.assertEqual(
            recommendation["policy"],
            {
                "interaction_channel": "chat_level",
                "interaction_requirement": "autonomous",
                "supported_interaction_types": [],
                "required_transport": "interactive",
                "recovery_class": "session_resumable",
            },
        )

    def test_recommends_codex_typed_categories_from_explicit_description(self) -> None:
        recommendation = build_agent_skill_interaction_recommendation(
            {
                "backend": "codex_cli",
                "display_name": "Report helper",
                "provider_skill_name": "report-helper",
                "provider_skill_reference": "report-helper",
                "description": "Ask the user to select Markdown or plain text before writing.",
                "provider_metadata": {},
            }
        )

        self.assertEqual(recommendation["recommended_channel"], "typed")
        self.assertEqual(
            recommendation["policy"]["supported_interaction_types"],
            ["clarification", "selection"],
        )
        self.assertEqual(recommendation["policy"]["interaction_requirement"], "conditional")

    def test_keeps_ordinary_skill_one_shot_when_evidence_is_ambiguous(self) -> None:
        recommendation = build_agent_skill_interaction_recommendation(
            {
                "backend": "codex_cli",
                "display_name": "Research Papers",
                "provider_skill_name": "research-paper-finder",
                "provider_skill_reference": "research-paper-finder",
                "description": "Find and summarize research papers.",
                "provider_metadata": {},
            }
        )

        self.assertEqual(recommendation["recommended_channel"], "none")
        self.assertEqual(recommendation["confidence"], "low")
        self.assertEqual(recommendation["policy"]["required_transport"], "one_shot")


class AgentSkillInteractionFormTests(unittest.TestCase):
    def test_builds_administrator_selected_codex_typed_policy(self) -> None:
        policy = interaction_policy_from_form(
            {
                "interaction_channel": "typed",
                "interaction_requirement": "required",
                "supported_interaction_types": ["selection", "clarification"],
            },
            backend="codex_cli",
        )

        self.assertEqual(
            policy,
            {
                "interaction_channel": "typed",
                "interaction_requirement": "required",
                "supported_interaction_types": ["clarification", "selection"],
                "required_transport": "interactive",
                "recovery_class": "turn_resumable",
            },
        )

    def test_rejects_chat_level_policy_for_codex(self) -> None:
        with self.assertRaisesRegex(ValueError, "AGENT_SKILL_INTERACTION_POLICY_INVALID"):
            interaction_policy_from_form(
                {"interaction_channel": "chat_level"}, backend="codex_cli"
            )


if __name__ == "__main__":
    unittest.main()
