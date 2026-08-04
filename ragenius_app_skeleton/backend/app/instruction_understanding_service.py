"""Persistent compiled understanding for builder application instructions."""

from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .builder_store import BuilderStore
from .chat_repos import InstructionUnderstandingRepo
from .llm_runtime import maybe_build_task_callable

try:
    from workflows.nodes import load_template_registry
except ModuleNotFoundError:  # pragma: no cover
    from ragenius_app_skeleton.workflows.nodes import load_template_registry


PARSER_CONTRACT_VERSION = "instruction-parser-2026-05-18-v3"
BINDING_LOGIC_VERSION = "binding-logic-2026-05-07-v1"
SEMANTIC_COMPILER_VERSION = "instruction-semantic-compiler-2026-05-14-v2"
REVIEW_PROMPT_VERSION = "instruction-understanding-review-2026-05-14-v3"
REVISION_PROMPT_VERSION = "instruction-understanding-revision-2026-05-13-v1"
SEMANTIC_COMPILE_PROMPT_VERSION = "instruction-understanding-compile-2026-05-18-v4"

INSTRUCTION_UNDERSTANDING_COMPILE_PROMPT = (
    "You are compiling semantic application understanding from a deterministic structural parse. "
    "You must classify only the supplied candidates and return JSON only. "
    "Do not invent resources, ids, workflows, modules, roles, or rules that are not grounded in the supplied context. "
    "If the app is a single default workflow app, set primary_service_mode=single_default_workflow and provide exactly one default primary_workflow block plus default_workflow_id. "
    "If the app is genuinely modeled as multiple executable workflows, set primary_service_mode=intent_routed_multi_workflow, do not set default_workflow_id, and provide grounded routing_rules plus executable workflow targets. "
    "If the app is primarily rule-routed by roles, mode-switching logic, or orchestration policy, set primary_service_mode=intent_routed_interaction_logic. "
    "For intent_routed_interaction_logic, top-level routing policy belongs in interaction_logic_blocks and routing_rules, and executable workflows or modules are optional subordinate targets rather than mode-wide requirements. "
    "For intent_routed_multi_workflow, every routing path must resolve to executable workflow or module targets, not only policy text or role labels. "
    "If a route targets a role, that role must point to concrete executable workflows or modules when workflow execution is required. "
    "Section title markers are authoritative: titles containing 模組 or Module mean module, titles containing 流程 or workflow mean workflow, and titles containing both are ambiguous authoring that must not be reinterpreted structurally. "
    "Global interaction logic may live at top level and should be captured in interaction_logic_blocks and global_app_contract. "
    "Multiple roles with role-specific tone, style, and workflow/module permissions are allowed when grounded. "
    "Module orchestration, if present, must be ordered sequential only."
)
INSTRUCTION_UNDERSTANDING_REVIEW_PROMPT = (
    "You are reviewing a compiled understanding of application instructions. "
    "Assess whether the inferred primary workflow, service-block classifications, procedures, "
    "steps, role routing, module orchestration, and resource bindings are plausible and internally consistent. "
    "Pay attention to false trigger extraction, phantom resources, empty step bodies, prose-only procedures, "
    "and incorrect default-workflow assumptions. "
    "Treat trigger candidates as suspicious when they appear to come from examples, illustrations, or body text inside a module "
    "instead of explicit routing or mode-selection rules. "
    "Return advisory findings only."
)
INSTRUCTION_UNDERSTANDING_REVISION_PROMPT = (
    "You are revising a compiled application understanding using only approved findings. "
    "Revise only the approved areas, preserve ids where possible, and return JSON only."
)

INSTRUCTION_UNDERSTANDING_COMPILE_TOOL = {
    "name": "create_instruction_understanding_compile",
    "description": "Return a semantic compile candidate for application instruction understanding.",
    "parameters": {
        "type": "object",
        "properties": {
            "app_semantic_model": {"type": "object"},
        },
        "required": ["app_semantic_model"],
        "additionalProperties": False,
    },
}
INSTRUCTION_UNDERSTANDING_REVIEW_TOOL = {
    "name": "create_instruction_understanding_review",
    "description": "Return an advisory review of the compiled application instruction understanding.",
    "parameters": {
        "type": "object",
        "properties": {
            "review_status": {
                "type": "string",
                "enum": ["reviewed_ok", "reviewed_with_warnings", "review_failed"],
            },
            "review_confidence": {"type": "number"},
            "review_findings": {"type": "object"},
            "review_summary_md": {"type": "string"},
            "review_recommendations": {"type": "object"},
        },
        "required": [
            "review_status",
            "review_confidence",
            "review_findings",
            "review_summary_md",
            "review_recommendations",
        ],
        "additionalProperties": False,
    },
}
INSTRUCTION_UNDERSTANDING_REVISION_TOOL = {
    "name": "create_instruction_understanding_revision",
    "description": "Return a revised semantic application-understanding candidate using approved findings only.",
    "parameters": {
        "type": "object",
        "properties": {
            "revised_semantic_model": {"type": "object"},
            "revision_notes": {"type": "array", "items": {"type": "string"}},
            "preserved_ids": {"type": "array", "items": {"type": "string"}},
            "changed_ids": {"type": "array", "items": {"type": "string"}},
            "revision_confidence": {"type": "number"},
        },
        "required": [
            "revised_semantic_model",
            "revision_notes",
            "preserved_ids",
            "changed_ids",
            "revision_confidence",
        ],
        "additionalProperties": False,
    },
}


def compute_instruction_source_hash(instruction_text: str) -> str:
    normalized = str(instruction_text or "").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def compute_resource_catalog_hash(documents: list[dict[str, Any]]) -> str:
    normalized_documents: list[dict[str, str]] = []
    for document in documents or []:
        if not isinstance(document, dict):
            continue
        normalized_documents.append(
            {
                "id": str(document.get("id") or "").strip(),
                "filename": str(document.get("filename") or "").strip(),
                "status": str(document.get("status") or "").strip(),
                "mime_type": str(document.get("mime_type") or "").strip(),
                "file_path": str(document.get("file_path") or "").strip(),
            }
        )
    normalized_documents.sort(
        key=lambda item: (
            item.get("filename") or "",
            item.get("id") or "",
            item.get("status") or "",
            item.get("mime_type") or "",
        )
    )
    return hashlib.sha256(
        json.dumps(normalized_documents, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def evaluate_instruction_understanding_cache(
    active_record: dict[str, Any] | None,
    *,
    instruction_source_hash: str,
    parser_contract_version: str = PARSER_CONTRACT_VERSION,
    binding_logic_version: str = BINDING_LOGIC_VERSION,
    resource_catalog_hash: str,
    semantic_compiler_version: str | None = None,
    semantic_compile_prompt_version: str | None = None,
) -> dict[str, Any]:
    if not isinstance(active_record, dict):
        return {"cache_status": "missing", "stale_reasons": ["missing"]}

    stale_reasons: list[str] = []
    cache_status = "hot"
    compiled_contract = (
        active_record.get("compiled_contract", {})
        if isinstance(active_record.get("compiled_contract"), dict)
        else {}
    )
    semantic_compile = (
        compiled_contract.get("semantic_compile", {})
        if isinstance(compiled_contract.get("semantic_compile"), dict)
        else {}
    )
    if str(active_record.get("instruction_source_hash") or "") != instruction_source_hash:
        cache_status = "stale_instructions"
        stale_reasons.append("instruction_source_hash")
    elif str(active_record.get("parser_contract_version") or "") != parser_contract_version:
        cache_status = "stale_parser_contract"
        stale_reasons.append("parser_contract_version")
    elif str(active_record.get("binding_logic_version") or "") != binding_logic_version:
        cache_status = "stale_binding_logic"
        stale_reasons.append("binding_logic_version")
    elif str(active_record.get("resource_catalog_hash") or "") != resource_catalog_hash:
        cache_status = "stale_resource_catalog"
        stale_reasons.append("resource_catalog_hash")
    elif semantic_compiler_version and str(semantic_compile.get("semantic_compiler_version") or "") != semantic_compiler_version:
        cache_status = "stale_semantic_compiler"
        stale_reasons.append("semantic_compiler_version")
    elif semantic_compile_prompt_version and str(semantic_compile.get("compiler_prompt_version") or "") != semantic_compile_prompt_version:
        cache_status = "stale_semantic_prompt"
        stale_reasons.append("semantic_compile_prompt_version")
    elif str(active_record.get("compiled_status") or "") != "ready":
        cache_status = "invalid"
        stale_reasons.append("compiled_status")
    return {"cache_status": cache_status, "stale_reasons": stale_reasons}


def _default_snapshot_root(builder_store: BuilderStore) -> Path:
    return Path(builder_store.db_path).resolve().parent / "instruction_understanding"


def _snapshot_fallback_root() -> Path:
    return Path(__file__).resolve().parents[1] / ".state" / "instruction_understanding_snapshots"


def _snapshot_json_path(*, app_id: str, snapshot_root: Path) -> Path:
    return Path(snapshot_root) / str(app_id) / "understanding.json"


def _snapshot_attempts_root(snapshot_root: Path) -> Path:
    return Path(f"{Path(snapshot_root)}_attempts")


def _snapshot_attempts_fallback_root() -> Path:
    return Path(__file__).resolve().parents[1] / ".state" / "instruction_understanding_attempts"


def _snapshot_attempt_slug(compiled_record: dict[str, Any]) -> str:
    compiled_at = str(compiled_record.get("compiled_at") or "").strip()
    record_id = str(compiled_record.get("id") or "").strip() or "record"
    timestamp_slug = (
        compiled_at.replace(":", "-").replace(".", "-").replace("+", "_")
        if compiled_at
        else "unknown-time"
    )
    return f"{timestamp_slug}--{record_id}"


def _parse_snapshot_compiled_at(value: Any) -> float:
    if not isinstance(value, str) or not value.strip():
        return 0.0
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return 0.0


def _load_snapshot_payload(*, app_id: str, snapshot_root: Path) -> dict[str, Any] | None:
    json_path = _snapshot_json_path(app_id=app_id, snapshot_root=snapshot_root)
    if not json_path.exists():
        return None
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if str(payload.get("app_id") or "").strip() != str(app_id):
        return None
    if not isinstance(payload.get("compiled_contract"), dict):
        return None
    return payload


def _hydrate_compiled_from_snapshot(
    *,
    app_id: str,
    repo: InstructionUnderstandingRepo,
    snapshot_root: Path,
) -> dict[str, Any] | None:
    candidate_roots = [Path(snapshot_root)]
    fallback_root = _snapshot_fallback_root()
    if fallback_root not in candidate_roots:
        candidate_roots.append(fallback_root)
    ranked_candidates: list[tuple[bool, float, int, Path, dict[str, Any]]] = []
    for root_index, root in enumerate(candidate_roots):
        payload = _load_snapshot_payload(app_id=app_id, snapshot_root=root)
        if not isinstance(payload, dict):
            continue
        ranked_candidates.append(
            (
                _record_has_valid_semantic_runtime(payload),
                _parse_snapshot_compiled_at(payload.get("compiled_at")),
                -root_index,
                root,
                payload,
            )
        )
    if not ranked_candidates:
        return None

    valid_candidates = [candidate for candidate in ranked_candidates if candidate[0]]
    if not valid_candidates:
        return None

    _, _, _, selected_root, selected_payload = max(valid_candidates, key=lambda item: item[:3])
    metadata = dict(selected_payload.get("metadata") or {})
    metadata.setdefault("restored_from_snapshot", True)
    metadata.setdefault("snapshot_root_used", str(selected_root))
    selected_payload["metadata"] = metadata
    selected_payload["is_active"] = True
    return repo.restore_compiled(selected_payload)


def _build_instruction_understanding_status(
    *,
    app_id: str,
    active: dict[str, Any] | None,
    review: dict[str, Any] | None,
    instruction_source_hash: str,
    resource_catalog_hash: str,
    parser_contract_version: str,
    binding_logic_version: str,
    semantic_compiler_version: str | None = None,
    semantic_compile_prompt_version: str | None = None,
) -> dict[str, Any]:
    cache = evaluate_instruction_understanding_cache(
        active,
        instruction_source_hash=instruction_source_hash,
        parser_contract_version=parser_contract_version,
        binding_logic_version=binding_logic_version,
        resource_catalog_hash=resource_catalog_hash,
        semantic_compiler_version=semantic_compiler_version,
        semantic_compile_prompt_version=semantic_compile_prompt_version,
    )
    return {
        "app_id": app_id,
        "compiled_status": active.get("compiled_status") if isinstance(active, dict) else None,
        "review_status": review.get("review_status") if isinstance(review, dict) else "not_reviewed",
        "cache_status": cache["cache_status"],
        "stale_reasons": cache["stale_reasons"],
        "instruction_source_hash": instruction_source_hash,
        "parser_contract_version": parser_contract_version,
        "binding_logic_version": binding_logic_version,
        "resource_catalog_hash": resource_catalog_hash,
    }


def _load_instruction_hashes(
    *,
    instructions: Dict[str, Any],
    documents: list[dict[str, Any]],
) -> tuple[str, str]:
    instruction_source_hash = compute_instruction_source_hash(str(instructions.get("content") or ""))
    resource_catalog_hash = compute_resource_catalog_hash(documents)
    return instruction_source_hash, resource_catalog_hash


def _build_instruction_understanding_detail(
    *,
    app_id: str,
    compiled: dict[str, Any] | None,
    latest_attempt: dict[str, Any] | None,
    review: dict[str, Any] | None,
    approval: dict[str, Any] | None,
    revision: dict[str, Any] | None,
    instruction_source_hash: str,
    resource_catalog_hash: str,
    parser_contract_version: str,
    binding_logic_version: str,
    semantic_compiler_version: str | None = None,
    semantic_compile_prompt_version: str | None = None,
) -> dict[str, Any]:
    status = _build_instruction_understanding_status(
        app_id=app_id,
        active=compiled,
        review=review,
        instruction_source_hash=instruction_source_hash,
        resource_catalog_hash=resource_catalog_hash,
        parser_contract_version=parser_contract_version,
        binding_logic_version=binding_logic_version,
        semantic_compiler_version=semantic_compiler_version,
        semantic_compile_prompt_version=semantic_compile_prompt_version,
    )
    return {
        "app_id": app_id,
        "compiled": compiled,
        "latest_attempt": latest_attempt,
        "review": review,
        "approval": approval,
        "revision": revision,
        "status": status,
    }


def _write_snapshot_files(*, target_dir: Path, app_id: str, compiled_record: dict[str, Any]) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    json_path = target_dir / "understanding.json"
    md_path = target_dir / "understanding.md"
    json_path.write_text(json.dumps(compiled_record, ensure_ascii=False, indent=2), encoding="utf-8")
    contract = dict(compiled_record.get("compiled_contract") or {})
    md_lines = [
        f"# Instruction Understanding: {app_id}",
        "",
        f"- Compiled status: {compiled_record.get('compiled_status')}",
        f"- Instruction source hash: {compiled_record.get('instruction_source_hash')}",
        f"- Parser contract version: {compiled_record.get('parser_contract_version')}",
        f"- Binding logic version: {compiled_record.get('binding_logic_version')}",
        "",
        "## Summary",
        "",
        f"- Service blocks: {len(contract.get('instruction_service_blocks', []) or [])}",
        f"- Procedures: {len(contract.get('instruction_procedures', []) or [])}",
        f"- Steps: {len(contract.get('procedure_steps', []) or [])}",
    ]
    md_path.write_text("\n".join(md_lines).strip() + "\n", encoding="utf-8")


def _write_snapshot_record(
    *,
    target_dir: Path,
    fallback_dir: Path,
    snapshot_root: Path,
    fallback_root: Path,
    app_id: str,
    compiled_record: dict[str, Any],
) -> dict[str, Any]:
    try:
        _write_snapshot_files(target_dir=target_dir, app_id=app_id, compiled_record=compiled_record)
        return {
            "snapshot_root_status": "primary",
            "snapshot_root_used": str(Path(snapshot_root)),
            "snapshot_dir_used": str(target_dir),
        }
    except OSError:
        _write_snapshot_files(target_dir=fallback_dir, app_id=app_id, compiled_record=compiled_record)
        return {
            "snapshot_root_status": "fallback",
            "snapshot_root_used": str(fallback_root),
            "snapshot_dir_used": str(fallback_dir),
            "snapshot_root_requested": str(Path(snapshot_root)),
        }


def _write_snapshots(*, app_id: str, compiled_record: dict[str, Any], snapshot_root: Path) -> dict[str, Any]:
    snapshot_meta: dict[str, Any] = {}
    publish_status = str((compiled_record.get("metadata") or {}).get("publish_status") or "")

    if publish_status == "active":
        active_meta = _write_snapshot_record(
            target_dir=Path(snapshot_root) / str(app_id),
            fallback_dir=_snapshot_fallback_root() / str(app_id),
            snapshot_root=Path(snapshot_root),
            fallback_root=_snapshot_fallback_root(),
            app_id=app_id,
            compiled_record=compiled_record,
        )
        snapshot_meta.update(active_meta)
        snapshot_meta["snapshot_publish_mode"] = "active"
    else:
        snapshot_meta["snapshot_publish_mode"] = "attempt_only"

    attempt_slug = _snapshot_attempt_slug(compiled_record)
    attempt_meta = _write_snapshot_record(
        target_dir=_snapshot_attempts_root(Path(snapshot_root)) / str(app_id) / attempt_slug,
        fallback_dir=_snapshot_attempts_fallback_root() / str(app_id) / attempt_slug,
        snapshot_root=_snapshot_attempts_root(Path(snapshot_root)),
        fallback_root=_snapshot_attempts_fallback_root(),
        app_id=app_id,
        compiled_record=compiled_record,
    )
    snapshot_meta.update(
        {
            "attempt_snapshot_root_status": attempt_meta.get("snapshot_root_status"),
            "attempt_snapshot_root_used": attempt_meta.get("snapshot_root_used"),
            "attempt_snapshot_dir_used": attempt_meta.get("snapshot_dir_used"),
            "attempt_snapshot_root_requested": attempt_meta.get("snapshot_root_requested"),
        }
    )
    return snapshot_meta


def _record_has_valid_semantic_runtime(record: dict[str, Any] | None) -> bool:
    if not isinstance(record, dict):
        return False
    metadata = dict(record.get("metadata") or {})
    if bool(metadata.get("semantic_compile_valid")):
        return True
    compiled_contract = dict(record.get("compiled_contract") or {})
    if isinstance(compiled_contract.get("hybrid_instruction_runtime_model"), dict):
        return True
    semantic_compile = dict(compiled_contract.get("semantic_compile") or {})
    validation = dict(semantic_compile.get("validation") or {})
    return bool(validation.get("valid"))


def _failed_semantic_compile_payload(
    *,
    semantic_compiler_version: str,
    error_message: str,
) -> dict[str, Any]:
    validation = {
        "valid": False,
        "errors": [error_message],
        "warnings": [],
        "normalized": {},
    }
    return {
        "compiler_prompt_version": SEMANTIC_COMPILE_PROMPT_VERSION,
        "semantic_compiler_version": semantic_compiler_version,
        "raw_result": {},
        "app_semantic_model": {},
        "errors": [error_message],
        "empty_result": True,
        "validation": validation,
    }


def _should_publish_compiled_record(
    *,
    active_record: dict[str, Any] | None,
    semantic_compile_attached: bool,
    semantic_compile_validation: dict[str, Any] | None,
) -> bool:
    if not semantic_compile_attached:
        return True
    if bool(semantic_compile_validation and semantic_compile_validation.get("valid")):
        return True
    return False


def _compile_contract(
    instruction_text: str,
    documents: list[dict[str, Any]],
) -> dict[str, Any]:
    document_registry = load_template_registry._build_builder_document_registry(documents)
    structural_candidate_graph = load_template_registry._build_structural_candidate_graph(
        instruction_text,
        document_registry=document_registry,
    )
    instruction_runtime_model = load_template_registry._build_instruction_runtime_model(
        instruction_text,
        document_registry=document_registry,
    )
    instruction_blocks = load_template_registry._extract_instruction_blocks(
        instruction_text,
        document_registry=document_registry,
    )
    instruction_scope_candidates = load_template_registry._extract_instruction_scope_candidates(
        instruction_text,
        instruction_blocks=instruction_blocks,
        document_registry=document_registry,
    )
    raw_resource_reference_catalog = load_template_registry._extract_resource_reference_catalog(
        instruction_text,
        document_registry=document_registry,
    )
    resource_reference_catalog = [
        item
        for item in raw_resource_reference_catalog or []
        if isinstance(item, dict) and str(item.get("filename") or "").strip()
    ]
    presentation_policy_hints = load_template_registry._extract_presentation_policy_hints(instruction_text)
    return {
        "full_instruction_text": load_template_registry._load_full_instruction_text(instruction_text),
        "structural_candidate_graph": structural_candidate_graph,
        "section_candidates": structural_candidate_graph.get("section_candidates", []),
        "step_candidates": structural_candidate_graph.get("step_candidates", []),
        "resource_candidates": structural_candidate_graph.get("resource_candidates", []),
        "rule_candidates": structural_candidate_graph.get("rule_candidates", []),
        "trigger_candidates": structural_candidate_graph.get("trigger_candidates", []),
        "role_candidates": structural_candidate_graph.get("role_candidates", []),
        "interaction_logic_candidates": structural_candidate_graph.get("interaction_logic_candidates", []),
        "parser_warnings": structural_candidate_graph.get("parser_warnings", []),
        "instruction_scope_candidates": instruction_scope_candidates,
        "resource_reference_catalog": resource_reference_catalog,
        "presentation_policy_hints": presentation_policy_hints,
        "instruction_units": load_template_registry._iter_instruction_units(
            instruction_text,
            document_registry=document_registry,
        ),
        "instruction_blocks": instruction_blocks,
        "instruction_modules": load_template_registry._extract_instruction_modules(
            instruction_text,
            document_registry=document_registry,
        ),
        "instruction_workflows": load_template_registry._extract_instruction_workflows(
            instruction_text,
            document_registry=document_registry,
        ),
        "instruction_runtime_model": instruction_runtime_model,
        "instruction_heading_tree": instruction_runtime_model.get("instruction_heading_tree", []),
        "instruction_service_blocks": instruction_runtime_model.get("instruction_service_blocks", []),
        "instruction_procedures": instruction_runtime_model.get("instruction_procedures", []),
        "procedure_steps": instruction_runtime_model.get("procedure_steps", []),
        "support_modules_v2": instruction_runtime_model.get("support_modules", []),
        "followup_modules": instruction_runtime_model.get("followup_modules", []),
        "global_policies": instruction_runtime_model.get("global_policies", []),
        "global_instruction_context": dict(instruction_runtime_model.get("global_instruction_context") or {}),
    }


def _semantic_compile_context(
    *,
    app_id: str,
    deterministic_contract: dict[str, Any],
) -> dict[str, Any]:
    runtime_model = deterministic_contract.get("instruction_runtime_model", {}) if isinstance(
        deterministic_contract, dict
    ) else {}
    return {
        "app_id": app_id,
        "full_instruction_text": deterministic_contract.get("full_instruction_text", ""),
        "heading_tree": deterministic_contract.get("instruction_heading_tree", []),
        "structural_candidate_graph": deterministic_contract.get("structural_candidate_graph", {}),
        "instruction_service_blocks": deterministic_contract.get("instruction_service_blocks", []),
        "instruction_procedures": deterministic_contract.get("instruction_procedures", []),
        "procedure_steps": deterministic_contract.get("procedure_steps", []),
        "support_modules": deterministic_contract.get("support_modules_v2", []),
        "followup_modules": deterministic_contract.get("followup_modules", []),
        "global_policies": deterministic_contract.get("global_policies", []),
        "resource_reference_catalog": deterministic_contract.get("resource_reference_catalog", []),
        "global_instruction_context": runtime_model.get("global_instruction_context", {}),
    }


def _normalize_semantic_compile_result(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {
            "app_semantic_model": {},
            "errors": ["semantic compiler returned non-dict payload"],
            "raw_result": result,
            "empty_result": True,
        }
    model = result.get("app_semantic_model")
    if not isinstance(model, dict):
        return {
            "app_semantic_model": {},
            "errors": ["semantic compiler payload missing app_semantic_model object"],
            "raw_result": result,
            "empty_result": not bool(result),
        }
    return {
        "app_semantic_model": model,
        "errors": [],
        "raw_result": result,
        "empty_result": not bool(model),
    }


def _semantic_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _semantic_slug(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    chars: list[str] = []
    last_was_sep = False
    for ch in text:
        if ch.isalnum():
            chars.append(ch)
            last_was_sep = False
        elif not last_was_sep:
            chars.append("_")
            last_was_sep = True
    return "".join(chars).strip("_")


def _semantic_tokens(*values: Any) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        slug = _semantic_slug(value)
        if not slug:
            continue
        tokens.add(slug)
        tokens.update(part for part in slug.split("_") if part)
    return tokens


def _semantic_alias_tokens(*values: Any) -> set[str]:
    joined = " ".join(str(value or "").strip().lower() for value in values if str(value or "").strip())
    alias_labels: set[str] = set()
    if not joined:
        return alias_labels
    if "3x1" in joined or "3×1" in joined or "建議清單" in joined:
        alias_labels.update({"3x1", "suggestion", "advice", "checklist"})
    if "按步就班" in joined or "逐步" in joined:
        alias_labels.update({"step_by_step", "step", "guided"})
    if "深度解析" in joined or "深度分析" in joined:
        alias_labels.update({"deep_analysis", "analysis", "mentor"})
    if "歸納釋經" in joined or "查經" in joined:
        alias_labels.update({"inductive_bible_study", "bible_study", "scripture_study", "tutor"})
    if "多重需求分層" in joined or "分層回應" in joined:
        alias_labels.update({"multi_layer_orchestration", "multi_layer_response", "orchestration"})
    if "親子靈修" in joined or "家庭活動" in joined:
        alias_labels.update({"partner", "family_devotion"})
    return _semantic_tokens(*sorted(alias_labels))


def _semantic_family(*values: Any) -> str | None:
    joined = " ".join(str(value or "").strip().lower() for value in values if str(value or "").strip())
    if "multi_layer_orchestration" in joined or "multi_layer_response" in joined:
        return "orchestration"
    if "inductive_bible_study" in joined or "bible_study" in joined or "scripture_study" in joined:
        return "bible_study"
    if "deep_analysis" in joined:
        return "deep_analysis"
    if "step_by_step" in joined or "step_by_step_method" in joined:
        return "step_by_step"
    if (
        "quick_suggestion_3x1" in joined
        or "3x1" in joined
        or "advice_checklist" in joined
        or "3x1_suggestion_list" in joined
    ):
        return "quick_suggestion_3x1"
    if "family_devotion" in joined:
        return "family_devotion"
    raw_tokens = _semantic_tokens(*values)
    if {"multi_layer_orchestration", "multi_layer_response", "orchestration"} & raw_tokens:
        return "orchestration"
    if {"inductive_bible_study", "bible_study", "scripture_study"} & raw_tokens:
        return "bible_study"
    if {"deep_analysis"} & raw_tokens:
        return "deep_analysis"
    if {"step_by_step", "method"} <= raw_tokens or {"step_by_step"} & raw_tokens:
        return "step_by_step"
    if {"3x1", "suggestion", "advice", "checklist", "quick_suggestion_3x1"} & raw_tokens:
        return "quick_suggestion_3x1"
    if {"family_devotion"} & raw_tokens:
        return "family_devotion"
    alias_tokens = _semantic_alias_tokens(*values)
    if {"multi_layer_orchestration", "multi_layer_response", "orchestration"} & alias_tokens:
        return "orchestration"
    if {"inductive_bible_study", "bible_study", "scripture_study", "tutor"} & alias_tokens:
        return "bible_study"
    if {"deep_analysis", "mentor"} & alias_tokens:
        return "deep_analysis"
    if {"step_by_step", "guided"} & alias_tokens:
        return "step_by_step"
    if {"3x1", "suggestion", "advice", "checklist"} & alias_tokens:
        return "quick_suggestion_3x1"
    if {"partner", "family_devotion"} & alias_tokens:
        return "family_devotion"
    return None


def _semantic_declared_structure_type(*values: Any) -> str | None:
    joined = " ".join(str(value or "").strip() for value in values if str(value or "").strip())
    if not joined:
        return None
    lowered = joined.lower()
    has_module = "模組" in joined or "module" in lowered
    has_workflow = "流程" in joined or "workflow" in lowered
    if has_module and not has_workflow:
        return "module"
    if has_workflow and not has_module:
        return "workflow"
    return None


def _normalized_workflow_block_id(workflow_id: str) -> str:
    value = str(workflow_id or "").strip()
    if not value:
        return value
    if value.startswith("wf:"):
        return f"workflow:{value.split(':', 1)[1]}"
    if value.startswith("wf_"):
        return f"workflow:{value[3:]}"
    if value.startswith("workflow_"):
        return f"workflow:{value[9:]}"
    return value


def _normalized_module_block_id(module_id: str) -> str:
    value = str(module_id or "").strip()
    if not value:
        return value
    if value.startswith("module_"):
        return f"module:{value[7:]}"
    return value


def _canonical_support_module_block_id(module_id: str, *, block_type: str = "support_module") -> str:
    value = str(module_id or "").strip()
    if not value:
        return value
    normalized_value = _normalized_module_block_id(value)
    if block_type == "followup_module":
        if normalized_value.startswith("followup_module:"):
            return normalized_value
        if normalized_value.startswith("support_module:"):
            return f"followup_module:{normalized_value.split(':', 1)[1]}"
        if normalized_value.startswith("module:"):
            return f"followup_module:{normalized_value.split(':', 1)[1]}"
        return f"followup_module:{normalized_value}"
    if normalized_value.startswith("support_module:"):
        return normalized_value
    if normalized_value.startswith("module:"):
        return f"support_module:{normalized_value.split(':', 1)[1]}"
    return f"support_module:{normalized_value}"


def _canonical_procedure_id_for_workflow_id(workflow_id: str) -> str:
    value = str(workflow_id or "").strip()
    return f"procedure:{_semantic_slug(value) or value}" if value else ""


def _canonical_procedure_id_for_block_id(block_id: str) -> str:
    value = str(block_id or "").strip()
    return f"procedure:{_semantic_slug(value) or value}" if value else ""


def _route_priority_value(value: Any, fallback: int) -> int:
    try:
        priority = int(value)
    except (TypeError, ValueError):
        priority = fallback
    return priority if priority > 0 else fallback


def _canonical_route_target_name(
    candidate: dict[str, Any],
    *,
    target_family: str | None,
    role_id: str = "",
) -> str:
    raw_source_values = candidate.get("source_values")
    if isinstance(raw_source_values, list):
        source_values = [str(value or "").strip() for value in raw_source_values if str(value or "").strip()]
    else:
        source_values = [
            str(candidate.get("title") or "").strip(),
            str(candidate.get("body_text") or "").strip(),
            str(candidate.get("candidate_id") or "").strip(),
            *[str(item or "").strip() for item in candidate.get("resource_files", []) or [] if str(item or "").strip()],
        ]
    source_text = " ".join(value for value in source_values if value).lower()
    candidate_family = str(candidate.get("family") or "").strip() or None
    family = candidate_family or target_family or _semantic_family(*source_values, role_id)

    if family == "deep_analysis" and "深度解析" in source_text:
        return "深度解析法"
    if family == "step_by_step" and ("按步就班" in source_text or "逐步" in source_text):
        return "按步就班法"
    if family == "quick_suggestion_3x1" and ("3x1" in source_text or "建議清單" in source_text):
        return "3x1建議清單法"
    if family == "bible_study" and ("歸納釋經" in source_text or "查經" in source_text):
        return "歸納釋經法"
    if family == "orchestration" and ("多重需求分層" in source_text or "分層回應" in source_text):
        return "多重需求分層規則"
    declared_target_type = str(candidate.get("declared_target_type") or "").strip()
    candidate_title = str(candidate.get("title") or "").strip()
    if (
        family == "family_devotion"
        and ("親子靈修" in source_text or "家庭活動" in source_text)
        and (declared_target_type == "workflow" or "流程" in candidate_title or "workflow" in candidate_title.lower())
    ):
        return "親子靈修"

    title = str(candidate.get("title") or "").strip()
    if title:
        title = re.sub(r"[（(].*?[)）]", "", title).strip()
        if title:
            if re.search(r"[^\x00-\x7F]", title):
                compact_title = re.sub(r"\s+", "", title)
            else:
                compact_title = _semantic_slug(title)
            if compact_title:
                return compact_title

    candidate_id = str(candidate.get("candidate_id") or "").strip()
    if candidate_id:
        compact_id = re.sub(r"\s+", "", candidate_id.split(":")[-1])
        if compact_id:
            return compact_id
    return ""


def _canonical_route_workflow_block_id(
    candidate: dict[str, Any],
    *,
    target_family: str | None,
    role_id: str = "",
) -> str:
    canonical_name = _canonical_route_target_name(candidate, target_family=target_family, role_id=role_id)
    return f"workflow:{canonical_name}" if canonical_name else ""


def _canonical_route_module_block_id(
    candidate: dict[str, Any],
    *,
    target_family: str | None,
    role_id: str = "",
) -> str:
    canonical_name = _canonical_route_target_name(candidate, target_family=target_family, role_id=role_id)
    return f"module:{canonical_name}" if canonical_name else ""


def _candidate_block_type(candidate: dict[str, Any]) -> str:
    return str(candidate.get("service_block_type") or candidate.get("candidate_kind") or "").strip()


def _candidate_is_module_like(candidate: dict[str, Any] | None) -> bool:
    if not isinstance(candidate, dict):
        return False
    return str(candidate.get("declared_target_type") or "").strip() == "module"


def _candidate_is_route_target_eligible(candidate: dict[str, Any] | None, desired_target_type: str = "") -> bool:
    if not isinstance(candidate, dict):
        return False
    if not bool(candidate.get("route_target_eligible")):
        return False
    declared_target_type = str(candidate.get("declared_target_type") or "").strip()
    if not desired_target_type:
        return True
    if desired_target_type == "workflow":
        return declared_target_type == "workflow"
    if desired_target_type == "module":
        return declared_target_type == "module"
    return True


def _synthetic_route_candidate(
    candidate_id: str,
    title: str = "",
    body_text: str = "",
    *,
    resource_files: list[str] | None = None,
    declared_target_type: str = "",
) -> dict[str, Any]:
    normalized_resource_files = [str(item or "").strip() for item in resource_files or [] if str(item or "").strip()]
    normalized_title = str(title or "").strip()
    normalized_body_text = str(body_text or "").strip()
    normalized_candidate_id = str(candidate_id or "").strip()
    source_values = [
        normalized_title,
        normalized_body_text,
        normalized_candidate_id,
        *normalized_resource_files,
    ]
    return {
        "candidate_id": normalized_candidate_id,
        "title": normalized_title,
        "body_text": normalized_body_text,
        "resource_files": normalized_resource_files,
        "declared_target_type": str(declared_target_type or "").strip(),
        "source_values": source_values,
    }


def _title_matches_target_family(title: str, target_family: str | None) -> bool:
    normalized_title = str(title or "").strip()
    if not normalized_title:
        return False
    if not target_family:
        return True
    title_family = _semantic_family(normalized_title)
    if title_family == target_family:
        return True
    title_tokens = _semantic_tokens(normalized_title) | _semantic_alias_tokens(normalized_title)
    family_tokens = _semantic_tokens(target_family) | _semantic_alias_tokens(target_family)
    return bool(title_tokens & family_tokens)


def _executable_title_quality(title: str, target_family: str | None, interaction_logic_titles: set[str]) -> tuple[int, int, int]:
    normalized_title = str(title or "").strip()
    return (
        1 if normalized_title else 0,
        1 if normalized_title and normalized_title not in interaction_logic_titles else 0,
        1 if _title_matches_target_family(normalized_title, target_family) else 0,
    )


def _should_preserve_step_specific_title(step_title: str, block_title: str) -> bool:
    normalized_step_title = str(step_title or "").strip()
    normalized_block_title = str(block_title or "").strip()
    if not normalized_step_title or normalized_step_title == normalized_block_title:
        return False
    lowered_step_title = normalized_step_title.lower()
    if lowered_step_title.startswith("step "):
        return False
    if any(token in normalized_step_title for token in ("模組", "流程")):
        return False
    if any(token in lowered_step_title for token in ("module", "workflow")):
        return False
    return True


def _preferred_executable_title(
    candidate: dict[str, Any],
    *,
    target_family: str | None,
    current_title: str,
    interaction_logic_titles: set[str],
) -> str:
    normalized_current_title = str(current_title or "").strip()
    if normalized_current_title and normalized_current_title not in interaction_logic_titles and _title_matches_target_family(
        normalized_current_title,
        target_family,
    ):
        return normalized_current_title
    canonical_name = _canonical_route_target_name(candidate, target_family=target_family)
    if canonical_name:
        return canonical_name
    candidate_title = str(candidate.get("title") or "").strip()
    if candidate_title and candidate_title not in interaction_logic_titles:
        return candidate_title
    return normalized_current_title or candidate_title


def _ground_semantic_model_from_deterministic_contract(
    semantic_model: dict[str, Any],
    deterministic_contract: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(semantic_model, dict):
        return {}

    normalized = dict(semantic_model)
    if not isinstance(normalized.get("service_blocks"), list):
        normalized["service_blocks"] = []
    if not isinstance(normalized.get("procedures"), list):
        normalized["procedures"] = []
    if not isinstance(normalized.get("procedure_steps"), list):
        normalized["procedure_steps"] = []
    if not isinstance(normalized.get("role_profiles"), list):
        normalized["role_profiles"] = []
    if not isinstance(normalized.get("routing_rules"), list):
        normalized["routing_rules"] = []
    if not isinstance(normalized.get("interaction_logic_blocks"), list):
        normalized["interaction_logic_blocks"] = []
    if not isinstance(normalized.get("clarification_gate_rules"), list):
        normalized["clarification_gate_rules"] = []

    service_blocks = list(normalized.get("service_blocks") or [])
    procedures = list(normalized.get("procedures") or [])
    procedure_steps = list(normalized.get("procedure_steps") or [])
    role_profiles = list(normalized.get("role_profiles") or [])
    routing_rules = list(normalized.get("routing_rules") or [])
    interaction_logic_blocks = list(normalized.get("interaction_logic_blocks") or [])
    clarification_gate_rules = list(normalized.get("clarification_gate_rules") or [])
    module_orchestration = (
        dict(normalized.get("module_orchestration") or {})
        if isinstance(normalized.get("module_orchestration"), dict)
        else None
    )
    primary_service_mode = str(normalized.get("primary_service_mode") or "").strip()

    existing_block_ids = {
        str(item.get("block_id") or "").strip()
        for item in service_blocks
        if isinstance(item, dict) and str(item.get("block_id") or "").strip()
    }
    existing_role_ids = {
        str(item.get("role_id") or "").strip()
        for item in role_profiles
        if isinstance(item, dict) and str(item.get("role_id") or "").strip()
    }
    existing_procedure_ids = {
        str(item.get("procedure_id") or "").strip()
        for item in procedures
        if isinstance(item, dict) and str(item.get("procedure_id") or "").strip()
    }
    existing_step_ids = {
        str(item.get("step_id") or "").strip()
        for item in procedure_steps
        if isinstance(item, dict) and str(item.get("step_id") or "").strip()
    }

    def _interaction_logic_block_has_rich_contract(block: dict[str, Any]) -> bool:
        if not isinstance(block, dict):
            return False
        for key in (
            "mode_behaviors",
            "layers",
            "layer_rules",
            "response_strategies",
            "rules",
            "entry_response_contract",
            "orchestration_mode",
            "subordinate_modules",
        ):
            value = block.get(key)
            if isinstance(value, list) and value:
                return True
            if isinstance(value, dict) and value:
                return True
            if isinstance(value, str) and value.strip():
                return True
        return False

    def _should_reclassify_intent_routed_to_interaction_logic() -> bool:
        if primary_service_mode != "intent_routed_multi_workflow":
            return False
        if str(normalized.get("default_workflow_id") or "").strip():
            return False
        if not interaction_logic_blocks:
            return False
        has_logic_target_rule = any(
            isinstance(rule, dict) and str(rule.get("target_interaction_logic_id") or rule.get("target") or "").strip()
            for rule in routing_rules
        )
        if not has_logic_target_rule:
            return False
        rich_logic_blocks = [
            block for block in interaction_logic_blocks
            if isinstance(block, dict) and _interaction_logic_block_has_rich_contract(block)
        ]
        return bool(rich_logic_blocks)

    def _infer_missing_primary_service_mode() -> str:
        if primary_service_mode:
            return primary_service_mode
        if str(normalized.get("default_workflow_id") or "").strip():
            return "single_default_workflow"
        if any(
            isinstance(block, dict)
            and str(block.get("block_type") or "").strip() == "primary_workflow"
            and bool(block.get("is_default"))
            for block in service_blocks
        ):
            return "single_default_workflow"
        rich_logic_blocks = [
            block for block in interaction_logic_blocks
            if isinstance(block, dict) and _interaction_logic_block_has_rich_contract(block)
        ]
        has_nested_logic_routes = any(
            isinstance(block, dict) and isinstance(block.get("routing_rules"), list) and block.get("routing_rules")
            for block in interaction_logic_blocks
        )
        if interaction_logic_blocks and (rich_logic_blocks or has_nested_logic_routes):
            return "intent_routed_interaction_logic"
        has_primary_workflow_blocks = any(
            isinstance(block, dict) and str(block.get("block_type") or "").strip() == "primary_workflow"
            for block in service_blocks
        )
        if routing_rules and has_primary_workflow_blocks:
            return "intent_routed_multi_workflow"
        return ""

    inferred_primary_service_mode = _infer_missing_primary_service_mode()
    if inferred_primary_service_mode and not primary_service_mode:
        primary_service_mode = inferred_primary_service_mode
        normalized["primary_service_mode"] = primary_service_mode

    if _should_reclassify_intent_routed_to_interaction_logic():
        primary_service_mode = "intent_routed_interaction_logic"
        normalized["primary_service_mode"] = primary_service_mode

    executable_block_types = {"primary_workflow", "support_module", "followup_module"}
    should_seed_deterministic_executables = (
        primary_service_mode == "intent_routed_interaction_logic"
        and bool(interaction_logic_blocks)
        and (
            not service_blocks
            or not procedures
            or not procedure_steps
        )
    )
    deterministic_service_blocks = [
        dict(item)
        for item in deterministic_contract.get("instruction_service_blocks", []) or []
        if isinstance(item, dict) and str(item.get("block_type") or "").strip() in executable_block_types
    ]
    deterministic_block_ids = {
        str(item.get("block_id") or "").strip()
        for item in deterministic_service_blocks
        if str(item.get("block_id") or "").strip()
    }
    deterministic_procedures = [
        dict(item)
        for item in deterministic_contract.get("instruction_procedures", []) or []
        if isinstance(item, dict) and str(item.get("service_block_id") or "").strip() in deterministic_block_ids
    ]
    deterministic_procedure_ids = {
        str(item.get("procedure_id") or "").strip()
        for item in deterministic_procedures
        if str(item.get("procedure_id") or "").strip()
    }
    deterministic_steps_by_procedure_id: dict[str, list[dict[str, Any]]] = {}
    for step in deterministic_contract.get("procedure_steps", []) or []:
        if not isinstance(step, dict):
            continue
        procedure_id = str(step.get("procedure_id") or "").strip()
        if not procedure_id:
            continue
        deterministic_steps_by_procedure_id.setdefault(procedure_id, []).append(dict(step))

    deterministic_module_specs: list[dict[str, Any]] = []
    deterministic_module_specs_by_block_id: dict[str, dict[str, Any]] = {}
    deterministic_module_alias_map: dict[str, str] = {}
    for block in deterministic_service_blocks:
        block_id = str(block.get("block_id") or "").strip()
        block_type = str(block.get("block_type") or "").strip()
        if block_type not in {"support_module", "followup_module"} or not block_id:
            continue
        procedure = next(
            (
                dict(item)
                for item in deterministic_procedures
                if str(item.get("service_block_id") or "").strip() == block_id
            ),
            None,
        )
        procedure_id = str((procedure or {}).get("procedure_id") or "").strip()
        steps = list(deterministic_steps_by_procedure_id.get(procedure_id, []))
        step_titles = [
            str(item.get("title") or "").strip()
            for item in steps
            if isinstance(item, dict) and str(item.get("title") or "").strip()
        ]
        deterministic_module_specs.append(
            {
                "block": dict(block),
                "procedure": procedure,
                "steps": steps,
                "step_titles": step_titles,
            }
        )
        deterministic_module_specs_by_block_id[block_id] = deterministic_module_specs[-1]
        normalized_title = re.sub(r"[（(].*?[）)]", "", str(block.get("title") or "").strip()).strip()
        for alias in {
            block_id,
            _normalized_module_block_id(block_id),
            str(block.get("title") or "").strip(),
            normalized_title,
            f"module:{normalized_title}" if normalized_title else "",
            f"support_module:{normalized_title}" if normalized_title else "",
        }:
            cleaned_alias = str(alias or "").strip()
            if cleaned_alias:
                deterministic_module_alias_map.setdefault(cleaned_alias, block_id)
    if should_seed_deterministic_executables:
        for block in deterministic_service_blocks:
            block_id = str(block.get("block_id") or "").strip()
            if not block_id or block_id in existing_block_ids:
                continue
            service_blocks.append(block)
            existing_block_ids.add(block_id)

        for procedure in deterministic_procedures:
            procedure_id = str(procedure.get("procedure_id") or "").strip()
            if not procedure_id or procedure_id in existing_procedure_ids:
                continue
            procedures.append(procedure)
            existing_procedure_ids.add(procedure_id)

        for step in deterministic_contract.get("procedure_steps", []) or []:
            if not isinstance(step, dict):
                continue
            if str(step.get("procedure_id") or "").strip() not in deterministic_procedure_ids:
                continue
            step_id = str(step.get("step_id") or "").strip()
            if not step_id or step_id in existing_step_ids:
                continue
            procedure_steps.append(dict(step))
            existing_step_ids.add(step_id)

    deterministic_candidates: list[dict[str, Any]] = []
    for workflow in deterministic_contract.get("instruction_workflows", []) or []:
        if not isinstance(workflow, dict):
            continue
        title = str(workflow.get("title") or workflow.get("workflow_name") or workflow.get("id") or "").strip()
        workflow_id = str(workflow.get("id") or workflow.get("workflow_name") or title).strip()
        step_titles = [
            str(step.get("title") or "").strip()
            for step in workflow.get("steps", []) or []
            if isinstance(step, dict) and str(step.get("title") or "").strip()
        ]
        deterministic_candidates.append(
            {
                "candidate_id": workflow_id,
                "title": title,
                "body_text": str(workflow.get("body_text") or "").strip(),
                "resource_files": [],
                "source_values": [title, str(workflow.get("body_text") or "").strip(), workflow_id],
                "candidate_kind": "workflow",
                "service_block_type": "primary_workflow",
                "declared_target_type": "workflow",
                "family": _semantic_family(workflow_id, title, workflow.get("body_text")),
                "alias_tokens": _semantic_alias_tokens(workflow_id, title, workflow.get("body_text")),
                "tokens": _semantic_tokens(workflow_id, title, workflow.get("body_text"))
                | _semantic_alias_tokens(workflow_id, title, workflow.get("body_text")),
                "route_target_eligible": (_semantic_family(workflow_id, title, workflow.get("body_text")) not in {None, "orchestration"}),
            }
        )
        for step in workflow.get("steps", []) or []:
            if not isinstance(step, dict):
                continue
            step_title = str(step.get("title") or "").strip()
            declared_step_type = _semantic_declared_structure_type(step_title)
            if declared_step_type not in {"workflow", "module"}:
                continue
            step_body_text = str(step.get("body_text") or "").strip()
            step_resource_files = [
                str(item or "").strip()
                for item in (
                    step.get("bundled_resource_refs", [])
                    or step.get("resource_refs", [])
                    or []
                )
                if str(item or "").strip()
            ]
            step_id = str(step.get("step_id") or "").strip() or step_title
            deterministic_candidates.append(
                {
                    "candidate_id": f"{workflow_id}::{step_id}",
                    "title": step_title,
                    "body_text": step_body_text,
                    "resource_files": step_resource_files,
                    "source_values": [step_title, step_body_text, step_id, title, workflow_id, *step_resource_files],
                    "candidate_kind": "workflow" if declared_step_type == "workflow" else "module",
                    "service_block_type": "primary_workflow" if declared_step_type == "workflow" else "support_module",
                    "declared_target_type": declared_step_type,
                    "family": _semantic_family(step_title, step_body_text, step_id, *step_resource_files),
                    "alias_tokens": _semantic_alias_tokens(step_title, step_body_text, step_id, *step_resource_files),
                    "tokens": _semantic_tokens(step_title, step_body_text, step_id, *step_resource_files)
                    | _semantic_alias_tokens(step_title, step_body_text, step_id, *step_resource_files),
                    "route_target_eligible": True,
                }
            )
    for module in deterministic_contract.get("instruction_modules", []) or []:
        if not isinstance(module, dict):
            continue
        title = str(module.get("title") or "").strip()
        resource_files = [
            str(item or "").strip()
            for item in module.get("resource_files", []) or []
            if str(item or "").strip()
        ]
        module_id = str(module.get("id") or "").strip()
        keywords = [
            str(item or "").strip()
            for item in module.get("keywords", []) or []
            if str(item or "").strip()
        ]
        deterministic_candidates.append(
            {
                "candidate_id": module_id,
                "title": title,
                "body_text": "",
                "resource_files": resource_files,
                "source_values": [title, module_id, *keywords, *resource_files],
                "candidate_kind": "module",
                "service_block_type": "support_module",
                "declared_target_type": _semantic_declared_structure_type(title),
                "family": _semantic_family(module_id, title, *keywords, *resource_files),
                "alias_tokens": _semantic_alias_tokens(module_id, title, *keywords, *resource_files),
                "tokens": _semantic_tokens(module_id, title, *keywords, *resource_files)
                | _semantic_alias_tokens(module_id, title, *keywords, *resource_files),
                "route_target_eligible": True,
            }
        )
    for block in deterministic_contract.get("instruction_service_blocks", []) or []:
        if not isinstance(block, dict):
            continue
        title = str(block.get("title") or "").strip()
        resource_files = [
            str(item or "").strip()
            for item in block.get("resource_refs", []) or []
            if str(item or "").strip()
        ]
        block_id = str(block.get("block_id") or "").strip()
        deterministic_candidates.append(
            {
                "candidate_id": block_id,
                "title": title,
                "body_text": str(block.get("body_text") or "").strip(),
                "resource_files": resource_files,
                "source_values": [title, str(block.get("body_text") or "").strip(), block_id, *resource_files],
                "candidate_kind": (
                    "module"
                    if str(block.get("block_type") or "").strip() in {"support_module", "followup_module"}
                    else ("workflow" if "workflow" in str(block.get("block_type") or "").lower() else "service_block")
                ),
                "service_block_type": str(block.get("block_type") or "").strip(),
                "declared_target_type": (
                    "module"
                    if str(block.get("block_type") or "").strip() in {"support_module", "followup_module"}
                    else ("workflow" if "workflow" in str(block.get("block_type") or "").lower() else _semantic_declared_structure_type(title))
                ),
                "family": _semantic_family(block_id, title, block.get("body_text"), *resource_files),
                "alias_tokens": _semantic_alias_tokens(block_id, title, block.get("body_text"), *resource_files),
                "tokens": _semantic_tokens(block_id, title, block.get("body_text"), *resource_files)
                | _semantic_alias_tokens(block_id, title, block.get("body_text"), *resource_files),
                "route_target_eligible": str(block.get("block_type") or "").strip() in {"support_module", "followup_module", "primary_workflow"},
            }
        )
    for procedure in deterministic_contract.get("instruction_procedures", []) or []:
        if not isinstance(procedure, dict):
            continue
        title = str(procedure.get("title") or "").strip()
        procedure_id = str(procedure.get("procedure_id") or "").strip()
        service_block_id = str(procedure.get("service_block_id") or "").strip()
        deterministic_candidates.append(
            {
                "candidate_id": procedure_id or service_block_id,
                "title": title,
                "body_text": "",
                "resource_files": [],
                "source_values": [title, procedure_id, service_block_id],
                "candidate_kind": "procedure",
                "family": _semantic_family(procedure_id, service_block_id, title),
                "alias_tokens": _semantic_alias_tokens(procedure_id, service_block_id, title),
                "tokens": _semantic_tokens(procedure_id, service_block_id, title)
                | _semantic_alias_tokens(procedure_id, service_block_id, title),
            }
        )
    for step in deterministic_contract.get("procedure_steps", []) or []:
        if not isinstance(step, dict):
            continue
        title = str(step.get("title") or "").strip()
        resource_files = [
            str(item or "").strip()
            for item in (
                step.get("bundled_resource_refs", [])
                or step.get("resource_refs", [])
                or []
            )
            if str(item or "").strip()
        ]
        step_id = str(step.get("step_id") or "").strip()
        body_text = str(step.get("body_text") or "").strip()
        deterministic_candidates.append(
            {
                "candidate_id": step_id,
                "title": title,
                "body_text": body_text,
                "resource_files": resource_files,
                "source_values": [title, body_text, step_id, *resource_files],
                "candidate_kind": "step",
                "family": _semantic_family(step_id, title, body_text, *resource_files),
                "alias_tokens": _semantic_alias_tokens(step_id, title, body_text, *resource_files),
                "tokens": _semantic_tokens(step_id, title, body_text, *resource_files)
                | _semantic_alias_tokens(step_id, title, body_text, *resource_files),
            }
        )

    orchestration_aliases = _semantic_tokens("multi_layer_orchestration", "multi_layer_response", "orchestration")
    bible_study_aliases = _semantic_tokens("inductive_bible_study", "bible_study", "scripture_study", "tutor")

    def _target_family(target_id: str, role_id: str = "") -> str | None:
        family = _semantic_family(target_id)
        role_text = role_id.strip().lower()
        if "partner" in role_text and family in {None, "step_by_step"}:
            return "family_devotion"
        if family:
            return family
        if "mentor" in role_text:
            return "deep_analysis"
        if "coach" in role_text:
            return "step_by_step"
        if "consultant" in role_text:
            return "quick_suggestion_3x1"
        if "tutor" in role_text:
            return "bible_study"
        return None

    def _candidate_type_rank(target_family: str | None, target_alias_tokens: set[str], candidate: dict[str, Any]) -> int:
        kind = str(candidate.get("candidate_kind") or "").strip()
        if target_family == "orchestration" or target_alias_tokens & orchestration_aliases:
            if kind == "workflow":
                return 6
            if kind == "service_block":
                return 4
            if kind == "module":
                return 2
            return 1
        if target_family == "bible_study" or target_alias_tokens & bible_study_aliases:
            if kind == "workflow":
                return 6
            if kind == "service_block":
                return 5
            if kind == "module":
                return 3
            return 1
        if kind == "module":
            return 6
        if kind == "workflow":
            return 5
        if kind == "service_block":
            return 4
        if kind == "procedure":
            return 2
        if kind == "step":
            return 1
        return 0

    def _family_is_compatible(target_family: str | None, candidate_family: str | None) -> bool:
        if target_family is None:
            return True
        if candidate_family is None:
            return False
        if target_family in {"family_devotion", "step_by_step"} and candidate_family in {"family_devotion", "step_by_step"}:
            return True
        return target_family == candidate_family

    def _match_candidate(
        target_id: str,
        role_id: str = "",
        used_candidate_ids: set[str] | None = None,
    ) -> dict[str, Any] | None:
        target_tokens = _semantic_tokens(target_id)
        target_alias_tokens = _semantic_alias_tokens(target_id)
        target_family = _target_family(target_id, role_id)
        if role_id:
            target_alias_tokens |= _semantic_alias_tokens(role_id)
        if target_family:
            target_alias_tokens |= _semantic_tokens(target_family) | _semantic_alias_tokens(target_family)
        if not target_tokens and not target_alias_tokens:
            return None
        ranked_matches: list[tuple[tuple[int, int, int, int, int], dict[str, Any]]] = []
        for candidate in deterministic_candidates:
            candidate_id = str(candidate.get("candidate_id") or "").strip()
            candidate_family = str(candidate.get("family") or "").strip() or None
            reusable_family_pair = target_family in {"family_devotion", "step_by_step"} and candidate_family in {
                "family_devotion",
                "step_by_step",
            }
            if used_candidate_ids and candidate_id in used_candidate_ids and target_family not in {"bible_study", "orchestration"} and not reusable_family_pair:
                continue
            if not _family_is_compatible(target_family, candidate_family):
                continue
            candidate_tokens = set(candidate.get("tokens") or set())
            candidate_alias_tokens = set(candidate.get("alias_tokens") or set())
            overlap = target_tokens & candidate_tokens
            alias_overlap = target_alias_tokens & candidate_alias_tokens
            if not overlap and not alias_overlap:
                continue
            type_rank = _candidate_type_rank(target_family, target_alias_tokens, candidate)
            alias_score = len(alias_overlap)
            score = len(overlap)
            richness = len(candidate.get("resource_files") or [])
            has_alias_match = 1 if alias_overlap else 0
            ranked_matches.append(((has_alias_match, type_rank, alias_score, score, richness), candidate))
        if not ranked_matches:
            return None
        ranked_matches.sort(key=lambda item: item[0], reverse=True)
        best_rank = ranked_matches[0][0]
        best_candidates = [candidate for rank, candidate in ranked_matches if rank == best_rank]
        if len(best_candidates) != 1:
            return None
        return best_candidates[0]

    def _match_candidate_for_values(
        values: list[str],
        role_id: str = "",
        used_candidate_ids: set[str] | None = None,
    ) -> tuple[dict[str, Any] | None, str | None]:
        text_values = [str(value or "").strip() for value in values if str(value or "").strip()]
        if not text_values:
            return None, None
        target_tokens = _semantic_tokens(*text_values)
        target_alias_tokens = _semantic_alias_tokens(*text_values)
        target_family = _semantic_family(*text_values, role_id) or _target_family(text_values[0], role_id)
        if role_id:
            target_alias_tokens |= _semantic_alias_tokens(role_id)
        if target_family:
            target_alias_tokens |= _semantic_tokens(target_family) | _semantic_alias_tokens(target_family)
        if not target_tokens and not target_alias_tokens:
            return None, target_family
        ranked_matches: list[tuple[tuple[int, int, int, int, int], dict[str, Any]]] = []
        for candidate in deterministic_candidates:
            candidate_id = str(candidate.get("candidate_id") or "").strip()
            candidate_family = str(candidate.get("family") or "").strip() or None
            reusable_family_pair = target_family in {"family_devotion", "step_by_step"} and candidate_family in {
                "family_devotion",
                "step_by_step",
            }
            if used_candidate_ids and candidate_id in used_candidate_ids and target_family not in {"bible_study", "orchestration"} and not reusable_family_pair:
                continue
            if not _family_is_compatible(target_family, candidate_family):
                continue
            candidate_tokens = set(candidate.get("tokens") or set())
            candidate_alias_tokens = set(candidate.get("alias_tokens") or set())
            overlap = target_tokens & candidate_tokens
            alias_overlap = target_alias_tokens & candidate_alias_tokens
            if not overlap and not alias_overlap:
                continue
            type_rank = _candidate_type_rank(target_family, target_alias_tokens, candidate)
            alias_score = len(alias_overlap)
            score = len(overlap)
            richness = len(candidate.get("resource_files") or [])
            has_alias_match = 1 if alias_overlap else 0
            ranked_matches.append(((has_alias_match, type_rank, alias_score, score, richness), candidate))
        if not ranked_matches:
            return None, target_family
        ranked_matches.sort(key=lambda item: item[0], reverse=True)
        best_rank = ranked_matches[0][0]
        best_candidates = [candidate for rank, candidate in ranked_matches if rank == best_rank]
        if len(best_candidates) != 1:
            return None, target_family
        return best_candidates[0], target_family

    existing_logic_titles = {
        str(item.get("title") or "").strip()
        for item in interaction_logic_blocks
        if isinstance(item, dict) and str(item.get("title") or "").strip()
    }

    def _resolve_explicit_route_target_candidate(
        target_family: str | None,
        desired_target_type: str,
    ) -> dict[str, Any] | None:
        if not target_family:
            return None
        ranked_matches: list[tuple[tuple[int, int, int, int], dict[str, Any]]] = []
        for candidate in deterministic_candidates:
            if not _candidate_is_route_target_eligible(candidate, desired_target_type):
                continue
            candidate_family = str(candidate.get("family") or "").strip() or None
            exact_family = 1 if candidate_family == target_family else 0
            compatible_family = 1 if _family_is_compatible(target_family, candidate_family) else 0
            if not exact_family and not compatible_family:
                continue
            candidate_title = str(candidate.get("title") or "").strip()
            quality = _executable_title_quality(candidate_title, candidate_family or target_family, existing_logic_titles)
            has_existing_block = 1 if _existing_executable_block_id_for_candidate(candidate) else 0
            ranked_matches.append(((exact_family, compatible_family, has_existing_block, quality[-1]), candidate))
        if not ranked_matches:
            return None
        ranked_matches.sort(key=lambda item: item[0], reverse=True)
        best_rank = ranked_matches[0][0]
        best_candidates = [candidate for rank, candidate in ranked_matches if rank == best_rank]
        if len(best_candidates) != 1:
            return None
        return best_candidates[0]

    def _existing_module_block_id_for_candidate(candidate: dict[str, Any] | None) -> str:
        if not isinstance(candidate, dict):
            return ""
        candidate_title = str(candidate.get("title") or "").strip()
        candidate_body = str(candidate.get("body_text") or "").strip()
        for block in service_blocks:
            if not isinstance(block, dict):
                continue
            block_type = str(block.get("block_type") or "").strip()
            block_id = str(block.get("block_id") or "").strip()
            block_title = str(block.get("title") or "").strip()
            block_body = str(block.get("body_text") or "").strip()
            if block_type not in {"support_module", "followup_module"}:
                continue
            if candidate_title and block_title and candidate_title == block_title:
                return _canonical_support_module_block_id(block_id, block_type=block_type)
            if candidate_title and block_title and candidate_title in block_title:
                return _canonical_support_module_block_id(block_id, block_type=block_type)
            if candidate_body and block_body and candidate_body == block_body:
                return _canonical_support_module_block_id(block_id, block_type=block_type)
        deterministic_block_id = _deterministic_module_block_id_for_values(
            [
                str(candidate.get("candidate_id") or "").strip(),
                candidate_title,
                candidate_body,
                *[str(item or "").strip() for item in candidate.get("resource_files", []) or [] if str(item or "").strip()],
            ]
        )
        if deterministic_block_id:
            return deterministic_block_id
        return ""

    def _existing_executable_block_id_for_candidate(candidate: dict[str, Any] | None) -> str:
        if not isinstance(candidate, dict):
            return ""
        if _candidate_is_module_like(candidate):
            return _existing_module_block_id_for_candidate(candidate)
        return ""

    def _resolved_executable_block_id_for_candidate(
        candidate: dict[str, Any] | None,
        *,
        target_family: str | None,
        role_id: str = "",
    ) -> str:
        if not isinstance(candidate, dict):
            return ""
        existing_block_id = _existing_executable_block_id_for_candidate(candidate)
        if existing_block_id:
            return existing_block_id
        if _candidate_is_module_like(candidate):
            return _canonical_route_module_block_id(candidate, target_family=target_family, role_id=role_id)
        return _canonical_route_workflow_block_id(candidate, target_family=target_family, role_id=role_id)

    def _module_title_match_score(values: list[str], block_title: str, block_body: str = "") -> int:
        text_values = [str(value or "").strip() for value in values if str(value or "").strip()]
        if not text_values:
            return 0
        normalized_block_title = re.sub(r"[ï¼ˆ(].*?[)ï¼‰]", "", str(block_title or "").strip()).strip()
        block_tokens = _semantic_tokens(normalized_block_title, block_title, block_body)
        block_alias_tokens = _semantic_alias_tokens(normalized_block_title, block_title, block_body)
        target_tokens = _semantic_tokens(*text_values)
        target_alias_tokens = _semantic_alias_tokens(*text_values)
        if not target_tokens and not target_alias_tokens:
            return 0
        score = 0
        if normalized_block_title:
            for value in text_values:
                compact_value = re.sub(r"^module:", "", str(value or "").strip())
                if compact_value and compact_value == normalized_block_title:
                    score += 12
                elif compact_value and compact_value in normalized_block_title:
                    score += 8
        score += len(target_tokens & block_tokens) * 3
        score += len(target_alias_tokens & block_alias_tokens) * 4
        return score

    def _existing_module_block_id_for_values(values: list[str]) -> str:
        ranked_matches: list[tuple[int, str]] = []
        for block in service_blocks:
            if not isinstance(block, dict):
                continue
            block_type = str(block.get("block_type") or "").strip()
            block_id = str(block.get("block_id") or "").strip()
            if block_type not in {"support_module", "followup_module"} or not block_id:
                continue
            score = _module_title_match_score(
                values,
                str(block.get("title") or "").strip(),
                str(block.get("body_text") or "").strip(),
            )
            if score > 0:
                ranked_matches.append((score, _canonical_support_module_block_id(block_id, block_type=block_type)))
        if not ranked_matches:
            return ""
        ranked_matches.sort(key=lambda item: item[0], reverse=True)
        best_score = ranked_matches[0][0]
        best_ids = sorted({block_id for score, block_id in ranked_matches if score == best_score})
        return best_ids[0] if len(best_ids) == 1 else ""

    def _deterministic_module_block_id_for_values(values: list[str]) -> str:
        for value in values:
            cleaned_value = str(value or "").strip()
            if not cleaned_value:
                continue
            exact_match = deterministic_module_alias_map.get(cleaned_value)
            if exact_match:
                return exact_match
        ranked_matches: list[tuple[int, str]] = []
        for spec in deterministic_module_specs:
            spec_block = spec.get("block") or {}
            block_id = str(spec_block.get("block_id") or "").strip()
            if not block_id:
                continue
            score = _module_title_match_score(
                values,
                str(spec_block.get("title") or "").strip(),
                str(spec_block.get("body_text") or "").strip(),
            )
            if score > 0:
                ranked_matches.append((score, block_id))
        if not ranked_matches:
            return ""
        ranked_matches.sort(key=lambda item: item[0], reverse=True)
        best_score = ranked_matches[0][0]
        best_ids = sorted({block_id for score, block_id in ranked_matches if score == best_score})
        return best_ids[0] if len(best_ids) == 1 else ""

    def _append_orchestration_logic_block(rule_id: str, workflow_id: str, candidate: dict[str, Any] | None) -> None:
        title = str((candidate or {}).get("title") or workflow_id).strip()
        if not title or title in existing_logic_titles:
            return
        block_id = f"logic:{_semantic_slug(title) or _semantic_slug(workflow_id) or rule_id or 'routing'}"
        interaction_logic_blocks.append(
            {
                "block_id": block_id,
                "title": title,
                "body_text": str((candidate or {}).get("body_text") or "").strip()
                or "Layered routing policy for selecting roles and child workflows by user need.",
            }
        )
        existing_logic_titles.add(title)

    def _is_orchestration_block_id(block_id: str) -> bool:
        value = str(block_id or "").strip()
        if not value:
            return False
        candidate, target_family = _match_candidate_for_values([value], "", None)
        return target_family == "orchestration"

    def _module_owned_deterministic_spec_for_workflow_block(
        block_id: str,
        title: str,
        body_text: str,
    ) -> dict[str, Any] | None:
        if not deterministic_module_specs:
            return None
        semantic_step_titles = [
            str(step.get("title") or "").strip()
            for step in procedure_steps
            if isinstance(step, dict)
            and str(step.get("title") or "").strip()
            and str(step.get("procedure_id") or "").strip() in {
                str(procedure.get("procedure_id") or "").strip()
                for procedure in procedures
                if isinstance(procedure, dict)
                and str(procedure.get("service_block_id") or "").strip() == block_id
            }
        ]
        best_match: dict[str, Any] | None = None
        best_rank: tuple[int, int] | None = None
        for spec in deterministic_module_specs:
            spec_block = spec.get("block") or {}
            spec_step_titles = [str(item).strip() for item in spec.get("step_titles", []) if str(item).strip()]
            if not spec_step_titles:
                continue
            overlap = len(
                {
                    step_title
                    for step_title in semantic_step_titles
                    if step_title and step_title in set(spec_step_titles)
                }
            )
            title_score = _module_title_match_score(
                [block_id, title, body_text, *semantic_step_titles],
                str(spec_block.get("title") or "").strip(),
                str(spec_block.get("body_text") or "").strip(),
            )
            rank = (overlap, title_score)
            if rank <= (0, 0):
                continue
            if best_rank is None or rank > best_rank:
                best_rank = rank
                best_match = spec
            elif best_rank == rank:
                best_match = None
        return best_match if best_rank and (best_rank[0] > 0 or best_rank[1] >= 8) else None

    role_workflow_targets: dict[str, set[str]] = {}
    module_targets_by_role: dict[str, set[str]] = {}
    used_candidate_ids: set[str] = set()
    normalized_routing_rules: list[dict[str, Any]] = []
    workflow_id_alias_map: dict[str, str] = {}
    module_id_alias_map: dict[str, str] = {}
    for rule in routing_rules:
        if not isinstance(rule, dict):
            continue
        normalized_rule = dict(rule)
        rule_id = str(normalized_rule.get("rule_id") or "").strip()
        role_id = str(rule.get("target_role_id") or "").strip()
        workflow_id = _normalized_workflow_block_id(rule.get("target_workflow_id") or "")
        if workflow_id:
            normalized_rule["target_workflow_id"] = workflow_id
        raw_target_module_id = str(rule.get("target_module_id") or "").strip()
        target_module_id = _normalized_module_block_id(raw_target_module_id)
        if target_module_id:
            normalized_rule["target_module_id"] = target_module_id
        module_ids = [
            _normalized_module_block_id(str(item or "").strip())
            for item in (
                rule.get("target_module_ids", [])
                or ([rule.get("target_module_id")] if rule.get("target_module_id") else [])
            )
            if str(item or "").strip()
        ]
        target_family = _target_family(workflow_id, role_id) if workflow_id else None
        if workflow_id and target_family == "orchestration":
            candidate = _match_candidate(workflow_id, role_id, used_candidate_ids)
            _append_orchestration_logic_block(rule_id, workflow_id, candidate)
            workflow_id_alias_map[workflow_id] = ""
            normalized_rule.pop("target_workflow_id", None)
            if role_id or module_ids or str(normalized_rule.get("target_module_id") or "").strip():
                normalized_routing_rules.append(normalized_rule)
            continue

        resolved_workflow_id = workflow_id
        candidate: dict[str, Any] | None = None
        resolved_explicit_module_target = False
        if (raw_target_module_id or target_module_id) and target_module_id not in existing_block_ids:
            deterministic_module_id = _deterministic_module_block_id_for_values(
                [raw_target_module_id, target_module_id, rule_id, role_id]
            )
            if deterministic_module_id:
                if target_module_id:
                    module_id_alias_map[target_module_id] = deterministic_module_id
                if raw_target_module_id:
                    module_id_alias_map[raw_target_module_id] = deterministic_module_id
                normalized_rule["target_module_id"] = deterministic_module_id
                module_targets_by_role.setdefault(role_id, set()).add(deterministic_module_id)
                target_module_id = deterministic_module_id
                resolved_explicit_module_target = True
        if not resolved_explicit_module_target and (raw_target_module_id or target_module_id) and target_module_id not in existing_block_ids:
            existing_module_id = _existing_module_block_id_for_values(
                [raw_target_module_id, target_module_id, rule_id, role_id]
            )
            if existing_module_id:
                if target_module_id:
                    module_id_alias_map[target_module_id] = existing_module_id
                if raw_target_module_id:
                    module_id_alias_map[raw_target_module_id] = existing_module_id
                normalized_rule["target_module_id"] = existing_module_id
                module_targets_by_role.setdefault(role_id, set()).add(existing_module_id)
                target_module_id = existing_module_id
                resolved_explicit_module_target = True
        if not resolved_explicit_module_target and (raw_target_module_id or target_module_id) and target_module_id not in existing_block_ids:
            module_candidate, module_family = _match_candidate_for_values(
                [raw_target_module_id, target_module_id, rule_id, role_id],
                role_id,
                None,
            )
            if module_candidate and _candidate_is_module_like(module_candidate):
                canonical_module_id = _resolved_executable_block_id_for_candidate(
                    module_candidate,
                    target_family=module_family,
                    role_id=role_id,
                )
                if canonical_module_id:
                    if target_module_id:
                        module_id_alias_map[target_module_id] = canonical_module_id
                    if raw_target_module_id:
                        module_id_alias_map[raw_target_module_id] = canonical_module_id
                    normalized_rule["target_module_id"] = canonical_module_id
                    module_targets_by_role.setdefault(role_id, set()).add(canonical_module_id)
                    target_module_id = canonical_module_id
        if workflow_id and workflow_id not in existing_block_ids:
            candidate = _match_candidate(workflow_id, role_id, used_candidate_ids)
            if not _candidate_is_route_target_eligible(candidate, "workflow"):
                fallback_workflow_candidate = _resolve_explicit_route_target_candidate(target_family, "workflow")
                if fallback_workflow_candidate is not None:
                    candidate = fallback_workflow_candidate
            if not candidate:
                normalized_routing_rules.append(normalized_rule)
                continue
            candidate_id = str(candidate.get("candidate_id") or "").strip()
            if candidate_id:
                used_candidate_ids.add(candidate_id)
            if _candidate_is_module_like(candidate):
                canonical_module_id = _resolved_executable_block_id_for_candidate(
                    candidate,
                    target_family=target_family,
                    role_id=role_id,
                )
                if not canonical_module_id:
                    normalized_routing_rules.append(normalized_rule)
                    continue
                module_id_alias_map[workflow_id] = canonical_module_id
                normalized_rule.pop("target_workflow_id", None)
                normalized_rule["target_module_id"] = canonical_module_id
                module_targets_by_role.setdefault(role_id, set()).add(canonical_module_id)
                if canonical_module_id not in existing_block_ids:
                    service_blocks.append(
                        {
                            "block_id": canonical_module_id,
                            "block_type": str(candidate.get("service_block_type") or "support_module"),
                            "title": candidate.get("title") or canonical_module_id,
                        }
                    )
                    existing_block_ids.add(canonical_module_id)
                normalized_routing_rules.append(normalized_rule)
                continue
            canonical_workflow_id = _canonical_route_workflow_block_id(
                candidate,
                target_family=target_family,
                role_id=role_id,
            )
            if not canonical_workflow_id:
                normalized_routing_rules.append(normalized_rule)
                continue
            resolved_workflow_id = canonical_workflow_id
            normalized_rule["target_workflow_id"] = resolved_workflow_id
            workflow_id_alias_map[workflow_id] = resolved_workflow_id
            if resolved_workflow_id not in existing_block_ids:
                service_blocks.append(
                    {
                        "block_id": resolved_workflow_id,
                        "block_type": "primary_workflow",
                        "title": candidate.get("title") or resolved_workflow_id,
                        "is_default": False,
                    }
                )
                existing_block_ids.add(resolved_workflow_id)

            procedure_id = _canonical_procedure_id_for_workflow_id(resolved_workflow_id)
            if procedure_id not in existing_procedure_ids:
                procedures.append(
                    {
                        "procedure_id": procedure_id,
                        "service_block_id": resolved_workflow_id,
                        "title": candidate.get("title") or resolved_workflow_id,
                    }
                )
                existing_procedure_ids.add(procedure_id)

            step_id = f"step:{_semantic_slug(resolved_workflow_id) or resolved_workflow_id}:1"
            if step_id not in existing_step_ids:
                resource_files = list(candidate.get("resource_files") or [])
                execution_mode = "bundled" if len(resource_files) > 1 else "interactive"
                procedure_steps.append(
                    {
                        "procedure_id": procedure_id,
                        "step_id": step_id,
                        "title": candidate.get("title") or resolved_workflow_id,
                        "order": 1,
                        "execution_mode": execution_mode,
                        "resource_refs": resource_files if execution_mode == "interactive" else [],
                        "bundled_step_ids": [step_id] if execution_mode == "bundled" else [],
                        "bundled_resource_refs": resource_files if execution_mode == "bundled" else [],
                    }
                )
                existing_step_ids.add(step_id)
        elif workflow_id:
            workflow_id_alias_map.setdefault(workflow_id, resolved_workflow_id)

        if role_id and resolved_workflow_id and resolved_workflow_id in existing_block_ids:
            role_workflow_targets.setdefault(role_id, set()).add(resolved_workflow_id)
        normalized_routing_rules.append(normalized_rule)

    for role_id, workflow_targets in role_workflow_targets.items():
        if role_id in existing_role_ids:
            continue
        role_profiles.append(
            {
                "role_id": role_id,
                "name": role_id,
                "target_workflow_ids": sorted(workflow_targets),
                "allowed_module_ids": sorted(module_targets_by_role.get(role_id, set())),
            }
        )
        existing_role_ids.add(role_id)
    for role_id, module_targets in module_targets_by_role.items():
        valid_module_targets = sorted(
            {
                target
                for target in module_targets
                if target in existing_block_ids or target in set(module_id_alias_map.values())
            }
        )
        if not valid_module_targets:
            continue
        if role_id in existing_role_ids:
            for role in role_profiles:
                if isinstance(role, dict) and str(role.get("role_id") or "").strip() == role_id:
                    existing_allowed = {
                        str(item or "").strip()
                        for item in role.get("allowed_module_ids", []) or []
                        if str(item or "").strip()
                    }
                    role["allowed_module_ids"] = sorted(existing_allowed | set(valid_module_targets))
                    break
            continue
        role_profiles.append(
            {
                "role_id": role_id,
                "name": role_id,
                "target_workflow_ids": [],
                "allowed_module_ids": valid_module_targets,
            }
        )
        existing_role_ids.add(role_id)

    if primary_service_mode in {"intent_routed_multi_workflow", "intent_routed_interaction_logic"}:
        rewritten_service_blocks: list[dict[str, Any]] = []
        canonical_block_index: dict[str, int] = {}
        canonical_block_titles: dict[str, str] = {}
        canonical_block_types: dict[str, str] = {}
        for item in service_blocks:
            if not isinstance(item, dict):
                continue
            block = dict(item)
            block_type = str(block.get("block_type") or "").strip()
            block_id = str(block.get("block_id") or "").strip()
            if block_type == "primary_workflow" and block_id:
                module_owned_spec = _module_owned_deterministic_spec_for_workflow_block(
                    block_id,
                    str(block.get("title") or "").strip(),
                    str(block.get("body_text") or "").strip(),
                )
                if isinstance(module_owned_spec, dict):
                    spec_block = dict(module_owned_spec.get("block") or {})
                    canonical_module_id = str(spec_block.get("block_id") or "").strip()
                    if canonical_module_id:
                        workflow_id_alias_map[block_id] = canonical_module_id
                        module_id_alias_map[block_id] = canonical_module_id
                        block["block_id"] = canonical_module_id
                        block["block_type"] = str(spec_block.get("block_type") or "support_module")
                        block["title"] = str(spec_block.get("title") or "").strip() or str(block.get("title") or "").strip()
                        block["body_text"] = str(spec_block.get("body_text") or "").strip() or str(block.get("body_text") or "").strip()
                        normalized_block_id = _normalized_module_block_id(block_id)
                        if normalized_block_id:
                            module_id_alias_map[normalized_block_id] = canonical_module_id
                if str(block.get("block_type") or "").strip() in {"support_module", "followup_module"}:
                    fallback_candidate = _synthetic_route_candidate(
                        _normalized_module_block_id(str(block.get("block_id") or "").strip()),
                        str(block.get("title") or "").strip(),
                        str(block.get("body_text") or "").strip(),
                        declared_target_type="module",
                    )
                    canonical_module_id = (
                        _existing_module_block_id_for_candidate(fallback_candidate)
                        or _deterministic_module_block_id_for_values(
                            [
                                str(block.get("block_id") or "").strip(),
                                str(block.get("title") or "").strip(),
                                str(block.get("body_text") or "").strip(),
                            ]
                        )
                        or _canonical_support_module_block_id(
                            str(block.get("block_id") or "").strip(),
                            block_type=str(block.get("block_type") or "").strip() or "support_module",
                        )
                    )
                    current_block_id = str(block.get("block_id") or "").strip()
                    module_id_alias_map[current_block_id] = canonical_module_id
                    normalized_block_id = _normalized_module_block_id(current_block_id)
                    if normalized_block_id:
                        module_id_alias_map[normalized_block_id] = canonical_module_id
                    block["block_id"] = canonical_module_id
                    block["title"] = _preferred_executable_title(
                        fallback_candidate,
                        target_family=_semantic_family(canonical_module_id, block.get("title"), block.get("body_text")),
                        current_title=str(block.get("title") or "").strip(),
                        interaction_logic_titles=existing_logic_titles,
                    ) or canonical_module_id
                    canonical_id = str(block.get("block_id") or "").strip()
                    if not canonical_id:
                        continue
                    canonical_title = str(block.get("title") or "").strip()
                    canonical_family = _semantic_family(canonical_id, canonical_title, block.get("body_text"))
                    if canonical_id in canonical_block_titles:
                        existing_index = canonical_block_index[canonical_id]
                        existing_block = rewritten_service_blocks[existing_index]
                        existing_title = str(existing_block.get("title") or "").strip()
                        if _executable_title_quality(canonical_title, canonical_family, existing_logic_titles) > _executable_title_quality(
                            existing_title,
                            canonical_family,
                            existing_logic_titles,
                        ):
                            existing_block["title"] = canonical_title
                            canonical_block_titles[canonical_id] = canonical_title
                        continue
                    canonical_block_index[canonical_id] = len(rewritten_service_blocks)
                    canonical_block_titles[canonical_id] = canonical_title
                    canonical_block_types[canonical_id] = str(block.get("block_type") or "").strip()
                    rewritten_service_blocks.append(block)
                    continue
                candidate, target_family = _match_candidate_for_values(
                    [block_id, str(block.get("title") or "").strip(), str(block.get("body_text") or "").strip()],
                    "",
                    None,
                )
                fallback_candidate = _synthetic_route_candidate(
                    block_id,
                    str(block.get("title") or "").strip(),
                    str(block.get("body_text") or "").strip(),
                    declared_target_type="workflow",
                )
                if target_family == "orchestration":
                    _append_orchestration_logic_block(block_id, block_id, candidate)
                    continue
                candidate_for_rewrite = candidate
                if not _candidate_is_route_target_eligible(candidate_for_rewrite, "workflow"):
                    candidate_for_rewrite = _resolve_explicit_route_target_candidate(target_family, "workflow")
                candidate_for_rewrite = candidate_for_rewrite or fallback_candidate
                canonical_block_id = _canonical_route_workflow_block_id(
                    candidate_for_rewrite,
                    target_family=target_family,
                    role_id="",
                )
                if canonical_block_id:
                    workflow_id_alias_map[block_id] = canonical_block_id
                    block["block_id"] = canonical_block_id
                block["title"] = _preferred_executable_title(
                    candidate_for_rewrite,
                    target_family=target_family,
                    current_title=str(block.get("title") or "").strip(),
                    interaction_logic_titles=existing_logic_titles,
                ) or str(block.get("title") or "").strip() or str(block.get("block_id") or "").strip()
            elif block_type in {"support_module", "followup_module"} and block_id:
                fallback_candidate = _synthetic_route_candidate(
                    _normalized_module_block_id(block_id),
                    str(block.get("title") or "").strip(),
                    str(block.get("body_text") or "").strip(),
                    declared_target_type="module",
                )
                canonical_module_id = (
                    _existing_module_block_id_for_candidate(fallback_candidate)
                    or _deterministic_module_block_id_for_values(
                        [
                            block_id,
                            str(block.get("title") or "").strip(),
                            str(block.get("body_text") or "").strip(),
                        ]
                    )
                    or _canonical_support_module_block_id(
                        block_id,
                        block_type=block_type,
                    )
                )
                module_id_alias_map[block_id] = canonical_module_id
                normalized_block_id = _normalized_module_block_id(block_id)
                if normalized_block_id:
                    module_id_alias_map[normalized_block_id] = canonical_module_id
                block["block_id"] = canonical_module_id
                block["title"] = _preferred_executable_title(
                    fallback_candidate,
                    target_family=_semantic_family(canonical_module_id, block.get("title"), block.get("body_text")),
                    current_title=str(block.get("title") or "").strip(),
                    interaction_logic_titles=existing_logic_titles,
                ) or canonical_module_id
            canonical_id = str(block.get("block_id") or "").strip()
            if not canonical_id:
                continue
            canonical_title = str(block.get("title") or "").strip()
            canonical_family = _semantic_family(canonical_id, canonical_title, block.get("body_text"))
            if canonical_id in canonical_block_titles:
                existing_index = canonical_block_index[canonical_id]
                existing_block = rewritten_service_blocks[existing_index]
                existing_title = str(existing_block.get("title") or "").strip()
                if _executable_title_quality(canonical_title, canonical_family, existing_logic_titles) > _executable_title_quality(
                    existing_title,
                    canonical_family,
                    existing_logic_titles,
                ):
                    existing_block["title"] = canonical_title
                    canonical_block_titles[canonical_id] = canonical_title
                continue
            canonical_block_index[canonical_id] = len(rewritten_service_blocks)
            canonical_block_titles[canonical_id] = canonical_title
            canonical_block_types[canonical_id] = str(block.get("block_type") or "").strip()
            rewritten_service_blocks.append(block)
        service_blocks = rewritten_service_blocks
        existing_block_ids = set(canonical_block_titles.keys())

        def _ensure_service_block_exists_for_procedure(
            service_block_id: str,
            procedure: dict[str, Any],
            candidate: dict[str, Any] | None,
            target_family: str | None,
        ) -> str:
            normalized_block_id = str(service_block_id or "").strip()
            if not normalized_block_id or normalized_block_id in existing_block_ids or _is_orchestration_block_id(normalized_block_id):
                return normalized_block_id

            if normalized_block_id.startswith(("support_module:", "followup_module:")):
                spec = deterministic_module_specs_by_block_id.get(normalized_block_id)
                if isinstance(spec, dict):
                    block_to_add = dict(spec.get("block") or {})
                else:
                    block_to_add = {
                        "block_id": normalized_block_id,
                        "block_type": "followup_module" if normalized_block_id.startswith("followup_module:") else "support_module",
                        "title": str(procedure.get("title") or "").strip() or normalized_block_id,
                    }
            else:
                block_to_add = {
                    "block_id": normalized_block_id,
                    "block_type": "primary_workflow",
                    "title": _preferred_executable_title(
                        candidate or _synthetic_route_candidate(
                            normalized_block_id,
                            str(procedure.get("title") or "").strip(),
                            declared_target_type="workflow",
                        ),
                        target_family=target_family,
                        current_title=str(procedure.get("title") or "").strip(),
                        interaction_logic_titles=existing_logic_titles,
                    )
                    or str(procedure.get("title") or "").strip()
                    or normalized_block_id,
                    "is_default": False,
                }

            canonical_id = str(block_to_add.get("block_id") or "").strip()
            if not canonical_id or canonical_id in existing_block_ids:
                return canonical_id or normalized_block_id
            rewritten_service_blocks.append(block_to_add)
            existing_block_ids.add(canonical_id)
            canonical_block_titles[canonical_id] = str(block_to_add.get("title") or "").strip()
            canonical_block_types[canonical_id] = str(block_to_add.get("block_type") or "").strip()
            canonical_block_index[canonical_id] = len(rewritten_service_blocks) - 1
            return canonical_id

        rewritten_role_profiles: list[dict[str, Any]] = []
        for item in role_profiles:
            if not isinstance(item, dict):
                continue
            role = dict(item)
            default_workflow_id = str(role.get("default_workflow_id") or role.get("target_workflow_id") or "").strip()
            if default_workflow_id:
                canonical_default = workflow_id_alias_map.get(default_workflow_id, default_workflow_id)
                role["default_workflow_id"] = canonical_default
                if "target_workflow_id" in role:
                    role["target_workflow_id"] = canonical_default
            target_workflow_ids = [
                workflow_id_alias_map.get(str(value or "").strip(), str(value or "").strip())
                for value in role.get("target_workflow_ids", []) or []
                if str(value or "").strip()
            ]
            if target_workflow_ids:
                role["target_workflow_ids"] = sorted(dict.fromkeys(target_workflow_ids))
            allowed_workflow_ids = [
                workflow_id_alias_map.get(str(value or "").strip(), str(value or "").strip())
                for value in role.get("allowed_workflow_ids", []) or []
                if str(value or "").strip()
            ]
            if allowed_workflow_ids:
                role["allowed_workflow_ids"] = sorted(dict.fromkeys(allowed_workflow_ids))
            allowed_module_ids = [
                module_id_alias_map.get(_normalized_module_block_id(str(value or "").strip()), _normalized_module_block_id(str(value or "").strip()))
                for value in role.get("allowed_module_ids", []) or []
                if str(value or "").strip()
            ]
            if allowed_module_ids:
                role["allowed_module_ids"] = sorted(dict.fromkeys(allowed_module_ids))
            rewritten_role_profiles.append(role)
        role_profiles = rewritten_role_profiles

        rewritten_routing_rules: list[dict[str, Any]] = []
        for item in normalized_routing_rules:
            if not isinstance(item, dict):
                continue
            rule = dict(item)
            target_workflow_id = str(rule.get("target_workflow_id") or "").strip()
            if target_workflow_id:
                canonical_target_workflow_id = workflow_id_alias_map.get(target_workflow_id, target_workflow_id)
                if canonical_target_workflow_id.startswith(("module:", "support_module:", "followup_module:")):
                    rule.pop("target_workflow_id", None)
                    existing_target_module_id = _normalized_module_block_id(str(rule.get("target_module_id") or "").strip())
                    rule["target_module_id"] = existing_target_module_id or canonical_target_workflow_id
                elif canonical_target_workflow_id:
                    rule["target_workflow_id"] = canonical_target_workflow_id
            target_module_id = _normalized_module_block_id(str(rule.get("target_module_id") or "").strip())
            if target_module_id:
                canonical_target_module_id = module_id_alias_map.get(target_module_id, target_module_id)
                direct_existing_module_id = _existing_module_block_id_for_values(
                    [target_module_id, str(rule.get("rule_id") or "").strip()]
                )
                if direct_existing_module_id:
                    canonical_target_module_id = direct_existing_module_id
                else:
                    deterministic_module_id = _deterministic_module_block_id_for_values(
                        [target_module_id, str(rule.get("rule_id") or "").strip()]
                    )
                    if deterministic_module_id:
                        canonical_target_module_id = deterministic_module_id
                rule["target_module_id"] = canonical_target_module_id
            target_module_ids = [
                module_id_alias_map.get(_normalized_module_block_id(str(value or "").strip()), _normalized_module_block_id(str(value or "").strip()))
                for value in rule.get("target_module_ids", []) or []
                if str(value or "").strip()
            ]
            if target_module_ids:
                rule["target_module_ids"] = sorted(dict.fromkeys(target_module_ids))
            rewritten_routing_rules.append(rule)
        normalized_routing_rules = rewritten_routing_rules

        def _canonicalize_workflow_reference(value: str) -> str:
            workflow_value = str(value or "").strip()
            if not workflow_value:
                return ""
            normalized_workflow_id = _normalized_workflow_block_id(workflow_value)
            canonical_workflow_id = workflow_id_alias_map.get(
                normalized_workflow_id,
                workflow_id_alias_map.get(workflow_value, normalized_workflow_id),
            )
            if canonical_workflow_id in existing_block_ids:
                return canonical_workflow_id
            candidate, target_family = _match_candidate_for_values([workflow_value], "", None)
            if isinstance(candidate, dict):
                if _candidate_is_module_like(candidate):
                    return _resolved_executable_block_id_for_candidate(
                        candidate,
                        target_family=target_family,
                    )
                resolved_workflow_id = _canonical_route_workflow_block_id(
                    candidate,
                    target_family=target_family,
                )
                if resolved_workflow_id:
                    return resolved_workflow_id
            return canonical_workflow_id

        def _canonicalize_module_reference(value: str) -> str:
            module_value = str(value or "").strip()
            if not module_value:
                return ""
            normalized_module_id = _normalized_module_block_id(module_value)
            direct_existing_module_id = _existing_module_block_id_for_values([module_value, normalized_module_id])
            if direct_existing_module_id:
                return direct_existing_module_id
            deterministic_module_id = _deterministic_module_block_id_for_values([module_value, normalized_module_id])
            if deterministic_module_id:
                return deterministic_module_id
            canonical_module_id = module_id_alias_map.get(
                normalized_module_id,
                module_id_alias_map.get(module_value, normalized_module_id),
            )
            if canonical_module_id in existing_block_ids:
                return canonical_module_id
            existing_module_id = _existing_module_block_id_for_values([module_value])
            if existing_module_id:
                return existing_module_id
            candidate, target_family = _match_candidate_for_values([module_value], "", None)
            if isinstance(candidate, dict) and _candidate_is_module_like(candidate):
                resolved_module_id = _resolved_executable_block_id_for_candidate(
                    candidate,
                    target_family=target_family,
                )
                if resolved_module_id:
                    return resolved_module_id
            return canonical_module_id

        def _rewrite_logic_target_refs(value: Any) -> Any:
            if isinstance(value, list):
                return [_rewrite_logic_target_refs(item) for item in value]
            if not isinstance(value, dict):
                return value
            rewritten = dict(value)
            for workflow_key in ("target_workflow_id", "workflow_id", "primary_workflow_id", "default_workflow_id"):
                workflow_id = str(rewritten.get(workflow_key) or "").strip()
                if not workflow_id:
                    continue
                canonical_workflow_id = _canonicalize_workflow_reference(workflow_id)
                if canonical_workflow_id:
                    rewritten[workflow_key] = canonical_workflow_id
            for module_key in ("target_module_id", "module_id"):
                target_module_id = str(rewritten.get(module_key) or "").strip()
                if not target_module_id:
                    continue
                canonical_target_module_id = _canonicalize_module_reference(target_module_id)
                if canonical_target_module_id:
                    rewritten[module_key] = canonical_target_module_id
            for key in (
                "target_module_ids",
                "subordinate_modules",
                "support_module_refs",
                "allowed_module_ids",
                "optional_support_modules",
                "workflow_options",
                "target_workflow_ids",
                "options",
            ):
                values = rewritten.get(key)
                if not isinstance(values, list):
                    continue
                rewritten_values: list[Any] = []
                for item in values:
                    if not isinstance(item, str):
                        rewritten_values.append(_rewrite_logic_target_refs(item))
                        continue
                    text = str(item).strip()
                    if not text:
                        continue
                    if key in {"target_module_ids", "subordinate_modules", "support_module_refs", "allowed_module_ids", "optional_support_modules"}:
                        rewritten_values.append(_canonicalize_module_reference(text))
                    elif key in {"workflow_options", "target_workflow_ids"}:
                        rewritten_values.append(_canonicalize_workflow_reference(text))
                    else:
                        rewritten_values.append(text)
                rewritten[key] = rewritten_values
            for nested_key, nested_value in list(rewritten.items()):
                if nested_key in {
                    "target_workflow_id",
                    "workflow_id",
                    "primary_workflow_id",
                    "default_workflow_id",
                    "target_module_id",
                    "module_id",
                    "target_module_ids",
                    "subordinate_modules",
                    "support_module_refs",
                    "allowed_module_ids",
                    "optional_support_modules",
                    "workflow_options",
                    "target_workflow_ids",
                    "options",
                }:
                    continue
                rewritten[nested_key] = _rewrite_logic_target_refs(nested_value)
            return rewritten

        interaction_logic_blocks = [
            _rewrite_logic_target_refs(item)
            for item in interaction_logic_blocks
            if isinstance(item, dict)
        ]
        if isinstance(module_orchestration, dict):
            module_orchestration = _rewrite_logic_target_refs(module_orchestration)

        procedure_id_alias_map: dict[str, str] = {}
        rewritten_procedures: list[dict[str, Any]] = []
        existing_procedure_ids = set()
        for item in procedures:
            if not isinstance(item, dict):
                continue
            procedure = dict(item)
            old_procedure_id = str(procedure.get("procedure_id") or "").strip()
            service_block_id = str(procedure.get("service_block_id") or "").strip()
            service_block_id = workflow_id_alias_map.get(service_block_id, module_id_alias_map.get(service_block_id, service_block_id))
            candidate = None
            target_family = None
            if service_block_id not in existing_block_ids:
                deterministic_module_id = _deterministic_module_block_id_for_values(
                    [old_procedure_id, str(procedure.get("title") or "").strip(), service_block_id]
                )
                if deterministic_module_id:
                    service_block_id = deterministic_module_id
                if not deterministic_module_id:
                    candidate, target_family = _match_candidate_for_values(
                        [old_procedure_id, str(procedure.get("title") or "").strip(), service_block_id],
                        "",
                        None,
                    )
                    if service_block_id not in existing_block_ids and candidate:
                        canonical_block_id = (
                            _resolved_executable_block_id_for_candidate(
                                candidate,
                                target_family=target_family,
                                role_id="",
                            )
                            if _candidate_is_module_like(candidate)
                            else _canonical_route_workflow_block_id(candidate, target_family=target_family, role_id="")
                        )
                        if canonical_block_id:
                            service_block_id = canonical_block_id
            service_block_id = _ensure_service_block_exists_for_procedure(
                service_block_id,
                procedure,
                candidate,
                target_family,
            )
            if _is_orchestration_block_id(service_block_id):
                if old_procedure_id:
                    procedure_id_alias_map[old_procedure_id] = ""
                continue
            canonical_procedure_id = _canonical_procedure_id_for_block_id(service_block_id) if service_block_id else old_procedure_id
            if old_procedure_id:
                procedure_id_alias_map[old_procedure_id] = canonical_procedure_id
            procedure["procedure_id"] = canonical_procedure_id
            if service_block_id:
                procedure["service_block_id"] = service_block_id
                canonical_block_title = canonical_block_titles.get(service_block_id, "")
                block_family = _semantic_family(service_block_id, canonical_block_title, procedure.get("title"))
                if canonical_block_title and _executable_title_quality(
                    canonical_block_title,
                    block_family,
                    existing_logic_titles,
                ) >= _executable_title_quality(
                    str(procedure.get("title") or "").strip(),
                    block_family,
                    existing_logic_titles,
                ):
                    procedure["title"] = canonical_block_title
            if not canonical_procedure_id or canonical_procedure_id in existing_procedure_ids:
                continue
            rewritten_procedures.append(procedure)
            existing_procedure_ids.add(canonical_procedure_id)

        for block_id in existing_block_ids:
            if _is_orchestration_block_id(block_id):
                continue
            canonical_procedure_id = _canonical_procedure_id_for_block_id(block_id)
            if canonical_procedure_id in existing_procedure_ids:
                continue
            rewritten_procedures.append(
                {
                    "procedure_id": canonical_procedure_id,
                    "service_block_id": block_id,
                    "title": canonical_block_titles.get(block_id) or block_id,
                }
            )
            existing_procedure_ids.add(canonical_procedure_id)

        procedures = rewritten_procedures
        rewritten_steps: list[dict[str, Any]] = []
        existing_step_ids = set()
        for item in procedure_steps:
            if not isinstance(item, dict):
                continue
            step = dict(item)
            old_procedure_id = str(step.get("procedure_id") or "").strip()
            canonical_procedure_id = procedure_id_alias_map.get(old_procedure_id, "")
            if not canonical_procedure_id:
                candidate, target_family = _match_candidate_for_values(
                    [
                        old_procedure_id,
                        str(step.get("title") or "").strip(),
                        str(step.get("body_text") or "").strip(),
                        *[str(ref or "").strip() for ref in step.get("resource_refs", []) or [] if str(ref or "").strip()],
                        *[
                            str(ref or "").strip()
                            for ref in step.get("bundled_resource_refs", []) or []
                            if str(ref or "").strip()
                        ],
                    ],
                    "",
                    None,
                )
                if candidate:
                    canonical_block_id = (
                        _resolved_executable_block_id_for_candidate(
                            candidate,
                            target_family=target_family,
                            role_id="",
                        )
                        if _candidate_is_module_like(candidate)
                        else _canonical_route_workflow_block_id(candidate, target_family=target_family, role_id="")
                    )
                    if canonical_block_id:
                        if _is_orchestration_block_id(canonical_block_id):
                            canonical_procedure_id = ""
                        else:
                            canonical_procedure_id = _canonical_procedure_id_for_block_id(canonical_block_id)
            if not canonical_procedure_id:
                continue
            step["procedure_id"] = canonical_procedure_id
            canonical_block_id = next(
                (
                    str(procedure.get("service_block_id") or "").strip()
                    for procedure in rewritten_procedures
                    if isinstance(procedure, dict)
                    and str(procedure.get("procedure_id") or "").strip() == canonical_procedure_id
                ),
                "",
            )
            canonical_block_title = canonical_block_titles.get(canonical_block_id, "")
            step_title = str(step.get("title") or "").strip()
            block_family = _semantic_family(canonical_block_id, canonical_block_title, step_title)
            if canonical_block_title and not _should_preserve_step_specific_title(step_title, canonical_block_title) and _executable_title_quality(
                canonical_block_title,
                block_family,
                existing_logic_titles,
            ) > _executable_title_quality(
                step_title,
                block_family,
                existing_logic_titles,
            ):
                step["title"] = canonical_block_title
            step_id = str(step.get("step_id") or "").strip()
            if step_id and step_id in existing_step_ids:
                continue
            rewritten_steps.append(step)
            if step_id:
                existing_step_ids.add(step_id)

        step_ids_by_procedure: dict[str, set[str]] = {}
        for step in rewritten_steps:
            if not isinstance(step, dict):
                continue
            pid = str(step.get("procedure_id") or "").strip()
            sid = str(step.get("step_id") or "").strip()
            if pid and sid:
                step_ids_by_procedure.setdefault(pid, set()).add(sid)
        for procedure in rewritten_procedures:
            if not isinstance(procedure, dict):
                continue
            procedure_id = str(procedure.get("procedure_id") or "").strip()
            service_block_id = str(procedure.get("service_block_id") or "").strip()
            if not procedure_id or not service_block_id:
                continue
            if step_ids_by_procedure.get(procedure_id):
                continue
            candidate, target_family = _match_candidate_for_values(
                [service_block_id, str(procedure.get("title") or "").strip()],
                "",
                None,
            )
            resource_files = list((candidate or {}).get("resource_files") or [])
            step_id = f"step:{_semantic_slug(service_block_id) or service_block_id}:1"
            if step_id in existing_step_ids:
                continue
            execution_mode = "bundled" if len(resource_files) > 1 else "interactive"
            rewritten_steps.append(
                {
                    "procedure_id": procedure_id,
                    "step_id": step_id,
                    "title": str(procedure.get("title") or service_block_id).strip(),
                    "order": 1,
                    "execution_mode": execution_mode,
                    "resource_refs": resource_files if execution_mode == "interactive" else [],
                    "bundled_step_ids": [step_id] if execution_mode == "bundled" else [],
                    "bundled_resource_refs": resource_files if execution_mode == "bundled" else [],
                }
            )
            existing_step_ids.add(step_id)

        procedure_steps = rewritten_steps
        rewritten_clarification_gate_rules: list[dict[str, Any]] = []
        for item in clarification_gate_rules:
            if not isinstance(item, dict):
                continue
            rule = dict(item)
            old_procedure_id = str(rule.get("procedure_id") or "").strip()
            if old_procedure_id:
                rule["procedure_id"] = procedure_id_alias_map.get(old_procedure_id, old_procedure_id)
            rewritten_clarification_gate_rules.append(rule)
        clarification_gate_rules = rewritten_clarification_gate_rules

    normalized["service_blocks"] = service_blocks
    normalized["procedures"] = procedures
    normalized["procedure_steps"] = procedure_steps
    normalized["role_profiles"] = role_profiles
    normalized["routing_rules"] = normalized_routing_rules
    normalized["interaction_logic_blocks"] = interaction_logic_blocks
    normalized["clarification_gate_rules"] = clarification_gate_rules
    normalized["module_orchestration"] = module_orchestration
    return normalized


def _canonicalize_provider_semantic_model(semantic_model: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(semantic_model, dict):
        return {}

    normalized = dict(semantic_model)

    if not isinstance(normalized.get("role_profiles"), list):
        roles = normalized.get("roles")
        if not isinstance(roles, list):
            roles = normalized.get("global_roles")
        if isinstance(roles, list):
            normalized["role_profiles"] = [
                {
                    "role_id": str(item.get("role_id") or "").strip(),
                    "name": str(item.get("role_name") or item.get("title") or item.get("name") or "").strip(),
                    "description": str(item.get("role_description") or item.get("description") or "").strip() or None,
                    "tone_profile": (
                        _semantic_dict(item.get("tone_profile")) or _semantic_dict(item.get("tone_style"))
                    ) if isinstance(item, dict) else {},
                    "permitted_boundaries": list(item.get("permitted_boundaries", []) or ((item.get("boundary") or {}).get("allowed", []) if isinstance(item.get("boundary"), dict) else [])) if isinstance(item, dict) else [],
                    "prohibited_topics": list(item.get("prohibited_topics", []) or ((item.get("boundary") or {}).get("forbidden", []) if isinstance(item.get("boundary"), dict) else [])) if isinstance(item, dict) else [],
                    "security_rules": list(item.get("security_rules", []) or []) if isinstance(item, dict) else [],
                }
                for item in roles
                if isinstance(item, dict)
            ]

    primary_workflows = normalized.get("primary_workflows")
    if not isinstance(primary_workflows, list):
        singular = normalized.get("primary_workflow")
        if isinstance(singular, list):
            primary_workflows = [item for item in singular if isinstance(item, dict)]
        else:
            primary_workflows = [singular] if isinstance(singular, dict) else None
    if isinstance(primary_workflows, list):
        if not isinstance(normalized.get("service_blocks"), list):
            normalized["service_blocks"] = []
        if not isinstance(normalized.get("procedures"), list):
            normalized["procedures"] = []
        if not isinstance(normalized.get("procedure_steps"), list):
            normalized["procedure_steps"] = []
        if not isinstance(normalized.get("clarification_gate_rules"), list):
            normalized["clarification_gate_rules"] = []

        service_blocks = list(normalized.get("service_blocks") or [])
        procedures = list(normalized.get("procedures") or [])
        procedure_steps = list(normalized.get("procedure_steps") or [])
        clarification_gate_rules = list(normalized.get("clarification_gate_rules") or [])

        existing_block_ids = {
            str(item.get("block_id") or "").strip()
            for item in service_blocks
            if isinstance(item, dict)
        }
        existing_procedure_ids = {
            str(item.get("procedure_id") or "").strip()
            for item in procedures
            if isinstance(item, dict)
        }
        existing_step_ids = {
            str(item.get("step_id") or "").strip()
            for item in procedure_steps
            if isinstance(item, dict)
        }

        if (
            normalized.get("default_workflow_id") is None
            and str(normalized.get("primary_service_mode") or "").strip() == "single_default_workflow"
        ):
            for workflow in primary_workflows:
                if isinstance(workflow, dict) and bool(workflow.get("is_default")):
                    normalized["default_workflow_id"] = str(workflow.get("workflow_id") or "").strip() or None
                    break

        for workflow in primary_workflows:
            if not isinstance(workflow, dict):
                continue
            workflow_id = str(workflow.get("workflow_id") or "").strip()
            if not workflow_id:
                continue
            if workflow_id not in existing_block_ids:
                service_blocks.append(
                    {
                        "block_id": workflow_id,
                        "block_type": "primary_workflow",
                        "title": str(
                            workflow.get("workflow_title")
                            or workflow.get("workflow_name")
                            or workflow.get("title")
                            or ""
                        ).strip(),
                        "is_default": bool(workflow.get("is_default")),
                    }
                )
                existing_block_ids.add(workflow_id)

            procedure_id = workflow_id
            if procedure_id not in existing_procedure_ids:
                procedures.append(
                    {
                        "procedure_id": procedure_id,
                        "service_block_id": workflow_id,
                        "title": str(
                            workflow.get("workflow_title")
                            or workflow.get("workflow_name")
                            or workflow.get("title")
                            or ""
                        ).strip(),
                    }
                )
                existing_procedure_ids.add(procedure_id)

            sequence = workflow.get("step_sequence")
            if not isinstance(sequence, list):
                sequence = workflow.get("steps")
            clarification_step_id = None
            completion_step_id = None
            if isinstance(sequence, list):
                for index, step in enumerate(sequence):
                    if not isinstance(step, dict):
                        continue
                    step_id = str(step.get("step_id") or "").strip()
                    if not step_id:
                        continue
                    if step_id in existing_step_ids:
                        continue
                    execution_mode = str(step.get("execution_mode") or "").strip() or "interactive"
                    bundled_step_ids = [
                        str(item).strip()
                        for item in (step.get("bundled_steps", []) or step.get("bundled_child_steps", []) or [])
                        if str(item).strip()
                    ]
                    if execution_mode == "bundled":
                        bundled_step_ids = [step_id] + [
                            item for item in bundled_step_ids if item != step_id
                        ]
                    procedure_steps.append(
                        {
                            "procedure_id": procedure_id,
                            "step_id": step_id,
                            "title": str(step.get("title") or "").strip(),
                            "order": step.get("order", step.get("step_order", index)),
                            "execution_mode": execution_mode,
                            "resource_refs": list(step.get("resource_refs", []) or step.get("bundled_resource_refs", []) or []),
                            "bundled_step_ids": bundled_step_ids,
                            "wait_for_user": step.get("wait_for_user"),
                            "stop_after_completion": step.get("stop_after_completion"),
                        }
                    )
                    existing_step_ids.add(step_id)
                    lowered_title = str(step.get("title") or "").strip().lower()
                    if clarification_step_id is None and (
                        "clarification" in lowered_title or step_id == "clarification"
                    ):
                        clarification_step_id = step_id
                    elif clarification_step_id is not None and completion_step_id is None:
                        completion_step_id = step_id
                if clarification_step_id and completion_step_id:
                    clarification_gate_rules.append(
                        {
                            "rule_id": f"{procedure_id}:clarification_gate",
                            "procedure_id": procedure_id,
                            "clarification_step_id": clarification_step_id,
                            "completion_step_id": completion_step_id,
                        }
                    )

        normalized["service_blocks"] = service_blocks
        normalized["procedures"] = procedures
        normalized["procedure_steps"] = procedure_steps
        normalized["clarification_gate_rules"] = clarification_gate_rules

    if not isinstance(normalized.get("service_blocks"), list):
        normalized["service_blocks"] = []
    service_blocks = list(normalized.get("service_blocks") or [])
    existing_block_ids = {
        str(item.get("block_id") or "").strip()
        for item in service_blocks
        if isinstance(item, dict)
    }

    support_modules = normalized.get("support_modules")
    if isinstance(support_modules, list):
        for module in support_modules:
            if not isinstance(module, dict):
                continue
            module_id = str(module.get("module_id") or "").strip()
            if not module_id or module_id in existing_block_ids:
                continue
            service_blocks.append(
                {
                    "block_id": module_id,
                    "block_type": "support_module",
                    "title": str(module.get("module_title") or module.get("title") or "").strip(),
                }
            )
            existing_block_ids.add(module_id)

    followup_modules = normalized.get("followup_modules")
    if isinstance(followup_modules, list):
        for module in followup_modules:
            if not isinstance(module, dict):
                continue
            module_id = str(module.get("module_id") or "").strip()
            if not module_id or module_id in existing_block_ids:
                continue
            service_blocks.append(
                {
                    "block_id": module_id,
                    "block_type": "followup_module",
                    "title": str(module.get("module_title") or module.get("title") or "").strip(),
                }
            )
            existing_block_ids.add(module_id)

    normalized["service_blocks"] = service_blocks

    return normalized


def _build_hybrid_runtime_model(
    semantic_model: dict[str, Any],
    deterministic_contract: dict[str, Any],
    validation: dict[str, Any],
) -> dict[str, Any]:
    interaction_logic_blocks = [
        dict(item)
        for item in (semantic_model.get("interaction_logic_blocks", []) or [])
        if isinstance(item, dict)
    ]

    service_blocks = [
        dict(item)
        for item in (semantic_model.get("service_blocks", []) or [])
        if isinstance(item, dict)
    ]
    role_profiles = [
        dict(item)
        for item in (semantic_model.get("role_profiles", []) or [])
        if isinstance(item, dict)
    ]

    service_block_registry: dict[str, dict[str, Any]] = {}
    instruction_procedures = [
        dict(item)
        for item in (semantic_model.get("procedures", []) or [])
        if isinstance(item, dict)
    ]

    def _register_service_block_alias(alias: str, block: dict[str, Any]) -> None:
        alias_value = str(alias or "").strip()
        if alias_value:
            service_block_registry[alias_value] = block

    for block in service_blocks:
        block_id = str(block.get("block_id") or "").strip()
        if not block_id:
            continue
        _register_service_block_alias(block_id, block)
        normalized_workflow_id = _normalized_workflow_block_id(block_id)
        normalized_module_id = _normalized_module_block_id(block_id)
        _register_service_block_alias(normalized_workflow_id, block)
        _register_service_block_alias(normalized_module_id, block)
        if ":" in block_id:
            suffix = block_id.split(":", 1)[1]
            block_type = str(block.get("block_type") or "").strip()
            if block_type in {"support_module", "followup_module"}:
                _register_service_block_alias(f"module:{suffix}", block)
            if block_type == "followup_module":
                _register_service_block_alias(f"followup_module:{suffix}", block)
            if block_type == "support_module":
                _register_service_block_alias(f"support_module:{suffix}", block)
            if block_type == "primary_workflow":
                _register_service_block_alias(f"workflow:{suffix}", block)

    interaction_logic_registry = {
        str(item.get("block_id") or "").strip(): item
        for item in interaction_logic_blocks
        if str(item.get("block_id") or "").strip()
    }
    role_profile_registry = {
        str(item.get("role_id") or "").strip(): item
        for item in role_profiles
        if str(item.get("role_id") or "").strip()
    }

    def _resolve_service_block_reference(value: Any) -> tuple[str, str] | None:
        reference = str(value or "").strip()
        if not reference:
            return None
        block = service_block_registry.get(reference)
        if not isinstance(block, dict):
            normalized_workflow_id = _normalized_workflow_block_id(reference)
            normalized_module_id = _normalized_module_block_id(reference)
            block = service_block_registry.get(normalized_workflow_id) or service_block_registry.get(normalized_module_id)
        if not isinstance(block, dict):
            return None
        block_id = str(block.get("block_id") or "").strip()
        block_type = str(block.get("block_type") or "").strip()
        if not block_id or not block_type:
            return None
        return block_type, block_id

    def _resolve_role_target(role_id: str) -> tuple[str, str] | None:
        role = role_profile_registry.get(str(role_id or "").strip())
        if not isinstance(role, dict):
            return None
        for key in ("default_workflow_id", "target_workflow_id"):
            resolved = _resolve_service_block_reference(role.get(key))
            if resolved:
                return resolved
        for workflow_id in role.get("target_workflow_ids", []) or []:
            resolved = _resolve_service_block_reference(workflow_id)
            if resolved:
                return resolved
        for workflow_id in role.get("allowed_workflow_ids", []) or []:
            resolved = _resolve_service_block_reference(workflow_id)
            if resolved:
                return resolved
        for module_id in role.get("allowed_module_ids", []) or []:
            resolved = _resolve_service_block_reference(module_id)
            if resolved:
                return resolved
        return None

    def _resolve_logic_target(logic_block_id: str) -> tuple[str, str] | None:
        logic_block = interaction_logic_registry.get(str(logic_block_id or "").strip())
        if not isinstance(logic_block, dict):
            return None
        subordinate_target = logic_block.get("subordinate_target")
        if isinstance(subordinate_target, dict):
            resolved = _resolve_service_block_reference(
                subordinate_target.get("target_id")
                or subordinate_target.get("target_module_id")
                or subordinate_target.get("target_workflow_id")
            )
            if resolved:
                return resolved
        for key in ("target_module_id", "target_workflow_id", "target_id"):
            resolved = _resolve_service_block_reference(logic_block.get(key))
            if resolved:
                return resolved
        return None

    def _canonicalize_module_list(modules: Any, *, expected_block_type: str) -> list[dict[str, Any]]:
        canonical_modules: list[dict[str, Any]] = []
        seen_module_ids: set[str] = set()
        if not isinstance(modules, list):
            return canonical_modules
        for item in modules:
            if not isinstance(item, dict):
                continue
            module = dict(item)
            raw_module_id = str(module.get("module_id") or module.get("block_id") or "").strip()
            resolved_target = _resolve_service_block_reference(raw_module_id) if raw_module_id else None
            if resolved_target is None:
                fallback_module_id = _canonical_support_module_block_id(
                    raw_module_id,
                    block_type=expected_block_type,
                ) if raw_module_id else ""
                resolved_target = (expected_block_type, fallback_module_id) if fallback_module_id else None
            if resolved_target is not None:
                target_type, target_id = resolved_target
                if target_type == expected_block_type and target_id:
                    module["module_id"] = target_id
            canonical_module_id = str(module.get("module_id") or "").strip()
            if canonical_module_id:
                if canonical_module_id in seen_module_ids:
                    continue
                seen_module_ids.add(canonical_module_id)
            canonical_modules.append(module)
        return canonical_modules

    def _project_modules_from_service_blocks(*, expected_block_type: str) -> list[dict[str, Any]]:
        projected_modules: list[dict[str, Any]] = []
        seen_module_ids: set[str] = set()
        for block in service_blocks:
            if not isinstance(block, dict):
                continue
            block_type = str(block.get("block_type") or "").strip()
            if block_type != expected_block_type:
                continue
            block_id = str(block.get("block_id") or "").strip()
            if not block_id or block_id in seen_module_ids:
                continue
            seen_module_ids.add(block_id)
            projected_modules.append(
                {
                    "module_id": block_id,
                    "module_title": str(block.get("title") or "").strip(),
                }
            )
        return projected_modules

    projected_routing_rules: list[dict[str, Any]] = []
    source_routing_rules = list(semantic_model.get("routing_rules", []) or [])
    if not source_routing_rules:
        for block in interaction_logic_blocks:
            for item in block.get("routing_rules", []) or []:
                if isinstance(item, dict):
                    projected_routing_rules.append(dict(item))
    else:
        projected_routing_rules = [dict(item) for item in source_routing_rules if isinstance(item, dict)]

    routing_rules: list[dict[str, Any]] = []
    for index, rule in enumerate(projected_routing_rules, start=1):
        projected_rule = dict(rule)
        trigger_keywords = [
            str(item or "").strip()
            for item in projected_rule.get("trigger_keywords", []) or []
            if str(item or "").strip()
        ]
        if trigger_keywords:
            projected_rule["trigger_keywords"] = list(dict.fromkeys(trigger_keywords))
        target_logic_block_id = str(
            projected_rule.get("target_logic_block_id")
            or projected_rule.get("target_interaction_logic_id")
            or projected_rule.get("target_logic_id")
            or ""
        ).strip()
        if target_logic_block_id:
            projected_rule["target_logic_block_id"] = target_logic_block_id
            projected_rule["target_interaction_logic_id"] = target_logic_block_id
        projected_rule["priority"] = _route_priority_value(projected_rule.get("priority"), index)

        resolved_target = (
            _resolve_service_block_reference(projected_rule.get("target_id"))
            or _resolve_service_block_reference(projected_rule.get("target_service_block_id"))
            or _resolve_service_block_reference(projected_rule.get("target_module_id"))
            or _resolve_service_block_reference(projected_rule.get("target_workflow_id"))
        )
        if resolved_target is None:
            resolved_target = _resolve_role_target(str(projected_rule.get("target_role_id") or "").strip())
        if resolved_target is None and target_logic_block_id:
            resolved_target = _resolve_logic_target(target_logic_block_id)

        if resolved_target is not None:
            target_type, target_id = resolved_target
            projected_rule["target_type"] = target_type
            projected_rule["target_id"] = target_id
            projected_rule["target_service_block_id"] = target_id
            if target_type == "primary_workflow":
                projected_rule["target_workflow_id"] = target_id
                projected_rule.pop("target_module_id", None)
            elif target_type in {"support_module", "followup_module"}:
                projected_rule["target_module_id"] = target_id
                projected_rule.pop("target_workflow_id", None)

        routing_rules.append(projected_rule)

    procedure_steps = [
        dict(item)
        for item in (semantic_model.get("procedure_steps", []) or [])
        if isinstance(item, dict)
    ]

    deterministic_step_resource_refs: dict[str, list[str]] = {}
    deterministic_steps_by_block: dict[str, list[dict[str, Any]]] = {}
    deterministic_block_direct_resource_refs: dict[str, list[str]] = {}

    deterministic_procedure_to_block_id = {
        str(item.get("procedure_id") or "").strip(): str(item.get("service_block_id") or "").strip()
        for item in (deterministic_contract.get("instruction_procedures", []) or [])
        if isinstance(item, dict)
        and str(item.get("procedure_id") or "").strip()
        and str(item.get("service_block_id") or "").strip()
    }

    def _canonical_block_lookup_key(value: Any) -> str:
        raw_value = str(value or "").strip()
        if not raw_value:
            return ""
        if raw_value.startswith("primary_workflow:"):
            return f"workflow:{raw_value.split(':', 1)[1]}"
        if raw_value.startswith("wf:"):
            return f"workflow:{raw_value.split(':', 1)[1]}"
        resolved = _resolve_service_block_reference(raw_value)
        if resolved is not None:
            target_type, target_id = resolved
            resolved_id = str(target_id or "").strip()
            if target_type == "primary_workflow" and ":" in resolved_id:
                return f"workflow:{resolved_id.split(':', 1)[1]}"
            return resolved_id
        normalized_module_id = _normalized_module_block_id(raw_value)
        if normalized_module_id:
            return normalized_module_id
        normalized_workflow_id = _normalized_workflow_block_id(raw_value)
        if normalized_workflow_id:
            return normalized_workflow_id
        return raw_value

    def _unique_resource_refs(values: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for value in values:
            ref = str(value or "").strip()
            if not ref or ref in seen:
                continue
            seen.add(ref)
            ordered.append(ref)
        return ordered

    def _step_order_sort_key(value: Any) -> int:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        raw_value = str(value if value is not None else "").strip()
        if raw_value.lstrip("-").isdigit():
            return int(raw_value)
        return 10_000

    def _capture_step_resources(step: dict[str, Any]) -> None:
        if not isinstance(step, dict):
            return
        step_id = str(step.get("step_id") or "").strip()
        if not step_id:
            return
        refs = [
            str(ref or "").strip()
            for ref in (
                step.get("resource_refs", [])
                or step.get("bundled_resource_refs", [])
                or ([step.get("resource_ref")] if str(step.get("resource_ref") or "").strip() else [])
            )
            if str(ref or "").strip()
        ]
        if refs:
            deterministic_step_resource_refs[step_id] = refs
        procedure_id = str(step.get("procedure_id") or "").strip()
        block_id = _canonical_block_lookup_key(deterministic_procedure_to_block_id.get(procedure_id))
        if block_id:
            deterministic_steps_by_block.setdefault(block_id, []).append(
                {
                    "step_id": step_id,
                    "order": step.get("order"),
                    "title": str(step.get("title") or "").strip(),
                    "resource_refs": list(refs),
                }
            )

    for step in deterministic_contract.get("procedure_steps", []) or []:
        _capture_step_resources(step)
    for workflow in deterministic_contract.get("instruction_workflows", []) or []:
        if not isinstance(workflow, dict):
            continue
        for step in workflow.get("steps", []) or []:
            _capture_step_resources(step)
    primary_workflow = deterministic_contract.get("primary_workflow")
    if isinstance(primary_workflow, dict):
        for step in primary_workflow.get("steps", []) or []:
            _capture_step_resources(step)

    for block_id, steps_for_block in deterministic_steps_by_block.items():
        deterministic_steps_by_block[block_id] = sorted(
            steps_for_block,
            key=lambda item: (
                _step_order_sort_key(item.get("order")),
                str(item.get("step_id") or "").strip(),
            ),
        )

    deterministic_step_resource_ids_by_block: dict[str, set[str]] = {}
    for block_id, steps_for_block in deterministic_steps_by_block.items():
        refs_for_block: set[str] = set()
        for step in steps_for_block:
            refs_for_block.update(str(ref or "").strip() for ref in step.get("resource_refs", []) or [] if str(ref or "").strip())
        deterministic_step_resource_ids_by_block[block_id] = refs_for_block

    for block in deterministic_contract.get("instruction_service_blocks", []) or []:
        if not isinstance(block, dict):
            continue
        block_id = _canonical_block_lookup_key(block.get("block_id"))
        if not block_id:
            continue
        block_refs = [
            str(ref or "").strip()
            for ref in block.get("resource_refs", []) or []
            if str(ref or "").strip()
        ]
        if not block_refs:
            continue
        owned_by_steps = deterministic_step_resource_ids_by_block.get(block_id, set())
        direct_refs = _unique_resource_refs([ref for ref in block_refs if ref not in owned_by_steps])
        deterministic_block_direct_resource_refs[block_id] = direct_refs

    semantic_procedure_to_block_id = {
        str(item.get("procedure_id") or "").strip(): str(item.get("service_block_id") or "").strip()
        for item in instruction_procedures
        if isinstance(item, dict)
        and str(item.get("procedure_id") or "").strip()
        and str(item.get("service_block_id") or "").strip()
    }
    semantic_step_positions: dict[str, int] = {}
    semantic_steps_by_block: dict[str, list[dict[str, Any]]] = {}
    for step in procedure_steps:
        if not isinstance(step, dict):
            continue
        procedure_id = str(step.get("procedure_id") or "").strip()
        block_id = _canonical_block_lookup_key(
            semantic_procedure_to_block_id.get(procedure_id) or procedure_id
        )
        if not block_id:
            continue
        semantic_steps_by_block.setdefault(block_id, []).append(step)
    for block_id, steps_for_block in semantic_steps_by_block.items():
        sorted_steps = sorted(
            steps_for_block,
            key=lambda item: (
                _step_order_sort_key(item.get("order")),
                str(item.get("step_id") or "").strip(),
            ),
        )
        for index, step in enumerate(sorted_steps):
            step_id = str(step.get("step_id") or "").strip()
            if step_id:
                semantic_step_positions[step_id] = index

    for step in procedure_steps:
        step_id = str(step.get("step_id") or "").strip()
        if not step_id:
            continue
        refs = deterministic_step_resource_refs.get(step_id, [])
        if not refs:
            procedure_id = str(step.get("procedure_id") or "").strip()
            block_id = _canonical_block_lookup_key(
                semantic_procedure_to_block_id.get(procedure_id) or procedure_id
            )
            position = semantic_step_positions.get(step_id)
            if block_id and position is not None:
                deterministic_steps = deterministic_steps_by_block.get(block_id, [])
                if 0 <= position < len(deterministic_steps):
                    refs = list(deterministic_steps[position].get("resource_refs", []) or [])
        if refs and not any(str(ref or "").strip() for ref in step.get("resource_refs", []) or []):
            step["resource_refs"] = list(refs)
        if (
            str(step.get("execution_mode") or "").strip() == "bundled"
            and refs
            and not any(str(ref or "").strip() for ref in step.get("resource_refs", []) or [])
            and not any(str(ref or "").strip() for ref in step.get("bundled_resource_refs", []) or [])
        ):
            step["bundled_resource_refs"] = list(refs)

    for block in service_blocks:
        if not isinstance(block, dict):
            continue
        block_id = _canonical_block_lookup_key(block.get("block_id"))
        if not block_id:
            continue
        if any(str(ref or "").strip() for ref in block.get("resource_refs", []) or []):
            continue
        direct_refs = deterministic_block_direct_resource_refs.get(block_id, [])
        if direct_refs:
            block["resource_refs"] = list(direct_refs)

    existing_procedure_ids = {
        str(item.get("procedure_id") or "").strip()
        for item in instruction_procedures
        if isinstance(item, dict) and str(item.get("procedure_id") or "").strip()
    }
    existing_step_ids = {
        str(item.get("step_id") or "").strip()
        for item in procedure_steps
        if isinstance(item, dict) and str(item.get("step_id") or "").strip()
    }
    procedures_by_block_id = {
        str(item.get("service_block_id") or "").strip(): item
        for item in instruction_procedures
        if isinstance(item, dict) and str(item.get("service_block_id") or "").strip()
    }
    for block in service_blocks:
        if not isinstance(block, dict):
            continue
        block_id = str(block.get("block_id") or "").strip()
        block_type = str(block.get("block_type") or "").strip()
        if block_type != "followup_module" or not block_id or block_id in procedures_by_block_id:
            continue
        procedure_id = _canonical_procedure_id_for_block_id(block_id)
        if procedure_id not in existing_procedure_ids:
            instruction_procedures.append(
                {
                    "procedure_id": procedure_id,
                    "service_block_id": block_id,
                    "title": str(block.get("title") or "").strip() or block_id,
                }
            )
            existing_procedure_ids.add(procedure_id)
        direct_refs = [
            str(ref or "").strip()
            for ref in block.get("resource_refs", []) or []
            if str(ref or "").strip()
        ]
        if not direct_refs:
            continue
        step_id = f"step:{_semantic_slug(block_id) or block_id}:1"
        if step_id in existing_step_ids:
            continue
        procedure_steps.append(
            {
                "procedure_id": procedure_id,
                "step_id": step_id,
                "title": str(block.get("title") or "").strip() or block_id,
                "order": 1,
                "execution_mode": "interactive",
                "resource_refs": list(direct_refs),
                "bundled_step_ids": [],
            }
        )
        existing_step_ids.add(step_id)

    support_modules = _canonicalize_module_list(
        semantic_model.get("support_modules", []),
        expected_block_type="support_module",
    )
    followup_modules = _canonicalize_module_list(
        semantic_model.get("followup_modules", []),
        expected_block_type="followup_module",
    )
    if not support_modules:
        support_modules = _project_modules_from_service_blocks(expected_block_type="support_module")
    if not followup_modules:
        followup_modules = _project_modules_from_service_blocks(expected_block_type="followup_module")

    return {
        "primary_service_mode": str(semantic_model.get("primary_service_mode") or "").strip() or None,
        "default_workflow_id": str(semantic_model.get("default_workflow_id") or "").strip() or None,
        "global_app_contract": dict(semantic_model.get("global_app_contract") or {}),
        "interaction_logic_blocks": interaction_logic_blocks,
        "role_profiles": role_profiles,
        "routing_rules": routing_rules,
        "module_orchestration": semantic_model.get("module_orchestration"),
        "support_modules": support_modules,
        "followup_modules": followup_modules,
        "instruction_service_blocks": service_blocks,
        "instruction_procedures": instruction_procedures,
        "procedure_steps": procedure_steps,
        "clarification_gate_rules": list(semantic_model.get("clarification_gate_rules", []) or []),
        "resource_bindings": list(semantic_model.get("resource_bindings", []) or []),
        "semantic_warnings": list(semantic_model.get("semantic_warnings", []) or []),
        "semantic_confidence": semantic_model.get("semantic_confidence"),
        "validation": validation,
        "deterministic_contract_summary": {
            "service_block_count": len(deterministic_contract.get("instruction_service_blocks", []) or []),
            "procedure_count": len(deterministic_contract.get("instruction_procedures", []) or []),
            "step_count": len(deterministic_contract.get("procedure_steps", []) or []),
        },
    }


def _project_compatibility_instruction_runtime_model(
    runtime_model: dict[str, Any],
    hybrid_runtime_model: dict[str, Any],
) -> dict[str, Any]:
    compatibility_model = dict(runtime_model or {})

    def _canonical_module_identity(module: dict[str, Any], *, default_prefix: str) -> str:
        if not isinstance(module, dict):
            return ""
        raw_module_id = str(module.get("module_id") or module.get("block_id") or "").strip()
        if not raw_module_id:
            return ""
        if default_prefix == "followup_module":
            if raw_module_id.startswith("support_module:"):
                suffix = raw_module_id.split(":", 1)[1]
                return f"followup_module:{suffix}"
            if raw_module_id.startswith("module:"):
                suffix = raw_module_id.split(":", 1)[1]
                return f"followup_module:{suffix}"
            if raw_module_id.startswith("followup_module:"):
                return raw_module_id
            return f"followup_module:{raw_module_id}"
        if raw_module_id.startswith("followup_module:"):
            suffix = raw_module_id.split(":", 1)[1]
            return f"support_module:{suffix}"
        normalized_module_id = _normalized_module_block_id(raw_module_id)
        if normalized_module_id.startswith("module:"):
            suffix = normalized_module_id.split(":", 1)[1]
            return f"support_module:{suffix}"
        if normalized_module_id.startswith("support_module:"):
            return normalized_module_id
        return f"support_module:{raw_module_id}"

    def _merge_module_lists(existing: Any, projected: Any, *, default_prefix: str) -> list[dict[str, Any]]:
        merged_by_identity: dict[str, dict[str, Any]] = {}
        passthrough: list[dict[str, Any]] = []
        for source_index, source in enumerate((existing or [], projected or [])):
            if not isinstance(source, list):
                continue
            for item in source:
                if not isinstance(item, dict):
                    continue
                module = dict(item)
                module_identity = _canonical_module_identity(module, default_prefix=default_prefix)
                if not module_identity:
                    passthrough.append(module)
                    continue
                existing_module = merged_by_identity.get(module_identity)
                if existing_module is None:
                    canonical_module = dict(module)
                    canonical_module["module_id"] = module_identity
                    merged_by_identity[module_identity] = canonical_module
                    continue
                merged_module = dict(existing_module)
                if source_index == 0:
                    for key, value in module.items():
                        if key not in merged_module or merged_module.get(key) in (None, "", [], {}):
                            merged_module[key] = value
                else:
                    for key, value in module.items():
                        if key == "module_id":
                            continue
                        if value not in (None, "", [], {}):
                            merged_module[key] = value
                merged_module["module_id"] = module_identity
                merged_by_identity[module_identity] = merged_module
        return passthrough + list(merged_by_identity.values())

    for key in (
        "primary_service_mode",
        "default_workflow_id",
        "global_app_contract",
        "module_orchestration",
        "resource_bindings",
        "semantic_warnings",
        "semantic_confidence",
        "validation",
        "deterministic_contract_summary",
    ):
        if key in hybrid_runtime_model:
            compatibility_model[key] = hybrid_runtime_model.get(key)

    compatibility_model["routing_rules"] = [
        dict(item)
        for item in (hybrid_runtime_model.get("routing_rules", []) or [])
        if isinstance(item, dict)
    ]
    compatibility_model["interaction_logic_blocks"] = [
        dict(item)
        for item in (hybrid_runtime_model.get("interaction_logic_blocks", []) or [])
        if isinstance(item, dict)
    ]
    compatibility_model["role_profiles"] = [
        dict(item)
        for item in (hybrid_runtime_model.get("role_profiles", []) or [])
        if isinstance(item, dict)
    ]
    compatibility_model["instruction_service_blocks"] = [
        dict(item)
        for item in (hybrid_runtime_model.get("instruction_service_blocks", []) or [])
        if isinstance(item, dict)
    ]
    compatibility_model["instruction_procedures"] = [
        dict(item)
        for item in (hybrid_runtime_model.get("instruction_procedures", []) or [])
        if isinstance(item, dict)
    ]
    compatibility_model["procedure_steps"] = [
        dict(item)
        for item in (hybrid_runtime_model.get("procedure_steps", []) or [])
        if isinstance(item, dict)
    ]
    compatibility_model["support_modules"] = [
        dict(item) for item in _merge_module_lists(
            compatibility_model.get("support_modules", []),
            hybrid_runtime_model.get("support_modules", []),
            default_prefix="support_module",
        )
    ]
    compatibility_model["followup_modules"] = [
        dict(item) for item in _merge_module_lists(
            compatibility_model.get("followup_modules", []),
            hybrid_runtime_model.get("followup_modules", []),
            default_prefix="followup_module",
        )
    ]
    return compatibility_model


def _validate_semantic_compile_candidate(
    *,
    semantic_model: dict[str, Any],
    deterministic_contract: dict[str, Any],
) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    parser_warnings = [
        str(item).strip()
        for item in (deterministic_contract.get("parser_warnings", []) if isinstance(deterministic_contract, dict) else [])
        if str(item).strip()
    ]
    if not isinstance(semantic_model, dict):
        return {"valid": False, "errors": ["semantic model must be an object"], "warnings": [], "normalized": {}}
    for warning in parser_warnings:
        if warning.startswith("ambiguous section title contains both module and workflow markers:"):
            errors.append(warning)
    semantic_model = _canonicalize_provider_semantic_model(semantic_model)
    semantic_model = _ground_semantic_model_from_deterministic_contract(
        semantic_model,
        deterministic_contract,
    )

    primary_service_mode = str(semantic_model.get("primary_service_mode") or "").strip()
    if not primary_service_mode:
        errors.append("primary_service_mode is required")
    valid_primary_service_modes = {
        "single_default_workflow",
        "intent_routed_multi_workflow",
        "intent_routed_interaction_logic",
    }
    if primary_service_mode and primary_service_mode not in valid_primary_service_modes:
        errors.append(f"unknown primary_service_mode: {primary_service_mode}")

    blocks = semantic_model.get("service_blocks", [])
    procedures = semantic_model.get("procedures", [])
    steps = semantic_model.get("procedure_steps", [])
    role_profiles = semantic_model.get("role_profiles", [])
    routing_rules = semantic_model.get("routing_rules", [])
    clarification_gate_rules = semantic_model.get("clarification_gate_rules", [])
    module_orchestration = semantic_model.get("module_orchestration")

    if not isinstance(blocks, list):
        errors.append("service_blocks must be a list")
        blocks = []
    if not isinstance(procedures, list):
        errors.append("procedures must be a list")
        procedures = []
    if not isinstance(steps, list):
        errors.append("procedure_steps must be a list")
        steps = []
    if not isinstance(role_profiles, list):
        errors.append("role_profiles must be a list")
        role_profiles = []
    if not isinstance(routing_rules, list):
        errors.append("routing_rules must be a list")
        routing_rules = []
    if not isinstance(clarification_gate_rules, list):
        errors.append("clarification_gate_rules must be a list")
        clarification_gate_rules = []

    block_ids = {str(item.get("block_id") or "").strip() for item in blocks if isinstance(item, dict)}
    block_ids.discard("")
    primary_workflow_block_ids = {
        str(item.get("block_id") or "").strip()
        for item in blocks
        if isinstance(item, dict) and str(item.get("block_type") or "").strip() == "primary_workflow"
    }
    primary_workflow_block_ids.discard("")
    procedure_ids = {str(item.get("procedure_id") or "").strip() for item in procedures if isinstance(item, dict)}
    procedure_ids.discard("")
    step_ids = {str(item.get("step_id") or "").strip() for item in steps if isinstance(item, dict)}
    step_ids.discard("")
    role_ids = {str(item.get("role_id") or "").strip() for item in role_profiles if isinstance(item, dict)}
    role_ids.discard("")
    module_ids = {
        str(item.get("block_id") or "").strip()
        for item in blocks
        if isinstance(item, dict) and str(item.get("block_type") or "").strip() in {"support_module", "followup_module"}
    }
    module_ids.discard("")
    executable_procedure_ids = {
        str(item.get("procedure_id") or "").strip()
        for item in steps
        if isinstance(item, dict) and str(item.get("procedure_id") or "").strip()
    }
    executable_block_ids = {
        str(item.get("service_block_id") or "").strip()
        for item in procedures
        if isinstance(item, dict)
        and str(item.get("procedure_id") or "").strip() in executable_procedure_ids
        and str(item.get("service_block_id") or "").strip()
    }
    executable_block_ids.discard("")
    executable_workflow_block_ids = {
        block_id
        for block_id in executable_block_ids
        if block_id in primary_workflow_block_ids
    }

    default_workflow_id = str(semantic_model.get("default_workflow_id") or "").strip() or None
    default_blocks = [
        item
        for item in blocks
        if isinstance(item, dict)
        and str(item.get("block_type") or "").strip() == "primary_workflow"
        and bool(item.get("is_default"))
    ]
    if primary_service_mode == "single_default_workflow":
        if len(default_blocks) != 1:
            errors.append("single_default_workflow requires exactly one default primary_workflow block")
        if not default_workflow_id:
            errors.append("single_default_workflow requires default_workflow_id")
        alternate_workflow_targets = {
            str(item.get("target_workflow_id") or "").strip()
            for item in routing_rules
            if isinstance(item, dict) and str(item.get("target_workflow_id") or "").strip()
        }
        if default_workflow_id:
            alternate_workflow_targets.discard(default_workflow_id)
        if alternate_workflow_targets:
            errors.append("single_default_workflow must not define routing_rules for alternate workflows")
    elif primary_service_mode == "intent_routed_multi_workflow" and default_workflow_id:
        errors.append("intent_routed_multi_workflow must not define default_workflow_id")
    elif primary_service_mode == "intent_routed_multi_workflow":
        if not primary_workflow_block_ids:
            errors.append("intent_routed_multi_workflow requires at least one primary_workflow block")
        if not routing_rules:
            errors.append("intent_routed_multi_workflow requires routing_rules")
    elif primary_service_mode == "intent_routed_interaction_logic":
        interaction_logic_items = [
            item
            for item in semantic_model.get("interaction_logic_blocks", []) or []
            if isinstance(item, dict)
        ]
        if not routing_rules and not interaction_logic_items:
            errors.append(
                "intent_routed_interaction_logic requires routing_rules or interaction_logic_blocks"
            )

    known_resources = {
        str(item.get("filename") or "").strip()
        for item in deterministic_contract.get("resource_reference_catalog", []) or []
        if isinstance(item, dict) and str(item.get("filename") or "").strip()
    }

    missing_intent_routed_procedure_steps = False
    for item in procedures:
        if not isinstance(item, dict):
            continue
        procedure_id = str(item.get("procedure_id") or "").strip()
        service_block_id = str(item.get("service_block_id") or "").strip()
        if service_block_id and service_block_id not in block_ids:
            errors.append(f"unknown service_block_id referenced by procedure: {service_block_id}")
            if primary_service_mode == "intent_routed_multi_workflow" and not service_block_id.startswith("module:"):
                missing_intent_routed_procedure_steps = True
        if procedure_id and not any(
            isinstance(step, dict) and str(step.get("procedure_id") or "").strip() == procedure_id
            for step in steps
        ):
            warnings.append(f"procedure has no executable steps: {procedure_id}")
            if primary_service_mode == "intent_routed_multi_workflow" and not service_block_id.startswith("module:"):
                missing_intent_routed_procedure_steps = True

    for item in steps:
        if not isinstance(item, dict):
            continue
        procedure_id = str(item.get("procedure_id") or "").strip()
        if procedure_id and procedure_id not in procedure_ids:
            errors.append(f"unknown procedure_id referenced by step: {procedure_id}")
        execution_mode = str(item.get("execution_mode") or "").strip() or "interactive"
        bundled_step_ids = [str(value).strip() for value in item.get("bundled_step_ids", []) or [] if str(value).strip()]
        step_id = str(item.get("step_id") or "").strip()
        step_title = str(item.get("title") or "").strip()
        direct_refs = [str(ref or "").strip() for ref in item.get("resource_refs", []) or [] if str(ref or "").strip()]
        bundled_refs = [
            str(ref or "").strip() for ref in item.get("bundled_resource_refs", []) or [] if str(ref or "").strip()
        ]
        if execution_mode == "bundled" and step_id and step_id not in bundled_step_ids:
            errors.append(f"bundled step must include itself in bundled_step_ids: {step_id}")
        if not step_title and not direct_refs and not bundled_refs:
            warnings.append(f"step has empty execution semantics: {step_id or '<unknown-step>'}")
        for filename in direct_refs:
            if filename and known_resources and filename not in known_resources:
                warnings.append(f"unresolved step resource ref: {filename}")
        for filename in bundled_refs:
            if filename and known_resources and filename not in known_resources:
                warnings.append(f"unresolved bundled resource ref: {filename}")

    for item in role_profiles:
        if not isinstance(item, dict):
            continue
        default_role_workflow_id = str(item.get("default_workflow_id") or item.get("target_workflow_id") or "").strip()
        if default_role_workflow_id and default_role_workflow_id not in primary_workflow_block_ids:
            errors.append(f"role references unknown workflow id: {default_role_workflow_id}")
        for workflow_id in item.get("target_workflow_ids", []) or []:
            workflow_id_str = str(workflow_id or "").strip()
            if workflow_id_str and workflow_id_str not in primary_workflow_block_ids:
                errors.append(f"role references unknown workflow id: {workflow_id_str}")
        for module_id in item.get("allowed_module_ids", []) or []:
            module_id_str = str(module_id).strip()
            if module_id_str and module_id_str not in module_ids:
                warnings.append(f"role references unknown module id: {module_id_str}")

    role_profile_map = {
        str(item.get("role_id") or "").strip(): item
        for item in role_profiles
        if isinstance(item, dict) and str(item.get("role_id") or "").strip()
    }
    block_map = {
        str(item.get("block_id") or "").strip(): item
        for item in blocks
        if isinstance(item, dict) and str(item.get("block_id") or "").strip()
    }
    procedure_map_by_block_id = {
        str(item.get("service_block_id") or "").strip(): item
        for item in procedures
        if isinstance(item, dict) and str(item.get("service_block_id") or "").strip()
    }
    interaction_logic_blocks = [
        item for item in semantic_model.get("interaction_logic_blocks", []) or [] if isinstance(item, dict)
    ]
    deterministic_service_blocks = [
        item for item in deterministic_contract.get("instruction_service_blocks", []) or [] if isinstance(item, dict)
    ]

    def _workflow_has_conversational_contract(workflow_id: str) -> bool:
        workflow = block_map.get(workflow_id)
        if not isinstance(workflow, dict):
            return False
        if workflow_id in procedure_map_by_block_id:
            return False
        workflow_family = _semantic_family(workflow_id, workflow.get("title"), workflow.get("body_text"))
        if workflow_family in {"bible_study", "orchestration"}:
            return False

        workflow_tokens = (
            _semantic_tokens(workflow_id, workflow.get("title"), workflow.get("body_text"))
            | _semantic_alias_tokens(workflow_id, workflow.get("title"), workflow.get("body_text"))
        )
        if not workflow_tokens:
            return False

        for item in interaction_logic_blocks:
            item_tokens = (
                _semantic_tokens(item.get("block_id"), item.get("title"), item.get("body_text"))
                | _semantic_alias_tokens(item.get("block_id"), item.get("title"), item.get("body_text"))
            )
            entry_contract = dict(item.get("entry_response_contract") or {})
            if workflow_tokens & item_tokens and (
                entry_contract or str(item.get("body_text") or "").strip() or item.get("interaction_rules")
            ):
                return True

        for item in deterministic_service_blocks:
            item_tokens = (
                _semantic_tokens(item.get("block_id"), item.get("title"), item.get("body_text"))
                | _semantic_alias_tokens(item.get("block_id"), item.get("title"), item.get("body_text"))
            )
            if workflow_tokens & item_tokens and str(item.get("body_text") or "").strip():
                return True

        return False

    def _role_has_executable_target(role_id: str) -> bool:
        role = role_profile_map.get(role_id)
        if not isinstance(role, dict):
            return False
        workflow_targets = [
            str(role.get("default_workflow_id") or role.get("target_workflow_id") or "").strip()
        ]
        workflow_targets.extend(
            str(value or "").strip()
            for value in role.get("target_workflow_ids", []) or []
            if str(value or "").strip()
        )
        if any(target in executable_block_ids for target in workflow_targets if target):
            return True
        module_targets = [
            str(value or "").strip()
            for value in role.get("allowed_module_ids", []) or []
            if str(value or "").strip()
        ]
        return any(target in module_ids for target in module_targets)

    has_executable_route_target = False
    has_executable_module_route_target = False
    has_conversational_route_target = False
    has_workflow_contract_reference = bool(procedures)
    for item in routing_rules:
        if not isinstance(item, dict):
            continue
        target_workflow_id = str(item.get("target_workflow_id") or "").strip()
        if target_workflow_id:
            has_workflow_contract_reference = True
        if target_workflow_id and target_workflow_id not in primary_workflow_block_ids:
            errors.append(f"routing rule references unknown workflow id: {target_workflow_id}")
        if target_workflow_id and target_workflow_id in executable_block_ids:
            has_executable_route_target = True
        elif target_workflow_id and _workflow_has_conversational_contract(target_workflow_id):
            has_conversational_route_target = True
        target_role_id = str(item.get("target_role_id") or "").strip()
        if target_role_id and target_role_id not in role_ids:
            errors.append(f"routing rule references unknown role id: {target_role_id}")
        if target_role_id and _role_has_executable_target(target_role_id):
            has_executable_route_target = True
        target_module_id = str(item.get("target_module_id") or "").strip()
        if target_module_id and target_module_id not in module_ids:
            errors.append(f"routing rule references unknown module id: {target_module_id}")
        if target_module_id and target_module_id in module_ids:
            has_executable_route_target = True
            has_executable_module_route_target = True
        for module_id in item.get("target_module_ids", []) or []:
            module_id_str = str(module_id or "").strip()
            if module_id_str and module_id_str not in module_ids:
                errors.append(f"routing rule references unknown module id: {module_id_str}")
            if module_id_str and module_id_str in module_ids:
                has_executable_route_target = True
                has_executable_module_route_target = True

    if isinstance(module_orchestration, dict):
        composition_mode = str(module_orchestration.get("composition_mode") or "").strip()
        if composition_mode not in {"", "ordered_sequential"}:
            errors.append("module_orchestration only supports ordered_sequential composition_mode")
        for mapping in module_orchestration.get("task_module_mappings", []) or []:
            if not isinstance(mapping, dict):
                continue
            target_module_id = str(mapping.get("target_module_id") or "").strip()
            target_module_ids = [
                str(module_id or "").strip()
                for module_id in mapping.get("target_module_ids", []) or []
                if str(module_id or "").strip()
            ]
            if not target_module_id and not target_module_ids:
                errors.append("module orchestration mapping requires target_module_id or target_module_ids")
            if target_module_id and target_module_id not in module_ids:
                errors.append(f"module orchestration references unknown module id: {target_module_id}")
            for module_id in target_module_ids:
                if module_id not in module_ids:
                    errors.append(f"module orchestration references unknown module id: {module_id}")
                else:
                    has_executable_route_target = True
                    has_executable_module_route_target = True

    if primary_service_mode == "intent_routed_multi_workflow":
        if not has_executable_route_target and not has_conversational_route_target:
            errors.append(
                "intent_routed_multi_workflow routing rules must resolve to executable workflow or module targets"
            )
        if (
            (has_workflow_contract_reference or not has_executable_module_route_target)
            and not executable_block_ids
            and not has_conversational_route_target
        ):
            errors.append("intent_routed_multi_workflow requires executable procedure_steps")
        elif missing_intent_routed_procedure_steps and not has_conversational_route_target:
            errors.append("intent_routed_multi_workflow requires executable procedure_steps")
    elif primary_service_mode == "intent_routed_interaction_logic":
        if routing_rules and not has_executable_route_target and not has_conversational_route_target:
            unresolved_non_role_targets = False
            for item in routing_rules:
                if not isinstance(item, dict):
                    continue
                if str(item.get("target_workflow_id") or "").strip() or str(item.get("target_module_id") or "").strip():
                    unresolved_non_role_targets = True
                    break
                for key in ("target_workflow_ids", "target_module_ids"):
                    values = [
                        str(value or "").strip()
                        for value in item.get(key, []) or []
                        if str(value or "").strip()
                    ]
                    if values:
                        unresolved_non_role_targets = True
                        break
                if unresolved_non_role_targets:
                    break
            if unresolved_non_role_targets:
                errors.append(
                    "intent_routed_interaction_logic routing rules must resolve to known workflow, module, or role targets"
                )

    for item in clarification_gate_rules:
        if not isinstance(item, dict):
            continue
        procedure_id = str(item.get("procedure_id") or "").strip()
        clarification_step_id = str(item.get("clarification_step_id") or "").strip()
        completion_step_id = str(item.get("completion_step_id") or "").strip()
        if procedure_id and procedure_id not in procedure_ids:
            errors.append(f"clarification gate references unknown procedure id: {procedure_id}")
        if clarification_step_id and clarification_step_id not in step_ids:
            errors.append(f"clarification gate references unknown clarification step: {clarification_step_id}")
        if completion_step_id and completion_step_id not in step_ids:
            errors.append(f"clarification gate references unknown completion step: {completion_step_id}")

    normalized = {
        "primary_service_mode": primary_service_mode or None,
        "default_workflow_id": default_workflow_id,
        "global_app_contract": dict(semantic_model.get("global_app_contract") or {}),
        "interaction_logic_blocks": list(semantic_model.get("interaction_logic_blocks", []) or []),
        "role_profiles": list(role_profiles),
        "routing_rules": list(routing_rules),
        "module_orchestration": module_orchestration if isinstance(module_orchestration, dict) else None,
        "service_blocks": list(blocks),
        "procedures": list(procedures),
        "procedure_steps": list(steps),
        "clarification_gate_rules": list(clarification_gate_rules),
        "resource_bindings": list(semantic_model.get("resource_bindings", []) or []),
        "semantic_warnings": list(semantic_model.get("semantic_warnings", []) or []),
        "semantic_confidence": semantic_model.get("semantic_confidence"),
        "support_modules": list(semantic_model.get("support_modules", []) or []),
        "followup_modules": list(semantic_model.get("followup_modules", []) or []),
    }
    return {"valid": not errors, "errors": errors, "warnings": warnings, "normalized": normalized}


def _normalize_review_result(review_result: Any) -> dict[str, Any]:
    if not isinstance(review_result, dict):
        return {
            "review_status": "review_failed",
            "review_confidence": 0.0,
            "review_findings": {"error": "reviewer returned non-dict payload"},
            "review_summary_md": "",
            "review_recommendations": {},
        }
    review_status = str(review_result.get("review_status") or "").strip()
    if review_status not in {"reviewed_ok", "reviewed_with_warnings", "review_failed"}:
        review_status = "review_failed"
    review_confidence = review_result.get("review_confidence")
    try:
        review_confidence = float(review_confidence) if review_confidence is not None else None
    except (TypeError, ValueError):
        review_confidence = 0.0 if review_status == "review_failed" else None
    review_findings = review_result.get("review_findings")
    if not isinstance(review_findings, dict):
        review_findings = {}
    review_recommendations = review_result.get("review_recommendations")
    if not isinstance(review_recommendations, dict):
        review_recommendations = {}
    review_summary_md = str(review_result.get("review_summary_md") or "")
    if review_status == "review_failed" and not review_findings:
        review_findings = {"error": "reviewer returned malformed payload"}
    return {
        "review_status": review_status,
        "review_confidence": review_confidence,
        "review_findings": review_findings,
        "review_summary_md": review_summary_md,
        "review_recommendations": review_recommendations,
    }


def _review_matches_compiled_record(review: dict[str, Any] | None, compiled_record: dict[str, Any] | None) -> bool:
    if not isinstance(review, dict) or not isinstance(compiled_record, dict):
        return False
    findings = dict(review.get("review_findings") or {})
    compiled_state = dict(findings.get("__compiled_state") or {})
    if compiled_state:
        if str(compiled_state.get("instruction_source_hash") or "") != str(
            compiled_record.get("instruction_source_hash") or ""
        ):
            return False
        if str(compiled_state.get("parser_contract_version") or "") != str(
            compiled_record.get("parser_contract_version") or ""
        ):
            return False
        if str(compiled_state.get("binding_logic_version") or "") != str(
            compiled_record.get("binding_logic_version") or ""
        ):
            return False
        if str(compiled_state.get("resource_catalog_hash") or "") != str(
            compiled_record.get("resource_catalog_hash") or ""
        ):
            return False
        return True
    return str(review.get("instruction_source_hash") or "") == str(compiled_record.get("instruction_source_hash") or "")


def _select_current_review(
    *,
    repo: InstructionUnderstandingRepo,
    app_id: str,
    compiled_record: dict[str, Any] | None,
) -> dict[str, Any] | None:
    review = repo.get_active_review(app_id)
    if _review_matches_compiled_record(review, compiled_record):
        return review
    return None


def compile_instruction_understanding(
    *,
    app_id: str,
    instruction_text: str,
    instruction_uri: str | None,
    instruction_source_version: int | None,
    documents: list[dict[str, Any]],
    repo: InstructionUnderstandingRepo,
    snapshot_root: Path,
    parser_contract_version: str = PARSER_CONTRACT_VERSION,
    binding_logic_version: str = BINDING_LOGIC_VERSION,
    semantic_compiler: Optional[Callable[[dict[str, Any]], dict[str, Any]]] = None,
    semantic_compiler_version: str = SEMANTIC_COMPILER_VERSION,
) -> dict[str, Any]:
    started = time.perf_counter()
    instruction_source_hash = compute_instruction_source_hash(instruction_text)
    resource_catalog_hash = compute_resource_catalog_hash(documents)
    active_record = repo.get_active_compiled(app_id)
    compiled_contract = _compile_contract(instruction_text, documents)
    semantic_compile = None
    semantic_compile_validation = None
    if semantic_compiler is not None:
        semantic_compile_context = _semantic_compile_context(
            app_id=app_id,
            deterministic_contract=compiled_contract,
        )
        try:
            semantic_compile_raw_result = semantic_compiler(semantic_compile_context)
            semantic_compile_result = _normalize_semantic_compile_result(semantic_compile_raw_result)
            semantic_compile_validation = _validate_semantic_compile_candidate(
                semantic_model=semantic_compile_result.get("app_semantic_model", {}),
                deterministic_contract=compiled_contract,
            )
            semantic_compile = {
                "compiler_prompt_version": SEMANTIC_COMPILE_PROMPT_VERSION,
                "semantic_compiler_version": semantic_compiler_version,
                "raw_result": semantic_compile_result.get("raw_result"),
                "app_semantic_model": semantic_compile_result.get("app_semantic_model", {}),
                "errors": list(semantic_compile_result.get("errors", []) or []),
                "empty_result": bool(semantic_compile_result.get("empty_result")),
                "validation": semantic_compile_validation,
            }
            if semantic_compile_validation.get("valid"):
                hybrid_runtime_model = _build_hybrid_runtime_model(
                    dict(semantic_compile_validation.get("normalized") or {}),
                    compiled_contract,
                    semantic_compile_validation,
                )
                compiled_contract["hybrid_instruction_runtime_model"] = hybrid_runtime_model
                compiled_contract["instruction_runtime_model"] = _project_compatibility_instruction_runtime_model(
                    dict(compiled_contract.get("instruction_runtime_model") or {}),
                    hybrid_runtime_model,
                )
                compiled_contract["instruction_service_blocks"] = list(
                    compiled_contract["instruction_runtime_model"].get("instruction_service_blocks", []) or []
                )
                compiled_contract["instruction_procedures"] = list(
                    compiled_contract["instruction_runtime_model"].get("instruction_procedures", []) or []
                )
                compiled_contract["procedure_steps"] = list(
                    compiled_contract["instruction_runtime_model"].get("procedure_steps", []) or []
                )
                compiled_contract["support_modules_v2"] = list(
                    compiled_contract["instruction_runtime_model"].get("support_modules", []) or []
                )
                compiled_contract["followup_modules"] = list(
                    compiled_contract["instruction_runtime_model"].get("followup_modules", []) or []
                )
        except Exception as exc:
            error_message = f"semantic compiler call failed: {exc}"
            semantic_compile = _failed_semantic_compile_payload(
                semantic_compiler_version=semantic_compiler_version,
                error_message=error_message,
            )
            semantic_compile_validation = dict(semantic_compile.get("validation") or {})
        compiled_contract["semantic_compile"] = semantic_compile
    publish_active = _should_publish_compiled_record(
        active_record=active_record,
        semantic_compile_attached=semantic_compile is not None,
        semantic_compile_validation=semantic_compile_validation,
    )
    compile_duration_ms = int((time.perf_counter() - started) * 1000)
    record = repo.save_compiled(
        app_id=app_id,
        instruction_source_hash=instruction_source_hash,
        instruction_source_version=instruction_source_version,
        instruction_uri=instruction_uri,
        parser_contract_version=parser_contract_version,
        binding_logic_version=binding_logic_version,
        resource_catalog_hash=resource_catalog_hash,
        compiled_status="ready",
        compile_duration_ms=compile_duration_ms,
        compile_errors=[],
        compiled_contract=compiled_contract,
        metadata={
            "service_block_count": len(compiled_contract.get("instruction_service_blocks", []) or []),
            "procedure_count": len(compiled_contract.get("instruction_procedures", []) or []),
            "semantic_compile_attached": bool(semantic_compile is not None),
            "semantic_compile_valid": bool(semantic_compile_validation and semantic_compile_validation.get("valid")),
            "semantic_compile_empty": bool(semantic_compile and semantic_compile.get("empty_result")),
            "publish_status": "active" if publish_active else "diagnostic_only",
            "preserved_active_record_id": (
                str(active_record.get("id") or "")
                if not publish_active and isinstance(active_record, dict)
                else None
            ),
        },
        is_active=publish_active,
    )
    snapshot_meta = _write_snapshots(app_id=app_id, compiled_record=record, snapshot_root=snapshot_root)
    if isinstance(snapshot_meta, dict):
        record.setdefault("metadata", {}).update(snapshot_meta)
    return record


def build_instruction_understanding_reviewer(state: Dict[str, Any]) -> Optional[Callable[[dict[str, Any]], dict[str, Any]]]:
    llm_review = maybe_build_task_callable(state, "instruction_understanding_review")
    if llm_review is None:
        llm_review = maybe_build_task_callable(state, "planner")
    if llm_review is None:
        return None

    def _reviewer(compiled_record: dict[str, Any]) -> dict[str, Any]:
        context = {
            "app_id": compiled_record.get("app_id"),
            "instruction_source_hash": compiled_record.get("instruction_source_hash"),
            "parser_contract_version": compiled_record.get("parser_contract_version"),
            "binding_logic_version": compiled_record.get("binding_logic_version"),
            "compiled_contract": compiled_record.get("compiled_contract", {}),
            "metadata": compiled_record.get("metadata", {}),
        }
        result = llm_review(
            INSTRUCTION_UNDERSTANDING_REVIEW_PROMPT,
            [INSTRUCTION_UNDERSTANDING_REVIEW_TOOL],
            context,
        )
        return result if isinstance(result, dict) else {}

    return _reviewer


def build_instruction_understanding_compiler(state: Dict[str, Any]) -> Optional[Callable[[dict[str, Any]], dict[str, Any]]]:
    llm_compile = maybe_build_task_callable(state, "instruction_understanding_compile")
    if llm_compile is None:
        return None

    def _compiler(context: dict[str, Any]) -> dict[str, Any]:
        result = llm_compile(
            INSTRUCTION_UNDERSTANDING_COMPILE_PROMPT,
            [INSTRUCTION_UNDERSTANDING_COMPILE_TOOL],
            context,
        )
        return result if isinstance(result, dict) else {}

    return _compiler


def build_instruction_understanding_reviser(state: Dict[str, Any]) -> Optional[Callable[[dict[str, Any]], dict[str, Any]]]:
    llm_reviser = maybe_build_task_callable(state, "instruction_understanding_revision")
    if llm_reviser is None:
        return None

    def _reviser(context: dict[str, Any]) -> dict[str, Any]:
        result = llm_reviser(
            INSTRUCTION_UNDERSTANDING_REVISION_PROMPT,
            [INSTRUCTION_UNDERSTANDING_REVISION_TOOL],
            context,
        )
        return result if isinstance(result, dict) else {}

    return _reviser


def prepare_instruction_understanding(
    *,
    app_id: str,
    instructions: Dict[str, Any],
    documents: list[dict[str, Any]],
    repo: InstructionUnderstandingRepo,
    snapshot_root: Path,
    parser_contract_version: str = PARSER_CONTRACT_VERSION,
    binding_logic_version: str = BINDING_LOGIC_VERSION,
    semantic_compiler: Optional[Callable[[dict[str, Any]], dict[str, Any]]] = None,
    semantic_compiler_version: str = SEMANTIC_COMPILER_VERSION,
    reviewer: Optional[Callable[[dict[str, Any]], dict[str, Any]]] = None,
    review_model: str | None = None,
    review_prompt_version: str = REVIEW_PROMPT_VERSION,
) -> dict[str, Any]:
    instruction_text = str(instructions.get("content") or "")
    instruction_source_hash, resource_catalog_hash = _load_instruction_hashes(
        instructions=instructions,
        documents=documents,
    )
    active = repo.get_active_compiled(app_id)
    cache = _build_instruction_understanding_status(
        app_id=app_id,
        active=active,
        review=None,
        instruction_source_hash=instruction_source_hash,
        resource_catalog_hash=resource_catalog_hash,
        parser_contract_version=parser_contract_version,
        binding_logic_version=binding_logic_version,
        semantic_compiler_version=semantic_compiler_version if semantic_compiler is not None else None,
        semantic_compile_prompt_version=SEMANTIC_COMPILE_PROMPT_VERSION if semantic_compiler is not None else None,
    )
    compiled_changed = cache["cache_status"] != "hot" or not isinstance(active, dict)
    attempt_record = None
    if compiled_changed:
        attempt_record = compile_instruction_understanding(
            app_id=app_id,
            instruction_text=instruction_text,
            instruction_uri=str(instructions.get("uri") or "") or None,
            instruction_source_version=instructions.get("version"),
            documents=documents,
            repo=repo,
            snapshot_root=snapshot_root,
            parser_contract_version=parser_contract_version,
            binding_logic_version=binding_logic_version,
            semantic_compiler=semantic_compiler,
            semantic_compiler_version=semantic_compiler_version,
        )
        record = attempt_record if bool(attempt_record.get("is_active")) else repo.get_active_compiled(app_id)
    else:
        record = active

    review = _select_current_review(repo=repo, app_id=app_id, compiled_record=record)
    if compiled_changed and reviewer is not None:
        review = review_instruction_understanding(
            app_id=app_id,
            compiled_record=record,
            repo=repo,
            reviewer=reviewer,
            review_model=review_model,
            review_prompt_version=review_prompt_version,
        )

    status = _build_instruction_understanding_status(
        app_id=app_id,
        active=record if isinstance(record, dict) else None,
        review=review,
        instruction_source_hash=instruction_source_hash,
        resource_catalog_hash=resource_catalog_hash,
        parser_contract_version=parser_contract_version,
        binding_logic_version=binding_logic_version,
        semantic_compiler_version=semantic_compiler_version if semantic_compiler is not None else None,
        semantic_compile_prompt_version=SEMANTIC_COMPILE_PROMPT_VERSION if semantic_compiler is not None else None,
    )
    return {
        "record": record,
        "attempt_record": attempt_record,
        "review": review,
        "cache_status": status["cache_status"],
        "stale_reasons": status["stale_reasons"],
        "status": status,
    }


def ensure_compiled_instruction_understanding(
    *,
    app_id: str,
    builder_store: BuilderStore,
    repo: InstructionUnderstandingRepo,
    snapshot_root: Path | None = None,
    parser_contract_version: str = PARSER_CONTRACT_VERSION,
    binding_logic_version: str = BINDING_LOGIC_VERSION,
    semantic_compiler: Optional[Callable[[dict[str, Any]], dict[str, Any]]] = None,
    semantic_compiler_version: str = SEMANTIC_COMPILER_VERSION,
) -> dict[str, Any]:
    instructions = builder_store.get_instructions(app_id) or {}
    documents = builder_store.list_documents(app_id)
    if repo.get_active_compiled(app_id) is None:
        _hydrate_compiled_from_snapshot(
            app_id=app_id,
            repo=repo,
            snapshot_root=snapshot_root or _default_snapshot_root(builder_store),
        )
    return prepare_instruction_understanding(
        app_id=app_id,
        instructions=instructions,
        documents=documents,
        repo=repo,
        snapshot_root=snapshot_root or _default_snapshot_root(builder_store),
        parser_contract_version=parser_contract_version,
        binding_logic_version=binding_logic_version,
        semantic_compiler=semantic_compiler,
        semantic_compiler_version=semantic_compiler_version,
    )


def load_instruction_understanding_detail(
    *,
    app_id: str,
    builder_store: BuilderStore,
    repo: InstructionUnderstandingRepo,
    parser_contract_version: str = PARSER_CONTRACT_VERSION,
    binding_logic_version: str = BINDING_LOGIC_VERSION,
    semantic_compiler_version: str | None = None,
    semantic_compile_prompt_version: str | None = None,
) -> dict[str, Any]:
    instructions = builder_store.get_instructions(app_id) or {}
    documents = builder_store.list_documents(app_id)
    compiled = repo.get_active_compiled(app_id)
    if compiled is None:
        compiled = _hydrate_compiled_from_snapshot(
            app_id=app_id,
            repo=repo,
            snapshot_root=_default_snapshot_root(builder_store),
        )
    latest_attempt = repo.get_latest_compiled(app_id)
    if isinstance(latest_attempt, dict) and isinstance(compiled, dict):
        if str(latest_attempt.get("id") or "") == str(compiled.get("id") or ""):
            latest_attempt = None
    review = _select_current_review(repo=repo, app_id=app_id, compiled_record=compiled)
    approval = repo.get_active_approval(app_id)
    revision = repo.get_active_revision(app_id)
    instruction_source_hash, resource_catalog_hash = _load_instruction_hashes(
        instructions=instructions,
        documents=documents,
    )
    return _build_instruction_understanding_detail(
        app_id=app_id,
        compiled=compiled,
        latest_attempt=latest_attempt,
        review=review,
        approval=approval,
        revision=revision,
        instruction_source_hash=instruction_source_hash,
        resource_catalog_hash=resource_catalog_hash,
        parser_contract_version=parser_contract_version,
        binding_logic_version=binding_logic_version,
        semantic_compiler_version=semantic_compiler_version,
        semantic_compile_prompt_version=semantic_compile_prompt_version,
    )


def force_recompile_instruction_understanding(
    *,
    app_id: str,
    builder_store: BuilderStore,
    repo: InstructionUnderstandingRepo,
    snapshot_root: Path | None = None,
    parser_contract_version: str = PARSER_CONTRACT_VERSION,
    binding_logic_version: str = BINDING_LOGIC_VERSION,
    semantic_compiler: Optional[Callable[[dict[str, Any]], dict[str, Any]]] = None,
    semantic_compiler_version: str = SEMANTIC_COMPILER_VERSION,
) -> dict[str, Any]:
    instructions = builder_store.get_instructions(app_id) or {}
    documents = builder_store.list_documents(app_id)
    attempt_record = compile_instruction_understanding(
        app_id=app_id,
        instruction_text=str(instructions.get("content") or ""),
        instruction_uri=str(instructions.get("uri") or "") or None,
        instruction_source_version=instructions.get("version"),
        documents=documents,
        repo=repo,
        snapshot_root=snapshot_root or _default_snapshot_root(builder_store),
        parser_contract_version=parser_contract_version,
        binding_logic_version=binding_logic_version,
        semantic_compiler=semantic_compiler,
        semantic_compiler_version=semantic_compiler_version,
    )
    record = attempt_record if bool(attempt_record.get("is_active")) else repo.get_active_compiled(app_id)
    review = _select_current_review(repo=repo, app_id=app_id, compiled_record=record)
    status = get_instruction_understanding_status(
        app_id=app_id,
        builder_store=builder_store,
        repo=repo,
        parser_contract_version=parser_contract_version,
        binding_logic_version=binding_logic_version,
    )
    return {
        "record": record,
        "attempt_record": attempt_record,
        "latest_attempt": attempt_record if isinstance(attempt_record, dict) and not bool(attempt_record.get("is_active")) else None,
        "review": review,
        "cache_status": "recompiled",
        "stale_reasons": ["forced_recompile"],
        "status": status,
    }


def review_instruction_understanding(
    *,
    app_id: str,
    compiled_record: dict[str, Any],
    repo: InstructionUnderstandingRepo,
    reviewer: Callable[[dict[str, Any]], dict[str, Any]],
    review_model: str | None = None,
    review_prompt_version: str = REVIEW_PROMPT_VERSION,
) -> dict[str, Any]:
    review_result = _normalize_review_result(reviewer(compiled_record))
    review_findings = dict(review_result.get("review_findings") or {})
    review_findings["__compiled_state"] = {
        "instruction_source_hash": str(compiled_record.get("instruction_source_hash") or ""),
        "parser_contract_version": str(compiled_record.get("parser_contract_version") or PARSER_CONTRACT_VERSION),
        "binding_logic_version": str(compiled_record.get("binding_logic_version") or BINDING_LOGIC_VERSION),
        "resource_catalog_hash": str(compiled_record.get("resource_catalog_hash") or ""),
    }
    return repo.save_review(
        app_id=app_id,
        instruction_source_hash=str(compiled_record.get("instruction_source_hash") or ""),
        parser_contract_version=str(compiled_record.get("parser_contract_version") or PARSER_CONTRACT_VERSION),
        review_model=review_model,
        review_prompt_version=review_prompt_version,
        review_status=str(review_result.get("review_status") or "review_failed"),
        review_confidence=review_result.get("review_confidence"),
        review_findings=review_findings,
        review_summary_md=str(review_result.get("review_summary_md") or ""),
        review_recommendations=review_result.get("review_recommendations"),
    )


def force_review_instruction_understanding(
    *,
    app_id: str,
    builder_store: BuilderStore,
    repo: InstructionUnderstandingRepo,
    reviewer: Optional[Callable[[dict[str, Any]], dict[str, Any]]],
    review_model: str | None = None,
    review_prompt_version: str = REVIEW_PROMPT_VERSION,
) -> dict[str, Any]:
    if reviewer is None:
        raise ValueError("reviewer is required to force instruction understanding review")
    compiled = repo.get_active_compiled(app_id)
    if not isinstance(compiled, dict):
        compiled = _hydrate_compiled_from_snapshot(
            app_id=app_id,
            repo=repo,
            snapshot_root=_default_snapshot_root(builder_store),
        )
    if not isinstance(compiled, dict):
        compiled = force_recompile_instruction_understanding(
            app_id=app_id,
            builder_store=builder_store,
            repo=repo,
        )["record"]
    review = review_instruction_understanding(
        app_id=app_id,
        compiled_record=compiled,
        repo=repo,
        reviewer=reviewer,
        review_model=review_model,
        review_prompt_version=review_prompt_version,
    )
    status = get_instruction_understanding_status(
        app_id=app_id,
        builder_store=builder_store,
        repo=repo,
    )
    return {
        "record": compiled,
        "review": review,
        "cache_status": "reviewed",
        "stale_reasons": [],
        "status": status,
    }


def approve_instruction_understanding_findings(
    *,
    app_id: str,
    repo: InstructionUnderstandingRepo,
    approved_findings: list[dict[str, Any]],
    approver: str | None = None,
) -> dict[str, Any]:
    compiled = repo.get_active_compiled(app_id)
    review = repo.get_active_review(app_id)
    if not isinstance(compiled, dict):
        raise ValueError("compiled understanding is required before approval")
    if not isinstance(review, dict):
        raise ValueError("review record is required before approval")
    approval = repo.save_approval(
        app_id=app_id,
        compiled_record_id=str(compiled.get("id") or ""),
        review_record_id=str(review.get("id") or ""),
        approved_findings=approved_findings,
        approver=approver,
    )
    return {"record": compiled, "review": review, "approval": approval}


def revise_instruction_understanding(
    *,
    app_id: str,
    repo: InstructionUnderstandingRepo,
    reviser: Callable[[dict[str, Any]], dict[str, Any]],
    revision_prompt_version: str = REVISION_PROMPT_VERSION,
) -> dict[str, Any]:
    compiled = repo.get_active_compiled(app_id)
    review = repo.get_active_review(app_id)
    approval = repo.get_active_approval(app_id)
    if not isinstance(compiled, dict):
        raise ValueError("compiled understanding is required before revision")
    if not isinstance(approval, dict):
        raise ValueError("approval record is required before revision")
    context = {
        "app_id": app_id,
        "instruction_source_hash": compiled.get("instruction_source_hash"),
        "compiled_contract": compiled.get("compiled_contract", {}),
        "review_findings": review.get("review_findings", {}) if isinstance(review, dict) else {},
        "approved_findings": approval.get("approved_findings", []),
    }
    revision_result = reviser(context)
    if not isinstance(revision_result, dict):
        revision_result = {}
    revised_semantic_model = revision_result.get("revised_semantic_model")
    if not isinstance(revised_semantic_model, dict):
        revised_semantic_model = {}
    validation = _validate_semantic_compile_candidate(
        semantic_model=revised_semantic_model,
        deterministic_contract=dict(compiled.get("compiled_contract", {}) or {}),
    )
    return {
        "record": compiled,
        "review": review,
        "approval": approval,
        "revision": repo.save_revision(
            app_id=app_id,
            compiled_record_id=str(compiled.get("id") or ""),
            review_record_id=(str(review.get("id") or "").strip() or None) if isinstance(review, dict) else None,
            approval_record_id=str(approval.get("id") or "") or None,
            instruction_source_hash=str(compiled.get("instruction_source_hash") or ""),
            parser_contract_version=str(compiled.get("parser_contract_version") or PARSER_CONTRACT_VERSION),
            revision_prompt_version=revision_prompt_version,
            revision_status="validated" if validation.get("valid") else "failed",
            revised_contract={
                "semantic_revision": revised_semantic_model,
                "validation": validation,
            },
            revision_notes=list(revision_result.get("revision_notes", []) or []),
            preserved_ids=[
                str(value).strip()
                for value in revision_result.get("preserved_ids", []) or []
                if str(value).strip()
            ],
            changed_ids=[
                str(value).strip()
                for value in revision_result.get("changed_ids", []) or []
                if str(value).strip()
            ],
            revision_confidence=revision_result.get("revision_confidence"),
        ),
        "validation": validation,
    }


def get_instruction_understanding_status(
    *,
    app_id: str,
    builder_store: BuilderStore,
    repo: InstructionUnderstandingRepo,
    parser_contract_version: str = PARSER_CONTRACT_VERSION,
    binding_logic_version: str = BINDING_LOGIC_VERSION,
    semantic_compiler_version: str | None = None,
    semantic_compile_prompt_version: str | None = None,
) -> dict[str, Any]:
    instructions = builder_store.get_instructions(app_id) or {}
    documents = builder_store.list_documents(app_id)
    instruction_source_hash, resource_catalog_hash = _load_instruction_hashes(
        instructions=instructions,
        documents=documents,
    )
    active = repo.get_active_compiled(app_id)
    if active is None:
        active = _hydrate_compiled_from_snapshot(
            app_id=app_id,
            repo=repo,
            snapshot_root=_default_snapshot_root(builder_store),
        )
    review = _select_current_review(repo=repo, app_id=app_id, compiled_record=active)
    return _build_instruction_understanding_status(
        app_id=app_id,
        active=active,
        review=review,
        instruction_source_hash=instruction_source_hash,
        resource_catalog_hash=resource_catalog_hash,
        parser_contract_version=parser_contract_version,
        binding_logic_version=binding_logic_version,
        semantic_compiler_version=semantic_compiler_version,
        semantic_compile_prompt_version=semantic_compile_prompt_version,
    )
