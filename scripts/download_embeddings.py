from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


MODELS = [
    {
        "env": "RAG_EMBEDDING_MODEL_PATH_BGE_LARGE_ZH",
        "local_name": "bge-large-zh",
        "repo_id": "BAAI/bge-large-zh-v1.5",
    },
    {
        "env": "RAG_EMBEDDING_MODEL_PATH_E5_LARGE",
        "local_name": "e5-large",
        "repo_id": "intfloat/e5-large-v2",
    },
]


def download_models(model_root: Path, *, force: bool = False) -> list[dict[str, str]]:
    try:
        from huggingface_hub import snapshot_download
    except Exception as exc:  # pragma: no cover - dependency boundary
        raise RuntimeError(
            "huggingface_hub is required. Install embedding dependencies first."
        ) from exc

    model_root = model_root.resolve()
    model_root.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, str]] = []

    for model in MODELS:
        destination = model_root / model["local_name"]
        if force and destination.exists():
            shutil.rmtree(destination)

        if not destination.exists():
            snapshot_download(
                repo_id=model["repo_id"],
                local_dir=str(destination),
                local_dir_use_symlinks=False,
            )

        results.append(
            {
                "env": model["env"],
                "local_name": model["local_name"],
                "path": str(destination),
                "repo_id": model["repo_id"],
            }
        )

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Download RAGenius local embedding models.")
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    result = download_models(args.model_root, force=args.force)
    print(json.dumps({"models": result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
