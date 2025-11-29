"""Chunking utilities implementing section-first and token chunking."""
from __future__ import annotations
from typing import List
from .schemas import Block
from .utils.hashing import compute_hash


def _tokenize(text: str) -> List[str]:
    return text.split()


def _apply_table_fallback(block: Block) -> str:
    if block.text:
        return block.text
    if block.table_raw:
        rows = [" ".join(row) for row in block.table_raw if row]
        return "\n".join(rows)
    return ""


def _apply_image_fallback(block: Block, existing_text: str) -> str:
    if existing_text:
        return existing_text
    if block.ocr_text:
        return block.ocr_text
    if block.caption:
        return block.caption
    return ""


def chunk_blocks(blocks: List[Block], chunk_size: int, overlap: int, section_token_threshold: int) -> List[dict]:
    chunks: List[dict] = []
    order = 0
    for block in blocks:
        text = _apply_table_fallback(block)
        text = _apply_image_fallback(block, text)
        if not text:
            continue
        tokens = _tokenize(text)
        if len(tokens) <= section_token_threshold:
            chunk_texts = [text]
        else:
            chunk_texts = []
            start = 0
            while start < len(tokens):
                end = min(start + chunk_size, len(tokens))
                chunk_tokens = tokens[start:end]
                chunk_texts.append(" ".join(chunk_tokens))
                if end == len(tokens):
                    break
                start = end - overlap
        for chunk_text in chunk_texts:
            chunks.append(
                {
                    "doc_id": block.doc_id,
                    "text": chunk_text,
                    "section_path": block.section_path,
                    "order": order,
                    "metadata": dict(block.metadata),
                    "hash": compute_hash(chunk_text),
                }
            )
            order += 1
    return chunks
