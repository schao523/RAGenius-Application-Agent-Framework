import unittest

from backend.openai_tools import get_openai_tools


class OpenAIToolRegistryTests(unittest.TestCase):
    def test_required_tools_are_registered(self):
        tools = get_openai_tools(include_optional=False)
        names = [tool["name"] for tool in tools]
        self.assertEqual(
            names,
            [
                "create_planner_output",
                "generate_adapter_draft",
                "create_final_answer",
            ],
        )

    def test_optional_tool_included_when_present(self):
        tools = get_openai_tools(include_optional=True)
        names = [tool["name"] for tool in tools]
        self.assertIn("evidence_analysis", names)

    def test_tool_payload_shape(self):
        tools = get_openai_tools(include_optional=True)
        for tool in tools:
            self.assertIn("name", tool)
            self.assertIn("parameters", tool)


if __name__ == "__main__":
    unittest.main()

