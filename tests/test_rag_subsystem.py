import os
import sys
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from rag_subsystem.normalize import normalize_documents
from rag_subsystem.chunking import chunk_blocks
from rag_subsystem.quality_filter import filter_chunks
from rag_subsystem.embedding_router import route
from rag_subsystem.language_detect import detect_language
from rag_subsystem.process_files import process_files
from rag_subsystem.retrieval_data import retrieve_data, _compare_semver
from rag_subsystem.vector_store.in_memory_store import InMemoryVectorStore
from rag_subsystem.vector_store.pgvector_store import SQL_SCHEMA
from rag_subsystem.config import ProcessConfig, RetrievalConfig


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


def test_process_and_retrieval_pipeline():
    documents = [
        {
            "doc_id": "doc3",
            "blocks": [
                {"type": "text", "text": "release notes version1", "metadata": {"version": "1.0.0", "updated_at": "2023-01-01"}},
                {"type": "text", "text": "release notes version2", "metadata": {"version": "2.0.0", "updated_at": "2024-01-01"}},
            ],
        }
    ]
    store = InMemoryVectorStore()
    process_files(documents, ProcessConfig(min_chunk_length=1), store=store)
    result = retrieve_data("release notes", top_k=2, filters={}, config=RetrievalConfig(candidate_k=5, fusion_k=60, top_k=2), store=store)
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


def test_retrieval_falls_back_when_semantic_search_fails():
    class FailingSemanticStore(InMemoryVectorStore):
        def semantic_search(self, query_embedding, namespace, top_k):
            raise RuntimeError("semantic backend unavailable")

    store = FailingSemanticStore()
    documents = [
        {
            "doc_id": "doc4",
            "blocks": [
                {
                    "type": "text",
                    "text": "fallback test content with enough tokens for ingestion and metadata retrieval path to work",
                    "metadata": {"tag": "fallback", "version": "1.0.0", "updated_at": "2024-02-01"},
                }
            ],
        }
    ]
    process_files(documents, ProcessConfig(min_chunk_length=1), store=store)
    result = retrieve_data(
        "tag:fallback retrieval",
        top_k=3,
        filters={},
        config=RetrievalConfig(candidate_k=5, fusion_k=60, top_k=3),
        store=store,
    )
    assert len(result.results) >= 1
    assert "semantic_search_error" in result.debug
