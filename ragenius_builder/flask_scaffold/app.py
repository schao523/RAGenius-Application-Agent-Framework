import datetime
import threading
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from flask import Flask, render_template, request, redirect, url_for, jsonify, abort

from storage import (
    store,
    ApplicationSchema,
    SettingsSchema,
    InstructionsSchema,
    DocumentUploadSchema,
)
from rag_stub import process_files, retrieve_data

app = Flask(__name__)
_BY_NAME_RATE_LIMIT = 60
_BY_NAME_WINDOW_SECONDS = 60
_by_name_requests = defaultdict(deque)
_by_name_lock = threading.Lock()
_retrieval_pool = ThreadPoolExecutor(max_workers=4)


def validation_error(path: str, msg: str, code: str):
    return {"path": path, "msg": msg, "code": code}


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


def run_retrieve(query_text, top_k, filters, app_id):
    future = _retrieval_pool.submit(
        retrieve_data,
        query_text=query_text,
        top_k=top_k,
        filters=filters,
        config=store.get_settings(app_id),
        store=store,
        embed_client=None,
        router=None,
    )
    try:
        return future.result(timeout=3)
    except TimeoutError as exc:
        raise TimeoutError("Retrieval timed out after 3 seconds") from exc


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
                "content": request.form.get("content", ""),
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
    return render_template(
        "config.html",
        app=app_obj,
        tab=tab,
        instructions=instructions,
        settings=settings,
        errors=errors,
        saved=saved,
    )


@app.route("/apps/<app_id>/upload", methods=["GET", "POST"])
def upload(app_id):
    app_obj = parse_app(app_id)
    errors = []
    if request.method == "POST":
        payload = request.form.to_dict(flat=True)
        payload["tags"] = [
            t.strip() for t in request.form.get("tags", "").split(",") if t.strip()
        ]
        schema = DocumentUploadSchema()
        valid, errors = schema.validate(payload)
        if valid:
            store.queue_document(app_id, payload)
            return redirect(url_for("upload", app_id=app_id))
    queue = store.list_documents(app_id)
    return render_template("upload.html", app=app_obj, errors=errors, queue=queue)


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
    error = None
    query_text = ""
    if request.method == "POST":
        query_text = request.form.get("query", "").strip()
        if query_text:
            try:
                results = run_retrieve(
                    query_text=query_text,
                    top_k=5,
                    filters={"app_id": app_id},
                    app_id=app_id,
                )
            except TimeoutError as exc:
                error = str(exc)
            except Exception as exc:  # noqa: BLE001
                error = str(exc)
    return render_template(
        "search.html", app=app_obj, results=results, error=error, query=query_text
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
    job = process_files(
        documents=[doc],
        config=store.get_settings(app_id),
        store=store,
        embed_client=None,
        router=None,
    )
    return jsonify({"document": doc, "job": job}), 202


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


@app.route("/api/apps/<app_id>/docs/<doc_id>", methods=["DELETE"])
def api_doc_delete(app_id, doc_id):
    if not store.get_application(app_id):
        return jsonify({"error": "not found"}), 404
    deleted = store.delete_document(app_id, doc_id)
    if not deleted:
        return jsonify({"error": "not found"}), 404
    return jsonify({"status": "deleted"})


@app.route("/api/apps/<app_id>/docs/<doc_id>/reingest", methods=["POST"])
def api_doc_reingest(app_id, doc_id):
    if not store.get_application(app_id):
        return jsonify({"error": "not found"}), 404
    doc = store.get_document(app_id, doc_id)
    if not doc:
        return jsonify({"error": "not found"}), 404
    job = process_files(
        documents=[doc],
        config=store.get_settings(app_id),
        store=store,
        embed_client=None,
        router=None,
    )
    store.update_document_status(app_id, doc_id, "ingesting")
    return jsonify({"job": job, "document": doc}), 202


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
        filters["app_id"] = app_id
        results = run_retrieve(
            query_text=query_text,
            top_k=data.get("top_k", 5),
            filters=filters,
            app_id=app_id,
        )
        return jsonify({"results": results})
    except TimeoutError as exc:
        return jsonify({"error": str(exc)}), 503
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 503


if __name__ == "__main__":
    app.run(debug=True)
