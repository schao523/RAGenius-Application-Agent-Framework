"""Document normalization utilities."""
from __future__ import annotations
from typing import Iterable, List
from .schemas import Block


def normalize_documents(documents: Iterable[dict]) -> List[Block]:
    blocks: List[Block] = []
    for doc in documents:
        doc_id = doc.get("doc_id") or doc.get("id")
        if not doc_id:
            raise ValueError("Document missing doc_id")
        raw_blocks = doc.get("blocks") or []
        for raw in raw_blocks:
            block = Block(
                doc_id=doc_id,
                type=raw.get("type", "text"),
                text=raw.get("text"),
                table_raw=raw.get("table_raw"),
                image_ref=raw.get("image_ref"),
                ocr_text=raw.get("ocr_text"),
                caption=raw.get("caption"),
                section_path=raw.get("section_path"),
                metadata=raw.get("metadata", {}),
            )
            blocks.append(block)
    return blocks
