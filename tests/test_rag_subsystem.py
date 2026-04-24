import os
import sys
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
from rag_subsystem.vector_store import factory as store_factory
from rag_subsystem.vector_store.factory import (
    create_vector_store,
    get_default_vector_store,
    clear_default_vector_store_cache,
)
from rag_subsystem.config import ProcessConfig, RetrievalConfig
from rag_subsystem.embedding import embed_text


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
        def semantic_search(self, query_embedding, namespace, top_k, app_id=None):
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
