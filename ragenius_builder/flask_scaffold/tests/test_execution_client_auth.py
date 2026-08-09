from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SCAFFOLD_ROOT = Path(__file__).resolve().parents[1]
if str(SCAFFOLD_ROOT) not in sys.path:
    sys.path.insert(0, str(SCAFFOLD_ROOT))

from execution_client import ExecutionSubsystemClient


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def getcode(self) -> int:
        return 200

    def read(self) -> bytes:
        return json.dumps({"status": "ok"}).encode("utf-8")


class ExecutionSubsystemClientAuthTests(unittest.TestCase):
    def test_attaches_configured_builder_service_token(self) -> None:
        client = ExecutionSubsystemClient(
            "http://127.0.0.1:3001",
            service_token="builder-secret",
        )

        with patch("execution_client.urllib.request.urlopen", return_value=_Response()) as urlopen:
            response = client.get_tool_inventory()

        self.assertTrue(response["ok"])
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer builder-secret")


if __name__ == "__main__":
    unittest.main()
