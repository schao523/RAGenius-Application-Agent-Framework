"""Node B: Config PDF extraction.

Flow:
1) Deterministic parser first (pdfplumber with pypdf fallback)
2) If strong section markers are missing, fallback to LLM extraction prompt
3) Validate output against config_json.schema.json
4) Persist extracted_text + config_json in config_instructions

No downstream business logic is implemented here beyond extraction/validation/persist.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Protocol

from backend.schemas import validate_config_json

from ..graph_state import GraphState

PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "config_pdf_extraction_prompt.txt"

SECTION_MARKERS = [
    "goals",
    "mode",
    "coverage",
    "retrieval",
    "style",
    "safety",
    "step skeleton",
    "modules",
    "controls",
]


class ConfigPersistenceRepo(Protocol):
    """Protocol for config persistence repositories."""

    def save(
        self,
        collection_id: str,
        config_json: Dict[str, Any],
        extracted_text: str,
        *,
        source_pdf_name: str | None = None,
    ) -> Dict[str, Any]:
        ...


def _extract_with_pdfplumber(pdf_path: Path) -> str:
    import pdfplumber  # type: ignore

    parts: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    return "\n".join(parts).strip()


def _extract_with_pypdf(pdf_path: Path) -> str:
    from pypdf import PdfReader  # type: ignore

    reader = PdfReader(str(pdf_path))
    return "\n".join((page.extract_text() or "") for page in reader.pages).strip()


def parser_available() -> bool:
    try:
        import pdfplumber  # noqa: F401

        return True
    except Exception:
        try:
            import pypdf  # noqa: F401

            return True
        except Exception:
            return False


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract text with deterministic parser-first strategy."""
    if not pdf_path.exists():
        raise FileNotFoundError(f"Config PDF not found: {pdf_path}")

    last_error: Exception | None = None
    for parser in (_extract_with_pdfplumber, _extract_with_pypdf):
        try:
            text = parser(pdf_path)
            if text:
                return text
        except Exception as exc:  # pragma: no cover - parser fallback path
            last_error = exc
            continue

    if last_error:
        raise RuntimeError("Failed to extract PDF text with deterministic parsers.") from last_error
    raise RuntimeError("No text extracted from PDF.")


def has_strong_sections(text: str) -> bool:
    """Detect whether text has enough section markers for deterministic shaping."""
    lowered = text.lower()
    matches = sum(1 for marker in SECTION_MARKERS if marker in lowered)
    return matches >= 3


def _extract_bullets(text: str, heading: str) -> list[str]:
    pattern = re.compile(
        rf"{heading}\s*:?(.*?)(?:\n[A-Z][A-Za-z ]{{2,30}}\s*:|\Z)",
        flags=re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        return []

    block = match.group(1)
    lines = [ln.strip(" -\t") for ln in block.splitlines()]
    return [ln for ln in lines if ln]


def deterministic_config_from_text(text: str) -> Dict[str, Any]:
    """Build schema-compliant config_json deterministically from extracted text."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    title = lines[0][:120] if lines else "Config PDF"

    goals = _extract_bullets(text, "goals")
    coverage_rules = _extract_bullets(text, "coverage")
    retrieval_rules = _extract_bullets(text, "retrieval")
    style_rules = _extract_bullets(text, "style")
    safety_rules = _extract_bullets(text, "safety")

    return {
        "meta": {"title": title, "domain_hint": None, "version_hint": None, "author": None},
        "role": {"name": "assistant", "mission": []},
        "goals": goals,
        "mode_detection": [],
        "coverage_rules": coverage_rules,
        "retrieval_rules": retrieval_rules,
        "style_rules": style_rules,
        "safety_rules": safety_rules,
        "step_skeletons": [],
        "modules": [],
        "controls_commands": [],
    }


def load_prompt() -> str:
    if not PROMPT_PATH.exists():
        raise FileNotFoundError(f"Prompt file not found: {PROMPT_PATH}")
    return PROMPT_PATH.read_text(encoding="utf-8", errors="ignore")


def call_llm_extractor(
    pdf_text: str,
    llm_callable: Optional[Callable[[str, str], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Fallback extractor callable signature: llm_callable(pdf_text, prompt_text) -> config_json."""
    if llm_callable is None:
        raise RuntimeError("LLM extractor is required when deterministic parsing is insufficient.")
    prompt = load_prompt()
    return llm_callable(pdf_text, prompt)


def persist_config_instruction(
    state: GraphState,
    extracted_text: str,
    config_json: Dict[str, Any],
    *,
    persist_fn: Optional[Callable[[GraphState, str, Dict[str, Any]], None]] = None,
    repo: Optional[ConfigPersistenceRepo] = None,
    source_pdf_name: str | None = None,
) -> None:
    """Persist extracted artifacts in config_instructions."""
    if persist_fn:
        persist_fn(state, extracted_text, config_json)
        return

    if repo is None:
        return

    collection_id = state.get("collection_id")
    if not collection_id:
        raise ValueError("collection_id is required to persist config_instructions.")

    repo.save(
        collection_id=collection_id,
        config_json=config_json,
        extracted_text=extracted_text,
        source_pdf_name=source_pdf_name,
    )


def run(
    state: GraphState,
    llm_extractor: Optional[Callable[[str, str], Dict[str, Any]]] = None,
    persist_fn: Optional[Callable[[GraphState, str, Dict[str, Any]], None]] = None,
    repo: Optional[ConfigPersistenceRepo] = None,
) -> GraphState:
    """Execute Node B extraction workflow.

    Input:
    - state["config_pdf_path"] required
    - state["collection_id"] required when repo persistence is used

    Output:
    - state["config_extracted_text"]
    - state["config_json"] (validated)
    """
    if llm_extractor is None:
        llm_extractor = state.get("_llm_config_extractor")

    if state.get("config_json"):
        # Config already loaded upstream (e.g., frozen session artifacts).
        state.setdefault("config_extracted_text", "")
        return state

    pdf_path_str = state.get("config_pdf_path")
    if not pdf_path_str:
        raise ValueError("config_pdf_path is required when config_json is not present.")

    pdf_path = Path(pdf_path_str)
    extracted_text = extract_text_from_pdf(pdf_path)
    state["config_extracted_text"] = extracted_text

    if has_strong_sections(extracted_text):
        config_json = deterministic_config_from_text(extracted_text)
    else:
        # In local/dev environments without LLM wiring, keep deterministic fallback
        # so config upload remains functional.
        if llm_extractor is None:
            config_json = deterministic_config_from_text(extracted_text)
        else:
            config_json = call_llm_extractor(extracted_text, llm_callable=llm_extractor)

    validate_config_json(config_json)
    state["config_json"] = config_json

    persist_config_instruction(
        state,
        extracted_text,
        config_json,
        persist_fn=persist_fn,
        repo=repo,
        source_pdf_name=pdf_path.name,
    )
    return state
