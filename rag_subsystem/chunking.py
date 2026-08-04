"""Chunking utilities implementing section-first and token chunking."""
from __future__ import annotations
import re
from typing import List
from .schemas import Block
from .utils.hashing import compute_hash


_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def _tokenize(text: str) -> List[str]:
    stripped = text or ""
    # CJK text often has no whitespace separators; tokenize by non-space characters
    # so chunking can split long Chinese/Japanese/Korean sections deterministically.
    if _CJK_RE.search(stripped):
        return [ch for ch in stripped if not ch.isspace()]
    return stripped.split()


def _reconstruct_chunk_text(tokens: List[str], is_cjk: bool) -> str:
    return "".join(tokens) if is_cjk else " ".join(tokens)


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
        is_cjk = bool(_CJK_RE.search(text))
        if len(tokens) <= section_token_threshold:
            chunk_texts = [text]
        else:
            chunk_texts = []
            start = 0
            while start < len(tokens):
                end = min(start + chunk_size, len(tokens))
                chunk_tokens = tokens[start:end]
                chunk_texts.append(_reconstruct_chunk_text(chunk_tokens, is_cjk))
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
