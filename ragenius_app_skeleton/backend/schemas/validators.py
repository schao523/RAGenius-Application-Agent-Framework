"""JSON Schema validators for RAGenius app payload contracts."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO_ROOT / "schemas"


def get_schema_path(filename: str) -> Path:
    path = SCHEMA_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Schema file not found: {path}")
    return path


@lru_cache(maxsize=16)
def load_schema(filename: str) -> Dict[str, Any]:
    schema_path = get_schema_path(filename)
    with schema_path.open("r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=16)
def get_validator(filename: str) -> Draft202012Validator:
    return Draft202012Validator(load_schema(filename))


def validate_config_json(payload: Dict[str, Any]) -> None:
    get_validator("config_json.schema.json").validate(payload)


def validate_adapter_json(payload: Dict[str, Any]) -> None:
    get_validator("adapter.schema.json").validate(payload)


def validate_planner_output(payload: Dict[str, Any]) -> None:
    get_validator("planner_output.schema.json").validate(payload)


def validate_final_answer(payload: Dict[str, Any]) -> None:
    get_validator("final_answer.schema.json").validate(payload)


def validate_evidence_item(payload: Dict[str, Any]) -> None:
    get_validator("evidence.schema.json").validate(payload)

