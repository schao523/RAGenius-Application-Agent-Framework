"""Deterministic parsing for explicit execution override turns."""

from __future__ import annotations

import json
import shlex
from typing import Any

from pydantic import BaseModel, Field


class ExecRouteDecision(BaseModel):
    is_exec_turn: bool
    command: str | None = None
    execution_mode: str | None = None
    skill_id: str | None = None
    tool_id: str | None = None
    agent_query: str | None = None
    agent_skill_hint: str | None = None
    execution_id: str | None = None
    raw_args: str = ""
    parsed_args: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


def _coerce_value(raw_value: str) -> Any:
    value = str(raw_value or "").strip()
    if not value:
        return ""
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "null":
        return None
    try:
        if value.startswith(("{", "[")) or value.startswith('"'):
            return json.loads(value)
    except Exception:
        pass
    try:
        if "." in value:
            return float(value)
        return int(value)
    except Exception:
        return value


def _parse_key_value_args(raw_args: str) -> dict[str, Any]:
    text = str(raw_args or "").strip()
    if not text:
        return {}
    if text.startswith("{"):
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else {}
    parsed: dict[str, Any] = {}
    for token in shlex.split(text):
        if "=" not in token:
            raise ValueError("Use key=value arguments after the skill id.")
        key, value = token.split("=", 1)
        key = key.strip()
        if not key:
            continue
        parsed[key] = _coerce_value(value)
    return parsed


def _parse_agent_query(raw_args: str) -> tuple[str | None, str | None]:
    text = str(raw_args or "").strip()
    if not text:
        return None, None
    tokens = shlex.split(text)
    if not tokens:
        return None, None
    if str(tokens[0] or "").strip().lower() == "use":
        if len(tokens) < 3:
            raise ValueError(
                "Use '@exec codex \"<request>\"' or '@exec codex use <skill> \"<request>\"'."
            )
        return str(tokens[1] or "").strip() or None, " ".join(tokens[2:]).strip() or None
    return None, " ".join(tokens).strip() or None


def parse_exec_turn(user_query: str) -> ExecRouteDecision:
    text = str(user_query or "").strip()
    if not text.startswith("@exec"):
        return ExecRouteDecision(is_exec_turn=False)
    remainder = text[len("@exec"):].strip()
    if not remainder:
        return ExecRouteDecision(
            is_exec_turn=True,
            error=(
                "Missing execution command. Use '@exec tool <tool_id> ...', "
                "'@exec skill <skill_id> ...', '@exec codex \"<request>\"', or '@exec status <execution_id>'."
            ),
        )
    execution_mode = None
    for candidate_mode in ("async", "sync"):
        prefix = f"{candidate_mode} "
        if remainder.lower().startswith(prefix):
            execution_mode = candidate_mode
            remainder = remainder[len(prefix):].strip()
            break
    if not remainder:
        return ExecRouteDecision(
            is_exec_turn=True,
            execution_mode=execution_mode,
            error=(
                "Missing execution command. Use '@exec tool <tool_id> ...', "
                "'@exec skill <skill_id> ...', '@exec codex \"<request>\"', or '@exec status <execution_id>'."
            ),
        )
    command_parts = remainder.split(maxsplit=1)
    command = str(command_parts[0] or "").strip().lower()
    rest = command_parts[1] if len(command_parts) > 1 else ""
    if command == "tool":
        if not rest:
            return ExecRouteDecision(
                is_exec_turn=True,
                execution_mode=execution_mode,
                command="tool",
                error="Missing tool id. Use '@exec tool <tool_id> ...'.",
            )
        tool_parts = rest.split(maxsplit=1)
        tool_id = tool_parts[0]
        raw_args = tool_parts[1] if len(tool_parts) > 1 else ""
        if not tool_id:
            return ExecRouteDecision(
                is_exec_turn=True,
                command="tool",
                execution_mode=execution_mode,
                error="Missing tool id. Use '@exec tool <tool_id> ...'.",
            )
        try:
            parsed_args = _parse_key_value_args(raw_args)
            if execution_mode and "execution_mode" not in parsed_args:
                parsed_args["execution_mode"] = execution_mode
        except Exception as exc:
            return ExecRouteDecision(
                is_exec_turn=True,
                command="tool",
                execution_mode=execution_mode,
                tool_id=tool_id,
                raw_args=raw_args,
                error=f"Invalid exec arguments: {exc}",
            )
        return ExecRouteDecision(
            is_exec_turn=True,
            command="tool",
            execution_mode=execution_mode,
            tool_id=tool_id,
            raw_args=raw_args,
            parsed_args=parsed_args,
        )
    if command == "skill":
        if not rest:
            return ExecRouteDecision(
                is_exec_turn=True,
                execution_mode=execution_mode,
                command="skill",
                error="Missing skill id. Use '@exec skill <skill_id> ...'.",
            )
        skill_parts = rest.split(maxsplit=1)
        skill_id = skill_parts[0]
        raw_args = skill_parts[1] if len(skill_parts) > 1 else ""
        if not skill_id:
            return ExecRouteDecision(
                is_exec_turn=True,
                command="skill",
                execution_mode=execution_mode,
                error="Missing skill id. Use '@exec skill <skill_id> ...'.",
            )
        try:
            parsed_args = _parse_key_value_args(raw_args)
            if execution_mode and "execution_mode" not in parsed_args:
                parsed_args["execution_mode"] = execution_mode
        except Exception as exc:
            return ExecRouteDecision(
                is_exec_turn=True,
                command="skill",
                execution_mode=execution_mode,
                skill_id=skill_id,
                raw_args=raw_args,
                error=f"Invalid exec arguments: {exc}",
            )
        return ExecRouteDecision(
            is_exec_turn=True,
            command="skill",
            execution_mode=execution_mode,
            skill_id=skill_id,
            raw_args=raw_args,
            parsed_args=parsed_args,
        )
    if command == "status":
        execution_id = rest.split(maxsplit=1)[0] if rest else ""
        if not execution_id:
            return ExecRouteDecision(
                is_exec_turn=True,
                command="status",
                execution_mode=execution_mode,
                error="Missing execution id. Use '@exec status <execution_id>'.",
            )
        return ExecRouteDecision(
            is_exec_turn=True,
            command="status",
            execution_mode=execution_mode,
            execution_id=execution_id,
            raw_args=execution_id,
        )
    if command == "codex":
        try:
            agent_skill_hint, agent_query = _parse_agent_query(rest)
        except Exception as exc:
            return ExecRouteDecision(
                is_exec_turn=True,
                command="codex",
                execution_mode=execution_mode,
                raw_args=rest,
                error=f"Invalid exec arguments: {exc}",
            )
        if not agent_query:
            return ExecRouteDecision(
                is_exec_turn=True,
                command="codex",
                execution_mode=execution_mode,
                raw_args=rest,
                error="Missing Codex request. Use '@exec codex \"<request>\"'.",
            )
        parsed_args: dict[str, Any] = {}
        if execution_mode:
            parsed_args["execution_mode"] = execution_mode
        if agent_skill_hint:
            parsed_args["agent_skill_hint"] = agent_skill_hint
        return ExecRouteDecision(
            is_exec_turn=True,
            command="codex",
            execution_mode=execution_mode,
            agent_query=agent_query,
            agent_skill_hint=agent_skill_hint,
            raw_args=rest,
            parsed_args=parsed_args,
        )
    return ExecRouteDecision(
        is_exec_turn=True,
        command=command,
        execution_mode=execution_mode,
        error="Unsupported exec command. Supported: tool, skill, codex, status.",
    )
