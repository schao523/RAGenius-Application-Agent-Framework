"""Background-friendly batched PDF ingestion into pgvector with local embeddings.

Example:
  python rag_subsystem/scripts/ingest_pdf_batched_pg.py ^
    --pdf "C:\\path\\book.pdf" ^
    --app-id church-history-real-v1 ^
    --doc-prefix church-history-upper-v1 ^
    --dsn postgresql://ragenius:ragenius@localhost:5433/ragenius
"""
from __future__ import annotations

import argparse
import time
from collections import defaultdict

from pypdf import PdfReader

from rag_subsystem.chunking import chunk_blocks
from rag_subsystem.config import ProcessConfig
from rag_subsystem.embedding import _load_local_model
from rag_subsystem.embedding_router import route
from rag_subsystem.language_detect import detect_language
from rag_subsystem.normalize import normalize_documents
from rag_subsystem.quality_filter import filter_chunks
from rag_subsystem.schemas import Chunk
from rag_subsystem.vector_store.pgvector_store import PgVectorStore


def ingest_batch(
    store: PgVectorStore,
    text: str,
    app_id: str,
    doc_id: str,
    source_path: str,
    cfg: ProcessConfig,
) -> int:
    docs = [
        {
            "doc_id": doc_id,
            "blocks": [
                {
                    "type": "text",
                    "text": text,
                    "metadata": {
                        "app_id": app_id,
                        "source_path": source_path,
                        "version": "1.0.0",
                    },
                }
            ],
        }
    ]
    blocks = normalize_documents(docs)
    raw = chunk_blocks(blocks, cfg.chunk_size, cfg.chunk_overlap, cfg.section_token_threshold)
    chunks_raw, _ = filter_chunks(raw, cfg)
    by_route: dict[tuple[str, str, str], list[tuple[int, dict]]] = defaultdict(list)
    for idx, c in enumerate(chunks_raw):
        r = route(detect_language(c["text"]))
        namespace = f"{app_id}:{r.namespace}"
        by_route[(r.language, r.model, namespace)].append((idx, c))

    inserted = 0
    for (lang, model_name, namespace), entries in by_route.items():
        model = _load_local_model(model_name)
        infer_batch_size = 32
        to_upsert: list[Chunk] = []
        for i in range(0, len(entries), infer_batch_size):
            batch = entries[i : i + infer_batch_size]
            texts = [x[1]["text"] for x in batch]
            embeddings = model.encode(
                texts,
                normalize_embeddings=True,
                convert_to_numpy=True,
                batch_size=infer_batch_size,
            )
            for (idx, c), emb in zip(batch, embeddings):
                to_upsert.append(
                    Chunk(
                        doc_id=c["doc_id"],
                        chunk_id=f"{c['doc_id']}::{idx}",
                        text=c["text"],
                        section_path=c.get("section_path"),
                        order=c.get("order", idx),
                        language=lang,
                        embedding_model=model_name,
                        namespace=namespace,
                        embedding=[float(v) for v in emb.tolist()],
                        metadata=c.get("metadata", {}),
                        hash=c["hash"],
                    )
                )
        if to_upsert:
            store.delete_by_doc_id(doc_id, app_id=app_id)
            store.upsert(to_upsert)
            inserted += len(to_upsert)
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--app-id", required=True)
    parser.add_argument("--doc-prefix", required=True)
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--page-batch", type=int, default=80)
    parser.add_argument("--chunk-size", type=int, default=800)
    parser.add_argument("--chunk-overlap", type=int, default=120)
    parser.add_argument("--section-token-threshold", type=int, default=2400)
    parser.add_argument("--min-chunk-length", type=int, default=30)
    args = parser.parse_args()

    started = time.time()
    cfg = ProcessConfig(
        min_chunk_length=args.min_chunk_length,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        section_token_threshold=args.section_token_threshold,
    )
    store = PgVectorStore(args.dsn)
    reader = PdfReader(args.pdf)
    total_pages = len(reader.pages)
    print(f"[start] pages={total_pages} page_batch={args.page_batch}", flush=True)

    total_inserted = 0
    batch_no = 0
    for start_page in range(0, total_pages, args.page_batch):
        end_page = min(start_page + args.page_batch, total_pages)
        batch_no += 1
        texts: list[str] = []
        for i in range(start_page, end_page):
            txt = (reader.pages[i].extract_text() or "").strip()
            if txt:
                texts.append(txt)
        if not texts:
            print(f"[batch {batch_no}] pages={start_page+1}-{end_page} skipped(empty)", flush=True)
            continue
        doc_id = f"{args.doc_prefix}-p{start_page+1}-{end_page}"
        inserted = ingest_batch(
            store=store,
            text="\n\n".join(texts),
            app_id=args.app_id,
            doc_id=doc_id,
            source_path=args.pdf,
            cfg=cfg,
        )
        total_inserted += inserted
        print(
            f"[batch {batch_no}] pages={start_page+1}-{end_page} inserted={inserted} total={total_inserted}",
            flush=True,
        )

    elapsed = time.time() - started
    print(f"[done] inserted={total_inserted} seconds={elapsed:.1f}", flush=True)


if __name__ == "__main__":
    main()

