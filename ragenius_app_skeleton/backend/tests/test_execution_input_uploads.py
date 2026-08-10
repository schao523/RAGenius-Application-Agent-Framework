from __future__ import annotations

import hashlib
import io
import sqlite3
from pathlib import Path

import pytest

from backend.app.chat_repos import SessionRepo


class ChunkedReader(io.BytesIO):
    def __init__(self, value: bytes, chunk_size: int = 3) -> None:
        super().__init__(value)
        self.chunk_size = chunk_size
        self.requested_sizes: list[int] = []

    def read(self, size: int = -1) -> bytes:
        self.requested_sizes.append(size)
        return super().read(min(size, self.chunk_size) if size >= 0 else self.chunk_size)


class FailingReader(io.BytesIO):
    def read(self, size: int = -1) -> bytes:
        value = super().read(min(size, 3))
        if not value:
            raise OSError("simulated upload failure")
        return value


def make_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SessionRepo:
    monkeypatch.setenv("RAGENIUS_APP_UPLOADS_DIR", str(tmp_path / "uploads"))
    return SessionRepo(db_path=tmp_path / "state.db")


def test_add_upload_stream_hashes_chunks_and_normalizes_basename(tmp_path, monkeypatch):
    repo = make_repo(tmp_path, monkeypatch)
    source = ChunkedReader(b"video-bytes")

    upload = repo.add_upload_stream(
        "session-1",
        filename="../unsafe/video.mp4",
        mime_type="video/mp4",
        source=source,
        max_bytes=100,
    )

    assert upload["filename"] == "video.mp4"
    assert upload["size_bytes"] == 11
    assert upload["sha256"] == f"sha256:{hashlib.sha256(b'video-bytes').hexdigest()}"
    assert Path(upload["file_path"]).read_bytes() == b"video-bytes"
    assert source.requested_sizes and all(size == 1024 * 1024 for size in source.requested_sizes)


def test_add_upload_stream_enforces_limit_and_removes_partial_files(tmp_path, monkeypatch):
    repo = make_repo(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="maximum"):
        repo.add_upload_stream(
            "session-1",
            filename="large.mp4",
            mime_type="video/mp4",
            source=ChunkedReader(b"too-large"),
            max_bytes=4,
        )
    assert list((tmp_path / "uploads").rglob("*")) in ([], [tmp_path / "uploads" / "session-1"])

    with pytest.raises(OSError, match="simulated"):
        repo.add_upload_stream(
            "session-1",
            filename="broken.mp4",
            mime_type="video/mp4",
            source=FailingReader(b"partial"),
            max_bytes=100,
        )
    assert not list((tmp_path / "uploads" / "session-1").glob("*.tmp"))


def test_upload_lookup_is_session_scoped_and_backfills_missing_hash(tmp_path, monkeypatch):
    repo = make_repo(tmp_path, monkeypatch)
    upload = repo.add_upload(
        "session-1",
        filename="notes.txt",
        mime_type="text/plain",
        content=b"notes",
        text_content="notes",
    )
    assert repo.get_upload("other-session", upload["id"]) is None
    assert repo.get_upload("session-1", upload["id"])["sha256"].startswith("sha256:")

    with sqlite3.connect(tmp_path / "state.db") as connection:
        connection.execute("UPDATE uploads SET sha256 = NULL WHERE id = ?", (upload["id"],))
        connection.commit()
    backfilled = repo.ensure_upload_sha256("session-1", upload["id"])
    assert backfilled["sha256"] == f"sha256:{hashlib.sha256(b'notes').hexdigest()}"


def test_get_upload_rejects_symlink_file(tmp_path, monkeypatch):
    repo = make_repo(tmp_path, monkeypatch)
    upload = repo.add_upload(
        "session-1",
        filename="notes.txt",
        mime_type="text/plain",
        content=b"notes",
        text_content="notes",
    )
    target = Path(upload["file_path"])
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"outside")
    target.unlink()
    try:
        target.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"Symlink creation unavailable: {exc}")
    assert repo.get_upload("session-1", upload["id"]) is None
