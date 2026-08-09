from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path


SCAFFOLD_DIR = Path(__file__).resolve().parents[1]
if str(SCAFFOLD_DIR) not in sys.path:
    sys.path.insert(0, str(SCAFFOLD_DIR))
os.environ["RAGENIUS_BUILDER_DISABLE_GLOBAL_STORE"] = "1"

from agent_skill_execution_client import AgentSkillExecutionClient  # noqa: E402


class AgentSkillExecutionClientTests(unittest.TestCase):
    def test_requires_dedicated_service_token(self) -> None:
        with self.assertRaisesRegex(ValueError, "service token"):
            AgentSkillExecutionClient("http://127.0.0.1:3001", "  ")


if __name__ == "__main__":
    unittest.main()
