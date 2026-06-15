from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _json_block(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=True, sort_keys=True)


def render_tools_info_markdown(tool_inventory_items: list[dict[str, Any]]) -> str:
    lines: list[str] = [
        "# RAGenius Tools Inventory",
        "",
        "Generated from the execution subsystem `/v1/tools/inventory` contract.",
        "Use this file as designer-facing reference when creating Builder-managed skills.",
        "",
        f"Total tools: {len(tool_inventory_items)}",
    ]

    for item in sorted(
        tool_inventory_items,
        key=lambda current: str(current.get("tool_id") or ""),
    ):
        permission_scopes = item.get("permission_scopes") or []
        permission_text = ", ".join(f"`{scope}`" for scope in permission_scopes) or "-"
        risk_class = "write" if item.get("side_effecting") else "read_only"
        fallback = item.get("fallback_strategy") if item.get("fallback_capable") else None
        lines.extend(
            [
                "",
                f"## `{item.get('tool_id', '')}`",
                "",
                f"- Name: {item.get('name') or '-'}",
                f"- Family: `{item.get('family') or '-'}`",
                f"- Provider: `{item.get('provider_id') or '-'}`",
                f"- Enabled: `{'yes' if item.get('enabled') else 'no'}`",
                f"- Permission scopes: {permission_text}",
                f"- Policy class: `{item.get('policy_class') or '-'}`",
                f"- Side effects: `{risk_class}`",
                f"- Timeout ms: `{item.get('timeout_ms') if item.get('timeout_ms') is not None else '-'}`",
                f"- Fallback strategy: `{fallback or '-'}`",
                "",
                "### Input Schema",
                "",
                "```json",
                _json_block(item.get("input_schema") or {}),
                "```",
                "",
                "### Output Schema",
                "",
                "```json",
                _json_block(item.get("output_schema") or {}),
                "```",
            ]
        )
        metadata = item.get("metadata")
        if metadata:
            lines.extend(
                [
                    "",
                    "### Metadata",
                    "",
                    "```json",
                    _json_block(metadata),
                    "```",
                ]
            )

    return "\n".join(lines) + "\n"


def write_tools_info_markdown(
    export_path: Path,
    tool_inventory_items: list[dict[str, Any]],
) -> Path:
    export_path.parent.mkdir(parents=True, exist_ok=True)
    export_path.write_text(
        render_tools_info_markdown(tool_inventory_items),
        encoding="utf-8",
    )
    return export_path


def render_tools_info_failure_markdown(
    *,
    base_url: str,
    status_code: int | None,
    error: dict[str, Any] | None,
) -> str:
    lines = [
        "# RAGenius Tools Inventory Export Failed",
        "",
        "Builder could not retrieve `/v1/tools/inventory` from the execution subsystem.",
        "",
        f"- Execution base URL: `{base_url}`",
        f"- HTTP status: `{status_code if status_code is not None else 'unavailable'}`",
        f"- Error code: `{(error or {}).get('code') or 'unknown'}`",
        f"- Error message: `{(error or {}).get('message') or 'unknown error'}`",
        "",
        "## Next Step",
        "",
        "Start or fix the execution subsystem, then export again.",
        "Check `RAGENIUS_EXECUTION_BASE_URL` in the Builder runtime if the URL is wrong.",
        "",
        "## Raw Error",
        "",
        "```json",
        _json_block(error or {}),
        "```",
    ]
    return "\n".join(lines) + "\n"


def write_tools_info_failure_markdown(
    export_path: Path,
    *,
    base_url: str,
    status_code: int | None,
    error: dict[str, Any] | None,
) -> Path:
    export_path.parent.mkdir(parents=True, exist_ok=True)
    export_path.write_text(
        render_tools_info_failure_markdown(
            base_url=base_url,
            status_code=status_code,
            error=error,
        ),
        encoding="utf-8",
    )
    return export_path
