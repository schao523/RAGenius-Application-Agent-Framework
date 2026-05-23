import json
import unittest
from pathlib import Path

from backend.app.adapter_repo import InMemoryAdapterRepo
from workflows.nodes import load_or_generate_adapter as node
from workflows.nodes import load_or_generate_adapter_c1, load_or_generate_adapter_c2, load_or_generate_adapter_c3
from workflows.nodes.load_or_generate_adapter_c3 import PendingAdapterApproval


def load_fixture(name: str):
    path = Path(__file__).resolve().parent / "fixtures" / name
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


class AdapterNodeTests(unittest.TestCase):
    def setUp(self):
        self.repo = InMemoryAdapterRepo()
        self.valid_adapter = load_fixture("adapter_valid.json")
        self.invalid_adapter = load_fixture("adapter_invalid.json")
        self.state = {
            "collection_id": "col1",
            "domain": "general",
            "config_json": {},
        }

    def test_c1_generates_and_saves_draft(self):
        calls = {"count": 0}

        def llm(prompt, tools, context):
            calls["count"] += 1
            self.assertTrue(prompt)
            self.assertEqual(tools[0]["name"], "generate_adapter_draft")
            self.assertEqual(context["collection_id"], "col1")
            return self.valid_adapter

        out = load_or_generate_adapter_c1.run(self.state.copy(), llm_generate_adapter=llm, repo=self.repo)
        self.assertEqual(calls["count"], 1)
        self.assertIn("adapter_draft", out)
        self.assertEqual(out["adapter_draft_version"], 1)
        self.assertIsNotNone(self.repo.get_draft("col1"))

    def test_c2_retries_when_invalid_then_passes(self):
        attempts = {"n": 0}

        def llm(_prompt, _tools, _context):
            attempts["n"] += 1
            return self.valid_adapter

        state = self.state.copy()
        state["adapter_draft"] = self.invalid_adapter
        state["adapter_draft_version"] = 1
        out = load_or_generate_adapter_c2.run(state, llm_generate_adapter=llm, repo=self.repo, max_retries=2)
        self.assertIn("adapter_draft", out)
        self.assertGreaterEqual(attempts["n"], 1)

    def test_c3_blocks_when_only_draft_exists(self):
        self.repo.save_draft("col1", self.valid_adapter, version=2)
        with self.assertRaises(PendingAdapterApproval):
            load_or_generate_adapter_c3.run(self.state.copy(), repo=self.repo)

    def test_c3_passes_when_approved_exists(self):
        self.repo.save_draft("col1", self.valid_adapter, version=2)
        approved = self.repo.approve("col1", approved_by="admin")
        out = load_or_generate_adapter_c3.run(self.state.copy(), repo=self.repo)
        self.assertEqual(out["adapter_version"], approved.version)

    def test_orchestrator_uses_existing_approved_without_llm(self):
        self.repo.save_draft("col1", self.valid_adapter, version=2)
        self.repo.approve("col1", approved_by="admin")

        def llm(_prompt, _tools, _context):
            raise AssertionError("LLM should not be called when approved adapter exists.")

        out = node.run(self.state.copy(), llm_generate_adapter=llm, repo=self.repo)
        self.assertIn("adapter_json", out)
        self.assertEqual(out["adapter_version"], self.repo.get_active_version("col1"))


if __name__ == "__main__":
    unittest.main()

