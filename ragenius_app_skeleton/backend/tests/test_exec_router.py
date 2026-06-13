from __future__ import annotations

from ragenius_app_skeleton.backend.app.exec_router import parse_exec_turn


def test_parse_exec_turn_non_prefixed_query_is_normal():
    decision = parse_exec_turn("Make the draft shorter.")
    assert decision.is_exec_turn is False
    assert decision.command is None


def test_parse_exec_turn_skill_command_with_key_values():
    decision = parse_exec_turn(
        '@exec skill notebooklm_generate_video notebookTitle="GPT Application Designer" waitForCompletion=false'
    )
    assert decision.is_exec_turn is True
    assert decision.command == "skill"
    assert decision.skill_id == "notebooklm_generate_video"
    assert decision.parsed_args["notebookTitle"] == "GPT Application Designer"
    assert decision.parsed_args["waitForCompletion"] is False


def test_parse_exec_turn_tool_command_with_key_values():
    decision = parse_exec_turn(
        '@exec tool adapter.notebooklm.generate_video notebookTitle="GPT Application Designer" waitForCompletion=false'
    )
    assert decision.is_exec_turn is True
    assert decision.command == "tool"
    assert decision.tool_id == "adapter.notebooklm.generate_video"
    assert decision.parsed_args["notebookTitle"] == "GPT Application Designer"
    assert decision.parsed_args["waitForCompletion"] is False


def test_parse_exec_turn_status_command():
    decision = parse_exec_turn("@exec status execution_123")
    assert decision.is_exec_turn is True
    assert decision.command == "status"
    assert decision.execution_id == "execution_123"


def test_parse_exec_turn_codex_command_with_plain_request():
    decision = parse_exec_turn('@exec codex "Use NotebookLM to summarize Micah 2."')

    assert decision.is_exec_turn is True
    assert decision.command == "codex"
    assert decision.agent_query == "Use NotebookLM to summarize Micah 2."
    assert decision.agent_skill_hint is None


def test_parse_exec_turn_codex_command_with_skill_hint():
    decision = parse_exec_turn('@exec codex use notebooklm "Generate a quiz from the approved content."')

    assert decision.is_exec_turn is True
    assert decision.command == "codex"
    assert decision.agent_skill_hint == "notebooklm"
    assert decision.agent_query == "Generate a quiz from the approved content."


def test_parse_exec_turn_async_skill_command():
    decision = parse_exec_turn(
        '@exec async skill notebooklm_generate_video notebookTitle="GPT Application Designer"'
    )
    assert decision.is_exec_turn is True
    assert decision.command == "skill"
    assert decision.skill_id == "notebooklm_generate_video"
    assert decision.parsed_args["notebookTitle"] == "GPT Application Designer"
    assert decision.parsed_args["execution_mode"] == "async"


def test_parse_exec_turn_rejects_malformed_key_value_args():
    decision = parse_exec_turn('@exec skill notebooklm_generate_video notebookTitle="Broken')

    assert decision.is_exec_turn is True
    assert decision.command == "skill"
    assert "Invalid exec arguments" in str(decision.error)


def test_parse_exec_turn_rejects_non_key_value_tokens_for_skill_args():
    decision = parse_exec_turn("@exec skill notebooklm_generate_video unexpected-token")

    assert decision.is_exec_turn is True
    assert decision.command == "skill"
    assert "Use key=value arguments" in str(decision.error)
