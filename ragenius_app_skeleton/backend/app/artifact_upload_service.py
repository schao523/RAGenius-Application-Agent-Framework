from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any, BinaryIO, Callable

from .chat_repos import SessionRepo
from .execution_subsystem_client import ExecutionSubsystemClient


_NON_RETRYABLE_CODES = {
    "EXECUTION_INPUT_TOO_LARGE",
    "EXECUTION_INPUT_MEDIA_TYPE_NOT_ALLOWED",
    "EXECUTION_INPUT_INTEGRITY_MISMATCH",
    "SESSION_UPLOAD_CONTENT_CONFLICT",
}


def _parse_time(value: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))


def _format_time(value: datetime.datetime) -> str:
    return value.astimezone(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


class ArtifactUploadService:
    def __init__(
        self,
        session_repo: SessionRepo,
        execution_client: ExecutionSubsystemClient,
        *,
        max_bytes: int,
    ) -> None:
        self.session_repo = session_repo
        self.execution_client = execution_client
        self.max_bytes = max_bytes

    @staticmethod
    def _response(operation: dict[str, Any], *, reused: bool = False) -> dict[str, Any]:
        return {
            "upload_operation_id": operation["upload_operation_id"],
            "status": operation["status"],
            "artifact": operation.get("artifact"),
            "reused_existing_artifact": reused,
            "error_code": operation.get("error_code"),
            "retryable": bool(operation.get("retryable")),
        }

    def upload(
        self,
        *,
        app_id: str,
        session_id: str,
        user_id: str,
        upload_operation_id: str,
        filename: str,
        mime_type: str | None,
        source: BinaryIO,
        analysis: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None,
        now: str | None = None,
        retention_hours: int = 24,
    ) -> dict[str, Any]:
        existing = self.session_repo.get_upload_operation(
            app_id=app_id, session_id=session_id, user_id=user_id,
            upload_operation_id=upload_operation_id,
        )
        if existing is not None:
            if existing["status"] == "ready":
                return self._response(existing, reused=True)
            if existing["status"] in {"staged", "failed", "preparing"} and existing.get("retryable"):
                return self._prepare(existing, analysis=analysis)
            raise ValueError("Upload operation is not retryable")

        current = _parse_time(now) if now else datetime.datetime.now(datetime.timezone.utc)
        expires = _format_time(current + datetime.timedelta(hours=retention_hours))
        operation = self.session_repo.add_upload_stream(
            session_id,
            filename=filename,
            mime_type=mime_type,
            source=source,
            max_bytes=self.max_bytes,
            app_id=app_id,
            user_id=user_id,
            upload_operation_id=upload_operation_id,
            staging_expires_at=expires,
        )
        return self._prepare(operation, analysis=analysis)

    def retry(
        self, *, app_id: str, session_id: str, user_id: str,
        upload_operation_id: str,
        analysis: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None,
    ) -> dict[str, Any]:
        operation = self.session_repo.get_upload_operation(
            app_id=app_id, session_id=session_id, user_id=user_id,
            upload_operation_id=upload_operation_id,
        )
        if operation is None:
            raise ValueError("Upload operation not found")
        if operation["status"] == "ready":
            return self._response(operation, reused=True)
        if not operation.get("retryable") or operation["status"] not in {"staged", "failed", "preparing"}:
            raise ValueError("Upload operation is not retryable")
        return self._prepare(operation, analysis=analysis)

    def _prepare(
        self,
        operation: dict[str, Any],
        *,
        analysis: Callable[[dict[str, Any]], dict[str, Any] | None] | None,
    ) -> dict[str, Any]:
        scope = {
            "app_id": operation["app_id"],
            "session_id": operation["session_id"],
            "user_id": operation["user_id"],
            "upload_operation_id": operation["upload_operation_id"],
        }
        operation = self.session_repo.update_upload_operation(
            **scope, status="preparing", artifact_id=operation.get("artifact_id"),
            error_code=None, retryable=True,
        )
        file_path = Path(str(operation.get("file_path") or ""))
        if file_path.is_symlink() or not file_path.is_file():
            failed = self.session_repo.update_upload_operation(
                **scope, status="failed", artifact_id=None,
                error_code="UPLOAD_STAGING_UNAVAILABLE", retryable=False,
            )
            return self._response(failed)
        result = self.execution_client.import_session_upload(
            app_id=operation["app_id"],
            session_id=operation["session_id"],
            source_upload_id=operation["upload_operation_id"],
            display_name=operation["filename"],
            mime_type=operation.get("normalized_mime_type") or operation.get("mime_type"),
            size_bytes=int(operation["size_bytes"]),
            sha256=str(operation["sha256"]),
            file_path=str(file_path),
        )
        error = result.get("error") if isinstance(result, dict) else None
        if isinstance(error, dict):
            code = str(error.get("code") or "EXECUTION_INPUT_PREPARATION_FAILED")[:128]
            failed = self.session_repo.update_upload_operation(
                **scope, status="failed", artifact_id=None, error_code=code,
                retryable=code not in _NON_RETRYABLE_CODES,
            )
            return self._response(failed)
        artifact = result.get("artifact") if isinstance(result, dict) else None
        if not isinstance(artifact, dict) or not artifact.get("artifact_id"):
            failed = self.session_repo.update_upload_operation(
                **scope, status="failed", artifact_id=None,
                error_code="INVALID_EXECUTION_INPUT_RESPONSE", retryable=True,
            )
            return self._response(failed)
        analysis_result = analysis(operation) if analysis is not None else None
        ready = self.session_repo.update_upload_operation(
            **scope, status="ready", artifact_id=str(artifact["artifact_id"]),
            artifact=artifact, error_code=None, retryable=False,
        )
        file_path.unlink(missing_ok=True)
        response = self._response(
            ready, reused=bool(result.get("reused_existing_artifact"))
        )
        if isinstance(analysis_result, dict):
            response["analysis_result"] = analysis_result
        return response

    def cleanup_expired(self, now: str | None = None) -> int:
        current = now or _format_time(datetime.datetime.now(datetime.timezone.utc))
        expired = self.session_repo.list_expired_upload_operations(current)
        for operation in expired:
            self.session_repo.delete_upload_operation(
                app_id=operation["app_id"], session_id=operation["session_id"],
                user_id=operation["user_id"],
                upload_operation_id=operation["upload_operation_id"],
            )
        return len(expired)
