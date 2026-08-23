from __future__ import annotations

import json
import re
from typing import Any, Mapping


_ONE_SHOT_POLICY = {
    "interaction_channel": "none",
    "interaction_requirement": "autonomous",
    "supported_interaction_types": [],
    "required_transport": "one_shot",
    "recovery_class": "not_resumable",
}

_EVIDENCE_PATTERNS = {
    "approval": (
        r"\bapproval\b",
        r"\bapprove\b",
        r"\bconfirm(?:ation)?\b",
        r"\bconsent\b",
    ),
    "clarification": (
        r"\bclarif(?:y|ication)\b",
        r"\bask (?:the )?user\b",
        r"\buser input\b",
        r"\bfollow[- ]up question\b",
    ),
    "selection": (
        r"\bselect(?:ion)?\b",
        r"\bchoose\b",
        r"\buser choice\b",
        r"\boptions? to (?:the )?user\b",
    ),
    "authentication_handoff": (
        r"\bauthentication\b",
        r"\bauthenticate\b",
        r"\blog[ -]?in\b",
        r"\bsign[ -]?in\b",
    ),
    "user_action_required": (
        r"\buser action\b",
        r"\bmanual action\b",
        r"\bwait for (?:the )?user\b",
        r"\bcontinue after\b",
    ),
}


def build_agent_skill_interaction_recommendation(skill: Mapping[str, Any]) -> dict[str, Any]:
    """Build advisory review metadata without changing trusted governance state."""
    text = _searchable_skill_text(skill)
    evidence_by_type = {
        interaction_type: _matching_evidence(text, patterns)
        for interaction_type, patterns in _EVIDENCE_PATTERNS.items()
    }
    matched_types = [
        interaction_type
        for interaction_type, evidence in evidence_by_type.items()
        if evidence
    ]
    evidence = sorted(
        {
            item
            for values in evidence_by_type.values()
            for item in values
        }
    )
    if re.search(r"\btask[ -]?flow\b", text):
        evidence.append("taskflow")

    backend = str(skill.get("backend") or "")
    if backend == "openclaw_cli" and evidence:
        return {
            "recommended_channel": "chat_level",
            "confidence": "medium",
            "reason": (
                "The discovered description explicitly suggests a user follow-up. "
                "OpenClaw should continue this skill through chat-level interaction."
            ),
            "evidence": sorted(set(evidence)),
            "policy": {
                "interaction_channel": "chat_level",
                "interaction_requirement": "autonomous",
                "supported_interaction_types": [],
                "required_transport": "interactive",
                "recovery_class": "session_resumable",
            },
        }

    if backend == "codex_cli" and matched_types:
        return {
            "recommended_channel": "typed",
            "confidence": "medium",
            "reason": (
                "The discovered description explicitly suggests structured user input. "
                "Confirm the interaction categories before approval."
            ),
            "evidence": sorted(set(evidence)),
            "policy": {
                "interaction_channel": "typed",
                "interaction_requirement": "conditional",
                "supported_interaction_types": sorted(matched_types),
                "required_transport": "interactive",
                "recovery_class": "turn_resumable",
            },
        }

    return {
        "recommended_channel": "none",
        "confidence": "low",
        "reason": (
            "Discovery found no explicit interaction evidence. Keep one-shot execution "
            "unless the skill instructions are known to require user input."
        ),
        "evidence": [],
        "policy": {**_ONE_SHOT_POLICY, "supported_interaction_types": []},
    }


def interaction_policy_from_form(form: Mapping[str, Any], *, backend: str) -> dict[str, Any]:
    channel = str(form.get("interaction_channel") or "none").strip()
    if channel == "none":
        return {**_ONE_SHOT_POLICY, "supported_interaction_types": []}
    if channel == "chat_level":
        if backend != "openclaw_cli":
            raise ValueError("AGENT_SKILL_INTERACTION_POLICY_INVALID")
        return {
            "interaction_channel": "chat_level",
            "interaction_requirement": "autonomous",
            "supported_interaction_types": [],
            "required_transport": "interactive",
            "recovery_class": "session_resumable",
        }
    if channel != "typed" or backend != "codex_cli":
        raise ValueError("AGENT_SKILL_INTERACTION_POLICY_INVALID")

    getlist = getattr(form, "getlist", None)
    raw_types = (
        getlist("supported_interaction_types")
        if callable(getlist)
        else form.get("supported_interaction_types", [])
    )
    if isinstance(raw_types, str):
        raw_types = [raw_types]
    interaction_types = sorted({str(item).strip() for item in raw_types if str(item).strip()})
    requirement = str(form.get("interaction_requirement") or "conditional").strip()
    if requirement not in {"conditional", "required"} or not interaction_types:
        raise ValueError("AGENT_SKILL_INTERACTION_POLICY_INVALID")
    return {
        "interaction_channel": "typed",
        "interaction_requirement": requirement,
        "supported_interaction_types": interaction_types,
        "required_transport": "interactive",
        "recovery_class": "turn_resumable",
    }


def _searchable_skill_text(skill: Mapping[str, Any]) -> str:
    values = [
        skill.get("display_name"),
        skill.get("provider_skill_name"),
        skill.get("provider_skill_reference"),
        skill.get("description"),
        json.dumps(skill.get("provider_metadata") or {}, sort_keys=True),
    ]
    return " ".join(str(value or "") for value in values).casefold()


def _matching_evidence(text: str, patterns: tuple[str, ...]) -> list[str]:
    evidence = []
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            evidence.append(match.group(0))
    return evidence
