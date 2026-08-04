import os
import unittest
import uuid
from pathlib import Path

from backend.app.env_bootstrap import bootstrap_local_env


class EnvBootstrapTests(unittest.TestCase):
    def test_bootstrap_local_env_loads_missing_values_without_overwriting_existing_env(self):
        tmp_root = Path(__file__).resolve().parent / "_tmp" / "env_bootstrap" / str(uuid.uuid4())
        tmp_root.mkdir(parents=True, exist_ok=True)
        try:
            env_path = tmp_root / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "DATABASE_URL=postgresql://ragenius:ragenius@localhost:5433/ragenius",
                        "DEEPSEEK_BASE_URL=https://api.deepseek.com",
                        "EXISTING_KEY=from-file",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            original_database_url = os.environ.pop("DATABASE_URL", None)
            original_base_url = os.environ.pop("DEEPSEEK_BASE_URL", None)
            original_existing = os.environ.get("EXISTING_KEY")
            os.environ["EXISTING_KEY"] = "from-env"
            try:
                loaded = bootstrap_local_env(env_path=env_path)
                self.assertEqual(
                    os.environ.get("DATABASE_URL"),
                    "postgresql://ragenius:ragenius@localhost:5433/ragenius",
                )
                self.assertEqual(
                    os.environ.get("DEEPSEEK_BASE_URL"),
                    "https://api.deepseek.com",
                )
                self.assertEqual(os.environ.get("EXISTING_KEY"), "from-env")
                self.assertIn("DATABASE_URL", loaded)
                self.assertIn("DEEPSEEK_BASE_URL", loaded)
                self.assertNotIn("EXISTING_KEY", loaded)
            finally:
                if original_database_url is None:
                    os.environ.pop("DATABASE_URL", None)
                else:
                    os.environ["DATABASE_URL"] = original_database_url
                if original_base_url is None:
                    os.environ.pop("DEEPSEEK_BASE_URL", None)
                else:
                    os.environ["DEEPSEEK_BASE_URL"] = original_base_url
                if original_existing is None:
                    os.environ.pop("EXISTING_KEY", None)
                else:
                    os.environ["EXISTING_KEY"] = original_existing
        finally:
            if tmp_root.exists():
                for path in sorted(tmp_root.glob("**/*"), reverse=True):
                    if path.is_file():
                        path.unlink()
                    elif path.is_dir():
                        path.rmdir()
