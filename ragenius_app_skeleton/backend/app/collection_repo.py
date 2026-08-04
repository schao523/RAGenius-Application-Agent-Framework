"""In-memory collection version tracker."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict


class CollectionRepo:
    def __init__(self, persistence_file: str | None = None) -> None:
        self._persistence_file = Path(persistence_file) if persistence_file else None
        self._versions: Dict[str, Dict[str, int]] = {}
        self._load()

    def _load(self) -> None:
        if self._persistence_file is None or not self._persistence_file.exists():
            return
        raw = json.loads(self._persistence_file.read_text(encoding="utf-8"))
        self._versions = {
            cid: {
                "active_config_version": int(v.get("active_config_version", 0)),
                "active_adapter_version": int(v.get("active_adapter_version", 0)),
                "active_template_version": int(v.get("active_template_version", 0)),
            }
            for cid, v in raw.get("versions", {}).items()
        }

    def _save(self) -> None:
        if self._persistence_file is None:
            return
        self._persistence_file.parent.mkdir(parents=True, exist_ok=True)
        self._persistence_file.write_text(
            json.dumps({"versions": self._versions}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def reset(self) -> None:
        self._versions.clear()
        self._save()

    def ensure(self, collection_id: str) -> None:
        if collection_id not in self._versions:
            self._versions[collection_id] = {
                "active_config_version": 0,
                "active_adapter_version": 0,
                "active_template_version": 0,
            }

    def set_active_adapter(self, collection_id: str, version: int) -> None:
        self.ensure(collection_id)
        self._versions[collection_id]["active_adapter_version"] = version
        self._save()

    def set_active_config(self, collection_id: str, version: int) -> None:
        self.ensure(collection_id)
        self._versions[collection_id]["active_config_version"] = version
        self._save()

    def set_active_template(self, collection_id: str, version: int) -> None:
        self.ensure(collection_id)
        self._versions[collection_id]["active_template_version"] = version
        self._save()

    def get_versions(self, collection_id: str) -> Dict[str, int]:
        self.ensure(collection_id)
        return self._versions[collection_id]
