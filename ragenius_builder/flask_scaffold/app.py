import datetime
import threading
import json
import os
import re
from pathlib import Path
from dataclasses import asdict
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from flask import Flask, render_template, request, redirect, url_for, jsonify, abort

from storage import (
    store,
    ApplicationSchema,
    SettingsSchema,
    InstructionsSchema,
    DocumentUploadSchema,
    DEFAULT_APP_CONFIG_SETTINGS,
    DEFAULT_APP_CONFIG_SCHEMA,
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
        "now": datetime.datetime.utcnow(),
    }


@app.route("/")
def root():
    return redirect(url_for("apps"))


@app.route("/apps")
def apps():
    return render_template("apps.html", apps=store.list_applications())


@app.route("/admin/subsystem")
def subsystem_settings():
    return render_template("subsystem_settings.html", subsystem=_global_subsystem_settings_view())


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
    return render_template("app_detail.html", app=app_obj, docs=docs)


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
