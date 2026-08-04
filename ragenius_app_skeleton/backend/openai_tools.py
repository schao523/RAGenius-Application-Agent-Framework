"""OpenAI function-calling tool registry.

Loads tool definitions from backend/function_schemas.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

FUNCTION_SCHEMA_DIR = Path(__file__).resolve().parent / "function_schemas"

REQUIRED_TOOLS = [
    "create_planner_output",
    "generate_adapter_draft",
    "create_final_answer",
]

OPTIONAL_TOOLS = ["evidence_analysis"]


def _load_function_schema(name: str) -> Dict:
    path = FUNCTION_SCHEMA_DIR / f"{name}.schema.json"
    if not path.exists():
        raise FileNotFoundError(f"Function schema not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def get_openai_tools(include_optional: bool = True) -> List[Dict]:
    tools: List[Dict] = []

    for tool_name in REQUIRED_TOOLS:
        tools.append(_load_function_schema(tool_name))

    if include_optional:
        for tool_name in OPTIONAL_TOOLS:
            path = FUNCTION_SCHEMA_DIR / f"{tool_name}.schema.json"
            if path.exists():
                tools.append(_load_function_schema(tool_name))

    return tools


__all__ = ["get_openai_tools"]

