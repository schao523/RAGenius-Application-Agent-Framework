import importlib
import os
import unittest
from unittest.mock import patch


class _TorchStub:
    def __init__(self) -> None:
        self.num_threads = None
        self.num_interop_threads = None

    def set_num_threads(self, value: int) -> None:
        self.num_threads = value

    def set_num_interop_threads(self, value: int) -> None:
        self.num_interop_threads = value


class EmbeddingRuntimeConfigTests(unittest.TestCase):
    def test_local_runtime_caps_threads_by_default(self) -> None:
        with patch.dict(
            os.environ,
            {},
            clear=True,
        ):
            embedding = importlib.import_module("rag_subsystem.embedding")
            embedding = importlib.reload(embedding)
            torch_stub = _TorchStub()
            with patch.object(embedding, "torch", torch_stub, create=True):
                embedding._configure_local_runtime_threads()

            self.assertEqual(os.environ["OMP_NUM_THREADS"], "1")
            self.assertEqual(os.environ["MKL_NUM_THREADS"], "1")
            self.assertEqual(os.environ["NUMEXPR_NUM_THREADS"], "1")
            self.assertEqual(torch_stub.num_threads, 1)
            self.assertEqual(torch_stub.num_interop_threads, 1)

    def test_explicit_thread_setting_is_respected(self) -> None:
        with patch.dict(
            os.environ,
            {"RAG_EMBEDDING_THREADS": "2"},
            clear=True,
        ):
            embedding = importlib.import_module("rag_subsystem.embedding")
            embedding = importlib.reload(embedding)
            torch_stub = _TorchStub()
            with patch.object(embedding, "torch", torch_stub, create=True):
                embedding._configure_local_runtime_threads()

            self.assertEqual(os.environ["OMP_NUM_THREADS"], "2")
            self.assertEqual(os.environ["MKL_NUM_THREADS"], "2")
            self.assertEqual(os.environ["NUMEXPR_NUM_THREADS"], "2")
            self.assertEqual(torch_stub.num_threads, 2)
            self.assertEqual(torch_stub.num_interop_threads, 2)


if __name__ == "__main__":
    unittest.main()
