import datetime
import hashlib
import hmac
import threading
import json
import os
import re
import uuid
from pathlib import Path
from dataclasses import asdict
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from flask import Flask, render_template, request, redirect, url_for, jsonify, abort, make_response

from storage import (
    store,
    ApplicationSchema,
    SettingsSchema,
    InstructionsSchema,
    DocumentUploadSchema,
    DEFAULT_APP_CONFIG_SETTINGS,
    DEFAULT_APP_CONFIG_SCHEMA,
)
from execution_client import ExecutionSubsystemClient
from agent_skill_execution_client import AgentSkillExecutionClient
from agent_skill_projection import synchronize_agent_skill_projection
from agent_skill_publication import (
    PublicationRevisionStale,
    build_publication_preview,
    publish_agent_skill_revision,
)
from agent_skill_interaction_review import (
    build_agent_skill_interaction_recommendation,
    interaction_policy_from_form,
)
from instruction_model_adapter import InstructionModelAdapter
from policy import get_template_family_policy
from skill_normalization import AUTHOR_TOOL_ALIAS_MAP, EXPLICIT_REQUIRED_TOOL_TEMPLATE_MAP
from tools_info_export import (
    write_tools_info_failure_markdown,
    write_tools_info_markdown,
)
from rag_stub import (
    process_files,
    retrieve_data,
    ingest_uploaded_file,
    delete_document_chunks,
    get_global_process_config,
    get_global_retrieval_config,
)

app = Flask(__name__)
_BY_NAME_RATE_LIMIT = 60
_BY_NAME_WINDOW_SECONDS = 60
_by_name_requests = defaultdict(deque)
_by_name_lock = threading.Lock()
_retrieval_pool = ThreadPoolExecutor(max_workers=4)
_UPLOAD_ROOT = Path(__file__).resolve().parent / "storage" / "uploads"
_ingest_jobs_lock = threading.Lock()
_ingest_running_apps: set[str] = set()
_ingest_cancel_lock = threading.Lock()
_ingest_cancel_doc_ids: set[str] = set()
_INGEST_STALE_SECONDS = 15 * 60
_SKILL_IMPORT_UPLOAD_ROOT = Path(__file__).resolve().parent / "storage" / "_skill_import_uploads"
_TOOLS_INFO_EXPORT_PATH = Path(__file__).resolve().parents[2] / "docs" / "tools_info.md"
_DEFAULT_EXECUTION_BASE_URL = "http://127.0.0.1:3001"
_DEFAULT_INSTRUCTION_MODEL_SNAPSHOT_ROOT = (
    Path(__file__).resolve().parents[2]
    / "ragenius_app_skeleton"
    / "backend"
    / ".state"
    / "instruction_understanding_snapshots"
)


def validation_error(path: str, msg: str, code: str):
    return {"path": path, "msg": msg, "code": code}


def _current_process_config():
    return get_global_process_config()


def _current_retrieval_config():
    return get_global_retrieval_config()


def _global_subsystem_settings_view():
    env_keys = [
        "RAG_VECTOR_STORE_BACKEND",
        "RAG_VECTOR_STORE_DSN",
        "RAG_VECTOR_STORE_PGVECTOR_FALLBACK",
        "RAG_PGVECTOR_BOOTSTRAP",
        "RAG_EMBEDDING_BACKEND",
        "RAG_PROCESS_CHUNK_SIZE",
        "RAG_PROCESS_CHUNK_OVERLAP",
        "RAG_PROCESS_SECTION_TOKEN_THRESHOLD",
        "RAG_PROCESS_MIN_CHUNK_LENGTH",
        "RAG_PROCESS_NEAR_DUP_THRESHOLD",
        "RAG_PROCESS_RETRY_UPSERT",
        "RAG_RETRIEVAL_CANDIDATE_K",
        "RAG_RETRIEVAL_FUSION_K",
        "RAG_RETRIEVAL_TOP_K",
        "RAG_RETRIEVAL_SEMANTIC_WEIGHT",
        "RAG_RETRIEVAL_METADATA_WEIGHT",
        "RAG_RETRIEVAL_MAX_CHUNKS_PER_DOC",
    ]
    env_values = [{"key": key, "value": os.environ.get(key, "")} for key in env_keys]
    return {
        "vector_store": {
            "backend": os.environ.get("RAG_VECTOR_STORE_BACKEND", ""),
            "dsn": os.environ.get("RAG_VECTOR_STORE_DSN", ""),
            "pgvector_fallback": os.environ.get("RAG_VECTOR_STORE_PGVECTOR_FALLBACK", ""),
            "bootstrap": os.environ.get("RAG_PGVECTOR_BOOTSTRAP", ""),
        },
        "embedding": {
            "backend": os.environ.get("RAG_EMBEDDING_BACKEND", ""),
        },
        "process_config": asdict(_current_process_config()),
        "retrieval_config": asdict(_current_retrieval_config()),
        "environment": env_values,
    }


def _instruction_model_snapshot_root():
    configured = (os.environ.get("RAGENIUS_INSTRUCTION_MODEL_SNAPSHOT_ROOT") or "").strip()
    if configured:
        return configured
    if _DEFAULT_INSTRUCTION_MODEL_SNAPSHOT_ROOT.is_dir():
        return _DEFAULT_INSTRUCTION_MODEL_SNAPSHOT_ROOT
    return None


def _tool_family(tool_id: str) -> str:
    value = str(tool_id or "")
    if value.startswith("mcp."):
        return "mcp"
    if value.startswith("adapter."):
        return "adapter"
    if value in {"read_file", "list_files", "write_file", "patch_file", "save_artifact", "load_artifact"}:
        return "local"
    if value in {"retrieve_documents", "search_metadata", "rag_retrieval_tool"}:
        return "rag_adapter"
    return "api"


def _alias_support_matrix() -> list[dict]:
    family_by_tool = {
        tuple(tools)[0]: family
        for tools, family in EXPLICIT_REQUIRED_TOOL_TEMPLATE_MAP.items()
        if len(tools) == 1
    }
    rows = []
    for alias, tool_id in sorted(AUTHOR_TOOL_ALIAS_MAP.items()):
        template_family = family_by_tool.get(tool_id)
        policy = get_template_family_policy(template_family) if template_family else {}
        support_level = (
            "default family inference supported"
            if template_family
            else "explicit schema recommended"
        )
        notes = []
        if tool_id.startswith("adapter.notebooklm."):
            notes.append("supports notebookId or notebookTitle when notebook-scoped")
        if tool_id.startswith("mcp."):
            notes.append("runtime provider discovery/configuration required")
        rows.append(
            {
                "alias": alias,
                "tool_id": tool_id,
                "family": _tool_family(tool_id),
                "template_family": template_family or "",
                "support_level": support_level,
                "policy_class": policy.get("policy_class", ""),
                "notes": notes,
            }
        )
    return rows


def _runtime_inventory_view():
    client = _execution_client()
    readyz = client.get_runtime_readyz()
    provider_status = client.get_mcp_provider_status()
    integrations = client.get_runtime_integrations()
    tool_inventory = client.get_tool_inventory()
    recent_execution_diagnostics = client.get_recent_execution_diagnostics(
        limit=10,
        used_fallback=True,
    )
    readyz_body = readyz.get("body", {}) if isinstance(readyz, dict) else {}
    checks = readyz_body.get("checks", {}) if isinstance(readyz_body, dict) else {}
    runtime_config = checks.get("runtime_config", {}) if isinstance(checks, dict) else {}
    mcp_runtime = runtime_config.get("mcp", {}) if isinstance(runtime_config, dict) else {}
    discovery = checks.get("mcp_discovery", {}) if isinstance(checks, dict) else {}
    provider_body = provider_status.get("body", {}) if isinstance(provider_status, dict) else {}
    providers = provider_body.get("providers", {}) if isinstance(provider_body, dict) else {}
    integrations_body = integrations.get("body", {}) if isinstance(integrations, dict) else {}
    integration_items = integrations_body.get("items", []) if isinstance(integrations_body, dict) else []
    if not isinstance(integration_items, list):
        integration_items = []
    integration_summary = integrations_body.get("summary", {}) if isinstance(integrations_body, dict) else {}
    if not isinstance(integration_summary, dict):
        integration_summary = {}
    tool_inventory_body = tool_inventory.get("body", {}) if isinstance(tool_inventory, dict) else {}
    tool_inventory_items = tool_inventory_body.get("items", []) if isinstance(tool_inventory_body, dict) else []
    if not isinstance(tool_inventory_items, list):
        tool_inventory_items = []
    diagnostics_body = (
        recent_execution_diagnostics.get("body", {})
        if isinstance(recent_execution_diagnostics, dict)
        else {}
    )
    diagnostics_items = diagnostics_body.get("items", []) if isinstance(diagnostics_body, dict) else []
    if not isinstance(diagnostics_items, list):
        diagnostics_items = []
    diagnostics_summary = diagnostics_body.get("summary", {}) if isinstance(diagnostics_body, dict) else {}
    if not isinstance(diagnostics_summary, dict):
        diagnostics_summary = {}

    provider_rows = []
    for provider_id, provider in sorted(providers.items()):
        provider_obj = provider if isinstance(provider, dict) else {}
        discovery_obj = (
            discovery.get("providers", {}).get(provider_id, {})
            if isinstance(discovery.get("providers", {}), dict)
            else {}
        )
        tool_ids = provider_obj.get("tool_ids", [])
        if not isinstance(tool_ids, list):
            tool_ids = []
        provider_rows.append(
            {
                "id": provider_id,
                "status": str(provider_obj.get("status") or discovery_obj.get("status") or "unknown"),
                "tool_count": int(
                    provider_obj.get("toolCount")
                    or provider_obj.get("tool_count")
                    or discovery_obj.get("toolCount")
                    or len(tool_ids)
                ),
                "tool_ids": tool_ids,
                "auth_configured": bool(
                    provider_obj.get("authConfigured")
                    if "authConfigured" in provider_obj
                    else discovery_obj.get("authConfigured", False)
                ),
                "last_discovered_at": provider_obj.get("last_discovered_at")
                or discovery_obj.get("lastDiscoveredAt"),
                "last_error": provider_obj.get("last_error") or discovery_obj.get("lastError"),
            }
        )

    return {
        "execution_base_url": getattr(
            client,
            "base_url",
            os.environ.get("RAGENIUS_EXECUTION_BASE_URL", _DEFAULT_EXECUTION_BASE_URL),
        ),
        "transport_ok": bool(
            readyz.get("ok", False)
            and provider_status.get("ok", False)
            and integrations.get("ok", False)
            and tool_inventory.get("ok", False)
            and recent_execution_diagnostics.get("ok", False)
        ),
        "endpoint_statuses": [
            {
                "path": "/readyz",
                "ok": bool(readyz.get("ok", False)),
                "status_code": readyz.get("status_code"),
            },
            {
                "path": "/v1/tools/providers/mcp/status",
                "ok": bool(provider_status.get("ok", False)),
                "status_code": provider_status.get("status_code"),
            },
            {
                "path": "/v1/runtime/integrations",
                "ok": bool(integrations.get("ok", False)),
                "status_code": integrations.get("status_code"),
            },
            {
                "path": "/v1/tools/inventory",
                "ok": bool(tool_inventory.get("ok", False)),
                "status_code": tool_inventory.get("status_code"),
            },
            {
                "path": "/v1/executions/diagnostics/recent",
                "ok": bool(recent_execution_diagnostics.get("ok", False)),
                "status_code": recent_execution_diagnostics.get("status_code"),
            },
        ],
        "readyz_status_code": readyz.get("status_code"),
        "provider_status_code": provider_status.get("status_code"),
        "integration_status_code": integrations.get("status_code"),
        "tool_inventory_status_code": tool_inventory.get("status_code"),
        "execution_diagnostics_status_code": recent_execution_diagnostics.get("status_code"),
        "runtime_error": None if readyz.get("ok", False) else readyz_body.get("error"),
        "startup_auto_discovery": bool(mcp_runtime.get("startupDiscoveryEnabled", False)),
        "configured_servers": int(mcp_runtime.get("configuredServers", 0) or 0),
        "enabled_servers": int(mcp_runtime.get("enabledServers", 0) or 0),
        "startup_completed": bool(provider_body.get("startup_completed", discovery.get("startupCompleted", False))),
        "mcp_providers": provider_rows,
        "integrations": integration_items,
        "integration_summary": integration_summary,
        "tool_inventory": tool_inventory_items,
        "recent_execution_summary": diagnostics_summary,
        "recent_execution_diagnostics": diagnostics_items,
        "authoring_coverage": _alias_support_matrix(),
    }


def _safe_json_loads(raw: str | None, fallback):
    if raw is None:
        return fallback
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        return fallback


def _get_nested_value(obj: dict, path: list[str], default=None):
    current = obj
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def _extract_instruction_resource_references(markdown: str) -> list[str]:
    text = str(markdown or "")
    refs = []
    # Match explicit markdown links: [label](file.md) or [file.md](...)
    refs.extend(re.findall(r"\[[^\]]*\]\(([^)\s]+\.md)\)", text, flags=re.IGNORECASE))
    # Match code-form file tokens: `file.md`
    refs.extend(re.findall(r"`([^`\s]+\.md)`", text, flags=re.IGNORECASE))
    # Match quoted file tokens: "file.md" / 'file.md'
    refs.extend(re.findall(r"['\"]([^'\"\s]+\.md)['\"]", text, flags=re.IGNORECASE))
    deduped = []
    seen = set()
    for ref in refs:
        name = Path(ref).name
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(name)
    return deduped


def _canonical_resource_name(name: str) -> str:
    stem = Path(str(name or "")).stem.lower().strip()
    tokens = re.split(r"[\s_\-]+", stem)
    normalized_tokens = []
    stopwords = {"in", "the", "a", "an", "of"}
    for tok in tokens:
        cleaned = re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", tok)
        if not cleaned or cleaned in stopwords:
            continue
        # Very small singularization heuristic for English guide names:
        # relationships -> relationship
        if len(cleaned) > 4 and cleaned.endswith("s"):
            cleaned = cleaned[:-1]
        normalized_tokens.append(cleaned)
    return "".join(normalized_tokens)


def _validate_instruction_resources(app_id: str, markdown: str) -> dict:
    referenced = _extract_instruction_resource_references(markdown)
    docs = store.list_documents(app_id)
    available_exact = {}
    available_canonical = {}
    for doc in docs:
        filename = Path(doc.get("filename") or "").name
        if not str(filename).strip():
            continue
        available_exact[filename.lower()] = doc
        key = _canonical_resource_name(filename)
        if key and key not in available_canonical:
            available_canonical[key] = doc
    matched = []
    missing = []
    for ref in referenced:
        doc = available_exact.get(ref.lower())
        if doc is None:
            doc = available_canonical.get(_canonical_resource_name(ref))
        if doc is None:
            missing.append(ref)
        else:
            matched.append(
                {
                    "reference": ref,
                    "document_id": doc.get("id"),
                    "status": doc.get("status"),
                    "filename": doc.get("filename"),
                }
            )
    return {
        "referenced_files": referenced,
        "matched_documents": matched,
        "missing_files": missing,
        "ok": len(missing) == 0,
    }


def _normalize_instruction_markdown(content: str) -> str:
    text = str(content or "").replace("\r\n", "\n").replace("\r", "\n")
    # Remove trailing spaces/tabs on each line.
    lines = [re.sub(r"[ \t]+$", "", line) for line in text.split("\n")]
    text = "\n".join(lines).strip()
    # Collapse 3+ blank lines to one blank line.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def _collect_schema_rows(properties: dict, settings_obj: dict, prefix: list[str] | None = None):
    prefix = prefix or []
    rows = []
    for key, spec in (properties or {}).items():
        spec_obj = spec or {}
        path = prefix + [key]
        value_type = spec_obj.get("type") or ("string" if spec_obj.get("enum") else "unknown")
        nested_props = spec_obj.get("properties") if isinstance(spec_obj, dict) else None
        has_children = value_type == "object" and isinstance(nested_props, dict) and len(nested_props) > 0
        if has_children:
            rows.extend(_collect_schema_rows(nested_props, settings_obj, path))
            continue
        has_schema_default = isinstance(spec_obj, dict) and "default" in spec_obj
        schema_default = spec_obj.get("default") if has_schema_default else None
        stored_default = _get_nested_value(settings_obj, path, None)
        default_value = schema_default if has_schema_default else stored_default
        current_value = _get_nested_value(settings_obj, path, default_value)
        rows.append(
            {
                "key_path": ".".join(path),
                "type": value_type,
                "default_display": "-" if default_value is None else json.dumps(default_value, ensure_ascii=False),
                "current_display": "" if current_value is None else (
                    current_value if isinstance(current_value, str) else json.dumps(current_value, ensure_ascii=False)
                ),
            }
        )
    return rows


def _ordered_unique(values):
    seen = set()
    ordered = []
    for value in values:
        key = str(value or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    return ordered


def _build_llm_settings_editor(schema_obj: dict, settings_obj: dict) -> dict:
    llm_schema = _get_nested_value(schema_obj, ["properties", "llm", "properties"], {}) or {}
    llm_settings = _get_nested_value(settings_obj, ["llm"], {}) or {}
    provider_schema = llm_schema.get("provider", {}) if isinstance(llm_schema, dict) else {}
    model_schema = llm_schema.get("models", {}).get("properties", {}) if isinstance(llm_schema.get("models"), dict) else {}
    temp_schema = (
        llm_schema.get("temperature", {}).get("properties", {})
        if isinstance(llm_schema.get("temperature"), dict)
        else {}
    )
    model_values = llm_settings.get("models", {}) if isinstance(llm_settings.get("models"), dict) else {}
    temp_values = llm_settings.get("temperature", {}) if isinstance(llm_settings.get("temperature"), dict) else {}
    task_names = _ordered_unique(list(model_schema.keys()) + list(model_values.keys()) + list(temp_schema.keys()) + list(temp_values.keys()))
    return {
        "provider": {
            "default": provider_schema.get("default", ""),
            "current": llm_settings.get("provider", provider_schema.get("default", "")),
            "type": provider_schema.get("type", "string"),
        },
        "tasks": [
            {
                "task": task,
                "model_default": model_schema.get(task, {}).get("default", ""),
                "model_current": model_values.get(task, model_schema.get(task, {}).get("default", "")),
                "temperature_default": temp_schema.get(task, {}).get("default", ""),
                "temperature_current": temp_values.get(task, temp_schema.get(task, {}).get("default", "")),
            }
            for task in task_names
        ],
    }


def _client_ip():
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def _is_rate_limited(ip: str):
    now = datetime.datetime.utcnow().timestamp()
    with _by_name_lock:
        window = _by_name_requests[ip]
        while window and now - window[0] > _BY_NAME_WINDOW_SECONDS:
            window.popleft()
        if len(window) >= _BY_NAME_RATE_LIMIT:
            return True
        window.append(now)
    return False


def parse_app(app_id: str):
    app_obj = store.get_application(app_id)
    if not app_obj:
        abort(404)
    return app_obj


def parse_skill(skill_id: str):
    skill_obj = store.get_skill(skill_id)
    if not skill_obj:
        abort(404)
    return skill_obj


def _execution_client() -> ExecutionSubsystemClient:
    base_url = os.environ.get("RAGENIUS_EXECUTION_BASE_URL", _DEFAULT_EXECUTION_BASE_URL)
    return ExecutionSubsystemClient(base_url)


def _agent_skill_execution_client() -> AgentSkillExecutionClient:
    base_url = os.environ.get("RAGENIUS_EXECUTION_BASE_URL", _DEFAULT_EXECUTION_BASE_URL)
    token = os.environ.get("RAGENIUS_BUILDER_EXECUTION_SERVICE_TOKEN", "")
    timeout_seconds = float(os.environ.get("RAGENIUS_BUILDER_EXECUTION_TIMEOUT_SECONDS", "30"))
    return AgentSkillExecutionClient(base_url, token, timeout_seconds=timeout_seconds)


def _agent_skill_actor_id() -> str:
    return (request.headers.get("X-RAGenius-Admin-Id") or "builder-admin").strip()[:128]


def _agent_skill_builder_instance_id() -> str:
    return (os.environ.get("RAGENIUS_BUILDER_INSTANCE_ID") or "builder-local-default").strip()


def _agent_skill_publication_correlation_id() -> str:
    return (request.headers.get("X-Request-Id") or str(uuid.uuid4())).strip()[:128]


_AGENT_SKILL_PUBLICATION_ENDPOINTS = {
    "agent_skill_publication_review",
    "publish_agent_skills_form",
    "api_synchronize_agent_skills",
    "api_agent_skill_publication_preview",
    "api_publish_agent_skills",
}
_AGENT_SKILL_PUBLICATION_BROWSER_ENDPOINTS = {
    "agent_skill_publication_review",
    "publish_agent_skills_form",
}


def _agent_skill_publication_csrf_token() -> str:
    configured_token = os.environ.get("RAGENIUS_BUILDER_ADMIN_TOKEN", "").strip()
    return hmac.new(
        configured_token.encode("utf-8"),
        b"ragenius-agent-skill-publication-form-v1",
        hashlib.sha256,
    ).hexdigest()


@app.before_request
def _require_agent_skill_publication_admin():
    if request.endpoint not in _AGENT_SKILL_PUBLICATION_ENDPOINTS:
        return None

    configured_token = os.environ.get("RAGENIUS_BUILDER_ADMIN_TOKEN", "").strip()
    if not configured_token:
        return jsonify(
            {
                "error": {
                    "code": "BUILDER_ADMIN_AUTH_NOT_CONFIGURED",
                    "message": "Builder publication authentication is not configured.",
                }
            }
        ), 503

    supplied_token = ""
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        supplied_token = authorization[7:].strip()
    elif (
        request.endpoint in _AGENT_SKILL_PUBLICATION_BROWSER_ENDPOINTS
        and request.authorization
        and request.authorization.type.lower() == "basic"
    ):
        supplied_token = request.authorization.password or ""

    if supplied_token and hmac.compare_digest(supplied_token, configured_token):
        return None

    response = make_response(
        jsonify(
            {
                "error": {
                    "code": "BUILDER_ADMIN_AUTH_REQUIRED",
                    "message": "A valid Builder administrator credential is required.",
                }
            }
        ),
        401,
    )
    response.headers["WWW-Authenticate"] = 'Basic realm="RAGenius Builder publication"'
    return response


def _public_agent_skill_publication_result(result):
    return {key: value for key, value in result.items() if key != "projection_state"}


def _agent_skill_publication_review_context(preview, result=None):
    apps = {item["id"]: item["name"] for item in store.list_applications()}
    return {
        "preview": preview,
        "result": result,
        "csrf_token": _agent_skill_publication_csrf_token(),
        "affected_apps": [
            {"id": app_id, "name": apps.get(app_id, app_id)}
            for app_id in preview["changes"]["affected_apps"]
        ],
    }


def _public_agent_skill_source(source_obj):
    return {
        key: source_obj[key]
        for key in (
            "id",
            "backend",
            "source_kind",
            "display_name",
            "runtime_target_id",
            "precedence",
            "enabled",
            "created_at",
            "updated_at",
        )
    }


def _public_agent_skill(skill_obj):
    approval = skill_obj.get("approval") or {}
    return {
        key: skill_obj[key]
        for key in (
            "id",
            "agent_skill_id",
            "backend",
            "runtime_target_id",
            "source_id",
            "provider_skill_name",
            "provider_skill_reference",
            "display_name",
            "description",
            "content_fingerprint",
            "discovery_status",
            "model_visible",
            "user_invocable",
            "direct_tool_dispatch",
            "missing_requirements",
            "discovered_at",
            "last_seen_at",
            "updated_at",
            "governance_state",
        )
    } | {
        "approved_fingerprint": approval.get("approved_fingerprint"),
        "approval_state": approval.get("state"),
        "source": skill_obj.get("source"),
    }


def _agent_skill_source_options():
    try:
        response = _agent_skill_execution_client().get_source_options()
    except (ValueError, OSError) as exc:
        return [], str(exc)
    body = response.get("body", {}) if isinstance(response, dict) else {}
    items = body.get("items", []) if isinstance(body, dict) else []
    if not response.get("ok") or not isinstance(items, list):
        error = body.get("error", {}) if isinstance(body, dict) else {}
        return [], str(error.get("message") or "Execution source options are unavailable.")
    allowed = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if all(
            isinstance(item.get(key), str) and item.get(key).strip()
            for key in (
                "backend",
                "source_kind",
                "display_name",
                "runtime_target_id",
                "protected_locator_ref",
            )
        ):
            precedence = item.get("precedence")
            if isinstance(precedence, int) and precedence >= 0:
                allowed.append(dict(item))
    return allowed, None


def _match_agent_skill_source_option(payload):
    options, error = _agent_skill_source_options()
    if error:
        raise ValueError(error)
    for option in options:
        if all(
            str(payload.get(key, "")).strip() == option[key]
            for key in (
                "backend",
                "source_kind",
                "runtime_target_id",
                "protected_locator_ref",
            )
        ):
            return option
    raise ValueError("Agent skill source is not configured by the execution subsystem")


def _discover_agent_skill_source(source_id):
    source = store.get_agent_skill_source(source_id)
    if not source:
        return None, ({"error": {"code": "NOT_FOUND", "message": "Agent skill source not found."}}, 404)
    response = _agent_skill_execution_client().discover(
        {
            "source_id": source["id"],
            "backend": source["backend"],
            "runtime_target_id": source["runtime_target_id"],
            "protected_locator_ref": source["protected_locator_ref"],
        }
    )
    body = response.get("body", {}) if isinstance(response, dict) else {}
    valid = (
        response.get("ok")
        and isinstance(body, dict)
        and body.get("complete") is True
        and body.get("backend") == source["backend"]
        and body.get("runtime_target_id") == source["runtime_target_id"]
        and body.get("source_id") == source["id"]
        and isinstance(body.get("items"), list)
    )
    if not valid:
        error = body.get("error", {}) if isinstance(body, dict) else {}
        return None, (
            {
                "error": {
                    "code": str(error.get("code") or "AGENT_SKILL_DISCOVERY_FAILED"),
                    "message": str(error.get("message") or "Agent skill discovery returned an incomplete response."),
                }
            },
            502,
        )
    try:
        items = store.refresh_agent_skill_catalog(
            source_id=source_id,
            candidates=body["items"],
            actor_id=_agent_skill_actor_id(),
            correlation_id=request.headers.get("X-Request-Id"),
        )
    except ValueError as exc:
        return None, ({"error": {"code": "INVALID_DISCOVERY_RESPONSE", "message": str(exc)}}, 502)
    return items, None


def _sample_value_from_schema(prop_name: str, schema_obj):
    if not isinstance(schema_obj, dict):
        return None
    if "default" in schema_obj:
        return schema_obj.get("default")
    enum_values = schema_obj.get("enum")
    if isinstance(enum_values, list) and enum_values:
        return enum_values[0]
    value_type = schema_obj.get("type")
    if prop_name == "topic":
        return "DeepSeek Mixture of Exports Technology"
    if value_type == "string":
        return "example"
    if value_type == "integer":
        return 1
    if value_type == "number":
        return 1
    if value_type == "boolean":
        return False
    if value_type == "array":
        return []
    if value_type == "object":
        return {}
    return None


def _should_prefill_optional_field(schema_obj) -> bool:
    if not isinstance(schema_obj, dict):
        return False
    return "default" in schema_obj or (
        isinstance(schema_obj.get("enum"), list) and len(schema_obj.get("enum", [])) > 0
    )


def _preferred_conditional_properties(schema_obj: dict) -> list[str]:
    if not isinstance(schema_obj, dict):
        return []
    properties = schema_obj.get("properties", {})
    if not isinstance(properties, dict):
        return []
    preferred = []
    conditional_groups = schema_obj.get("anyOf")
    if not isinstance(conditional_groups, list):
        return preferred
    for group in conditional_groups:
        if not isinstance(group, dict):
            continue
        required_props = group.get("required")
        if not isinstance(required_props, list):
            continue
        for prop_name in required_props:
            if prop_name in properties and prop_name not in preferred:
                preferred.append(str(prop_name))
    if "notebookTitle" in preferred:
        return ["notebookTitle"]
    return preferred[:1]


def _extract_markdown_section(markdown: str, title: str) -> str | None:
    text = str(markdown or "").replace("\r\n", "\n").replace("\r", "\n")
    parts = text.split("\n---\n", 1)
    body = parts[1] if len(parts) == 2 else text
    pattern = (
        rf"(?ms)^(?:##\s*{re.escape(title)}\s*$|{re.escape(title)}\s*$\n[-=]+\s*$)"
        rf"(.*?)(?=^(?:##\s+[^\n]+$|[^\n]+\n[-=]+\s*$)|\Z)"
    )
    match = re.search(pattern, body)
    if not match:
        return None
    return match.group(1).strip()


def _has_json_code_block(section_text: str | None) -> bool:
    if not section_text:
        return False
    return bool(re.search(r"```json\s*(\{.*?\})\s*```", section_text, re.DOTALL))


def _read_skill_markdown(version_row: dict) -> str:
    inline_text = str(version_row.get("manifest_text") or "").strip()
    if inline_text:
        return inline_text
    rel_path = str(version_row.get("skill_md_rel_path") or "").strip()
    if not rel_path:
        return ""
    path = (store.base_dir / rel_path).resolve()
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _sample_input_payload_and_reasons(skill_id: str, schema_obj: dict) -> tuple[dict, list[dict]]:
    properties = schema_obj.get("properties", {}) if isinstance(schema_obj, dict) else {}
    required = schema_obj.get("required", []) if isinstance(schema_obj, dict) else []
    payload = {}
    reasons = []

    for prop_name in required:
        if prop_name not in properties:
            continue
        value = _sample_value_from_schema(str(prop_name), properties.get(prop_name))
        if value is not None:
            payload[str(prop_name)] = value
            reasons.append(
                {
                    "field": str(prop_name),
                    "reason": "Included because the normalized input schema marks it as required.",
                }
            )

    for prop_name in _preferred_conditional_properties(schema_obj):
        if prop_name in payload:
            continue
        value = _sample_value_from_schema(str(prop_name), properties.get(prop_name))
        if value is not None:
            payload[str(prop_name)] = value
            conditional_reason = "Included to satisfy a conditional notebook selector requirement."
            if prop_name == "notebookTitle":
                conditional_reason = (
                    "Included to satisfy the conditional notebook selector requirement; "
                    "Builder prefers notebookTitle over notebookId for authoring and testing."
                )
            reasons.append({"field": str(prop_name), "reason": conditional_reason})

    for prop_name, prop_schema in properties.items():
        if prop_name in payload:
            continue
        if not _should_prefill_optional_field(prop_schema):
            continue
        value = _sample_value_from_schema(str(prop_name), prop_schema)
        if value is not None:
            payload[str(prop_name)] = value
            if "default" in prop_schema:
                reason = f"Included with its schema default ({json.dumps(prop_schema.get('default'), ensure_ascii=False)})."
            else:
                reason = "Included because the schema advertises an enum or default-backed optional value."
            reasons.append({"field": str(prop_name), "reason": reason})

    if skill_id == "research_paper_finder":
        payload.setdefault("topic", "DeepSeek Mixture of Exports Technology")
        payload.setdefault("limit", 5)
        payload.setdefault("source", "auto")
        existing_fields = {item["field"] for item in reasons}
        if "topic" not in existing_fields:
            reasons.append(
                {
                    "field": "topic",
                    "reason": "Included from the Builder research-paper sample prompt override.",
                }
            )
        if "limit" not in existing_fields:
            reasons.append(
                {
                    "field": "limit",
                    "reason": "Included from the Builder research-paper sample limit override.",
                }
            )
        if "source" not in existing_fields:
            reasons.append(
                {
                    "field": "source",
                    "reason": "Included from the Builder research-paper sample source override.",
                }
            )

    return payload, reasons


def _default_skill_test_input(skill_id: str) -> str:
    published = store.get_published_skill_definition(skill_id=skill_id)
    if not published:
        return "{}"
    schema_obj = published.get("input_schema", {}) or {}
    payload, _ = _sample_input_payload_and_reasons(skill_id, schema_obj)

    return json.dumps(payload or {}, ensure_ascii=False, indent=2)


def _pretty_json(value) -> str:
    if value in (None, "", [], {}):
        return "{}"
    return json.dumps(value, ensure_ascii=False, indent=2)


def _build_skill_review_view(version_row: dict) -> dict:
    metadata = version_row.get("metadata") or {}
    policy_class = str(metadata.get("policy_class") or "unsupported")
    template_family = str(metadata.get("template_family") or "unsupported")
    family_policy = get_template_family_policy(template_family)
    required_tools = metadata.get("required_tools", []) or []
    required_permissions = metadata.get("required_permissions", []) or []
    input_schema = metadata.get("input_schema", {}) or {}
    output_schema = metadata.get("output_schema", {}) or {}
    workflow_definition = metadata.get("workflow_definition", {}) or {}
    has_contract = bool(required_tools or required_permissions or input_schema or output_schema or workflow_definition)

    risk_label = {
        "safe_read": "Safe Read",
        "review_required": "Review Required",
        "unsupported": "Unsupported",
    }.get(policy_class, policy_class.replace("_", " ").title())

    if not has_contract or policy_class == "unsupported":
        review_note = "No normalized executable contract available."
    elif policy_class == "review_required":
        review_note = (
            "This version publishes an executable contract. Review tools, permissions, "
            "schemas, and workflow carefully before publish. Runtime confirmation may still "
            "be required for write-capable execution paths."
        )
    else:
        review_note = (
            "This version normalized into a low-risk read-oriented contract suitable for "
            "safe Builder-managed execution."
        )

    markdown = _read_skill_markdown(version_row)
    explicit_input_schema = _has_json_code_block(_extract_markdown_section(markdown, "Input Schema"))
    explicit_output_schema = _has_json_code_block(_extract_markdown_section(markdown, "Expected Output"))
    contract_source = "unsupported"
    contract_source_note = "No executable runtime contract was derived for this version."
    if has_contract and policy_class != "unsupported":
        if explicit_input_schema or explicit_output_schema:
            contract_source = "explicit skill markdown sections"
            contract_source_note = (
                "Builder used explicit structured sections from SKILL.md for schema extraction "
                "and filled the remaining contract from the recognized workflow family."
            )
        else:
            contract_source = "default family inference"
            contract_source_note = (
                "Builder inferred the runtime contract from the recognized tool family and "
                "published policy defaults because explicit schema sections were not provided."
            )

    if not has_contract or policy_class == "unsupported":
        normalization_confidence = "unsupported composition"
        normalization_confidence_note = (
            "Builder does not have a safe first-class normalization path for this skill shape yet. "
            "Add explicit schema sections or simplify the tool composition."
        )
    elif template_family in EXPLICIT_REQUIRED_TOOL_TEMPLATE_MAP.values():
        if explicit_input_schema or explicit_output_schema:
            normalization_confidence = "high confidence first-class family"
            normalization_confidence_note = (
                "This skill matches a first-class Builder family and also provides explicit structured "
                "sections, so the inferred contract should be predictable."
            )
        else:
            normalization_confidence = "default family inference supported"
            normalization_confidence_note = (
                "This skill matches a first-class Builder family. Builder can infer a solid default "
                "contract, but explicit sections are still better when you want tighter control."
            )
    else:
        normalization_confidence = "explicit schema recommended"
        normalization_confidence_note = (
            "Builder derived a contract, but this shape is not one of the strongest first-class families. "
            "Explicit input/output sections are recommended for predictable authoring results."
        )

    contract_explanation = [
        f"Template family: {template_family}.",
        f"Policy class: {policy_class}.",
        f"Contract source: {contract_source}.",
        f"Normalization confidence: {normalization_confidence}.",
    ]
    if family_policy.get("policy_expectations"):
        contract_explanation.append(
            "Policy expectations: " + "; ".join(family_policy.get("policy_expectations", []))
        )

    return {
        "policy_class": policy_class,
        "risk_label": risk_label,
        "auto_finalize": bool(metadata.get("auto_finalize", False)),
        "template_family": template_family,
        "required_tools": required_tools,
        "required_permissions": required_permissions,
        "input_schema_pretty": _pretty_json(input_schema),
        "output_schema_pretty": _pretty_json(output_schema),
        "workflow_pretty": _pretty_json(workflow_definition),
        "has_contract": has_contract and policy_class != "unsupported",
        "review_note": review_note,
        "fallback_capable_tools": family_policy.get("fallback_capable_tools", []),
        "policy_expectations": family_policy.get("policy_expectations", []),
        "contract_source": contract_source,
        "contract_source_note": contract_source_note,
        "normalization_confidence": normalization_confidence,
        "normalization_confidence_note": normalization_confidence_note,
        "explicit_input_schema": explicit_input_schema,
        "explicit_output_schema": explicit_output_schema,
        "contract_explanation": contract_explanation,
    }


def _selected_skill_version(skill_id: str, selected_version: str) -> dict | None:
    if selected_version:
        version_row = store.get_skill_version_by_number(skill_id, selected_version)
        if version_row:
            return version_row
    version_rows = store.list_skill_versions(skill_id)
    published_version = next((row for row in version_rows if row.get("state") == "published"), None)
    return published_version or (version_rows[0] if version_rows else None)


def _build_skill_test_context(skill_id: str, selected_version: str) -> dict:
    version_row = _selected_skill_version(skill_id, selected_version)
    if not version_row:
        return {
            "contract_source": "unsupported",
            "contract_source_note": "No version is available for testing.",
            "template_family": "unsupported",
            "policy_class": "unsupported",
            "sample_input_pretty": "{}",
            "sample_input_reasons": [],
            "test_input_note": "Builder could not derive a sample input because no published contract is available.",
        }
    review_view = _build_skill_review_view(version_row)
    metadata = version_row.get("metadata") or {}
    schema_obj = metadata.get("input_schema", {}) or {}
    sample_payload, sample_reasons = _sample_input_payload_and_reasons(skill_id, schema_obj)
    return {
        **review_view,
        "sample_input_pretty": json.dumps(sample_payload or {}, ensure_ascii=False, indent=2),
        "sample_input_reasons": sample_reasons,
        "test_input_note": (
            "Builder generates this starter payload from the normalized input schema by combining "
            "required fields, one preferred conditional selector, and optional defaults."
        ),
    }


def _build_skill_preview_context(preview_payload: dict) -> dict:
    skill = preview_payload.get("skill", {}) or {}
    version_row = dict(preview_payload.get("version", {}) or {})
    review_view = _build_skill_review_view(version_row)
    metadata = version_row.get("metadata") or {}
    schema_obj = metadata.get("input_schema", {}) or {}
    sample_payload, sample_reasons = _sample_input_payload_and_reasons(
        str(skill.get("id") or ""),
        schema_obj,
    )
    return {
        "skill": skill,
        "version": {
            **version_row,
            **review_view,
        },
        "sample_input_pretty": json.dumps(sample_payload or {}, ensure_ascii=False, indent=2),
        "sample_input_reasons": sample_reasons,
        "test_input_note": (
            "If you import this skill, Builder will use this normalized contract to generate "
            "test input from required fields, one preferred conditional selector, and optional defaults."
        ),
    }


def _preferred_skill_summary_version(skill_row: dict) -> dict | None:
    active_id = skill_row.get("current_active_version_id")
    if active_id:
        version_row = store.get_skill_version(str(active_id))
        if version_row:
            return version_row
    published_id = skill_row.get("current_published_version_id")
    if published_id:
        version_row = store.get_skill_version(str(published_id))
        if version_row:
            return version_row
    versions = store.list_skill_versions(skill_row["id"])
    return versions[0] if versions else None


def _build_skill_list_view() -> list[dict]:
    items = []
    for skill_row in store.list_skills():
        skill_view = dict(skill_row)
        summary_version = _preferred_skill_summary_version(skill_row)
        if summary_version:
            review_view = _build_skill_review_view(summary_version)
            skill_view.update(
                {
                    "summary_version": summary_version.get("version"),
                    "summary_state": summary_version.get("state"),
                    "template_family": review_view.get("template_family"),
                    "policy_class": review_view.get("policy_class"),
                    "risk_label": review_view.get("risk_label"),
                    "normalization_confidence": review_view.get("normalization_confidence"),
                    "normalization_confidence_note": review_view.get("normalization_confidence_note"),
                    "contract_source": review_view.get("contract_source"),
                    "has_contract": review_view.get("has_contract"),
                }
            )
        else:
            skill_view.update(
                {
                    "summary_version": None,
                    "summary_state": None,
                    "template_family": "unsupported",
                    "policy_class": "unsupported",
                    "risk_label": "Unsupported",
                    "normalization_confidence": "unsupported composition",
                    "normalization_confidence_note": "No skill version has been imported yet.",
                    "contract_source": "unsupported",
                    "has_contract": False,
                }
            )
        items.append(skill_view)
    return items


_NORMALIZATION_CONFIDENCE_ORDER = {
    "unsupported composition": 0,
    "explicit schema recommended": 1,
    "default family inference supported": 2,
    "high confidence first-class family": 3,
}


def _filter_and_sort_skill_list(
    items: list[dict],
    *,
    confidence: str,
    policy_class: str,
    sort_key: str,
) -> list[dict]:
    filtered = list(items)
    confidence_value = str(confidence or "").strip()
    policy_value = str(policy_class or "").strip()
    sort_value = str(sort_key or "confidence_desc").strip()

    if confidence_value:
        filtered = [
            item for item in filtered if str(item.get("normalization_confidence") or "") == confidence_value
        ]
    if policy_value:
        filtered = [
            item for item in filtered if str(item.get("policy_class") or "") == policy_value
        ]

    if sort_value == "name_asc":
        filtered.sort(key=lambda item: (str(item.get("name") or "").lower(), str(item.get("id") or "").lower()))
    elif sort_value == "name_desc":
        filtered.sort(key=lambda item: (str(item.get("name") or "").lower(), str(item.get("id") or "").lower()), reverse=True)
    else:
        filtered.sort(
            key=lambda item: (
                -_NORMALIZATION_CONFIDENCE_ORDER.get(str(item.get("normalization_confidence") or ""), -1),
                str(item.get("name") or "").lower(),
            )
        )
    return filtered


def _save_uploaded_skill_archive(uploaded_file) -> Path:
    _SKILL_IMPORT_UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    target = _SKILL_IMPORT_UPLOAD_ROOT / f"{uuid.uuid4()}_{_safe_filename(uploaded_file.filename)}"
    uploaded_file.save(target)
    return target


def _cleanup_uploaded_skill_archive(archive_path: Path) -> None:
    try:
        archive_path.unlink(missing_ok=True)
    except PermissionError:
        pass


def _uploaded_file_size(file_obj):
    try:
        pos = file_obj.stream.tell()
        file_obj.stream.seek(0, 2)
        size = file_obj.stream.tell()
        file_obj.stream.seek(pos)
        return int(size)
    except Exception:
        return 0


def _safe_filename(name: str) -> str:
    return Path(name or "").name.replace("\\", "_").replace("/", "_")


def _save_uploaded_file(uploaded_file, app_id: str, doc_id: str) -> Path:
    app_dir = _UPLOAD_ROOT / app_id
    app_dir.mkdir(parents=True, exist_ok=True)
    target = app_dir / f"{doc_id}_{_safe_filename(uploaded_file.filename)}"
    uploaded_file.save(target)
    return target


def _ingest_queued_doc(app_id: str, doc: dict):
    store.update_document_status(app_id, doc["id"], "ingesting")
    ingest_result = ingest_uploaded_file(app_id, doc, config=_current_process_config(), store=None)
    detected_language = None
    if isinstance(ingest_result, dict):
        detected_language = ingest_result.get("detected_language")
    if detected_language:
        store.update_document_language(app_id, doc["id"], detected_language)
    canceled = _is_cancel_requested(doc["id"])
    current = store.get_document(app_id, doc["id"]) or {}
    if canceled or (current.get("status") == "canceled"):
        try:
            delete_document_chunks(doc["id"], app_id, store=None)
        except Exception:
            pass
        store.update_document_status(app_id, doc["id"], "canceled", "Canceled by user.")
        _clear_cancel_request(doc["id"])
        return
    store.update_document_status(app_id, doc["id"], "ready")
    _clear_cancel_request(doc["id"])


def _request_cancel_doc(doc_id: str) -> None:
    with _ingest_cancel_lock:
        _ingest_cancel_doc_ids.add(doc_id)


def _clear_cancel_request(doc_id: str) -> None:
    with _ingest_cancel_lock:
        _ingest_cancel_doc_ids.discard(doc_id)


def _is_cancel_requested(doc_id: str) -> bool:
    with _ingest_cancel_lock:
        return doc_id in _ingest_cancel_doc_ids


def _mark_stale_ingesting_docs(app_id: str) -> int:
    with _ingest_jobs_lock:
        if app_id in _ingest_running_apps:
            return 0
    now = datetime.datetime.utcnow()
    updated = 0
    for doc in store.list_documents(app_id):
        if (doc.get("status") or "").lower() != "ingesting":
            continue
        uploaded_at = doc.get("uploaded_at")
        if not uploaded_at:
            continue
        try:
            started_at = datetime.datetime.fromisoformat(uploaded_at)
        except ValueError:
            continue
        age_seconds = (now - started_at).total_seconds()
        if age_seconds > _INGEST_STALE_SECONDS:
            store.update_document_status(
                app_id,
                doc["id"],
                "error",
                f"Ingest timed out after {_INGEST_STALE_SECONDS} seconds; please re-ingest.",
            )
            updated += 1
    return updated


def _run_ingest_pending_for_app(app_id: str) -> None:
    try:
        while True:
            pending_docs = [
                d for d in store.list_documents(app_id) if d.get("status") == "pending" and d.get("file_path")
            ]
            if not pending_docs:
                break
            doc = pending_docs[0]
            try:
                _ingest_queued_doc(app_id, doc)
            except Exception as exc:  # noqa: BLE001
                store.update_document_status(app_id, doc["id"], "error", str(exc))
    finally:
        with _ingest_jobs_lock:
            _ingest_running_apps.discard(app_id)


def _start_ingest_worker(app_id: str) -> bool:
    with _ingest_jobs_lock:
        if app_id in _ingest_running_apps:
            return False
        _ingest_running_apps.add(app_id)
    worker = threading.Thread(target=_run_ingest_pending_for_app, args=(app_id,), daemon=True)
    worker.start()
    return True


def _queue_selected_files(app_id: str, uploaded_files, language: str, tags: list[str]):
    queued_docs = []
    errors = []
    schema = DocumentUploadSchema()

    for uploaded in uploaded_files:
        original_name = _safe_filename(uploaded.filename)
        payload = {
            "filename": original_name,
            "mime_type": uploaded.mimetype or "application/octet-stream",
            "size_bytes": _uploaded_file_size(uploaded),
            "language": language,
            "tags": tags,
        }
        valid, file_errors = schema.validate(payload)
        if not valid:
            errors.extend(file_errors)
            continue

        queued = store.queue_document(app_id, payload)
        if not queued:
            errors.append(validation_error("files", f"{original_name}: queue failed", "queue_failed"))
            continue

        try:
            saved_path = _save_uploaded_file(uploaded, app_id, queued["id"])
            queued = store.update_document_file_path(app_id, queued["id"], str(saved_path))
            queued_docs.append(queued)
        except Exception as exc:  # noqa: BLE001
            store.update_document_status(app_id, queued["id"], "error", str(exc))
            errors.append(validation_error("files", f"{original_name}: {exc}", "save_failed"))

    return queued_docs, errors


def _delete_local_file(file_path: str | None) -> None:
    if not file_path:
        return
    path = Path(file_path)
    if path.exists():
        path.unlink()


def _delete_app_artifacts(app_id: str) -> list[str]:
    warnings = []
    docs = store.list_documents(app_id)
    for doc in docs:
        try:
            delete_document_chunks(doc["id"], app_id, store=None)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"vector cleanup failed for {doc.get('filename')}: {exc}")
        try:
            _delete_local_file(doc.get("file_path"))
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"local file cleanup failed for {doc.get('filename')}: {exc}")

    instructions_dir = Path(store.db_path).parent / "instructions" / app_id
    if instructions_dir.exists():
        try:
            for child in instructions_dir.glob("**/*"):
                if child.is_file():
                    child.unlink()
            for child in sorted(instructions_dir.glob("**/*"), reverse=True):
                if child.is_dir():
                    child.rmdir()
            instructions_dir.rmdir()
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"instructions cleanup failed: {exc}")

    upload_dir = _UPLOAD_ROOT / app_id
    if upload_dir.exists():
        try:
            for child in upload_dir.glob("**/*"):
                if child.is_file():
                    child.unlink()
            for child in sorted(upload_dir.glob("**/*"), reverse=True):
                if child.is_dir():
                    child.rmdir()
            upload_dir.rmdir()
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"upload directory cleanup failed: {exc}")

    return warnings


def run_retrieve(query_text, top_k, filters, app_id):
    merged_filters = dict(filters or {})
    merged_filters["app_id"] = app_id
    future = _retrieval_pool.submit(
        retrieve_data,
        query_text=query_text,
        top_k=top_k,
        filters=merged_filters,
        config=_current_retrieval_config(),
        store=None,
        embed_client=None,
        router=None,
    )
    try:
        return future.result(timeout=3)
    except TimeoutError as exc:
        raise TimeoutError("Retrieval timed out after 3 seconds") from exc


def _serialize_retrieval_result(retrieval_result):
    items = []
    raw_results = getattr(retrieval_result, "results", []) or []
    for candidate in raw_results:
        chunk = getattr(candidate, "chunk", None)
        metadata = getattr(chunk, "metadata", {}) if chunk else {}
        items.append(
            {
                "score": round(float(getattr(candidate, "score", 0.0)), 6),
                "source": getattr(candidate, "source", "unknown"),
                "text": getattr(chunk, "text", ""),
                "doc_id": getattr(chunk, "doc_id", None),
                "chunk_id": getattr(chunk, "chunk_id", None),
                "filename": metadata.get("filename"),
                "metadata": metadata,
            }
        )
    return items, getattr(retrieval_result, "debug", {}) or {}


@app.context_processor
def inject_globals():
    return {
        "nav_apps": store.list_applications(),
        "nav_skills": store.list_skills(),
        "now": datetime.datetime.utcnow(),
    }


@app.route("/")
def root():
    return redirect(url_for("apps"))


@app.route("/apps")
def apps():
    return render_template("apps.html", apps=store.list_applications())


@app.route("/skills")
def skills():
    filters = {
        "confidence": (request.args.get("confidence") or "").strip(),
        "policy_class": (request.args.get("policy_class") or "").strip(),
        "sort": (request.args.get("sort") or "confidence_desc").strip(),
    }
    skills_view = _filter_and_sort_skill_list(
        _build_skill_list_view(),
        confidence=filters["confidence"],
        policy_class=filters["policy_class"],
        sort_key=filters["sort"],
    )
    return render_template("skills_list.html", skills=skills_view, filters=filters)


@app.route("/agent-skills")
def agent_skills():
    source_options, source_options_error = _agent_skill_source_options()
    display_options = [
        {
            "index": index,
            "backend": option["backend"],
            "source_kind": option["source_kind"],
            "display_name": option["display_name"],
            "runtime_target_id": option["runtime_target_id"],
        }
        for index, option in enumerate(source_options)
    ]
    sources = sorted(
        [_public_agent_skill_source(item) for item in store.list_agent_skill_sources()],
        key=lambda item: (item["display_name"].casefold(), item["id"]),
    )
    catalog_view = (request.args.get("catalog_view") or "active").strip()
    source_id = catalog_view.split(":", 1)[1] if catalog_view.startswith("source:") else None
    normalized_view = "source" if source_id else catalog_view
    if normalized_view not in {"active", "source", "disabled"}:
        abort(404)
    if source_id and not store.get_agent_skill_source(source_id):
        abort(404)
    publication_preview = build_publication_preview(
        store=store, builder_instance_id=_agent_skill_builder_instance_id()
    )
    return render_template(
        "agent_skills.html",
        sources=sources,
        agent_skills=[
            _public_agent_skill(item)
            for item in store.list_agent_skill_catalog_view(view=normalized_view, source_id=source_id)
        ],
        catalog_view=catalog_view,
        source_options=display_options,
        source_options_error=source_options_error,
        projection_state=store.get_agent_skill_projection_state(),
        publication_preview=publication_preview,
    )


@app.route("/agent-skill-sources", methods=["POST"])
def create_agent_skill_source_form():
    options, error = _agent_skill_source_options()
    try:
        option_index = int(request.form.get("source_option_index", "-1"))
        if error or option_index < 0 or option_index >= len(options):
            raise ValueError(error or "Select a configured Agent skill source")
        option = options[option_index]
        store.create_agent_skill_source(
            backend=option["backend"],
            source_kind=option["source_kind"],
            display_name=(request.form.get("display_name") or option["display_name"]).strip(),
            runtime_target_id=option["runtime_target_id"],
            protected_locator_ref=option["protected_locator_ref"],
            precedence=int(option["precedence"]),
            actor_id=_agent_skill_actor_id(),
        )
    except (ValueError, TypeError) as exc:
        return jsonify({"errors": [validation_error("source", str(exc), "invalid")]}), 422
    return redirect(url_for("agent_skills"))


@app.route("/agent-skill-sources/<source_id>/discover", methods=["POST"])
def discover_agent_skill_source_form(source_id):
    items, error = _discover_agent_skill_source(source_id)
    if error:
        return jsonify(error[0]), error[1]
    return redirect(url_for(
        "agent_skills",
        catalog_view=request.form.get("catalog_view") or f"source:{source_id}",
    ))


@app.route("/agent-skill-sources/<source_id>/toggle", methods=["POST"])
def toggle_agent_skill_source_form(source_id):
    try:
        expected_raw = (request.form.get("expected_local_revision") or "").strip()
        store.update_agent_skill_source(
            source_id,
            enabled=(request.form.get("enabled") or "").strip().lower() == "true",
            actor_id=_agent_skill_actor_id(),
            expected_local_revision=int(expected_raw) if expected_raw else None,
        )
    except ValueError as exc:
        status = 409 if str(exc) == "AGENT_SKILL_LOCAL_REVISION_STALE" else 422
        return jsonify({"errors": [validation_error("source", str(exc), "invalid")]}), status
    return redirect(url_for("agent_skills", catalog_view=request.form.get("catalog_view") or "active"))


@app.route("/agent-skill-sources/<source_id>/disable-review")
def agent_skill_source_disable_review(source_id):
    source = store.get_agent_skill_source(source_id)
    if not source:
        abort(404)
    return render_template(
        "agent_skill_source_disable_review.html",
        source=_public_agent_skill_source(source),
        impact=store.get_agent_skill_source_impact(source_id),
        projection_state=store.get_agent_skill_projection_state(),
    )


@app.route("/agent-skills/publication-review")
def agent_skill_publication_review():
    preview = build_publication_preview(
        store=store, builder_instance_id=_agent_skill_builder_instance_id()
    )
    return render_template(
        "agent_skill_publication_review.html",
        **_agent_skill_publication_review_context(preview),
    )


@app.route("/agent-skills/publications", methods=["POST"])
def publish_agent_skills_form():
    supplied_csrf = str(request.form.get("csrf_token") or "")
    if not hmac.compare_digest(supplied_csrf, _agent_skill_publication_csrf_token()):
        return jsonify({
            "error": {
                "code": "BUILDER_PUBLICATION_CSRF_INVALID",
                "message": "Publication form validation failed. Reload the review page.",
            }
        }), 403
    try:
        expected_revision = int(request.form.get("expected_local_revision", ""))
        result = publish_agent_skill_revision(
            store=store,
            execution_client=_agent_skill_execution_client(),
            builder_instance_id=_agent_skill_builder_instance_id(),
            expected_local_revision=expected_revision,
            actor_id=_agent_skill_actor_id(),
            correlation_id=_agent_skill_publication_correlation_id(),
        )
    except (TypeError, ValueError) as exc:
        preview = build_publication_preview(
            store=store, builder_instance_id=_agent_skill_builder_instance_id()
        )
        status = 409 if isinstance(exc, PublicationRevisionStale) else 422
        result = {
            "ok": False,
            "state": preview["state"],
            "error": {
                "code": getattr(exc, "code", "PUBLICATION_REQUEST_INVALID"),
                "message": str(exc),
            },
        }
        return (
            render_template(
                "agent_skill_publication_review.html",
                **_agent_skill_publication_review_context(preview, result),
            ),
            status,
        )
    preview = build_publication_preview(
        store=store, builder_instance_id=_agent_skill_builder_instance_id()
    )
    return (
        render_template(
            "agent_skill_publication_review.html",
            **_agent_skill_publication_review_context(preview, result),
        ),
        200 if result["ok"] else 502,
    )


@app.route("/agent-skills/<agent_skill_id>")
def agent_skill_detail(agent_skill_id):
    skill = store.get_agent_skill_catalog_item(agent_skill_id)
    if not skill:
        abort(404)
    bindings = []
    apps_by_id = {item["id"]: item for item in store.list_applications()}
    for app_id, app_obj in apps_by_id.items():
        for binding in store.list_app_agent_skill_bindings(app_id):
            if binding["agent_skill_id"] == agent_skill_id:
                bindings.append({**binding, "app_name": app_obj["name"]})
    interaction_recommendation = build_agent_skill_interaction_recommendation(skill)
    selected_interaction_policy = interaction_recommendation["policy"]
    if skill.get("approval"):
        approval = skill["approval"]
        selected_interaction_policy = {
            "interaction_channel": approval["interaction_channel"],
            "interaction_requirement": approval["interaction_requirement"],
            "supported_interaction_types": json.loads(
                approval["supported_interaction_types_json"]
            ),
            "required_transport": approval["required_transport"],
            "recovery_class": approval["recovery_class"],
        }
    return render_template(
        "agent_skill_detail.html",
        agent_skill=_public_agent_skill(skill),
        bindings=bindings,
        apps=list(apps_by_id.values()),
        projection_state=store.get_agent_skill_projection_state(),
        interaction_recommendation=interaction_recommendation,
        selected_interaction_policy=selected_interaction_policy,
    )


@app.route("/agent-skills/<agent_skill_id>/approve", methods=["POST"])
def approve_agent_skill_form(agent_skill_id):
    try:
        skill = store.get_agent_skill_catalog_item(agent_skill_id)
        if not skill:
            abort(404)
        interaction_policy = interaction_policy_from_form(
            request.form, backend=skill["backend"]
        )
        store.approve_agent_skill(
            agent_skill_id=agent_skill_id,
            expected_fingerprint=(request.form.get("expected_fingerprint") or "").strip(),
            approved_by=_agent_skill_actor_id(),
            review_notes=(request.form.get("review_notes") or "").strip(),
            interaction_policy=interaction_policy,
        )
    except ValueError as exc:
        status = 409 if str(exc) == "AGENT_SKILL_FINGERPRINT_CHANGED" else 422
        return jsonify({"errors": [validation_error("approval", str(exc), "invalid")]}), status
    return redirect(url_for("agent_skill_detail", agent_skill_id=agent_skill_id))


@app.route("/agent-skills/<agent_skill_id>/revoke", methods=["POST"])
def revoke_agent_skill_form(agent_skill_id):
    try:
        store.revoke_agent_skill(
            agent_skill_id=agent_skill_id,
            actor_id=_agent_skill_actor_id(),
            review_notes=(request.form.get("review_notes") or "").strip(),
        )
    except ValueError as exc:
        return jsonify({"errors": [validation_error("approval", str(exc), "invalid")]}), 422
    return redirect(url_for("agent_skill_detail", agent_skill_id=agent_skill_id))


@app.route("/agent-skills/<agent_skill_id>/bind", methods=["POST"])
def bind_agent_skill_form(agent_skill_id):
    try:
        store.create_app_agent_skill_binding(
            app_id=(request.form.get("app_id") or "").strip(),
            agent_skill_id=agent_skill_id,
            created_by=_agent_skill_actor_id(),
        )
    except ValueError as exc:
        return jsonify({"errors": [validation_error("binding", str(exc), "invalid")]}), 422
    return redirect(url_for("agent_skill_detail", agent_skill_id=agent_skill_id))


@app.route("/agent-skills/<agent_skill_id>/bindings/<binding_id>/toggle", methods=["POST"])
def toggle_agent_skill_binding_form(agent_skill_id, binding_id):
    binding = store.get_app_agent_skill_binding(binding_id)
    if not binding or binding["agent_skill_id"] != agent_skill_id:
        abort(404)
    store.update_app_agent_skill_binding(
        binding_id,
        enabled=(request.form.get("enabled") or "").strip().lower() == "true",
        actor_id=_agent_skill_actor_id(),
    )
    return redirect(url_for("agent_skill_detail", agent_skill_id=agent_skill_id))


@app.route("/agent-skills/<agent_skill_id>/bindings/<binding_id>/delete", methods=["POST"])
def delete_agent_skill_binding_form(agent_skill_id, binding_id):
    binding = store.get_app_agent_skill_binding(binding_id)
    if not binding or binding["agent_skill_id"] != agent_skill_id:
        abort(404)
    store.delete_app_agent_skill_binding(binding_id, actor_id=_agent_skill_actor_id())
    return redirect(url_for("agent_skill_detail", agent_skill_id=agent_skill_id))


@app.route("/agent-skills/synchronize", methods=["POST"])
def synchronize_agent_skills_form():
    try:
        synchronize_agent_skill_projection(
            store,
            _agent_skill_execution_client(),
            _agent_skill_builder_instance_id(),
        )
    except (ValueError, OSError) as exc:
        return jsonify({"errors": [validation_error("synchronization", str(exc), "invalid")]}), 502
    return redirect(url_for("agent_skills"))


@app.route("/skills/import", methods=["GET", "POST"])
def import_skill():
    errors = []
    preview = None
    if request.method == "POST":
        archive = request.files.get("archive")
        scope = (request.form.get("scope") or "managed").strip().lower()
        action = (request.form.get("action") or "import").strip().lower()
        if not archive or not archive.filename:
            errors.append(validation_error("archive", "Skill archive is required", "required"))
        else:
            archive_path = _save_uploaded_skill_archive(archive)
            try:
                if action == "preview":
                    preview = _build_skill_preview_context(
                        store.preview_skill_package(
                            archive_path=archive_path,
                            scope=scope,
                        )
                    )
                else:
                    imported = store.import_skill_package(
                        archive_path=archive_path,
                        scope=scope,
                        import_source="upload",
                    )
                    return redirect(url_for("skill_detail", skill_id=imported["skill"]["id"]))
            except ValueError as exc:
                errors.append(validation_error("archive", str(exc), "invalid"))
            finally:
                _cleanup_uploaded_skill_archive(archive_path)
    return render_template("skills_import.html", errors=errors, preview=preview)


@app.route("/skills/<skill_id>")
def skill_detail(skill_id):
    skill = parse_skill(skill_id)
    versions = []
    for version in store.list_skill_versions(skill_id):
        version_view = dict(version)
        version_view.update(_build_skill_review_view(version_view))
        versions.append(version_view)
    all_bindings = store.list_skill_bindings(skill_id)
    return render_template(
        "skill_detail.html",
        skill=skill,
        versions=versions,
        bindings=all_bindings,
        apps=store.list_applications(),
    )


@app.route("/skills/<skill_id>/versions/<version_id>/publish", methods=["POST"])
def publish_skill_version(skill_id, version_id):
    parse_skill(skill_id)
    try:
        store.publish_skill_version(version_id)
    except ValueError as exc:
        return jsonify({"errors": [validation_error("version", str(exc), "invalid")]}), 422
    return redirect(url_for("skill_detail", skill_id=skill_id))


@app.route("/skills/<skill_id>/delete", methods=["POST"])
def delete_skill(skill_id):
    parse_skill(skill_id)
    deleted = store.delete_skill(skill_id)
    if not deleted:
        abort(404)
    return redirect(url_for("skills"))


@app.route("/skills/<skill_id>/bind", methods=["POST"])
def bind_skill(skill_id):
    parse_skill(skill_id)
    app_id = (request.form.get("app_id") or "").strip()
    skill_version = (request.form.get("skill_version") or "").strip()
    permission_mode = (request.form.get("permission_mode") or "blocked").strip()
    execution_policy = {
        "allowAsync": bool(request.form.get("allow_async")),
        "allowRetries": bool(request.form.get("allow_retries")),
        "requireApproval": bool(request.form.get("require_approval")),
    }
    try:
        store.create_app_skill_binding(
            app_id=app_id,
            skill_id=skill_id,
            skill_version=skill_version,
            permission_mode=permission_mode,
            execution_policy=execution_policy,
        )
    except ValueError as exc:
        return jsonify({"errors": [validation_error("binding", str(exc), "invalid")]}), 422
    return redirect(url_for("skill_detail", skill_id=skill_id))


@app.route("/skills/<skill_id>/test", methods=["GET", "POST"])
def test_skill(skill_id):
    skill = parse_skill(skill_id)
    versions = store.list_skill_versions(skill_id)
    selected_version = (request.values.get("skill_version") or "").strip()
    app_id = (request.values.get("app_id") or "").strip()
    test_context = _build_skill_test_context(skill_id, selected_version)
    result = None
    input_json = request.values.get("input_json")
    if input_json is None or str(input_json).strip() == "{}":
        input_json = test_context["sample_input_pretty"]
    request_payload = {
        "session_id": request.values.get("session_id", f"builder-test-{uuid.uuid4().hex[:8]}"),
        "input_json": input_json,
        "dry_run": bool(request.values.get("dry_run")),
        "require_confirmation": bool(request.values.get("require_confirmation")),
    }
    errors = []

    if request.method == "POST":
        bindings = [b for b in store.list_app_skill_bindings(app_id) if b["skill_id"] == skill_id and b["enabled"]]
        if not bindings:
            errors.append(validation_error("app_id", "Selected app is not bound to this skill", "binding_missing"))
        else:
            try:
                input_payload = json.loads(request_payload["input_json"])
                exec_payload = {
                    "request_type": "execute_skill",
                    "app_id": app_id,
                    "session_id": request_payload["session_id"],
                    "skill_id": skill_id,
                    "input": input_payload,
                    "execution_options": {
                        "dry_run": request_payload["dry_run"],
                        "require_confirmation": request_payload["require_confirmation"],
                    },
                }
                result = _execution_client().execute_skill(exec_payload)
            except json.JSONDecodeError:
                errors.append(validation_error("input_json", "Input must be valid JSON", "json"))

    return render_template(
        "skill_test.html",
        skill=skill,
        versions=versions,
        selected_version=selected_version,
        selected_app_id=app_id,
        request_payload=request_payload,
        result=result,
        errors=errors,
        apps=store.list_applications(),
        test_context=test_context,
    )


@app.route("/admin/subsystem")
def subsystem_settings():
    export_status = (request.args.get("tools_info_export") or "").strip().lower()
    export_path = (request.args.get("tools_info_path") or "").strip()
    return render_template(
        "subsystem_settings.html",
        subsystem=_global_subsystem_settings_view(),
        runtime_inventory=_runtime_inventory_view(),
        tools_info_export_status=export_status,
        tools_info_export_path=export_path,
    )


@app.route("/admin/subsystem/tools-info/export", methods=["POST"])
def export_tools_info():
    client = _execution_client()
    inventory_response = client.get_tool_inventory()
    body = inventory_response.get("body", {}) if isinstance(inventory_response, dict) else {}
    status_code = inventory_response.get("status_code") if isinstance(inventory_response, dict) else None
    inventory_items = body.get("items", []) if isinstance(body, dict) else []
    if (
        not isinstance(inventory_response, dict)
        or not inventory_response.get("ok", False)
        or not isinstance(inventory_items, list)
    ):
        written_path = write_tools_info_failure_markdown(
            _TOOLS_INFO_EXPORT_PATH,
            base_url=getattr(
                client,
                "base_url",
                os.environ.get("RAGENIUS_EXECUTION_BASE_URL", _DEFAULT_EXECUTION_BASE_URL),
            ),
            status_code=status_code,
            error=body.get("error") if isinstance(body, dict) else None,
        )
        relative_path = written_path.relative_to(Path(__file__).resolve().parents[2]).as_posix()
        return redirect(
            url_for(
                "subsystem_settings",
                tools_info_export="written",
                tools_info_path=relative_path,
            )
        )

    written_path = write_tools_info_markdown(_TOOLS_INFO_EXPORT_PATH, inventory_items)
    relative_path = written_path.relative_to(Path(__file__).resolve().parents[2]).as_posix()
    return redirect(
        url_for(
            "subsystem_settings",
            tools_info_export="written",
            tools_info_path=relative_path,
        )
    )


@app.route("/admin/subsystem/mcp/providers/<provider_id>/refresh", methods=["POST"])
def refresh_mcp_provider(provider_id):
    response = _execution_client().refresh_mcp_provider(provider_id)
    body = response.get("body", {}) if isinstance(response, dict) else {}
    status_code = response.get("status_code", 200) if isinstance(response, dict) else 200
    if (request.form.get("redirect_to") or "").strip() == "subsystem":
        return redirect(url_for("subsystem_settings"))
    return jsonify(body), status_code


@app.route("/apps/new", methods=["GET", "POST"])
def new_app():
    if request.method == "POST":
        payload = request.form.to_dict(flat=True)
        payload["starter_questions"] = [
            request.form.get(f"starter_questions[{i}]") or "" for i in range(4)
        ]
        schema = ApplicationSchema()
        valid, errors = schema.validate(payload)
        if not valid:
            return render_template("new_app.html", errors=errors, values=payload), 422
        created = store.create_application(payload)
        if not created:
            errors.append({"path": "slug", "msg": "Slug must be unique", "code": "conflict"})
            return render_template("new_app.html", errors=errors, values=payload), 409
        return redirect(url_for("view_app", app_id=created["id"]))
    return render_template("new_app.html", errors={}, values={})


@app.route("/apps/<app_id>")
def view_app(app_id):
    app_obj = parse_app(app_id)
    docs = store.list_documents(app_id)
    agent_skills_by_id = {
        item["id"]: _public_agent_skill(item)
        for item in store.list_agent_skill_catalog()
    }
    agent_skill_bindings = [
        {
            **binding,
            "agent_skill": agent_skills_by_id.get(binding["agent_skill_id"]),
        }
        for binding in store.list_app_agent_skill_bindings(app_id)
    ]
    return render_template(
        "app_detail.html",
        app=app_obj,
        docs=docs,
        agent_skill_bindings=agent_skill_bindings,
    )


@app.route("/apps/<app_id>/config", methods=["GET", "POST"])
def app_config(app_id):
    app_obj = parse_app(app_id)
    tab = request.args.get("tab", "instructions")
    errors = []
    saved = False

    if request.method == "POST":
        if tab == "instructions":
            schema = InstructionsSchema()
            payload = {
                "content": _normalize_instruction_markdown(request.form.get("content", "")),
                "version": request.form.get("version", ""),
                "uri": request.form.get("uri", ""),
            }
            valid, errors = schema.validate(payload)
            if valid:
                store.update_instructions(app_id, payload)
                saved = True
        else:
            schema = SettingsSchema()
            payload = {
                "config_settings": request.form.get("config_settings", ""),
                "config_schema": request.form.get("config_schema", ""),
            }
            valid, errors = schema.validate(payload)
            if valid:
                store.update_settings(app_id, payload)
                saved = True

    instructions = store.get_instructions(app_id)
    settings = store.get_settings(app_id)
    if request.method == "POST" and tab == "settings":
        settings = {
            "config_settings": request.form.get("config_settings", ""),
            "config_schema": request.form.get("config_schema", ""),
            "updated_at": (settings or {}).get("updated_at", ""),
        }
    instructions_payload = instructions or {"content": "", "version": "", "uri": ""}
    if request.method == "POST" and tab == "instructions":
        instructions_payload = {
            "content": request.form.get("content", ""),
            "version": request.form.get("version", ""),
            "uri": request.form.get("uri", ""),
        }
    resource_validation = _validate_instruction_resources(app_id, instructions_payload.get("content", ""))
    schema_obj = _safe_json_loads((settings or {}).get("config_schema"), {})
    if not (schema_obj.get("properties") if isinstance(schema_obj, dict) else None):
        store.update_settings(
            app_id,
            {
                "config_settings": json.dumps(DEFAULT_APP_CONFIG_SETTINGS, ensure_ascii=False, indent=2),
                "config_schema": json.dumps(DEFAULT_APP_CONFIG_SCHEMA, ensure_ascii=False, indent=2),
            },
        )
        settings = store.get_settings(app_id)
        schema_obj = _safe_json_loads((settings or {}).get("config_schema"), {})
    settings_obj = _safe_json_loads((settings or {}).get("config_settings"), {})
    settings_rows = [
        row for row in _collect_schema_rows(schema_obj.get("properties", {}), settings_obj)
        if not str(row.get("key_path", "")).startswith("llm.")
    ]
    llm_editor = _build_llm_settings_editor(schema_obj, settings_obj)
    return render_template(
        "config.html",
        app=app_obj,
        tab=tab,
        instructions=instructions,
        instruction_resource_validation=resource_validation,
        settings=settings,
        settings_rows=settings_rows,
        llm_editor=llm_editor,
        errors=errors,
        saved=saved,
    )


@app.route("/apps/<app_id>/upload", methods=["GET", "POST"])
def upload(app_id):
    app_obj = parse_app(app_id)
    errors = []
    notice = request.args.get("notice", "")
    stale_fixed = _mark_stale_ingesting_docs(app_id)
    if stale_fixed > 0 and not notice:
        notice = f"Recovered {stale_fixed} stale ingesting file(s). They are marked as error for retry."
    if request.method == "POST":
        action = request.form.get("action", "queue").strip().lower()
        uploaded_files = [f for f in request.files.getlist("files") if f and f.filename]
        tags = [t.strip() for t in request.form.get("tags", "").split(",") if t.strip()]
        language = request.form.get("language", "en")

        if uploaded_files:
            queued_docs, queue_errors = _queue_selected_files(app_id, uploaded_files, language, tags)
            errors.extend(queue_errors)
            if action == "ingest":
                for queued in queued_docs:
                    try:
                        _ingest_queued_doc(app_id, queued)
                    except Exception as exc:  # noqa: BLE001
                        store.update_document_status(app_id, queued["id"], "error", str(exc))
                        errors.append(validation_error("files", f"{queued.get('filename')}: {exc}", "ingest_failed"))
            if not errors:
                return redirect(url_for("upload", app_id=app_id))
        elif action == "ingest":
            pending_docs = [d for d in store.list_documents(app_id) if d.get("status") == "pending" and d.get("file_path")]
            if not pending_docs:
                errors.append(validation_error("files", "No pending queued files to ingest", "nothing_to_ingest"))
            else:
                started = _start_ingest_worker(app_id)
                if started:
                    return redirect(
                        url_for(
                            "upload",
                            app_id=app_id,
                            notice=f"Ingest started for {len(pending_docs)} pending file(s). Progress will auto-refresh.",
                        )
                    )
                return redirect(
                    url_for(
                        "upload",
                        app_id=app_id,
                        notice="Ingest is already running for this application. Progress will auto-refresh.",
                    )
                )
        else:
            schema = DocumentUploadSchema()
            payload = request.form.to_dict(flat=True)
            payload["tags"] = tags
            valid, errors = schema.validate(payload)
            if valid:
                store.queue_document(app_id, payload)
                return redirect(url_for("upload", app_id=app_id))
    queue = store.list_documents(app_id)
    status_counts = defaultdict(int)
    for doc in queue:
        status_counts[(doc.get("status") or "unknown")] += 1
    has_ingesting = status_counts.get("ingesting", 0) > 0
    return render_template(
        "upload.html",
        app=app_obj,
        errors=errors,
        queue=queue,
        notice=notice,
        status_counts=dict(status_counts),
        has_ingesting=has_ingesting,
    )


@app.route("/apps/<app_id>/docs")
def documents(app_id):
    app_obj = parse_app(app_id)
    docs = store.list_documents(app_id)
    return render_template("documents.html", app=app_obj, docs=docs)


@app.route("/apps/<app_id>/docs/<doc_id>")
def document_detail(app_id, doc_id):
    app_obj = parse_app(app_id)
    doc = store.get_document(app_id, doc_id)
    if not doc:
        abort(404)
    return render_template("document_detail.html", app=app_obj, doc=doc)


@app.route("/apps/<app_id>/search", methods=["GET", "POST"])
def search(app_id):
    app_obj = parse_app(app_id)
    results = []
    debug = {}
    error = None
    query_text = ""
    if request.method == "POST":
        query_text = request.form.get("query", "").strip()
        if query_text:
            try:
                retrieval_result = run_retrieve(
                    query_text=query_text,
                    top_k=12,
                    filters={},
                    app_id=app_id,
                )
                results, debug = _serialize_retrieval_result(retrieval_result)
            except TimeoutError as exc:
                error = str(exc)
            except Exception as exc:  # noqa: BLE001
                error = str(exc)
    return render_template(
        "search.html", app=app_obj, results=results, debug=debug, error=error, query=query_text
    )


@app.route("/api/apps")
def api_list_apps():
    return jsonify(store.list_applications())


@app.route("/api/skills")
def api_list_skills():
    return jsonify({"items": store.list_skills()})


@app.route("/api/agent-skill-sources")
def api_list_agent_skill_sources():
    return jsonify({
        "items": [
            _public_agent_skill_source(item)
            for item in store.list_agent_skill_sources()
        ]
    })


@app.route("/api/agent-skill-sources", methods=["POST"])
def api_create_agent_skill_source():
    data = request.get_json(force=True, silent=True) or {}
    try:
        option = _match_agent_skill_source_option(data)
        created = store.create_agent_skill_source(
            backend=option["backend"],
            source_kind=option["source_kind"],
            display_name=str(data.get("display_name") or option["display_name"]).strip(),
            runtime_target_id=option["runtime_target_id"],
            protected_locator_ref=option["protected_locator_ref"],
            precedence=int(option["precedence"]),
            enabled=bool(data.get("enabled", True)),
            actor_id=_agent_skill_actor_id(),
            correlation_id=request.headers.get("X-Request-Id"),
        )
    except (ValueError, TypeError) as exc:
        return jsonify({"error": {"code": "INVALID_AGENT_SKILL_SOURCE", "message": str(exc)}}), 422
    return jsonify(_public_agent_skill_source(created)), 201


@app.route("/api/agent-skill-sources/<source_id>", methods=["PATCH"])
def api_update_agent_skill_source(source_id):
    data = request.get_json(force=True, silent=True) or {}
    try:
        precedence = None
        if data.get("precedence") is not None:
            source = store.get_agent_skill_source(source_id)
            if not source:
                raise ValueError("Agent skill source not found")
            option = _match_agent_skill_source_option(source)
            precedence = int(data["precedence"])
            if precedence != int(option["precedence"]):
                raise ValueError(
                    "Agent skill source precedence is owned by the execution subsystem"
                )
            precedence = int(option["precedence"])
        updated = store.update_agent_skill_source(
            source_id,
            display_name=data.get("display_name"),
            precedence=precedence,
            enabled=data.get("enabled"),
            actor_id=_agent_skill_actor_id(),
            correlation_id=request.headers.get("X-Request-Id"),
        )
    except (ValueError, TypeError) as exc:
        status = 404 if str(exc) == "Agent skill source not found" else 422
        return jsonify({"error": {"code": "INVALID_AGENT_SKILL_SOURCE", "message": str(exc)}}), status
    return jsonify(_public_agent_skill_source(updated))


@app.route("/api/agent-skill-sources/<source_id>/discover", methods=["POST"])
def api_discover_agent_skill_source(source_id):
    try:
        items, error = _discover_agent_skill_source(source_id)
    except (ValueError, OSError) as exc:
        return jsonify({"error": {"code": "AGENT_SKILL_DISCOVERY_FAILED", "message": str(exc)}}), 502
    if error:
        return jsonify(error[0]), error[1]
    return jsonify({"items": [_public_agent_skill(item) for item in items]})


@app.route("/api/agent-skills")
def api_list_agent_skills():
    source_id = (request.args.get("source_id") or "").strip() or None
    return jsonify({
        "items": [
            _public_agent_skill(item)
            for item in store.list_agent_skill_catalog(source_id)
        ],
        "projection_state": store.get_agent_skill_projection_state(),
    })


@app.route("/api/agent-skills/<agent_skill_id>")
def api_agent_skill_detail(agent_skill_id):
    skill = store.get_agent_skill_catalog_item(agent_skill_id)
    if not skill:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "Agent skill not found."}}), 404
    return jsonify(_public_agent_skill(skill))


@app.route("/api/agent-skills/<agent_skill_id>/approve", methods=["POST"])
def api_approve_agent_skill(agent_skill_id):
    data = request.get_json(force=True, silent=True) or {}
    try:
        approval = store.approve_agent_skill(
            agent_skill_id=agent_skill_id,
            expected_fingerprint=str(data.get("expected_fingerprint") or "").strip(),
            approved_by=_agent_skill_actor_id(),
            review_notes=str(data.get("review_notes") or "").strip(),
            interaction_policy=data.get("interaction_policy"),
            correlation_id=request.headers.get("X-Request-Id"),
        )
    except ValueError as exc:
        code = str(exc)
        status = 409 if code == "AGENT_SKILL_FINGERPRINT_CHANGED" else 422
        return jsonify({"error": {"code": code, "message": str(exc)}}), status
    return jsonify({
        "id": approval["id"],
        "agent_skill_id": approval["agent_skill_id"],
        "approved_fingerprint": approval["approved_fingerprint"],
        "interaction_policy": {
            "interaction_channel": approval["interaction_channel"],
            "interaction_requirement": approval["interaction_requirement"],
            "supported_interaction_types": json.loads(
                approval["supported_interaction_types_json"]
            ),
            "required_transport": approval["required_transport"],
            "recovery_class": approval["recovery_class"],
        },
        "state": approval["state"],
        "approved_at": approval["approved_at"],
    })


@app.route("/api/agent-skills/<agent_skill_id>/revoke", methods=["POST"])
def api_revoke_agent_skill(agent_skill_id):
    data = request.get_json(force=True, silent=True) or {}
    try:
        approval = store.revoke_agent_skill(
            agent_skill_id=agent_skill_id,
            actor_id=_agent_skill_actor_id(),
            review_notes=str(data.get("review_notes") or "").strip(),
            correlation_id=request.headers.get("X-Request-Id"),
        )
    except ValueError as exc:
        return jsonify({"error": {"code": "INVALID_AGENT_SKILL", "message": str(exc)}}), 422
    return jsonify({
        "id": approval["id"],
        "agent_skill_id": approval["agent_skill_id"],
        "approved_fingerprint": approval["approved_fingerprint"],
        "state": approval["state"],
        "approved_at": approval["approved_at"],
    })


@app.route("/api/apps/<app_id>/agent-skill-bindings")
def api_list_app_agent_skill_bindings(app_id):
    if not store.get_application(app_id):
        return jsonify({"error": {"code": "NOT_FOUND", "message": "Application not found."}}), 404
    return jsonify({"items": store.list_app_agent_skill_bindings(app_id)})


@app.route("/api/apps/<app_id>/agent-skill-bindings", methods=["POST"])
def api_create_app_agent_skill_binding(app_id):
    data = request.get_json(force=True, silent=True) or {}
    try:
        binding = store.create_app_agent_skill_binding(
            app_id=app_id,
            agent_skill_id=str(data.get("agent_skill_id") or "").strip(),
            enabled=bool(data.get("enabled", True)),
            created_by=_agent_skill_actor_id(),
            correlation_id=request.headers.get("X-Request-Id"),
        )
    except ValueError as exc:
        return jsonify({"error": {"code": "INVALID_AGENT_SKILL_BINDING", "message": str(exc)}}), 422
    return jsonify(binding), 201


@app.route("/api/apps/<app_id>/agent-skill-bindings/<binding_id>", methods=["PATCH"])
def api_update_app_agent_skill_binding(app_id, binding_id):
    binding = store.get_app_agent_skill_binding(binding_id)
    if not binding or binding["app_id"] != app_id:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "Agent skill binding not found."}}), 404
    data = request.get_json(force=True, silent=True) or {}
    updated = store.update_app_agent_skill_binding(
        binding_id,
        enabled=bool(data.get("enabled", binding["enabled"])),
        actor_id=_agent_skill_actor_id(),
        correlation_id=request.headers.get("X-Request-Id"),
    )
    return jsonify(updated)


@app.route("/api/apps/<app_id>/agent-skill-bindings/<binding_id>", methods=["DELETE"])
def api_delete_app_agent_skill_binding(app_id, binding_id):
    binding = store.get_app_agent_skill_binding(binding_id)
    if not binding or binding["app_id"] != app_id:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "Agent skill binding not found."}}), 404
    store.delete_app_agent_skill_binding(
        binding_id,
        actor_id=_agent_skill_actor_id(),
        correlation_id=request.headers.get("X-Request-Id"),
    )
    return "", 204


@app.route("/api/agent-skills/synchronize", methods=["POST"])
def api_synchronize_agent_skills():
    try:
        state = synchronize_agent_skill_projection(
            store,
            _agent_skill_execution_client(),
            _agent_skill_builder_instance_id(),
        )
    except (ValueError, OSError) as exc:
        return jsonify({"error": {"code": "AGENT_SKILL_PROJECTION_SYNC_FAILED", "message": str(exc)}}), 502
    status = 200 if state["sync_status"] == "synchronized" else 502
    public_state = {
        key: value for key, value in state.items() if key != "published_snapshot_json"
    }
    public_state["_meta"] = {
        "deprecated": True,
        "replacement": "/api/agent-skills/publications",
    }
    return jsonify(public_state), status


@app.route("/api/agent-skills/publication-preview")
def api_agent_skill_publication_preview():
    preview = build_publication_preview(
        store=store, builder_instance_id=_agent_skill_builder_instance_id()
    )
    return jsonify(preview)


@app.route("/api/agent-skills/publications", methods=["POST"])
def api_publish_agent_skills():
    data = request.get_json(force=True, silent=True) or {}
    try:
        expected_revision = int(data.get("expected_local_revision"))
        result = publish_agent_skill_revision(
            store=store,
            execution_client=_agent_skill_execution_client(),
            builder_instance_id=_agent_skill_builder_instance_id(),
            expected_local_revision=expected_revision,
            actor_id=_agent_skill_actor_id(),
            correlation_id=_agent_skill_publication_correlation_id(),
        )
    except PublicationRevisionStale as exc:
        return jsonify(
            {
                "error": {
                    "code": exc.code,
                    "message": str(exc),
                    "expected_local_revision": exc.expected_revision,
                    "current_local_revision": exc.current_revision,
                }
            }
        ), 409
    except (TypeError, ValueError) as exc:
        return jsonify(
            {
                "error": {
                    "code": "PUBLICATION_REQUEST_INVALID",
                    "message": str(exc),
                }
            }
        ), 422
    return jsonify(_public_agent_skill_publication_result(result)), 200 if result["ok"] else 502


@app.route("/api/agent-skills/synchronize", methods=["GET"])
def api_synchronize_agent_skills_get_not_allowed():
    abort(405)


@app.route("/api/skills/<skill_id>")
def api_skill_detail(skill_id):
    skill = store.get_skill(skill_id)
    if not skill:
        return jsonify({"error": "not found"}), 404
    return jsonify(
        {
            "skill": skill,
            "versions": store.list_skill_versions(skill_id),
        }
    )


@app.route("/api/skills/import", methods=["POST"])
def api_import_skill():
    archive = request.files.get("archive")
    scope = (request.form.get("scope") or "managed").strip().lower()
    if not archive or not archive.filename:
        return jsonify({"errors": [validation_error("archive", "Skill archive is required", "required")]}), 422
    archive_path = _save_uploaded_skill_archive(archive)
    try:
        imported = store.import_skill_package(
            archive_path=archive_path,
            scope=scope,
            import_source="upload",
        )
        return jsonify(imported), 201
    except ValueError as exc:
        return jsonify({"errors": [validation_error("archive", str(exc), "invalid")]}), 422
    finally:
        _cleanup_uploaded_skill_archive(archive_path)


@app.route("/api/skills/<skill_id>/versions/<version_id>/publish", methods=["POST"])
def api_publish_skill_version(skill_id, version_id):
    if not store.get_skill(skill_id):
        return jsonify({"error": "not found"}), 404
    try:
        published = store.publish_skill_version(version_id)
    except ValueError as exc:
        return jsonify({"errors": [validation_error("version", str(exc), "invalid")]}), 422
    if not published:
        return jsonify({"error": "not found"}), 404
    return jsonify(published)


@app.route("/api/skills/published/<skill_id>")
def api_published_skill_definition(skill_id):
    version = request.args.get("version")
    try:
        payload = store.get_published_skill_definition(skill_id=skill_id, version=version)
    except ValueError as exc:
        return jsonify({"errors": [validation_error("version", str(exc), "invalid")]}), 422
    if payload is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(payload)


@app.route("/api/apps/<app_id>/skill-bindings")
def api_list_app_skill_bindings(app_id):
    if not store.get_application(app_id):
        return jsonify({"error": "not found"}), 404
    skill_id = (request.args.get("skill_id") or "").strip()
    items = store.list_app_skill_bindings(app_id)
    if skill_id:
        items = [item for item in items if item["skill_id"] == skill_id]
    return jsonify({"items": items})


@app.route("/api/apps/<app_id>/skill-bindings", methods=["POST"])
def api_create_app_skill_binding(app_id):
    if not store.get_application(app_id):
        return jsonify({"error": "not found"}), 404
    data = request.get_json(force=True, silent=True) or {}
    try:
        binding = store.create_app_skill_binding(
            app_id=app_id,
            skill_id=str(data.get("skill_id", "")).strip(),
            skill_version=str(data.get("skill_version", "")).strip(),
            permission_mode=str(data.get("permission_mode", "blocked")).strip(),
            execution_policy=data.get("execution_policy") if isinstance(data.get("execution_policy"), dict) else {},
            enabled=bool(data.get("enabled", True)),
        )
    except ValueError as exc:
        return jsonify({"errors": [validation_error("binding", str(exc), "invalid")]}), 422
    return jsonify(binding), 201


@app.route("/api/apps/by-name/<name>")
def api_app_by_name(name):
    if _is_rate_limited(_client_ip()):
        return jsonify({"errors": [validation_error("name", "Rate limit exceeded", "rate_limited")]}), 429
    app_obj = store.get_application_by_name(name)
    if not app_obj:
        return jsonify({"error": "not found"}), 404
    return jsonify(app_obj)


@app.route("/api/apps", methods=["POST"])
def api_create_app():
    data = request.get_json(force=True, silent=True) or {}
    schema = ApplicationSchema()
    valid, errors = schema.validate(data)
    if not valid:
        return jsonify({"errors": errors}), 422
    created = store.create_application(data)
    if not created:
        return jsonify({"errors": [{"path": "slug", "msg": "Slug must be unique", "code": "conflict"}]}), 409
    return jsonify(created), 201


@app.route("/api/apps/<app_id>", methods=["PATCH"])
def api_update_app(app_id):
    data = request.get_json(force=True, silent=True) or {}
    valid_fields = {
        key: value
        for key, value in data.items()
        if key in {"description", "starter_questions"}
    }
    updated = store.update_application(app_id, valid_fields)
    if not updated:
        return jsonify({"error": "not found"}), 404
    return jsonify(updated)


@app.route("/apps/<app_id>/delete", methods=["POST"])
def delete_app(app_id):
    app_obj = store.get_application(app_id)
    if not app_obj:
        abort(404)
    _delete_app_artifacts(app_id)
    store.delete_application(app_id)
    return redirect(url_for("apps"))


@app.route("/api/apps/<app_id>", methods=["DELETE"])
def api_delete_app(app_id):
    if not store.get_application(app_id):
        return jsonify({"error": "not found"}), 404
    warnings = _delete_app_artifacts(app_id)
    deleted = store.delete_application(app_id)
    if not deleted:
        return jsonify({"error": "not found"}), 404
    response = {"status": "deleted"}
    if warnings:
        response["warnings"] = warnings
    return jsonify(response)


@app.route("/api/apps/<app_id>/instructions")
def api_get_instructions(app_id):
    instructions = store.get_instructions(app_id)
    if not instructions:
        return jsonify({"error": "not found"}), 404
    return jsonify(instructions)


@app.route("/api/apps/<app_id>/instruction-model")
def api_get_instruction_model(app_id):
    if not store.get_application(app_id):
        return jsonify({"error": "not found"}), 404
    instructions = store.get_instructions(app_id) or {"content": "", "version": "", "uri": ""}
    snapshot_root = _instruction_model_snapshot_root()
    adapter = InstructionModelAdapter(snapshot_root=snapshot_root)
    return jsonify(adapter.get_latest_instruction_model(app_id, instructions))


@app.route("/api/apps/<app_id>/instructions", methods=["PATCH"])
def api_update_instructions(app_id):
    data = request.get_json(force=True, silent=True) or {}
    schema = InstructionsSchema()
    valid, errors = schema.validate(data)
    if not valid:
        return jsonify({"errors": errors}), 422
    updated = store.update_instructions(app_id, data)
    if not updated:
        return jsonify({"error": "not found"}), 404
    return jsonify(updated)


@app.route("/api/apps/<app_id>/settings")
def api_get_settings(app_id):
    settings = store.get_settings(app_id)
    if settings is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(settings)


@app.route("/api/apps/<app_id>/settings", methods=["PATCH"])
def api_update_settings(app_id):
    data = request.get_json(force=True, silent=True) or {}
    schema = SettingsSchema()
    valid, errors = schema.validate(data)
    if not valid:
        return jsonify({"errors": errors}), 422
    updated = store.update_settings(app_id, data)
    if not updated:
        return jsonify({"error": "not found"}), 404
    return jsonify(updated)


@app.route("/api/apps/<app_id>/uploads", methods=["POST"])
def api_upload(app_id):
    if not store.get_application(app_id):
        return jsonify({"error": "not found"}), 404
    data = request.get_json(force=True, silent=True) or {}
    schema = DocumentUploadSchema()
    valid, errors = schema.validate(data)
    if not valid:
        return jsonify({"errors": errors}), 422
    doc = store.queue_document(app_id, data)
    if not doc:
        return jsonify({"error": "not found"}), 404
    # JSON endpoint queues metadata only. File upload + ingestion is handled by the HTML upload form.
    return jsonify({"document": doc, "job": {"status": "queued"}}), 202


@app.route("/api/apps/<app_id>/docs")
def api_docs(app_id):
    if not store.get_application(app_id):
        return jsonify({"error": "not found"}), 404
    docs = store.list_documents(app_id)
    return jsonify(docs)


@app.route("/api/apps/<app_id>/docs/<doc_id>")
def api_doc_detail(app_id, doc_id):
    if not store.get_application(app_id):
        return jsonify({"error": "not found"}), 404
    doc = store.get_document(app_id, doc_id)
    if not doc:
        return jsonify({"error": "not found"}), 404
    return jsonify(doc)


@app.route("/api/apps/<app_id>/docs/<doc_id>", methods=["DELETE", "POST"])
def api_doc_delete(app_id, doc_id):
    if not store.get_application(app_id):
        return jsonify({"error": "not found"}), 404

    if request.method == "POST":
        method_override = (request.form.get("_method") or "").strip().lower()
        if method_override and method_override != "delete":
            return jsonify({"error": "method not allowed"}), 405

    doc = store.get_document(app_id, doc_id)
    if not doc:
        return jsonify({"error": "not found"}), 404

    vector_cleanup_error = None
    try:
        delete_document_chunks(doc_id, app_id, store=None)
    except Exception as exc:  # noqa: BLE001
        vector_cleanup_error = str(exc)

    try:
        _delete_local_file(doc.get("file_path"))
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"Failed to delete file: {exc}"}), 500

    deleted = store.delete_document(app_id, doc_id)
    if not deleted:
        return jsonify({"error": "not found"}), 404

    if request.method == "POST":
        return redirect(request.referrer or url_for("upload", app_id=app_id))
    if vector_cleanup_error:
        return jsonify({"status": "deleted", "warning": f"vector cleanup failed: {vector_cleanup_error}"})
    return jsonify({"status": "deleted"})


@app.route("/api/apps/<app_id>/docs/<doc_id>/reingest", methods=["POST"])
def api_doc_reingest(app_id, doc_id):
    if not store.get_application(app_id):
        return jsonify({"error": "not found"}), 404
    doc = store.get_document(app_id, doc_id)
    if not doc:
        return jsonify({"error": "not found"}), 404
    try:
        store.update_document_status(app_id, doc_id, "ingesting")
        ingest_uploaded_file(app_id, doc, config=_current_process_config(), store=None)
        store.update_document_status(app_id, doc_id, "ready")
    except Exception as exc:  # noqa: BLE001
        store.update_document_status(app_id, doc_id, "error", str(exc))
        return jsonify({"error": str(exc)}), 500
    return jsonify({"job": {"status": "reingested"}, "document": store.get_document(app_id, doc_id)}), 202


@app.route("/api/apps/<app_id>/docs/<doc_id>/cancel", methods=["POST"])
def api_doc_cancel(app_id, doc_id):
    if not store.get_application(app_id):
        return jsonify({"error": "not found"}), 404
    doc = store.get_document(app_id, doc_id)
    if not doc:
        return jsonify({"error": "not found"}), 404

    status = (doc.get("status") or "").lower()
    if status not in {"pending", "ingesting"}:
        if request.form:
            return redirect(request.referrer or url_for("upload", app_id=app_id))
        return jsonify({"status": "no_op", "document": doc}), 200

    _request_cancel_doc(doc_id)
    store.update_document_status(app_id, doc_id, "canceled", "Canceled by user.")

    if status == "pending":
        _clear_cancel_request(doc_id)

    if request.form:
        return redirect(request.referrer or url_for("upload", app_id=app_id))
    return jsonify({"status": "canceled", "document": store.get_document(app_id, doc_id)}), 202


@app.route("/api/apps/<app_id>/search", methods=["POST"])
def api_search(app_id):
    if not store.get_application(app_id):
        return jsonify({"error": "not found"}), 404
    data = request.get_json(force=True, silent=True) or {}
    query_text = data.get("query", "").strip()
    if not query_text:
        return (
            jsonify({"errors": [validation_error("query", "Required", "required")]}),
            422,
        )
    try:
        filters = data.get("filters", {})
        if not isinstance(filters, dict):
            return jsonify({"errors": [validation_error("filters", "Must be an object", "type")]}), 422
        retrieval_result = run_retrieve(
            query_text=query_text,
            top_k=data.get("top_k", 5),
            filters=filters,
            app_id=app_id,
        )
        results, debug = _serialize_retrieval_result(retrieval_result)
        return jsonify({"results": results, "debug": debug})
    except TimeoutError as exc:
        return jsonify({"error": str(exc)}), 503
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 503


if __name__ == "__main__":
    app.run(debug=True)
