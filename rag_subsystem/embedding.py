"""Embedding utilities supporting local model inference and hash fallback."""
from __future__ import annotations
import os
import hashlib
from pathlib import Path
from typing import List

try:  # pragma: no cover - optional runtime dependency
    import torch
except Exception:  # pragma: no cover
    torch = None


MODEL_SPECS = {
    "e5-large": {"hf_id": "intfloat/e5-large-v2", "dimension": 1024},
    "bge-large-zh": {"hf_id": "BAAI/bge-large-zh-v1.5", "dimension": 1024},
}

_MODEL_CACHE: dict[str, object] = {}
_MODULE_DIR = Path(__file__).resolve().parent
_SENTENCE_TRANSFORMER_CLS = None


def _embedding_backend() -> str:
    return (os.getenv("RAG_EMBEDDING_BACKEND", "local") or "local").strip().lower()


def _default_dimension() -> int:
    try:
        return int(os.getenv("RAG_EMBEDDING_DIM", "1024"))
    except ValueError:
        return 1024


def _expected_dimension(model: str) -> int:
    spec = MODEL_SPECS.get(model, {})
    return int(spec.get("dimension", _default_dimension()))


def _hash_vector(seed_text: str, dimension: int) -> List[float]:
    values: List[float] = []
    counter = 0
    while len(values) < dimension:
        seed = hashlib.sha256(f"{seed_text}::{counter}".encode("utf-8")).digest()
        for i in range(0, len(seed), 4):
            if len(values) >= dimension:
                break
            values.append((int.from_bytes(seed[i : i + 4], "big") % 1000) / 1000.0)
        counter += 1
    return values


def _embed_hash(text: str, model: str) -> List[float]:
    return _hash_vector(f"{model}::{text}", _expected_dimension(model))


def _truthy(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _fallback_to_local_on_hf_error() -> bool:
    return _truthy(os.getenv("RAG_EMBEDDING_LOCAL_FALLBACK"), default=True)


def _model_local_override(model: str) -> str | None:
    model_key = model.upper().replace("-", "_")
    return (
        os.getenv(f"RAG_EMBEDDING_MODEL_PATH_{model_key}")
        or os.getenv(f"RAG_EMBEDDING_MODEL_DIR_{model_key}")
        or os.getenv("RAG_EMBEDDING_MODEL_PATH")
        or os.getenv("RAG_EMBEDDING_MODEL_DIR")
    )


def _default_model_dir(model: str) -> Path:
    return _MODULE_DIR / "models" / model


def _resolve_local_model_source(model: str) -> str | None:
    override = _model_local_override(model)
    if override:
        path = Path(override)
        if path.exists():
            return str(path)
    default_path = _default_model_dir(model)
    if default_path.exists():
        return str(default_path)
    return None


def _hf_auth_token() -> str | None:
    return os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_HUB_TOKEN")


def _configure_hf_runtime_env() -> None:
    endpoint = os.getenv("RAG_HF_ENDPOINT")
    if endpoint:
        os.environ.setdefault("HF_ENDPOINT", endpoint)
    home = os.getenv("RAG_HF_HOME")
    if home:
        os.environ.setdefault("HF_HOME", home)
    hub_cache = os.getenv("RAG_HF_HUB_CACHE")
    if hub_cache:
        os.environ.setdefault("HUGGINGFACE_HUB_CACHE", hub_cache)
    proxy = os.getenv("RAG_HF_PROXY")
    if proxy:
        os.environ.setdefault("HTTPS_PROXY", proxy)
        os.environ.setdefault("HTTP_PROXY", proxy)
    token = _hf_auth_token()
    if token:
        os.environ.setdefault("HUGGINGFACE_HUB_TOKEN", token)
        os.environ.setdefault("HF_TOKEN", token)


def _local_thread_limit() -> int:
    raw = (os.getenv("RAG_EMBEDDING_THREADS", "1") or "1").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 1


def _configure_local_runtime_threads() -> int:
    threads = _local_thread_limit()
    value = str(threads)
    os.environ["OMP_NUM_THREADS"] = value
    os.environ["MKL_NUM_THREADS"] = value
    os.environ["NUMEXPR_NUM_THREADS"] = value
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    torch_module = globals().get("torch")
    if torch_module is not None:
        try:
            torch_module.set_num_threads(threads)
        except Exception:
            pass
        try:
            torch_module.set_num_interop_threads(threads)
        except Exception:
            pass
    return threads


def _sentence_transformer_cls():  # pragma: no cover - runtime-heavy path
    global _SENTENCE_TRANSFORMER_CLS
    if _SENTENCE_TRANSFORMER_CLS is not None:
        return _SENTENCE_TRANSFORMER_CLS
    try:
        from sentence_transformers import SentenceTransformer as _SentenceTransformer
    except Exception:
        _SENTENCE_TRANSFORMER_CLS = None
        return None
    _SENTENCE_TRANSFORMER_CLS = _SentenceTransformer
    return _SENTENCE_TRANSFORMER_CLS


def _load_st_model(source: str, hf_id_for_cache: str):  # pragma: no cover - runtime-heavy path
    device = (os.getenv("RAG_EMBEDDING_DEVICE", "cpu") or "cpu").strip().lower()
    cache_key = f"{source}::{device}"
    cached = _MODEL_CACHE.get(cache_key)
    if cached is not None:
        return cached
    sentence_transformer_cls = _sentence_transformer_cls()
    if sentence_transformer_cls is None:
        raise RuntimeError(
            "sentence-transformers is not installed. Install with: python -m pip install -e .[local-embeddings]"
        )
    kwargs = {}
    token = _hf_auth_token()
    if token:
        kwargs["token"] = token
    cache_folder = os.getenv("RAG_HF_HUB_CACHE")
    if cache_folder:
        kwargs["cache_folder"] = cache_folder
    local_files_only = _truthy(os.getenv("RAG_EMBEDDING_LOCAL_ONLY"), default=False)
    if local_files_only:
        kwargs["local_files_only"] = True
    model_obj = sentence_transformer_cls(source, device=device, **kwargs)
    _MODEL_CACHE[cache_key] = model_obj
    # Keep backward key compatibility for repeated lookups by HF id.
    _MODEL_CACHE.setdefault(f"{hf_id_for_cache}::{device}", model_obj)
    return model_obj


def _load_model_with_fallback(hf_id: str, model: str):  # pragma: no cover - runtime-heavy path
    # 1) Explicit/local pre-downloaded directory first.
    local_source = _resolve_local_model_source(model)
    if local_source:
        return _load_st_model(local_source, hf_id)
    # 2) Hugging Face online/offline cache resolution.
    try:
        return _load_st_model(hf_id, hf_id)
    except Exception as exc:
        if not _fallback_to_local_on_hf_error():
            raise RuntimeError(f"Failed to load model from Hugging Face: {hf_id}") from exc
        # 3) Last chance: re-check default pre-downloaded location.
        fallback = _default_model_dir(model)
        if fallback.exists():
            return _load_st_model(str(fallback), hf_id)
        raise RuntimeError(
            f"Failed to load model '{model}' ({hf_id}) from Hugging Face and no local model directory was found. "
            f"Set RAG_EMBEDDING_MODEL_PATH_{model.upper().replace('-', '_')} "
            f"or place files under {fallback}."
        ) from exc


def clear_model_cache() -> None:
    _MODEL_CACHE.clear()


def _load_local_model(model: str):  # pragma: no cover - runtime-heavy path
    _configure_local_runtime_threads()
    _configure_hf_runtime_env()
    spec = MODEL_SPECS.get(model, {})
    hf_id = spec.get("hf_id", model)
    return _load_model_with_fallback(hf_id, model)


def _embed_local(text: str, model: str) -> List[float]:  # pragma: no cover - runtime-heavy path
    local_model = _load_local_model(model)
    normalize = (os.getenv("RAG_EMBEDDING_NORMALIZE", "true") or "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    vector = local_model.encode([text], normalize_embeddings=normalize, convert_to_numpy=True)[0].tolist()
    expected = _expected_dimension(model)
    if len(vector) != expected:
        raise RuntimeError(f"Embedding dimension mismatch for {model}: expected {expected}, got {len(vector)}")
    return [float(v) for v in vector]


def embed_text(text: str, model: str) -> List[float]:
    backend = _embedding_backend()
    if backend in ("hash", "deterministic"):
        return _embed_hash(text, model)
    if backend == "local":
        return _embed_local(text, model)
    if backend == "auto":
        try:
            return _embed_local(text, model)
        except Exception:
            return _embed_hash(text, model)
    raise RuntimeError(f"Unsupported embedding backend: {backend}")
