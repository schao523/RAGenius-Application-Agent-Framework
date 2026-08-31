import os
import json
import sys
from pathlib import Path
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault("RAG_EMBEDDING_BACKEND", "hash")

from rag_subsystem.normalize import normalize_documents
from rag_subsystem.chunking import chunk_blocks
from rag_subsystem.quality_filter import filter_chunks
from rag_subsystem.embedding_router import route
from rag_subsystem.language_detect import detect_language
from rag_subsystem.process_files import process_files
from rag_subsystem.retrieval_data import retrieve_data, _compare_semver
from rag_subsystem.schemas import Chunk, ValidationError
from rag_subsystem.vector_store.in_memory_store import InMemoryVectorStore
from rag_subsystem.vector_store.json_file_store import JsonFileVectorStore
from rag_subsystem.vector_store.pgvector_store import PgVectorStore
from rag_subsystem.vector_store.pgvector_store import SQL_SCHEMA
from rag_subsystem.vector_store import pgvector_store as pgvector_module
from rag_subsystem.vector_store import factory as store_factory
from rag_subsystem.vector_store.factory import (
    create_vector_store,
    get_default_vector_store,
    clear_default_vector_store_cache,
)
from rag_subsystem.config import ProcessConfig, RetrievalConfig
from rag_subsystem.embedding import embed_text, _default_model_dir


def test_pgvector_uses_pure_python_fallback_when_psycopg2_is_unavailable(monkeypatch):
    captured = {}
    expected_connection = object()

    class FakePg8000:
        @staticmethod
        def connect(**kwargs):
            captured.update(kwargs)
            return expected_connection

    monkeypatch.setattr(pgvector_module, "psycopg2", None)
    monkeypatch.setattr(pgvector_module, "pg8000_dbapi", FakePg8000, raising=False)

    store = object.__new__(PgVectorStore)
    store.dsn = "postgresql://rag%20user:p%40ss@db.example:5544/rag%20db"

    assert store._conn() is expected_connection
    assert captured == {
        "user": "rag user",
        "password": "p@ss",
        "host": "db.example",
        "port": 5544,
        "database": "rag db",
    }


def test_pgvector_upsert_serializes_json_for_all_dbapi_drivers():
    calls = []
    cursor_state = {"closed": False}

    class FakeCursor:
        def execute(self, sql, params):
            calls.append((sql, params))

        def close(self):
            cursor_state["closed"] = True

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def cursor(self):
            return FakeCursor()

        def commit(self):
            pass

    store = object.__new__(PgVectorStore)
    store._conn = lambda: FakeConnection()
    chunk = Chunk(
        doc_id="doc-1",
        chunk_id="chunk-1",
        text="text",
        section_path=None,
        order=0,
        language="en",
        embedding_model="test",
        namespace="app:test",
        embedding=[0.1, 0.2],
        metadata={"app_id": "app-1", "nested": {"ok": True}},
        hash="hash-1",
    )

    store.upsert([chunk])

    sql, params = calls[0]
    assert "%s::jsonb" in sql
    assert json.loads(params[8]) == chunk.metadata
    assert cursor_state["closed"] is True


def test_normalize_and_fallbacks():
    documents = [
        {
            "doc_id": "doc1",
            "blocks": [
                {"type": "table", "table_raw": [["a", "b"], ["c", "d"]]},
                {"type": "image", "ocr_text": "ocr text here"},
            ],
        }
    ]
    blocks = normalize_documents(documents)
    chunks = chunk_blocks(blocks, chunk_size=400, overlap=60, section_token_threshold=1200)
    assert any("a b" in c["text"] for c in chunks)
    assert any("ocr text here" in c["text"] for c in chunks)


def test_chunking_long_section_and_quality_filter():
    long_text = " ".join(["word"] * 1300)
    documents = [{"doc_id": "doc2", "blocks": [{"type": "text", "text": long_text}]}]
    blocks = normalize_documents(documents)
    chunks = chunk_blocks(blocks, chunk_size=400, overlap=60, section_token_threshold=1200)
    assert len(chunks) > 1
    cfg = ProcessConfig(min_chunk_length=10)
    filtered, counts = filter_chunks(chunks, cfg)
    assert counts["skipped_too_short_count"] == 0
    assert counts["skipped_near_dup_count"] > 0
    assert len(filtered) == 1


def test_chunking_cjk_splits_without_whitespace():
    long_cjk = "耶穌" * 1500
    documents = [{"doc_id": "doc-cjk", "blocks": [{"type": "text", "text": long_cjk}]}]
    blocks = normalize_documents(documents)
    chunks = chunk_blocks(blocks, chunk_size=400, overlap=60, section_token_threshold=1200)
    assert len(chunks) > 1
    assert all(" " not in c["text"] for c in chunks)


def test_quality_filter_cjk_min_length_counts_char_tokens():
    chunks = [{"doc_id": "doc-q-cjk", "text": "耶穌" * 40, "metadata": {}, "hash": "h1"}]
    filtered, counts = filter_chunks(chunks, ProcessConfig(min_chunk_length=30))
    assert len(filtered) == 1
    assert counts["skipped_too_short_count"] == 0


def test_embedding_router_language_detection():
    assert detect_language("这是中文") == "zh"
    zh_route = route("zh")
    assert zh_route.model == "bge-large-zh"
    en_route = route("en")
    assert en_route.namespace.startswith("en:")


def test_default_model_dir_is_repo_relative_not_cwd_relative():
    original_cwd = os.getcwd()
    try:
        os.chdir(os.path.join(ROOT, "ragenius_app_skeleton"))
        model_dir = _default_model_dir("bge-large-zh")
        assert model_dir == Path(ROOT, "rag_subsystem", "models", "bge-large-zh").resolve()
    finally:
        os.chdir(original_cwd)


def test_in_memory_store_and_upsert():
    store = InMemoryVectorStore()
    chunk = type("Mock", (), {})()
    chunk.doc_id = "docA"
    chunk.chunk_id = "docA::0"
    chunk.text = "hello world"
    chunk.section_path = None
    chunk.order = 0
    chunk.language = "en"
    chunk.embedding_model = "e5-large"
    chunk.namespace = "en:e5-large"
    chunk.embedding = [1.0] * 8
    chunk.metadata = {"version": "1.0.0"}
    chunk.hash = "hash1"
    store.upsert([chunk])
    chunk.embedding = [0.5] * 8
    store.upsert([chunk])
    results = store.semantic_search([0.5] * 8, "en:e5-large", 5)
    assert results[0][0].embedding == [0.5] * 8
    meta_results = store.metadata_search({"version": "1.0.0"}, "en:e5-large", 5)
    assert len(meta_results) == 1


def test_in_memory_upsert_uses_chunk_id_key():
    store = InMemoryVectorStore()
    chunk1 = type("Mock", (), {})()
    chunk1.doc_id = "docA"
    chunk1.chunk_id = "docA::0"
    chunk1.text = "same text"
    chunk1.section_path = None
    chunk1.order = 0
    chunk1.language = "en"
    chunk1.embedding_model = "e5-large"
    chunk1.namespace = "en:e5-large"
    chunk1.embedding = [1.0] * 8
    chunk1.metadata = {"version": "1.0.0"}
    chunk1.hash = "samehash"

    chunk2 = type("Mock", (), {})()
    chunk2.doc_id = "docA"
    chunk2.chunk_id = "docA::1"
    chunk2.text = "same text"
    chunk2.section_path = None
    chunk2.order = 1
    chunk2.language = "en"
    chunk2.embedding_model = "e5-large"
    chunk2.namespace = "en:e5-large"
    chunk2.embedding = [1.0] * 8
    chunk2.metadata = {"version": "1.0.0"}
    chunk2.hash = "samehash"

    store.upsert([chunk1, chunk2])
    results = store.semantic_search([1.0] * 8, "en:e5-large", 10)
    assert len(results) == 2


def test_in_memory_dimension_mismatch_raises():
    store = InMemoryVectorStore()
    chunk = type("Mock", (), {})()
    chunk.doc_id = "docA"
    chunk.chunk_id = "docA::0"
    chunk.text = "hello world"
    chunk.section_path = None
    chunk.order = 0
    chunk.language = "en"
    chunk.embedding_model = "e5-large"
    chunk.namespace = "en:e5-large"
    chunk.embedding = [1.0] * 8
    chunk.metadata = {"version": "1.0.0"}
    chunk.hash = "hash1"
    store.upsert([chunk])
    with pytest.raises(ValueError, match="Embedding dimension mismatch"):
        store.semantic_search([1.0] * 7, "en:e5-large", 5)


def test_json_store_dimension_mismatch_raises():
    path = os.path.join(ROOT, "tests", "_tmp_json_vectors_test.json")
    if os.path.exists(path):
        os.remove(path)
    try:
        store = JsonFileVectorStore(path)
        chunk = Chunk(
            doc_id="docA",
            chunk_id="docA::0",
            text="hello world",
            section_path=None,
            order=0,
            language="en",
            embedding_model="e5-large",
            namespace="en:e5-large",
            embedding=[1.0] * 8,
            metadata={"version": "1.0.0"},
            hash="hash1",
        )
        store.upsert([chunk])
        with pytest.raises(ValueError, match="Embedding dimension mismatch"):
            store.semantic_search([1.0] * 7, "en:e5-large", 5)
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_process_and_retrieval_pipeline():
    documents = [
        {
            "doc_id": "doc3",
            "blocks": [
                {
                    "type": "text",
                    "text": "release notes version1",
                    "metadata": {"app_id": "app-a", "version": "1.0.0", "updated_at": "2023-01-01"},
                },
                {
                    "type": "text",
                    "text": "release notes version2",
                    "metadata": {"app_id": "app-a", "version": "2.0.0", "updated_at": "2024-01-01"},
                },
            ],
        }
    ]
    store = InMemoryVectorStore()
    process_files(documents, ProcessConfig(min_chunk_length=1), store=store)
    result = retrieve_data(
        "release notes",
        top_k=2,
        filters={"app_id": "app-a"},
        config=RetrievalConfig(candidate_k=5, fusion_k=60, top_k=2),
        store=store,
    )
    # ensure version preference picks newer version 2
    assert any(c.chunk.metadata.get("version") == "2.0.0" for c in result.results)
    assert "fusion_scores" in result.debug


def test_process_files_populates_filename_metadata_from_source_path():
    documents = [
        {
            "doc_id": "doc-filemeta",
            "blocks": [
                {
                    "type": "text",
                    "text": "filename metadata enrichment test text with enough tokens for ingestion.",
                    "metadata": {
                        "app_id": "app-filemeta",
                        "source_path": r"C:\\tmp\\Bible 新約聖經和合本.PDF",
                    },
                }
            ],
        }
    ]
    store = InMemoryVectorStore()
    process_files(documents, ProcessConfig(min_chunk_length=1), store=store)
    assert len(store._items) >= 1
    meta = store._items[0].metadata
    assert meta.get("filename") == "Bible 新約聖經和合本.PDF"
    assert meta.get("filename_norm") == "bible 新約聖經和合本.pdf"


def test_compare_semver():
    assert _compare_semver("1.0.0", "1.0.0") == 0
    assert _compare_semver("2.0.0", "1.9.9") > 0
    assert _compare_semver("0.1.0", "0.1.1") < 0


def test_pgvector_schema_contains_on_conflict():
    assert "ON CONFLICT" in SQL_SCHEMA
    assert "CREATE TABLE IF NOT EXISTS rag_chunks" in SQL_SCHEMA
    assert "app_id TEXT NOT NULL" in SQL_SCHEMA
    assert "embedding vector(1024)" in SQL_SCHEMA


def test_retrieval_falls_back_when_semantic_search_fails():
    class FailingSemanticStore(InMemoryVectorStore):
        def semantic_search(self, query_embedding, namespace, top_k, app_id=None, doc_filter=None):
            raise RuntimeError("semantic backend unavailable")

    store = FailingSemanticStore()
    documents = [
        {
            "doc_id": "doc4",
            "blocks": [
                {
                    "type": "text",
                    "text": "fallback test content with enough tokens for ingestion and metadata retrieval path to work",
                    "metadata": {"app_id": "app-fallback", "tag": "fallback", "version": "1.0.0", "updated_at": "2024-02-01"},
                }
            ],
        }
    ]
    process_files(documents, ProcessConfig(min_chunk_length=1), store=store)
    result = retrieve_data(
        "tag:fallback retrieval",
        top_k=3,
        filters={"app_id": "app-fallback"},
        config=RetrievalConfig(candidate_k=5, fusion_k=60, top_k=3),
        store=store,
    )
    assert len(result.results) >= 1
    assert "semantic_search_error" in result.debug


def test_retrieval_source_hybrid_when_semantic_and_metadata_both_match():
    documents = [
        {
            "doc_id": "doc-hybrid",
            "blocks": [
                {
                    "type": "text",
                    "text": "hybrid source test content with enough tokens for both semantic and metadata matching",
                    "metadata": {"app_id": "app-hybrid", "tag": "hybrid", "version": "1.0.0", "updated_at": "2024-02-01"},
                }
            ],
        }
    ]
    store = InMemoryVectorStore()
    process_files(documents, ProcessConfig(min_chunk_length=1), store=store)
    result = retrieve_data(
        "hybrid source test",
        top_k=3,
        filters={"app_id": "app-hybrid", "tag": "hybrid"},
        config=RetrievalConfig(candidate_k=5, fusion_k=60, top_k=3),
        store=store,
    )
    assert len(result.results) >= 1
    assert result.results[0].source == "hybrid"


def test_retrieval_filters_by_filename_case_insensitive():
    documents = [
        {
            "doc_id": "doc-file-a",
            "blocks": [
                {
                    "type": "text",
                    "text": "shared retrieval query token alpha",
                    "metadata": {"app_id": "app-file-filter", "filename": "Book One.PDF", "version": "1.0.0"},
                }
            ],
        },
        {
            "doc_id": "doc-file-b",
            "blocks": [
                {
                    "type": "text",
                    "text": "shared retrieval query token alpha",
                    "metadata": {"app_id": "app-file-filter", "filename": "Book Two.pdf", "version": "1.0.0"},
                }
            ],
        },
    ]
    store = InMemoryVectorStore()
    process_files(documents, ProcessConfig(min_chunk_length=1), store=store)
    result = retrieve_data(
        "shared retrieval query",
        top_k=10,
        filters={"app_id": "app-file-filter", "filename": "book one.pdf"},
        config=RetrievalConfig(candidate_k=20, fusion_k=60, top_k=10),
        store=store,
    )
    assert len(result.results) >= 1
    assert all(r.chunk.doc_id == "doc-file-a" for r in result.results)


def test_retrieval_filters_by_doc_id():
    documents = [
        {
            "doc_id": "doc-filter-id-a",
            "blocks": [
                {
                    "type": "text",
                    "text": "queryable text for doc id a",
                    "metadata": {"app_id": "app-doc-filter", "filename": "a.pdf"},
                }
            ],
        },
        {
            "doc_id": "doc-filter-id-b",
            "blocks": [
                {
                    "type": "text",
                    "text": "queryable text for doc id b",
                    "metadata": {"app_id": "app-doc-filter", "filename": "b.pdf"},
                }
            ],
        },
    ]
    store = InMemoryVectorStore()
    process_files(documents, ProcessConfig(min_chunk_length=1), store=store)
    result = retrieve_data(
        "queryable text",
        top_k=10,
        filters={"app_id": "app-doc-filter", "doc_id": "doc-filter-id-b"},
        config=RetrievalConfig(candidate_k=20, fusion_k=60, top_k=10),
        store=store,
    )
    assert len(result.results) >= 1
    assert all(r.chunk.doc_id == "doc-filter-id-b" for r in result.results)


def test_retrieval_filters_by_filename_in():
    documents = [
        {
            "doc_id": "doc-in-a",
            "blocks": [
                {
                    "type": "text",
                    "text": "multi file include alpha",
                    "metadata": {"app_id": "app-file-in", "filename": "A.md"},
                }
            ],
        },
        {
            "doc_id": "doc-in-b",
            "blocks": [
                {
                    "type": "text",
                    "text": "multi file include alpha",
                    "metadata": {"app_id": "app-file-in", "filename": "B.md"},
                }
            ],
        },
        {
            "doc_id": "doc-in-c",
            "blocks": [
                {
                    "type": "text",
                    "text": "multi file include alpha",
                    "metadata": {"app_id": "app-file-in", "filename": "C.md"},
                }
            ],
        },
    ]
    store = InMemoryVectorStore()
    process_files(documents, ProcessConfig(min_chunk_length=1), store=store)
    result = retrieve_data(
        "multi file include",
        top_k=10,
        filters={"app_id": "app-file-in", "filename_in": ["a.md", "c.md"]},
        config=RetrievalConfig(candidate_k=20, fusion_k=60, top_k=10),
        store=store,
    )
    assert len(result.results) >= 1
    allowed = {"doc-in-a", "doc-in-c"}
    assert all(r.chunk.doc_id in allowed for r in result.results)
    assert "doc-in-b" not in {r.chunk.doc_id for r in result.results}


def test_semantic_filename_in_pre_scoping_keeps_relevant_not_globally_top_ranked(monkeypatch):
    class ScopedStore(InMemoryVectorStore):
        pass

    store = ScopedStore()
    # Build manually to control ranking with a 2D embedding space.
    from rag_subsystem.schemas import Chunk

    chunks = [
        Chunk(
            doc_id="doc-noise",
            chunk_id="doc-noise::0",
            text="noise",
            section_path=None,
            order=0,
            language="en",
            embedding_model="e5-large",
            namespace="app-pre:en:e5-large",
            embedding=[1.0, 0.0],
            metadata={"app_id": "app-pre", "filename": "noise.md", "filename_norm": "noise.md"},
            hash="h-noise",
        ),
        Chunk(
            doc_id="doc-target",
            chunk_id="doc-target::0",
            text="target",
            section_path=None,
            order=0,
            language="en",
            embedding_model="e5-large",
            namespace="app-pre:en:e5-large",
            embedding=[0.6, 0.0],
            metadata={"app_id": "app-pre", "filename": "target.md", "filename_norm": "target.md"},
            hash="h-target",
        ),
    ]
    store.upsert(chunks)

    class RouteObj:
        language = "en"
        model = "e5-large"
        namespace = "en:e5-large"

    import rag_subsystem.retrieval_data as rd

    monkeypatch.setattr(rd, "detect_language", lambda _: "en")
    monkeypatch.setattr(rd, "route", lambda _: RouteObj())
    monkeypatch.setattr(rd, "embed_text", lambda *_args, **_kwargs: [1.0, 0.0])

    result = retrieve_data(
        "q",
        top_k=1,
        filters={"app_id": "app-pre", "filename_in": ["target.md"]},
        config=RetrievalConfig(candidate_k=1, fusion_k=60, top_k=1),
        store=store,
    )
    assert len(result.results) == 1
    assert result.results[0].chunk.doc_id == "doc-target"
    assert result.debug.get("semantic_pre_scoped") is True


def test_semantic_doc_id_pre_scoping_under_namespace_competition(monkeypatch):
    from rag_subsystem.schemas import Chunk
    import rag_subsystem.retrieval_data as rd

    store = InMemoryVectorStore()
    store.upsert(
        [
            Chunk(
                doc_id="doc-a",
                chunk_id="doc-a::0",
                text="a",
                section_path=None,
                order=0,
                language="en",
                embedding_model="e5-large",
                namespace="app-docscope:en:e5-large",
                embedding=[1.0, 0.0],
                metadata={"app_id": "app-docscope", "filename": "a.md", "filename_norm": "a.md"},
                hash="h-a",
            ),
            Chunk(
                doc_id="doc-b",
                chunk_id="doc-b::0",
                text="b",
                section_path=None,
                order=0,
                language="en",
                embedding_model="e5-large",
                namespace="app-docscope:en:e5-large",
                embedding=[0.8, 0.0],
                metadata={"app_id": "app-docscope", "filename": "b.md", "filename_norm": "b.md"},
                hash="h-b",
            ),
        ]
    )

    class RouteObj:
        language = "en"
        model = "e5-large"
        namespace = "en:e5-large"

    monkeypatch.setattr(rd, "detect_language", lambda _: "en")
    monkeypatch.setattr(rd, "route", lambda _: RouteObj())
    monkeypatch.setattr(rd, "embed_text", lambda *_args, **_kwargs: [1.0, 0.0])

    result = retrieve_data(
        "q",
        top_k=1,
        filters={"app_id": "app-docscope", "doc_id": "doc-b"},
        config=RetrievalConfig(candidate_k=1, fusion_k=60, top_k=1),
        store=store,
    )
    assert len(result.results) == 1
    assert result.results[0].chunk.doc_id == "doc-b"


def test_metadata_and_semantic_paths_consistent_with_filename_scope():
    documents = [
        {
            "doc_id": "doc-cons-a",
            "blocks": [
                {"type": "text", "text": "consistent path alpha", "metadata": {"app_id": "app-cons", "filename": "A.md", "tag": "t"}}
            ],
        },
        {
            "doc_id": "doc-cons-b",
            "blocks": [
                {"type": "text", "text": "consistent path alpha", "metadata": {"app_id": "app-cons", "filename": "B.md", "tag": "t"}}
            ],
        },
    ]
    store = InMemoryVectorStore()
    process_files(documents, ProcessConfig(min_chunk_length=1), store=store)
    result = retrieve_data(
        "consistent path alpha",
        top_k=10,
        filters={"app_id": "app-cons", "filename_in": ["A.md"], "tag": "t"},
        config=RetrievalConfig(candidate_k=10, fusion_k=60, top_k=10),
        store=store,
    )
    assert len(result.results) >= 1
    assert all(r.chunk.doc_id == "doc-cons-a" for r in result.results)


def test_filename_filter_respects_app_isolation_with_same_filename():
    documents = [
        {
            "doc_id": "doc-same-name-a",
            "blocks": [
                {
                    "type": "text",
                    "text": "shared filename content for app A",
                    "metadata": {"app_id": "app-file-iso-a", "filename": "shared.pdf", "version": "1.0.0"},
                }
            ],
        },
        {
            "doc_id": "doc-same-name-b",
            "blocks": [
                {
                    "type": "text",
                    "text": "shared filename content for app B",
                    "metadata": {"app_id": "app-file-iso-b", "filename": "shared.pdf", "version": "1.0.0"},
                }
            ],
        },
    ]
    store = InMemoryVectorStore()
    process_files(documents, ProcessConfig(min_chunk_length=1), store=store)

    result_a = retrieve_data(
        "shared filename content",
        top_k=10,
        filters={"app_id": "app-file-iso-a", "filename": "shared.pdf"},
        config=RetrievalConfig(candidate_k=20, fusion_k=60, top_k=10),
        store=store,
    )
    assert len(result_a.results) >= 1
    assert all(r.chunk.metadata.get("app_id") == "app-file-iso-a" for r in result_a.results)
    assert all(r.chunk.doc_id == "doc-same-name-a" for r in result_a.results)

    result_b = retrieve_data(
        "shared filename content",
        top_k=10,
        filters={"app_id": "app-file-iso-b", "filename": "shared.pdf"},
        config=RetrievalConfig(candidate_k=20, fusion_k=60, top_k=10),
        store=store,
    )
    assert len(result_b.results) >= 1
    assert all(r.chunk.metadata.get("app_id") == "app-file-iso-b" for r in result_b.results)
    assert all(r.chunk.doc_id == "doc-same-name-b" for r in result_b.results)


def test_retrieval_respects_max_chunks_per_doc_diversity_cap():
    store = InMemoryVectorStore()
    documents = [
        {
            "doc_id": "doc-many",
            "blocks": [
                {"type": "text", "text": "alpha token one", "metadata": {"app_id": "app-diversity"}},
                {"type": "text", "text": "alpha token two", "metadata": {"app_id": "app-diversity"}},
                {"type": "text", "text": "alpha token three", "metadata": {"app_id": "app-diversity"}},
            ],
        },
        {
            "doc_id": "doc-other",
            "blocks": [
                {"type": "text", "text": "alpha token other", "metadata": {"app_id": "app-diversity"}},
            ],
        },
    ]
    process_files(documents, ProcessConfig(min_chunk_length=1), store=store)
    result = retrieve_data(
        "alpha token",
        top_k=10,
        filters={"app_id": "app-diversity"},
        config=RetrievalConfig(candidate_k=20, fusion_k=60, top_k=10, max_chunks_per_doc=1),
        store=store,
    )
    counts = {}
    for r in result.results:
        counts[r.chunk.doc_id] = counts.get(r.chunk.doc_id, 0) + 1
    assert counts.get("doc-many", 0) <= 1
    assert counts.get("doc-other", 0) <= 1


def test_retrieval_weighting_can_prioritize_metadata_rank():
    store = InMemoryVectorStore()
    documents = [
        {
            "doc_id": "doc-w-1",
            "blocks": [
                {"type": "text", "text": "weighted retrieval content one", "metadata": {"app_id": "app-weight", "tag": "t"}},
            ],
        },
        {
            "doc_id": "doc-w-2",
            "blocks": [
                {"type": "text", "text": "weighted retrieval content two", "metadata": {"app_id": "app-weight", "tag": "t"}},
            ],
        },
    ]
    process_files(documents, ProcessConfig(min_chunk_length=1), store=store)
    result = retrieve_data(
        "weighted retrieval content",
        top_k=5,
        filters={"app_id": "app-weight", "tag": "t"},
        config=RetrievalConfig(candidate_k=10, fusion_k=60, top_k=5, semantic_weight=0.1, metadata_weight=2.0),
        store=store,
    )
    assert len(result.results) >= 1
    assert result.debug.get("weights") == {"semantic": 0.1, "metadata": 2.0, "lexical": 1.5}


def test_chinese_query_lexical_fallback_recovers_when_semantic_misses(monkeypatch):
    from rag_subsystem.schemas import Chunk
    import rag_subsystem.retrieval_data as rd

    store = InMemoryVectorStore()
    store.upsert(
        [
            Chunk(
                doc_id="doc-noise",
                chunk_id="doc-noise::0",
                text="無關內容",
                section_path=None,
                order=0,
                language="zh",
                embedding_model="bge-large-zh",
                namespace="app-zh:zh:bge-large-zh",
                embedding=[1.0, 0.0],
                metadata={"app_id": "app-zh", "filename": "noise.md", "filename_norm": "noise.md"},
                hash="h-noise",
            ),
            Chunk(
                doc_id="doc-observation",
                chunk_id="doc-observation::0",
                text="細察事實觀察的項目 包含在這份 observation_guide.md",
                section_path=None,
                order=0,
                language="zh",
                embedding_model="bge-large-zh",
                namespace="app-zh:zh:bge-large-zh",
                embedding=[0.0, 1.0],
                metadata={"app_id": "app-zh", "filename": "observation_guide.md", "filename_norm": "observation_guide.md"},
                hash="h-obs",
            ),
        ]
    )

    class RouteObj:
        language = "zh"
        model = "bge-large-zh"
        namespace = "zh:bge-large-zh"

    # Force semantic query vector to favor doc-noise; lexical should recover doc-observation.
    monkeypatch.setattr(rd, "detect_language", lambda _: "zh")
    monkeypatch.setattr(rd, "route", lambda _: RouteObj())
    monkeypatch.setattr(rd, "embed_text", lambda *_args, **_kwargs: [1.0, 0.0])

    result = retrieve_data(
        "細察事實觀察的項目",
        top_k=1,
        filters={"app_id": "app-zh"},
        config=RetrievalConfig(
            candidate_k=1,
            fusion_k=60,
            top_k=1,
            semantic_weight=0.1,
            metadata_weight=0.0,
            lexical_weight=3.0,
            lexical_candidate_k=10,
        ),
        store=store,
    )
    assert len(result.results) == 1
    assert result.results[0].chunk.doc_id == "doc-observation"
    assert len(result.debug.get("lexical_candidates", [])) >= 1


def test_factory_resolves_pgvector_from_env(monkeypatch):
    class FakePgStore:
        def __init__(self, dsn: str, bootstrap_schema: bool = True):
            self.dsn = dsn
            self.bootstrap_schema = bootstrap_schema

    monkeypatch.setenv("RAG_VECTOR_STORE_BACKEND", "pgvector")
    monkeypatch.setenv("RAG_VECTOR_STORE_DSN", "postgresql://x:y@localhost:5433/db")
    monkeypatch.setattr(store_factory, "PgVectorStore", FakePgStore)
    store = create_vector_store()
    assert isinstance(store, FakePgStore)
    assert store.dsn == "postgresql://x:y@localhost:5433/db"
    assert store.bootstrap_schema is True


def test_factory_auto_without_dsn_uses_in_memory(monkeypatch):
    monkeypatch.setenv("RAG_VECTOR_STORE_BACKEND", "auto")
    monkeypatch.delenv("RAG_VECTOR_STORE_DSN", raising=False)
    monkeypatch.delenv("PGVECTOR_DSN", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    store = create_vector_store()
    assert isinstance(store, InMemoryVectorStore)


def test_default_store_cache_clear(monkeypatch):
    monkeypatch.setenv("RAG_VECTOR_STORE_BACKEND", "in_memory")
    clear_default_vector_store_cache()
    store = get_default_vector_store()
    assert isinstance(store, InMemoryVectorStore)


def test_factory_fallback_in_memory_when_pgvector_unavailable(monkeypatch):
    class FailingPgStore:
        def __init__(self, dsn: str, bootstrap_schema: bool = True):
            raise RuntimeError("cannot connect")

    monkeypatch.setenv("RAG_VECTOR_STORE_BACKEND", "pgvector")
    monkeypatch.setenv("RAG_VECTOR_STORE_PGVECTOR_FALLBACK", "in_memory")
    monkeypatch.setattr(store_factory, "PgVectorStore", FailingPgStore)
    store = create_vector_store()
    assert isinstance(store, InMemoryVectorStore)


def test_factory_explicit_error_when_pgvector_unavailable(monkeypatch):
    class FailingPgStore:
        def __init__(self, dsn: str, bootstrap_schema: bool = True):
            raise RuntimeError("cannot connect")

    monkeypatch.setenv("RAG_VECTOR_STORE_BACKEND", "pgvector")
    monkeypatch.setenv("RAG_VECTOR_STORE_PGVECTOR_FALLBACK", "error")
    monkeypatch.setattr(store_factory, "PgVectorStore", FailingPgStore)
    with pytest.raises(RuntimeError, match="fallback mode is 'error'"):
        create_vector_store()


def test_cross_app_isolation_prevents_leakage():
    store = InMemoryVectorStore()
    documents = [
        {
            "doc_id": "doc_app_a",
            "blocks": [
                {
                    "type": "text",
                    "text": "policy text for app A only",
                    "metadata": {"app_id": "app-a", "version": "1.0.0", "updated_at": "2024-01-01"},
                }
            ],
        },
        {
            "doc_id": "doc_app_b",
            "blocks": [
                {
                    "type": "text",
                    "text": "policy text for app B only",
                    "metadata": {"app_id": "app-b", "version": "1.0.0", "updated_at": "2024-01-01"},
                }
            ],
        },
    ]
    process_files(documents, ProcessConfig(min_chunk_length=1), store=store)
    result = retrieve_data(
        "policy text",
        top_k=10,
        filters={"app_id": "app-a"},
        config=RetrievalConfig(candidate_k=20, fusion_k=60, top_k=10),
        store=store,
    )
    assert len(result.results) >= 1
    assert all(c.chunk.metadata.get("app_id") == "app-a" for c in result.results)


def test_retrieve_requires_app_id_for_isolation():
    with pytest.raises(ValidationError, match="app_id is required"):
        retrieve_data("policy text", top_k=5, filters={}, config=RetrievalConfig(), store=InMemoryVectorStore())


def test_reingest_deletes_stale_chunks_for_same_doc_and_app():
    store = InMemoryVectorStore()
    first = [
        {
            "doc_id": "doc-stale",
            "blocks": [
                {"type": "text", "text": "alpha old chunk", "metadata": {"app_id": "app-a", "version": "1.0.0"}},
                {"type": "text", "text": "beta old chunk", "metadata": {"app_id": "app-a", "version": "1.0.0"}},
            ],
        }
    ]
    second = [
        {
            "doc_id": "doc-stale",
            "blocks": [
                {"type": "text", "text": "gamma new chunk", "metadata": {"app_id": "app-a", "version": "2.0.0"}}
            ],
        }
    ]
    process_files(first, ProcessConfig(min_chunk_length=1), store=store)
    process_files(second, ProcessConfig(min_chunk_length=1), store=store)
    result = retrieve_data(
        "gamma new",
        top_k=10,
        filters={"app_id": "app-a"},
        config=RetrievalConfig(candidate_k=20, fusion_k=60, top_k=10),
        store=store,
    )
    assert len(result.results) == 1
    assert "gamma new chunk" in result.results[0].chunk.text


def test_hash_embedding_backend_outputs_1024():
    vec = embed_text("sample embedding text", "e5-large")
    assert len(vec) == 1024
