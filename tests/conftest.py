import shutil
import uuid
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRATCH_ROOT = REPO_ROOT / ".tmp" / "tests"


@pytest.fixture
def scratch_dir() -> Path:
    path = SCRATCH_ROOT / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
