"""In-memory adapter version repository for draft/approval lifecycle."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional


@dataclass
class AdapterVersion:
    collection_id: str
    version: int
    adapter_json: Dict
    is_draft: bool
    is_approved: bool
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None


class InMemoryAdapterRepo:
    """Temporary repository matching Hybrid Adapter Strategy contracts."""

    def __init__(self, persistence_file: str | None = None) -> None:
        self._persistence_file = Path(persistence_file) if persistence_file else None
        self._drafts: Dict[str, AdapterVersion] = {}
        self._approved: Dict[str, Dict[int, AdapterVersion]] = {}
        self._active_version: Dict[str, int] = {}
        self._load()

    def _load(self) -> None:
        if self._persistence_file is None or not self._persistence_file.exists():
            return
        raw = json.loads(self._persistence_file.read_text(encoding="utf-8"))
        drafts = raw.get("drafts", {})
        approved = raw.get("approved", {})
        active = raw.get("active_version", {})

        self._drafts = {
            k: AdapterVersion(**v)
            for k, v in drafts.items()
        }
        self._approved = {
            cid: {int(ver): AdapterVersion(**payload) for ver, payload in versions.items()}
            for cid, versions in approved.items()
        }
        self._active_version = {k: int(v) for k, v in active.items()}

    def _save(self) -> None:
        if self._persistence_file is None:
            return
        self._persistence_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "drafts": {k: vars(v) for k, v in self._drafts.items()},
            "approved": {
                cid: {str(ver): vars(obj) for ver, obj in versions.items()}
                for cid, versions in self._approved.items()
            },
            "active_version": self._active_version,
        }
        self._persistence_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def reset(self) -> None:
        self._drafts.clear()
        self._approved.clear()
        self._active_version.clear()
        self._save()

    def get_active_version(self, collection_id: str) -> int:
        return self._active_version.get(collection_id, 0)

    def get_active_adapter(self, collection_id: str) -> Optional[AdapterVersion]:
        active_version = self.get_active_version(collection_id)
        if active_version <= 0:
            return None
        return self._approved.get(collection_id, {}).get(active_version)

    def get_draft(self, collection_id: str) -> Optional[AdapterVersion]:
        return self._drafts.get(collection_id)

    def _max_known_version(self, collection_id: str) -> int:
        approved_versions = self._approved.get(collection_id, {})
        max_approved = max(approved_versions.keys()) if approved_versions else 0
        draft = self._drafts.get(collection_id)
        draft_version = draft.version if draft else 0
        return max(max_approved, draft_version, self.get_active_version(collection_id))

    def next_draft_version(self, collection_id: str) -> int:
        return self._max_known_version(collection_id) + 1

    def save_draft(self, collection_id: str, adapter_json: Dict, *, version: Optional[int] = None) -> AdapterVersion:
        next_version = version if version is not None else self.next_draft_version(collection_id)
        draft = AdapterVersion(
            collection_id=collection_id,
            version=next_version,
            adapter_json=adapter_json,
            is_draft=True,
            is_approved=False,
        )
        self._drafts[collection_id] = draft
        self._save()
        return draft

    def reject_draft(self, collection_id: str) -> None:
        self._drafts.pop(collection_id, None)
        self._save()

    def approve(self, collection_id: str, *, approved_by: Optional[str] = None) -> AdapterVersion:
        draft = self.get_draft(collection_id)
        if draft is None:
            raise ValueError("No draft adapter to approve.")

        approved_version = draft.version + 1
        approved = AdapterVersion(
            collection_id=collection_id,
            version=approved_version,
            adapter_json=draft.adapter_json,
            is_draft=False,
            is_approved=True,
            approved_by=approved_by,
            approved_at=datetime.now(timezone.utc).isoformat(),
        )
        self._approved.setdefault(collection_id, {})[approved_version] = approved
        self._active_version[collection_id] = approved_version
        self._drafts.pop(collection_id, None)
        self._save()
        return approved
