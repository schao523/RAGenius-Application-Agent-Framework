"""PDF text extraction utilities for ingestion pipelines."""
from __future__ import annotations

from pathlib import Path
import re

try:  # pragma: no cover - optional runtime dependency
    import pdfplumber
except Exception:  # pragma: no cover
    pdfplumber = None

try:  # pragma: no cover - optional runtime dependency
    from pypdf import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None


def _extract_with_pdfplumber(path: str, max_pages: int | None = None) -> tuple[str, int]:
    if pdfplumber is None:
        raise RuntimeError("pdfplumber is not installed")
    texts: list[str] = []
    page_count = 0
    with pdfplumber.open(path) as pdf:
        total = len(pdf.pages)
        limit = total if max_pages is None else min(total, max_pages)
        for i in range(limit):
            page_count += 1
            txt = (pdf.pages[i].extract_text() or "").strip()
            if txt:
                texts.append(txt)
    return "\n\n".join(texts), page_count


def _extract_with_pypdf(path: str, max_pages: int | None = None) -> tuple[str, int]:
    if PdfReader is None:
        raise RuntimeError("pypdf is not installed")
    reader = PdfReader(path)
    total = len(reader.pages)
    limit = total if max_pages is None else min(total, max_pages)
    texts: list[str] = []
    for i in range(limit):
        txt = (reader.pages[i].extract_text() or "").strip()
        if txt:
            texts.append(txt)
    return "\n\n".join(texts), limit


_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def _quality_score(text: str) -> float:
    stripped = text or ""
    if not stripped:
        return 0.0
    total = len(stripped)
    cjk_count = len(_CJK_RE.findall(stripped))
    # For CJK documents, good extraction keeps real CJK chars.
    # Combine cjk presence and overall extracted volume.
    return (cjk_count * 5.0) + (total * 0.01)


def extract_pdf_text(
    path: str,
    max_pages: int | None = None,
    engine: str = "auto",
    fallback: bool = True,
) -> tuple[str, str, int]:
    """Extract text from PDF.

    Returns:
        (text, engine_used, pages_processed)
    """
    pdf_path = Path(path)
    if not pdf_path.exists():
        raise FileNotFoundError(path)

    preferred = (engine or "auto").strip().lower()
    if preferred not in ("auto", "pdfplumber", "pypdf"):
        raise ValueError(f"Unsupported PDF engine: {preferred}")

    if preferred == "auto":
        candidates: list[tuple[str, tuple[str, int]]] = []
        errors: list[str] = []
        for selected in ("pdfplumber", "pypdf"):
            try:
                extracted = (
                    _extract_with_pdfplumber(str(pdf_path), max_pages=max_pages)
                    if selected == "pdfplumber"
                    else _extract_with_pypdf(str(pdf_path), max_pages=max_pages)
                )
                candidates.append((selected, extracted))
            except Exception as exc:
                errors.append(f"{selected}: {exc}")
        if not candidates:
            raise RuntimeError("Failed to extract PDF text in auto mode. " + " | ".join(errors))
        best_engine, best_result = max(candidates, key=lambda item: _quality_score(item[1][0]))
        return best_result[0], best_engine, best_result[1]

    tried: list[str] = []
    for selected in ([preferred, "pypdf" if preferred == "pdfplumber" else "pdfplumber"] if fallback else [preferred]):
        tried.append(selected)
        try:
            if selected == "pdfplumber":
                text, pages = _extract_with_pdfplumber(str(pdf_path), max_pages=max_pages)
            else:
                text, pages = _extract_with_pypdf(str(pdf_path), max_pages=max_pages)
            return text, selected, pages
        except Exception:
            continue

    raise RuntimeError(f"Failed to extract PDF text with engines: {', '.join(tried)}")
