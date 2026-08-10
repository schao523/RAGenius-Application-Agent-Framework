from __future__ import annotations

from pathlib import Path
from typing import Any

from .chat_repos import SessionRepo
from .execution_subsystem_client import ExecutionSubsystemClient


class ExecutionInputPreparationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _safe_upload_metadata(upload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: upload[key]
        for key in ("id", "session_id", "filename", "mime_type", "size_bytes", "sha256", "created_at")
        if key in upload
    }


def prepare_session_upload(
    *,
    session_repo: SessionRepo,
    execution_client: ExecutionSubsystemClient,
    app_id: str,
    session_id: str,
    upload_id: str,
) -> dict[str, Any]:
    upload = session_repo.ensure_upload_sha256(session_id, upload_id)
    file_path = Path(str(upload.get("file_path") or ""))
    if file_path.is_symlink() or not file_path.is_file():
        raise ExecutionInputPreparationError("SESSION_UPLOAD_NOT_FOUND", "Session upload is not available.")
    result = execution_client.import_session_upload(
        app_id=app_id,
        session_id=session_id,
        source_upload_id=upload["id"],
        display_name=upload["filename"],
        mime_type=upload.get("mime_type"),
        size_bytes=int(upload["size_bytes"]),
        sha256=str(upload["sha256"]),
        file_path=str(file_path),
    )
    error = result.get("error") if isinstance(result, dict) else None
    if isinstance(error, dict):
        raise ExecutionInputPreparationError(
            str(error.get("code") or "EXECUTION_INPUT_PREPARATION_FAILED"),
            str(error.get("message") or "Execution input preparation failed."),
        )
    artifact = result.get("artifact") if isinstance(result, dict) else None
    if not isinstance(artifact, dict):
        raise ExecutionInputPreparationError(
            "INVALID_EXECUTION_INPUT_RESPONSE",
            "Execution subsystem returned no prepared artifact.",
        )
    return {
        "upload": _safe_upload_metadata(upload),
        "artifact": artifact,
        "preparation_status": "ready",
        "reused_existing_artifact": bool(result.get("reused_existing_artifact")),
    }
