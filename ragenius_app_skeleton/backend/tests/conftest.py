from __future__ import annotations

import os
import sys
import tempfile
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SKELETON_ROOT = ROOT / "ragenius_app_skeleton"

for candidate in (ROOT, SKELETON_ROOT):
    text = str(candidate)
    if text not in sys.path:
        sys.path.insert(0, text)

TEST_STATE_ROOT = Path(tempfile.gettempdir()) / "ragenius_app_tests" / uuid.uuid4().hex
TEST_STATE_ROOT.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR = TEST_STATE_ROOT / "session_uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("RAGENIUS_APP_STATE_DB", str(TEST_STATE_ROOT / "runtime_state.db"))
os.environ.setdefault("RAGENIUS_APP_UPLOADS_DIR", str(UPLOADS_DIR))
