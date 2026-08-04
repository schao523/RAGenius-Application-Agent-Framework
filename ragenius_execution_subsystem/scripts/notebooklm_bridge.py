import asyncio
import json
import os
import re
import shutil
import ssl
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any


def _sanitize_proxy_environment() -> list[str]:
    """Remove known-dead local proxy placeholders that break NotebookLM HTTP calls.

    Some local shells inherit null-routed proxy settings like 127.0.0.1:9.
    notebooklm-py/httpx honors them by default, which causes all outbound
    NotebookLM requests to fail with ConnectError before any auth or RPC call.
    """

    if os.getenv("NOTEBOOKLM_ALLOW_SYSTEM_PROXY", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        return []

    removed: list[str] = []

    def _is_dead_local_proxy(value: str) -> bool:
        normalized = str(value or "").strip().lower()
        return normalized in {
            "http://127.0.0.1:9",
            "http://localhost:9",
            "https://127.0.0.1:9",
            "https://localhost:9",
            "socks5://127.0.0.1:9",
            "socks5://localhost:9",
            "socks5h://127.0.0.1:9",
            "socks5h://localhost:9",
        }

    for key in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        if _is_dead_local_proxy(os.getenv(key, "")):
            os.environ.pop(key, None)
            removed.append(key)
    return removed


REMOVED_PROXY_VARS = _sanitize_proxy_environment()


def _configure_tls_trust() -> str | None:
    try:
        import pip_system_certs  # type: ignore  # noqa: F401

        return "pip_system_certs"
    except Exception:
        pass

    try:
        import truststore  # type: ignore

        truststore.inject_into_ssl()
        return "truststore"
    except Exception:
        pass

    return None


TLS_TRUST_MODE = _configure_tls_trust()

SCRIPT_DIR = str(Path(__file__).resolve().parent)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from notebooklm_compat import activate_renamed_host_compatibility

NOTEBOOKLM_RENAMED_HOST_COMPAT_ACTIVE = activate_renamed_host_compatibility()

try:
    from notebooklm import NotebookLMClient
except Exception as exc:  # pragma: no cover - runtime-only dependency path
    NotebookLMClient = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


def _error(
    code: str,
    message: str,
    *,
    details: Any = None,
    recoverable: bool = False,
    suggested_action: str = "",
) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "recoverable": recoverable,
            "suggested_action": suggested_action,
        },
    }


def _source_summary(source: Any) -> dict[str, Any]:
    status = getattr(source, "status", None)
    if hasattr(status, "name"):
        status = str(getattr(status, "name")).lower()
    return {
        "id": str(getattr(source, "id", "")),
        "title": str(getattr(source, "title", "")),
        "kind": str(getattr(source, "kind", "")),
        "status": status,
    }


def _reference_summary(reference: Any) -> dict[str, Any]:
    return {
        "source_id": str(getattr(reference, "source_id", "")),
        "title": str(getattr(reference, "title", "")),
    }


def _safe_source_filename(title: str, original_path: str) -> str:
    """Create a local upload filename that makes NotebookLM's fallback title useful."""

    original = Path(original_path)
    extension = original.suffix or ".txt"
    normalized_title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", str(title or "").strip())
    normalized_title = re.sub(r"\s+", " ", normalized_title).strip(" .")
    if not normalized_title:
        normalized_title = original.stem or "notebooklm-source"
    if not normalized_title.lower().endswith(extension.lower()):
        normalized_title = f"{normalized_title}{extension}"
    return normalized_title


class _UploadTempDir:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.name = str(path)

    def cleanup(self) -> None:
        shutil.rmtree(self.path, ignore_errors=True)


def _create_upload_temp_dir(original: Path) -> _UploadTempDir:
    last_error: OSError | None = None
    for candidate_dir in (original.parent, None):
        try:
            parent = candidate_dir if candidate_dir is not None else Path(tempfile.gettempdir())
            path = parent / (
                f"ragenius-notebooklm-source-{uuid.uuid4().hex}"
            )
            path.mkdir(parents=True, exist_ok=False)
            return _UploadTempDir(path)
        except OSError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise RuntimeError("Unable to create NotebookLM upload temporary directory.")


def _prepare_titled_upload_path(file_path: str, title: str | None) -> tuple[str, _UploadTempDir | None]:
    """Copy an artifact to a title-named temp file when NotebookLM would otherwise use an opaque artifact id.

    notebooklm-py also receives ``title`` and attempts UPDATE_SOURCE after upload, but that
    rename is best-effort. A title-named temporary file gives the source a readable title even
    if NotebookLM keeps the uploaded filename.
    """

    requested_title = str(title or "").strip()
    if not requested_title:
        return file_path, None
    original = Path(file_path)
    safe_filename = _safe_source_filename(requested_title, file_path)
    if original.name == safe_filename:
        return file_path, None
    temp_dir = _create_upload_temp_dir(original)
    titled_path = Path(temp_dir.name) / safe_filename
    shutil.copy2(original, titled_path)
    return str(titled_path), temp_dir


def _artifact_status_summary(status: Any) -> dict[str, Any]:
    return {
        "task_id": str(getattr(status, "task_id", "")),
        "status": str(getattr(status, "status", "")),
        "error": getattr(status, "error", None),
        "error_code": getattr(status, "error_code", None),
    }


def _temp_output_path(suffix: str) -> str:
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    handle.close()
    return handle.name


def _resolve_client_from_storage_options() -> tuple[dict[str, Any], str | None]:
    auth_mode = str(os.getenv("NOTEBOOKLM_AUTH_MODE", "env_json") or "env_json").strip().lower()
    profile = str(os.getenv("NOTEBOOKLM_PROFILE", "")).strip() or None
    storage_path = str(os.getenv("NOTEBOOKLM_STORAGE_PATH", "")).strip() or None
    auth_json = str(os.getenv("NOTEBOOKLM_AUTH_JSON", "")).strip()

    if auth_mode == "storage_path":
        return (
            {"path": storage_path} if storage_path else ({"profile": profile} if profile else {}),
            None,
        )

    if auth_mode == "profile":
        return (
            {"profile": profile} if profile else ({"path": storage_path} if storage_path else {}),
            None,
        )

    if auth_json:
        try:
            parsed = json.loads(auth_json)
        except json.JSONDecodeError as exc:
            raise ValueError("NOTEBOOKLM_AUTH_JSON is not valid JSON.") from exc
        temp_path = _temp_output_path(".storage_state.json")
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(parsed, handle)
        return {"path": temp_path}, temp_path

    if storage_path:
        return {"path": storage_path}, None
    if profile:
        return {"profile": profile}, None
    return {}, None


async def _run_operation(operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if NotebookLMClient is None:
        return _error(
            "NOTEBOOKLM_DEPENDENCY_MISSING",
            "notebooklm-py is not installed in the Python bridge environment.",
            details={"import_error": str(IMPORT_ERROR)},
            suggested_action="Install notebooklm-py for the NotebookLM bridge runtime.",
        )

    from_storage_options, temp_auth_path = _resolve_client_from_storage_options()
    try:
        async with NotebookLMClient.from_storage(**from_storage_options) as client:
            if operation == "list_notebooks":
                notebooks = await client.notebooks.list()
                return {
                    "ok": True,
                    "result": {
                        "notebooks": [
                            {
                                "id": str(getattr(notebook, "id", "")),
                                "title": str(getattr(notebook, "title", "")),
                                "sources_count": int(
                                    getattr(notebook, "sources_count", 0) or 0
                                ),
                            }
                            for notebook in notebooks
                        ]
                    },
                }

            if operation == "list_sources":
                notebook_id = str(arguments.get("notebookId", "")).strip()
                sources = await client.sources.list(notebook_id)
                return {
                    "ok": True,
                    "result": {"sources": [_source_summary(source) for source in sources]},
                }

            if operation == "ask":
                notebook_id = str(arguments.get("notebookId", "")).strip()
                question = str(arguments.get("question", "")).strip()
                source_ids = arguments.get("sourceIds")
                conversation_id = arguments.get("conversationId")
                result = await client.chat.ask(
                    notebook_id,
                    question,
                    source_ids=source_ids if isinstance(source_ids, list) else None,
                    conversation_id=str(conversation_id)
                    if isinstance(conversation_id, str) and conversation_id.strip()
                    else None,
                )
                references = getattr(result, "references", None) or []
                return {
                    "ok": True,
                    "result": {
                        "answer": str(getattr(result, "answer", "")),
                        "conversation_id": str(getattr(result, "conversation_id", "")),
                        "references": [
                            _reference_summary(reference) for reference in references
                        ],
                        "turn_number": getattr(result, "turn_number", None),
                    },
                }

            if operation == "poll_artifact_task":
                notebook_id = str(arguments.get("notebookId", "")).strip()
                task_id = str(arguments.get("taskId", "")).strip()
                artifact_kind = str(arguments.get("artifactKind", "")).strip() or "video"
                download_if_complete = bool(arguments.get("downloadIfComplete", False))
                output_format = str(arguments.get("outputFormat", "")).strip() or "pdf"
                status = await client.artifacts.poll_status(notebook_id, task_id)
                result = {
                    "notebook_id": notebook_id,
                    "artifact_kind": artifact_kind,
                    **_artifact_status_summary(status),
                }
                if download_if_complete and str(getattr(status, "status", "")).lower() == "completed":
                    if artifact_kind == "video":
                        output_path = _temp_output_path(".mp4")
                        download_path = await client.artifacts.download_video(
                            notebook_id,
                            output_path,
                            artifact_id=task_id,
                        )
                        result["download_path"] = download_path
                        result["mime_type"] = "video/mp4"
                    elif artifact_kind == "report":
                        output_path = _temp_output_path(".md")
                        download_path = await client.artifacts.download_report(
                            notebook_id,
                            output_path,
                            artifact_id=task_id,
                        )
                        result["download_path"] = download_path
                        result["mime_type"] = "text/markdown"
                    elif artifact_kind == "slide_deck":
                        suffix = ".pptx" if output_format == "pptx" else ".pdf"
                        output_path = _temp_output_path(suffix)
                        download_path = await client.artifacts.download_slide_deck(
                            notebook_id,
                            output_path,
                            artifact_id=task_id,
                        )
                        result["output_format"] = output_format
                        result["download_path"] = download_path
                        result["mime_type"] = (
                            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                            if output_format == "pptx"
                            else "application/pdf"
                        )
                return {"ok": True, "result": result}

            if operation == "add_source_text":
                notebook_id = str(arguments.get("notebookId", "")).strip()
                title = str(arguments.get("title", "")).strip()
                content = str(arguments.get("content", ""))
                wait = bool(arguments.get("wait", False))
                source = await client.sources.add_text(
                    notebook_id,
                    title,
                    content,
                    wait=wait,
                )
                return {
                    "ok": True,
                    "result": {
                        "notebook_id": notebook_id,
                        "source": _source_summary(source),
                    },
                }

            if operation == "add_source_url":
                notebook_id = str(arguments.get("notebookId", "")).strip()
                url = str(arguments.get("url", "")).strip()
                wait = bool(arguments.get("wait", False))
                source = await client.sources.add_url(
                    notebook_id,
                    url,
                    wait=wait,
                )
                return {
                    "ok": True,
                    "result": {
                        "notebook_id": notebook_id,
                        "source": _source_summary(source),
                    },
                }

            if operation == "add_source_file":
                notebook_id = str(arguments.get("notebookId", "")).strip()
                file_path = str(arguments.get("filePath", "")).strip()
                title_value = arguments.get("title")
                mime_type_value = arguments.get("mimeType")
                wait = bool(arguments.get("wait", False))
                requested_title = (
                    str(title_value).strip()
                    if isinstance(title_value, str) and title_value.strip()
                    else None
                )
                upload_path, temp_upload_dir = _prepare_titled_upload_path(
                    file_path,
                    requested_title,
                )
                try:
                    source = await client.sources.add_file(
                        notebook_id,
                        upload_path,
                        mime_type=str(mime_type_value).strip()
                        if isinstance(mime_type_value, str) and mime_type_value.strip()
                        else None,
                        wait=wait,
                        title=requested_title,
                    )
                    source_id = str(getattr(source, "id", "")).strip()
                    if (
                        requested_title
                        and source_id
                        and str(getattr(source, "title", "")).strip() != requested_title
                    ):
                        source = await client.sources.rename(
                            notebook_id,
                            source_id,
                            requested_title,
                        )
                finally:
                    if temp_upload_dir is not None:
                        temp_upload_dir.cleanup()
                return {
                    "ok": True,
                    "result": {
                        "notebook_id": notebook_id,
                        "source": _source_summary(source),
                    },
                }

            if operation == "generate_report":
                notebook_id = str(arguments.get("notebookId", "")).strip()
                source_ids = arguments.get("sourceIds")
                wait_for_completion = bool(arguments.get("waitForCompletion", True))
                report_format = arguments.get("reportFormat")
                custom_prompt = arguments.get("customPrompt")
                extra_instructions = arguments.get("extraInstructions")
                language = arguments.get("language")
                report_kwargs: dict[str, Any] = {
                    "source_ids": source_ids if isinstance(source_ids, list) else None,
                    "language": str(language)
                    if isinstance(language, str) and language
                    else "en",
                    "custom_prompt": str(custom_prompt)
                    if isinstance(custom_prompt, str) and custom_prompt.strip()
                    else None,
                    "extra_instructions": str(extra_instructions)
                    if isinstance(extra_instructions, str) and extra_instructions.strip()
                    else None,
                }
                if report_format is not None:
                    report_kwargs["report_format"] = report_format
                status = await client.artifacts.generate_report(notebook_id, **report_kwargs)
                result = {
                    "notebook_id": notebook_id,
                    "artifact_kind": "report",
                    **_artifact_status_summary(status),
                }
                if wait_for_completion and str(getattr(status, "task_id", "")).strip():
                    completed = await client.artifacts.wait_for_completion(
                        notebook_id,
                        str(getattr(status, "task_id", "")),
                    )
                    result.update(_artifact_status_summary(completed))
                    output_path = _temp_output_path(".md")
                    download_path = await client.artifacts.download_report(
                        notebook_id,
                        output_path,
                        artifact_id=str(getattr(completed, "task_id", "")) or None,
                    )
                    with open(download_path, "r", encoding="utf-8") as handle:
                        result["content_markdown"] = handle.read()
                    result["download_path"] = download_path
                    result["mime_type"] = "text/markdown"
                return {"ok": True, "result": result}

            if operation == "generate_slide_deck":
                notebook_id = str(arguments.get("notebookId", "")).strip()
                source_ids = arguments.get("sourceIds")
                wait_for_completion = bool(arguments.get("waitForCompletion", True))
                output_format = str(arguments.get("outputFormat", "pdf")).strip() or "pdf"
                slide_format = arguments.get("slideFormat")
                slide_length = arguments.get("slideLength")
                instructions = arguments.get("instructions")
                language = arguments.get("language")
                slide_kwargs: dict[str, Any] = {
                    "source_ids": source_ids if isinstance(source_ids, list) else None,
                    "language": str(language)
                    if isinstance(language, str) and language
                    else "en",
                    "instructions": str(instructions)
                    if isinstance(instructions, str) and instructions.strip()
                    else None,
                }
                if slide_format is not None:
                    slide_kwargs["slide_format"] = slide_format
                if slide_length is not None:
                    slide_kwargs["slide_length"] = slide_length
                status = await client.artifacts.generate_slide_deck(notebook_id, **slide_kwargs)
                result = {
                    "notebook_id": notebook_id,
                    "artifact_kind": "slide_deck",
                    "output_format": output_format,
                    **_artifact_status_summary(status),
                }
                if wait_for_completion and str(getattr(status, "task_id", "")).strip():
                    completed = await client.artifacts.wait_for_completion(
                        notebook_id,
                        str(getattr(status, "task_id", "")),
                    )
                    result.update(_artifact_status_summary(completed))
                    suffix = ".pptx" if output_format == "pptx" else ".pdf"
                    output_path = _temp_output_path(suffix)
                    download_path = await client.artifacts.download_slide_deck(
                        notebook_id,
                        output_path,
                        artifact_id=str(getattr(completed, "task_id", "")) or None,
                        output_format=output_format,
                    )
                    result["download_path"] = download_path
                    result["mime_type"] = (
                        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                        if output_format == "pptx"
                        else "application/pdf"
                    )
                return {"ok": True, "result": result}

            if operation == "generate_video":
                notebook_id = str(arguments.get("notebookId", "")).strip()
                source_ids = arguments.get("sourceIds")
                wait_for_completion = bool(arguments.get("waitForCompletion", True))
                instructions = arguments.get("instructions")
                language = arguments.get("language")
                video_format = arguments.get("videoFormat")
                video_style = arguments.get("videoStyle")
                style_prompt = arguments.get("stylePrompt")
                video_kwargs: dict[str, Any] = {
                    "source_ids": source_ids if isinstance(source_ids, list) else None,
                    "language": str(language)
                    if isinstance(language, str) and language
                    else "en",
                    "instructions": str(instructions)
                    if isinstance(instructions, str) and instructions.strip()
                    else None,
                    "style_prompt": str(style_prompt)
                    if isinstance(style_prompt, str) and style_prompt.strip()
                    else None,
                }
                if video_format is not None:
                    video_kwargs["video_format"] = video_format
                if video_style is not None:
                    video_kwargs["video_style"] = video_style
                status = await client.artifacts.generate_video(notebook_id, **video_kwargs)
                result = {
                    "notebook_id": notebook_id,
                    "artifact_kind": "video",
                    **_artifact_status_summary(status),
                }
                if wait_for_completion and str(getattr(status, "task_id", "")).strip():
                    completed = await client.artifacts.wait_for_completion(
                        notebook_id,
                        str(getattr(status, "task_id", "")),
                    )
                    result.update(_artifact_status_summary(completed))
                    output_path = _temp_output_path(".mp4")
                    download_path = await client.artifacts.download_video(
                        notebook_id,
                        output_path,
                        artifact_id=str(getattr(completed, "task_id", "")) or None,
                    )
                    result["download_path"] = download_path
                    result["mime_type"] = "video/mp4"
                return {"ok": True, "result": result}

            return _error(
                "NOTEBOOKLM_BRIDGE_NOT_IMPLEMENTED",
                f"Operation not implemented: {operation}",
                details={"arguments": arguments},
                suggested_action="Implement the NotebookLM bridge operation.",
            )
    finally:
        if temp_auth_path:
            try:
                os.remove(temp_auth_path)
            except OSError:
                pass


async def _main_async() -> int:
    payload = json.loads(sys.stdin.read() or "{}")
    operation = str(payload.get("operation", "")).strip()
    arguments = payload.get("arguments", {})
    if not operation:
        sys.stdout.write(
            json.dumps(
                _error(
                    "NOTEBOOKLM_OPERATION_REQUIRED",
                    "NotebookLM bridge operation is required.",
                    suggested_action="Provide an operation in the request payload.",
                    recoverable=True,
                )
            )
        )
        return 0

    try:
        response = await _run_operation(
            operation,
            arguments if isinstance(arguments, dict) else {},
        )
    except Exception as exc:  # pragma: no cover - runtime-only path
        details = {"operation": operation, "error": str(exc)}
        details["auth_mode"] = str(os.getenv("NOTEBOOKLM_AUTH_MODE", "env_json") or "env_json")
        if os.getenv("NOTEBOOKLM_PROFILE"):
            details["profile"] = os.getenv("NOTEBOOKLM_PROFILE")
        if os.getenv("NOTEBOOKLM_STORAGE_PATH"):
            details["storage_path"] = os.getenv("NOTEBOOKLM_STORAGE_PATH")
        if REMOVED_PROXY_VARS:
            details["removed_proxy_env"] = REMOVED_PROXY_VARS
        if isinstance(exc, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(exc):
            details["tls_trust_mode"] = TLS_TRUST_MODE
            details["ssl_cert_file"] = os.getenv("SSL_CERT_FILE")
            details["hint"] = (
                "Install pip-system-certs or truststore in the Python environment used by the "
                "NotebookLM bridge so Windows trust roots are available to httpx/OpenSSL."
            )
        response = _error(
            "NOTEBOOKLM_BRIDGE_FAILED",
            "NotebookLM bridge execution failed.",
            details=details,
            suggested_action="Inspect NotebookLM bridge configuration and retry.",
            recoverable=True,
        )
    sys.stdout.write(json.dumps(response))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main_async()))
