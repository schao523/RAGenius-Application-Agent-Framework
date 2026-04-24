"""Pre-download sentence-transformer models for offline local inference.

Usage:
  python rag_subsystem/scripts/prefetch_embedding_models.py
"""
from __future__ import annotations

import os
from pathlib import Path

from sentence_transformers import SentenceTransformer

MODEL_MAP = {
    "e5-large": "intfloat/e5-large-v2",
    "bge-large-zh": "BAAI/bge-large-zh-v1.5",
}


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out_dir = root / "models"
    out_dir.mkdir(parents=True, exist_ok=True)

    cache_folder = os.getenv("RAG_HF_HUB_CACHE")
    token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_HUB_TOKEN")

    for model_name, hf_id in MODEL_MAP.items():
        print(f"Downloading {hf_id} for {model_name}...")
        kwargs = {}
        if cache_folder:
            kwargs["cache_folder"] = cache_folder
        if token:
            kwargs["token"] = token
        try:
            model = SentenceTransformer(hf_id, device="cpu", **kwargs)
            target = out_dir / model_name
            target.mkdir(parents=True, exist_ok=True)
            model.save(str(target))
            print(f"Saved {model_name} -> {target}")
        except Exception as exc:
            print(f"Failed to download {hf_id}: {exc}")


if __name__ == "__main__":
    main()
