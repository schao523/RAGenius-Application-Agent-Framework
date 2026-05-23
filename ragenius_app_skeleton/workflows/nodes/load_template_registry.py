"""Node D: load template registry assets.

Requirements covered:
- Resolve effective domain folder, fallback to general/
- Load required domain JSON files
- Load prompt templates from repository prompts/ directory
- Return template_registry in state
- Respect frozen session template_version
"""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from ..graph_state import GraphState
from ..runtime_models import (
    ArtifactContract,
    DependencyGroup,
    GlobalInstructionContext,
    InstructionHeadingNode,
    InstructionProcedure,
    InstructionResourceBinding,
    InstructionRuntimeModel,
    InstructionServiceBlock,
    ModeRule,
    PhaseResourceBinding,
    ProgressionRules,
    ProcedureStepDefinition,
    SessionExecutionState,
    SupportModuleRule,
    TriggerCondition,
    TurnConstraints,
    to_plain_dict,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DOMAINS_BASE_DIR = REPO_ROOT / "config" / "domains"
PROMPTS_DIR = REPO_ROOT / "prompts"
FALLBACK_DOMAIN = "general"

DOMAIN_JSON_FILES = [
    "intent_templates.json",
    "step_skeletons.json",
    "info_type_rules.json",
    "retrieval_mapping_rules.json",
]

RESOURCE_PATTERN = re.compile(
    r"([A-Za-z0-9_\-\[\]\u4e00-\u9fff][A-Za-z0-9_\-\[\]\u4e00-\u9fff ]*\.(?:md|pdf|txt|docx|zip))"
)
COMMAND_PATTERN = re.compile(r"(?<!\w)(/[a-z0-9][a-z0-9_\-]*)", re.IGNORECASE)
NUMBERED_ITEM_PATTERN = re.compile(r"^(\d+)\.\s*(.+)$")
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
HEADING_STYLE_STEP_PATTERN = re.compile(r"^step\s*(\d+)\s*[:：ï¼š\-–â€“]\s*(.+)$", re.IGNORECASE)
PAREN_SUFFIX_PATTERN = re.compile(r"^(.+?)[（(ï¼ˆ]([^）)ï¼‰]+)[）)ï¼‰]$")
MD_VERB_RULES: tuple[tuple[str, str], ...] = (
    ("ä½¿ç”¨", "use"),
    ("å•Ÿå‹•", "activate"),
    ("å¯åŠ¨", "activate"),
    ("éµå®ˆ", "obey"),
    ("ä¾†æº", "source"),
    ("æ¥æº", "source"),
    ("ä¾æ“š", "bind"),
    ("ä¾ç…§", "bind"),
    ("must use", "use"),
    ("use ", "use"),
    ("start ", "activate"),
    ("obey ", "obey"),
    ("source", "source"),
    ("bind", "bind"),
)
MODULE_HEADING_TOKENS = ("æ¨¡çµ„", "module", "modules")
RESOURCE_BINDING_TOKENS = ("resource binding", "knowledge binding", "è³‡æºæ•´åˆ", "çŸ¥è­˜ç¶å®š", "çŸ¥è¯†ç»‘å®š")
RULE_SECTION_TOKENS = ("rules", "è¦å‰‡", "è§„åˆ™")
OUTPUT_TEMPLATE_TOKENS = (
    "template",
    "spec",
    "format guide",
    "standard",
    "package guide",
    "\u8f38\u51fa\u683c\u5f0f",
    "\u683c\u5f0f\u898f\u7bc4",
    "\u683c\u5f0f\u89c4\u8303",
)
OUTPUT_ARTIFACT_TOKENS = (
    "\u751f\u6210",
    "\u8f38\u51fa",
    "\u8f93\u51fa",
    "\u7522\u51fa",
    "\u4ea7\u51fa",
    "generate",
    "generated",
    "produce",
    "produced",
    "download",
    "\u4fdd\u5b58",
    "save",
    "output option",
    "\u8f38\u51fa\u9078\u9805",
)
OUTPUT_ARTIFACT_NAME_HINTS = (
    "[title]",
    "dialogue_",
    "dialogue[",
    "ai_videoprompt_",
)
LOW_CONFIDENCE_FILENAME_TOKENS = {"guide.md", "reference.md", "template.md", "standard.md", "spec.md", "bundle.md"}
STARTER_HEADING_TOKENS = ("starter", "start here", "kickoff", "getting started")
PHASE_HEADING_TOKENS = ("phase", "stage", "step")
OUTPUT_HEADING_TOKENS = ("output", "export", "deliverable", "è¼¸å‡º", "è¾“å‡º", "åŒ¯å‡º", "å¯¼å‡º", "輸出", "匯出", "导出")
ARTIFACT_GATE_REQUIRED_TOKENS = ("upload", "ä¸Šå‚³", "ä¸Šä¼ ", "è¼‰å…¥", "è½½å…¥", "上傳", "上传")
ARTIFACT_GATE_MISSING_TOKENS = ("missing", "ç¼ºå°‘", "ç¼ºå¤±", "æœªä¸Šå‚³", "æœªä¸Šä¼ ", "æ‰¾ä¸åˆ°", "æœªæä¾›", "缺少", "缺失")
ARTIFACT_GATE_PROGRESS_TOKENS = ("before executing", "before continuing", "å…ˆ", "ä¹‹å‰", "å†åŸ·è¡Œ", "å†æ‰§è¡Œ", "ä¸‹ä¸€æ­¥", "ç¹¼çºŒ", "ç»§ç»­", "下一步", "繼續")
ALTERNATIVE_TOKENS = (" or ", "either", "one of", "ä»»ä¸€", "å…¶ä¸­ä¸€å€‹", "å…¶ä¸­ä¸€ä¸ª", "æˆ–", "æˆ–è€…", "æ“‡ä¸€", "æ‹©ä¸€")
PROCEDURE_HEADING_TOKENS = (
    "interaction logic",
    "execution flow",
    "interaction flow",
    "workflow",
    "procedure",
    "playbook",
    "runbook",
    "process flow",
    "åŸ·è¡Œæµç¨‹",
    "æ‰§è¡Œæµç¨‹",
    "äº’å‹•æµç¨‹",
    "äº’åŠ¨æµç¨‹",
    "äº’å‹•é‚è¼¯",
    "äº’åŠ¨é€»è¾‘",
    "æµç¨‹",
)

FOLLOWUP_HEADING_TOKENS = (
    "optimization",
    "optimizer",
    "follow-up",
    "followup",
    "refine",
    "revise",
    "rewrite",
    "improve",
    "\u512a\u5316",
    "\u4f18\u5316",
    "\u7cbe\u7149",
    "\u7cbe\u70bc",
    "\u4fee\u8a02",
    "\u4fee\u8ba2",
    "\u6539\u5beb",
    "\u6539\u5199",
    "\u91cd\u5beb",
    "\u91cd\u5199",
)
RESOURCE_CATALOG_HEADING_TOKENS = (
    "resource binding",
    "resource index",
    "resource catalog",
    "knowledge binding",
    "\u8cc7\u6e90\u6574\u5408",
    "\u8cc7\u6e90\u76ee\u9304",
    "\u8d44\u6e90\u6574\u5408",
    "\u8d44\u6e90\u76ee\u5f55",
    "\u77e5\u8b58\u7d81\u5b9a",
    "\u77e5\u8bc6\u7ed1\u5b9a",
)
GLOBAL_POLICY_HEADING_TOKENS = (
    "role",
    "mission",
    "objective",
    "goal",
    "style",
    "policy",
    "guardrail",
    "\u89d2\u8272",
    "\u4f7f\u547d",
    "\u76ee\u6a19",
    "\u76ee\u6807",
    "\u98a8\u683c",
    "\u98ce\u683c",
    "\u653f\u7b56",
    "\u898f\u5247",
    "\u89c4\u5219",
)

def _resolve_domain_dir(domain: str | None, base_dir: Path = DOMAINS_BASE_DIR) -> tuple[Path, str]:
    target_domain = domain or FALLBACK_DOMAIN
    target_dir = base_dir / target_domain
    if target_dir.exists() and target_dir.is_dir():
        return target_dir, target_domain
    return base_dir / FALLBACK_DOMAIN, FALLBACK_DOMAIN


def _load_json_or_empty(path: Path) -> Any:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_prompt_templates(prompts_dir: Path = PROMPTS_DIR) -> Dict[str, str]:
    if not prompts_dir.exists():
        return {}

    templates: Dict[str, str] = {}
    for file in sorted(prompts_dir.iterdir()):
        if file.is_file() and file.suffix.lower() in {".txt", ".md"}:
            templates[file.name] = file.read_text(encoding="utf-8", errors="ignore")
    return templates


def _slugify_module_title(title: str) -> str:
    lowered = str(title or "").strip().lower()
    lowered = re.sub(r"[()ï¼ˆï¼‰]", " ", lowered)
    lowered = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "_", lowered)
    lowered = re.sub(r"_+", "_", lowered).strip("_")
    return lowered or "module"


def _normalize_keyword(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _contains_any(text: str, tokens: Iterable[str]) -> bool:
    lowered = str(text or "").lower()
    return any(str(token or "").lower() in lowered for token in tokens)


FILENAME_PREFIX_STOPWORDS = {
    "use",
    "load",
    "obey",
    "start",
    "export",
    "import",
    "run",
    "resource",
    "with",
    "and",
    "or",
    "the",
    "a",
    "an",
    "please",
    "prompt",
    "user",
    "to",
    "if",
    "before",
    "after",
    "using",
    "upload",
    "download",
    "\u4f7f\u7528",
    "\u5957\u7528",
    "\u8f09\u5165",
    "\u8f7d\u5165",
    "\u555f\u52d5",
    "\u542f\u52a8",
    "\u9075\u5b88",
    "\u532f\u51fa",
    "\u5bfc\u51fa",
    "\u4e0a\u50b3",
    "\u4e0a\u4f20",
    "\u4ee5\u53ca",
    "\u4e26",
    "\u6216",
    "\u6216\u8005",
    "\u8acb",
    "\u8bf7",
    "\u82e5",
    "\u5982\u679c",
    "\u53ef",
    "\u53ef\u532f\u51fa",
    "\u53ef\u5bfc\u51fa",
    "\u751f\u6210",
    "\u8f38\u51fa",
    "\u8f93\u51fa",
    "\u7522\u51fa",
    "\u4ea7\u51fa",
    "\u4fdd\u5b58",
    "??????",
    "??????",
    "??????",
    "??????",
    "??????",
    "??????",
    "??????",
    "??????",
    "??????",
    "??????",
    "??????",
    "???",
    "???",
    "??????",
    "???",
    "???",
    "???",
    "??????",
    "???",
    "?????????",
    "?????????",
    "???????????????????????????",
    "????????????????????????",
    "????????????????????????",
}


def _filename_token_score(token: str, *, is_final: bool) -> int:
    cleaned = str(token or "").strip()
    lowered = cleaned.lower()
    if not cleaned:
        return -100
    if lowered in FILENAME_PREFIX_STOPWORDS:
        return -25

    score = 0
    if any(char in cleaned for char in "_-[]"):
        score += 5
    if re.fullmatch(r"[A-Z][A-Za-z0-9]*", cleaned):
        score += 4
    elif re.fullmatch(r"[a-z0-9]+", cleaned):
        score += 1
    elif re.search(r"[\u4e00-\u9fff]", cleaned):
        if len(cleaned) >= 4 and not is_final:
            score -= 5
        else:
            score += 1
    if re.search(r"[,:?????????;]", cleaned):
        score -= 6
    if is_final and re.search(r"\.(?:md|pdf|txt|docx|zip)$", lowered):
        score += 8
    return score


def _normalize_extracted_filename(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"^[\s\-\*\u2022#>]+", "", text).strip()
    text = re.sub(r"^\d+\.\s*", "", text).strip()
    parts = [part for part in text.split() if part]
    while parts and parts[0].lower() in FILENAME_PREFIX_STOPWORDS:
        parts.pop(0)
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]

    best_candidate = " ".join(parts)
    best_score = None
    for index in range(len(parts)):
        candidate_parts = parts[index:]
        if not candidate_parts:
            continue
        candidate = " ".join(candidate_parts).strip()
        score = sum(
            _filename_token_score(token, is_final=(position == len(candidate_parts) - 1))
            for position, token in enumerate(candidate_parts)
        )
        rank = (score, -index)
        if best_score is None or rank > best_score:
            best_score = rank
            best_candidate = candidate
    return best_candidate


def _extract_resource_filenames(text: str) -> list[str]:
    filenames: list[str] = []
    seen: set[str] = set()
    for match in RESOURCE_PATTERN.findall(str(text or "")):
        normalized = _normalize_extracted_filename(match)
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        filenames.append(Path(normalized).name)
    return filenames


def _normalize_filename_key(filename: str) -> str:
    return Path(str(filename or "").strip()).name.lower()


def _normalize_stem_key(filename: str) -> str:
    stem = Path(str(filename or "").strip()).stem.lower()
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", stem)


def _normalize_text_key(text: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(text or "").lower())


def _normalize_section_name(text: str) -> str:
    normalized = str(text or "").strip().lower()
    normalized = normalized.rstrip("ã€‚ï¼Ž.;:ï¼š。．：")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def _repair_mojibake_text(text: str) -> str:
    value = str(text or "")
    try:
        repaired = value.encode("latin1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value
    if any("\u4e00" <= char <= "\u9fff" for char in repaired) or any(marker in repaired for marker in ("「", "」", "（", "）", "：")):
        return repaired
    return value


def _strip_parenthetical_suffix(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    for pattern in (
        r"^(.+?)[（(][^）)]+[）)]$",
        r"^(.+?)ã€Œ[^ã]+ã€$",
        r"^(.+?)ï¼ˆ[^ï]+ï¼‰$",
    ):
        match = re.match(pattern, value)
        if match:
            return match.group(1).strip()
    return value


def _title_declared_structure_type(title: str) -> str | None:
    value = _repair_mojibake_text(str(title or "")).strip()
    lowered = value.lower()
    has_module = "模組" in value or "module" in lowered
    has_workflow = "流程" in value or "workflow" in lowered
    if has_module and has_workflow:
        return "ambiguous"
    if has_module:
        return "module"
    if has_workflow:
        return "workflow"
    return None


def _extract_parser_contract_warnings(markdown: str) -> list[str]:
    warnings: list[str] = []
    seen: set[str] = set()
    for heading, _body in _iter_heading_sections(markdown):
        title = str(heading or "").strip()
        if not title or _title_declared_structure_type(title) != "ambiguous":
            continue
        warning = f"ambiguous section title contains both module and workflow markers: {title}"
        if warning in seen:
            continue
        seen.add(warning)
        warnings.append(warning)
    return warnings


def _build_builder_document_registry(builder_documents: Any) -> dict[str, Any]:
    documents = [item for item in (builder_documents or []) if isinstance(item, dict)]
    by_filename: dict[str, dict[str, Any]] = {}
    by_stem: dict[str, list[dict[str, Any]]] = {}
    for document in documents:
        filename = str(document.get("filename") or "").strip()
        if not filename:
            continue
        by_filename[_normalize_filename_key(filename)] = document
        by_stem.setdefault(_normalize_stem_key(filename), []).append(document)
    return {
        "documents": documents,
        "by_filename": by_filename,
        "by_stem": by_stem,
    }


def _resolve_builder_document(filename: str, document_registry: dict[str, Any] | None) -> dict[str, Any] | None:
    if not document_registry:
        return None

    filename_key = _normalize_filename_key(filename)
    if not filename_key:
        return None

    exact = document_registry.get("by_filename", {}).get(filename_key)
    if isinstance(exact, dict):
        return exact

    stem_key = _normalize_stem_key(filename)
    stem_matches = [item for item in document_registry.get("by_stem", {}).get(stem_key, []) if isinstance(item, dict)]
    if len(stem_matches) == 1:
        return stem_matches[0]

    target_ext = Path(filename_key).suffix.lower()
    target_key = stem_key or filename_key
    best_doc = None
    best_score = 0.0
    for document in document_registry.get("documents", []):
        if not isinstance(document, dict):
            continue
        candidate_filename = str(document.get("filename") or "").strip()
        if not candidate_filename:
            continue
        candidate_key = _normalize_filename_key(candidate_filename)
        if Path(candidate_key).suffix.lower() != target_ext:
            continue
        candidate_stem = _normalize_stem_key(candidate_filename)
        score = SequenceMatcher(None, target_key, candidate_stem or candidate_key).ratio()
        if score > best_score:
            best_score = score
            best_doc = document
    if best_score >= 0.84:
        return best_doc
    return None


def _resolved_filename(filename: str, document_registry: dict[str, Any] | None) -> str:
    matched = _resolve_builder_document(filename, document_registry)
    if isinstance(matched, dict):
        return str(matched.get("filename") or filename).strip() or filename
    return filename


def _match_builder_documents_in_text(text: str, document_registry: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not document_registry:
        return []
    text_key = _normalize_text_key(text)
    if not text_key:
        return []
    matches: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for document in document_registry.get("documents", []):
        if not isinstance(document, dict):
            continue
        filename = str(document.get("filename") or "").strip()
        if not filename:
            continue
        stem_key = _normalize_stem_key(filename)
        filename_key = _normalize_text_key(filename)
        if (
            (len(stem_key) >= 6 and stem_key in text_key)
            or (len(filename_key) >= 8 and filename_key in text_key)
        ):
            doc_id = str(document.get("id") or filename)
            if doc_id not in seen_ids:
                seen_ids.add(doc_id)
                matches.append(document)
    return matches


def _split_lines(markdown: str) -> list[str]:
    return [str(raw or "") for raw in str(markdown or "").splitlines()]


def _strip_heading_markers(line: str) -> str:
    match = HEADING_PATTERN.match(str(line or "").strip())
    if not match:
        return str(line or "").strip()
    return match.group(2).strip()


def _tokenize_heading_lines(markdown: str) -> list[dict[str, Any]]:
    tokens: list[dict[str, Any]] = []
    for line_index, raw_line in enumerate(_split_lines(markdown)):
        line = _repair_mojibake_text(str(raw_line or "").strip())
        match = HEADING_PATTERN.match(line)
        if not match:
            continue
        title = match.group(2).strip()
        tokens.append(
            {
                "line_index": line_index,
                "level": len(match.group(1)),
                "title": title,
                "normalized_title": _slugify_module_title(title),
            }
        )
    return tokens


def _infer_top_level_heading_depth(heading_tokens: list[dict[str, Any]]) -> int | None:
    levels = {int(token.get("level") or 0) for token in heading_tokens if int(token.get("level") or 0) > 0}
    if not levels:
        return None
    if 1 in levels:
        return 1
    if 2 in levels:
        return 2
    return min(levels)


def _build_instruction_heading_tree(markdown: str) -> list[dict[str, Any]]:
    lines = _split_lines(markdown)
    heading_tokens = _tokenize_heading_lines(markdown)
    top_level_depth = _infer_top_level_heading_depth(heading_tokens)
    if top_level_depth is None:
        return []

    root_nodes: list[dict[str, Any]] = []
    stack: list[dict[str, Any]] = []
    for token in heading_tokens:
        level = int(token.get("level") or 0)
        if level < top_level_depth:
            continue
        node = {
            "node_id": f"heading:{str(token.get('normalized_title') or 'section')}:{int(token.get('line_index') or 0)}",
            "level": level,
            "title": str(token.get("title") or "").strip(),
            "normalized_title": str(token.get("normalized_title") or "").strip(),
            "body_lines": [],
            "children": [],
            "source_span": {
                "heading_line_index": int(token.get("line_index") or 0),
            },
        }
        while stack and int(stack[-1].get("level") or 0) >= level:
            stack.pop()
        if stack:
            stack[-1]["children"].append(node)
        else:
            root_nodes.append(node)
        stack.append(node)

    if not root_nodes:
        return []

    line_to_node: dict[int, dict[str, Any]] = {}
    for token, node in zip(
        [token for token in heading_tokens if int(token.get("level") or 0) >= top_level_depth],
        [node for node in _flatten_heading_node_dicts(root_nodes)],
    ):
        raw_line_index = token.get("line_index")
        line_index = int(raw_line_index) if raw_line_index is not None else -1
        line_to_node[line_index] = node
    current_stack: list[dict[str, Any]] = []
    valid_heading_lines = set(line_to_node.keys())
    for line_index, raw_line in enumerate(lines):
        if line_index in valid_heading_lines:
            node = line_to_node[line_index]
            level = int(node.get("level") or 0)
            while current_stack and int(current_stack[-1].get("level") or 0) >= level:
                current_stack.pop()
            current_stack.append(node)
            continue
        if current_stack:
            current_stack[-1].setdefault("body_lines", []).append(str(raw_line or ""))

    def _finalize(node: dict[str, Any]) -> dict[str, Any]:
        body_lines = node.pop("body_lines", [])
        node["body_text"] = "\n".join(body_lines).strip()
        node["children"] = [_finalize(child) for child in node.get("children", []) if isinstance(child, dict)]
        return to_plain_dict(InstructionHeadingNode(**node))

    return [_finalize(node) for node in root_nodes]


def _flatten_heading_node_dicts(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        flattened.append(node)
        flattened.extend(_flatten_heading_node_dicts(node.get("children", [])))
    return flattened


def _is_low_confidence_filename(filename: str) -> bool:
    lowered = str(filename or "").strip().lower()
    if not lowered:
        return True
    if lowered in LOW_CONFIDENCE_FILENAME_TOKENS:
        return True
    stem = Path(lowered).stem
    return len(stem) <= 4


def _resource_confidence(filename: str, context_text: str) -> float:
    lowered = str(filename or "").strip().lower()
    context_lower = str(context_text or "").lower()
    confidence = 0.95
    if _is_low_confidence_filename(lowered):
        confidence -= 0.45
    if any(token in context_lower for token in OUTPUT_TEMPLATE_TOKENS):
        confidence += 0.05
    if any(token in context_lower for token in MODULE_HEADING_TOKENS):
        confidence += 0.05
    if any(token in context_lower for token in ("resource", "åƒè€ƒ", "å‚è€ƒ", "ä½¿ç”¨", "éµå®ˆ", "å•Ÿå‹•")):
        confidence += 0.05
    return max(0.0, min(confidence, 1.0))


def _infer_resource_role(filename: str, context_text: str, section_role: str) -> str:
    lowered = str(filename or "").strip().lower()
    context_lower = str(context_text or "").lower()
    if lowered.endswith((".pdf", ".txt")):
        return "knowledge_source"
    if any(token in lowered for token in ("template", "spec", "standard")) or any(token in context_lower for token in ("format guide", "package guide", "æ¨¡æ¿", "è¦ç¯„", "è§„èŒƒ")):
        return "output_template"
    if any(token in context_lower for token in OUTPUT_ARTIFACT_TOKENS) or any(hint in lowered for hint in OUTPUT_ARTIFACT_NAME_HINTS):
        return "output_artifact"
    if section_role in {"instruction_module", "module", "rule", "activation", "resource_binding"}:
        return "instruction_source"
    return "instruction_source"


def _select_resource_filenames(
    text: str,
    *,
    context_text: str,
    min_confidence: float = 0.6,
    document_registry: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    selected_keys: set[str] = set()

    for matched_document in _match_builder_documents_in_text(text, document_registry):
        filename = str(matched_document.get("filename") or "").strip()
        if not filename:
            continue
        filename_key = _normalize_filename_key(filename)
        selected.append(
            {
                "filename": filename,
                "parsed_filename": filename,
                "confidence": 0.99,
                "matched_document": matched_document,
            }
        )
        selected_keys.add(filename_key)

    for filename in _extract_resource_filenames(text):
        confidence = _resource_confidence(filename, context_text)
        if confidence < min_confidence:
            continue
        matched_document = _resolve_builder_document(filename, document_registry)
        actual_filename = (
            str(matched_document.get("filename") or filename)
            if isinstance(matched_document, dict)
            else filename
        )
        actual_key = _normalize_filename_key(actual_filename)
        if actual_key in selected_keys:
            continue
        selected.append(
            {
                "filename": actual_filename,
                "parsed_filename": filename,
                "confidence": confidence,
                "matched_document": matched_document,
            }
        )
        selected_keys.add(actual_key)
    return selected


def _collect_resource_entries(
    heading: str,
    body: str,
    document_registry: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    section_role = _classify_section_role(heading, body)
    lines = [line.rstrip() for line in body.splitlines()]
    entries: dict[str, dict[str, Any]] = {}

    for index, raw_line in enumerate(lines):
        if not _extract_resource_filenames(raw_line):
            continue
        window = "\n".join(
            line for line in lines[max(0, index - 1): min(len(lines), index + 2)] if str(line or "").strip()
        )
        context_text = f"{heading}\n{window}"
        for selected in _select_resource_filenames(
            raw_line,
            context_text=context_text,
            document_registry=document_registry,
        ):
            filename = str(selected.get("filename") or "")
            confidence = float(selected.get("confidence") or 0.0)
            resource_role = _infer_resource_role(filename, context_text, section_role)
            matched_document = selected.get("matched_document") if isinstance(selected, dict) else None
            existing = entries.get(filename)
            payload = {
                "filename": filename,
                "parsed_filename": str(selected.get("parsed_filename") or filename),
                "confidence": confidence,
                "resource_role": resource_role,
                "document_id": matched_document.get("id") if isinstance(matched_document, dict) else None,
                "file_status": matched_document.get("status") if isinstance(matched_document, dict) else None,
            }
            if existing is None or float(payload["confidence"]) >= float(existing.get("confidence") or 0.0):
                entries[filename] = payload

    if entries:
        return list(entries.values())

    return [
        {
            "filename": str(selected.get("filename") or ""),
            "parsed_filename": str(selected.get("parsed_filename") or selected.get("filename") or ""),
            "confidence": float(selected.get("confidence") or 0.0),
            "resource_role": _infer_resource_role(str(selected.get("filename") or ""), f"{heading}\n{body}", section_role),
            "document_id": selected.get("matched_document", {}).get("id")
            if isinstance(selected.get("matched_document"), dict)
            else None,
            "file_status": selected.get("matched_document", {}).get("status")
            if isinstance(selected.get("matched_document"), dict)
            else None,
        }
        for selected in _select_resource_filenames(
            body,
            context_text=f"{heading}\n{body}",
            document_registry=document_registry,
        )
    ]


def _extract_command_triggers(text: str) -> list[str]:
    seen: set[str] = set()
    commands: list[str] = []
    for match in COMMAND_PATTERN.findall(str(text or "")):
        command = str(match or "").strip()
        lowered = command.lower()
        if command and lowered not in seen:
            seen.add(lowered)
            commands.append(command)
    return commands


def _contains_artifact_gate_language(text: str) -> bool:
    text_value = str(text or "")
    lowered = text_value.lower()
    has_required_ref = any(token.lower() in lowered for token in ARTIFACT_GATE_REQUIRED_TOKENS)
    has_missing_ref = any(token.lower() in lowered for token in ARTIFACT_GATE_MISSING_TOKENS)
    has_progress_ref = any(token.lower() in lowered for token in ARTIFACT_GATE_PROGRESS_TOKENS)
    has_bundle = "bundle" in lowered
    return (
        (has_required_ref and has_missing_ref)
        or (has_progress_ref and (has_required_ref or has_bundle))
        or "load bundle" in lowered
    )


def _infer_artifact_role(heading: str, body: str, filenames: list[str]) -> str | None:
    text = f"{heading}\n{body}".lower()
    for filename in filenames:
        stem = Path(str(filename or "")).stem.lower()
        if "bundle" in stem:
            return "bundle"
    if "bundle" in text:
        return "bundle"
    if "upload" in text:
        return "upload"
    return None


def _infer_binding_trigger_type(heading: str, body: str, section_role: str, commands: list[str], artifact_gate: bool) -> str | None:
    heading_lower = str(heading or "").lower()
    body_lower = str(body or "").lower()
    if commands:
        return "command_trigger"
    if artifact_gate:
        return "artifact_gate"
    if any(token in heading_lower for token in STARTER_HEADING_TOKENS):
        return "starter"
    if any(token in heading_lower for token in OUTPUT_HEADING_TOKENS):
        return "phase"
    if "support module" in heading_lower or "Ã¦â€Â¯Ã¦ÂÂ´Ã¦Â¨Â¡Ã§Âµâ€ž" in heading:
        return "module"
    if any(token in heading_lower for token in PHASE_HEADING_TOKENS) or any(token in body_lower for token in ("before executing", "phase")):
        return "phase"
    if section_role in {"instruction_module", "knowledge_module", "module"}:
        return "module"
    return None


def _binding_mode_from_text(body: str, filenames: list[str], artifact_gate: bool) -> str:
    if artifact_gate:
        return "none"
    lowered = str(body or "").lower()
    if any(token in lowered for token in ALTERNATIVE_TOKENS):
        return "one_of" if filenames else "none"
    if len(filenames) <= 1:
        return "single_required" if filenames else "none"
    numbered_with_files = 0
    for raw_line in str(body or "").splitlines():
        line = str(raw_line or "").strip()
        if NUMBERED_ITEM_PATTERN.match(line) and _extract_resource_filenames(line):
            numbered_with_files += 1
    if numbered_with_files >= 2:
        if filenames and all(str(name).lower().endswith((".docx", ".zip")) for name in filenames):
            return "one_of"
        return "ordered_multi"
    return "multi_required"


def _resource_kind_for_filename(filename: str, context_text: str, artifact_gate: bool = False) -> str:
    if artifact_gate:
        return "artifact_template"
    role = _infer_resource_role(filename, context_text, "generic")
    if role == "output_template":
        return "template_resource"
    if filename.lower().endswith((".docx", ".zip")):
        return "artifact_template"
    return "instruction_resource"


def _collect_generic_binding_resources(
    heading: str,
    body: str,
    document_registry: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    entries = _collect_resource_entries(heading, body, document_registry=document_registry)
    seen = {_normalize_filename_key(str(entry.get("filename") or "")) for entry in entries}
    for filename in _extract_resource_filenames(f"{heading}\n{body}"):
        matched_document = _resolve_builder_document(filename, document_registry)
        actual_filename = str(matched_document.get("filename") or filename) if isinstance(matched_document, dict) else filename
        filename_key = _normalize_filename_key(actual_filename)
        if not filename_key or filename_key in seen:
            continue
        entries.append(
            {
                "filename": actual_filename,
                "parsed_filename": filename,
                "confidence": _resource_confidence(filename, f"{heading}\n{body}"),
                "resource_role": _infer_resource_role(filename, f"{heading}\n{body}", _classify_section_role(heading, body)),
                "document_id": matched_document.get("id") if isinstance(matched_document, dict) else None,
                "file_status": matched_document.get("status") if isinstance(matched_document, dict) else None,
            }
        )
        seen.add(filename_key)
    return entries


def _build_generic_phase_bindings(
    markdown: str,
    resources: list[InstructionResourceBinding],
    document_registry: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    resource_ids_by_filename = {
        str(resource.filename or "").strip(): str(resource.resource_id or "").strip()
        for resource in resources
        if str(resource.filename or "").strip() and str(resource.resource_id or "").strip()
    }
    dependency_groups: list[dict[str, Any]] = []
    bindings: list[dict[str, Any]] = []
    block_updates: dict[str, dict[str, Any]] = {}

    for heading, body in _iter_heading_sections(markdown):
        section_role = _classify_section_role(heading, body)
        resource_entries = _collect_generic_binding_resources(heading, body, document_registry=document_registry)
        filenames = [str(entry.get("filename") or "").strip() for entry in resource_entries if str(entry.get("filename") or "").strip()]
        commands = _extract_command_triggers(f"{heading}\n{body}")
        artifact_gate = _contains_artifact_gate_language(f"{heading}\n{body}")
        trigger_type = _infer_binding_trigger_type(heading, body, section_role, commands, artifact_gate)
        if trigger_type is None:
            continue

        slug = _slugify_module_title(heading)
        if trigger_type == "command_trigger":
            block_id = f"command:{slug}"
        elif trigger_type == "artifact_gate":
            block_id = f"artifact_gate:{slug}"
        elif trigger_type == "starter":
            block_id = f"starter:{slug}"
        elif "support module" in heading.lower() or "Ã¦â€Â¯Ã¦ÂÂ´Ã¦Â¨Â¡Ã§Âµâ€ž" in heading:
            block_id = f"support_module:{slug}"
        elif any(token in heading.lower() for token in OUTPUT_HEADING_TOKENS):
            block_id = f"output:{slug}"
        else:
            block_id = f"phase:{slug}"

        artifact_role = _infer_artifact_role(heading, body, filenames)
        binding_mode = _binding_mode_from_text(body, filenames, artifact_gate)
        dependency_group_ids: list[str] = []
        if len(filenames) >= 2 and binding_mode in {"multi_required", "ordered_multi"}:
            dependency_group_id = f"dependency:{slug}"
            dependency_groups.append(
                to_plain_dict(
                    DependencyGroup(
                        group_id=dependency_group_id,
                        title=heading.strip(),
                        resource_ids=[resource_ids_by_filename[name] for name in filenames if name in resource_ids_by_filename],
                        filenames=filenames,
                        ordered=binding_mode == "ordered_multi",
                    )
                )
            )
            dependency_group_ids.append(dependency_group_id)

        artifact_contract = ArtifactContract()
        if artifact_gate:
            artifact_contract = ArtifactContract(
                mode="requires_artifact",
                artifact_role=artifact_role,
                filename_patterns=filenames,
                required_for_progression=True,
                missing_artifact_prompt=next(
                    (line.strip() for line in body.splitlines() if line.strip()),
                    body.strip() or None,
                ),
            )

        binding = PhaseResourceBinding(
            binding_id=block_id,
            title=heading.strip(),
            trigger_type=trigger_type,
            binding_mode=binding_mode,
            trigger_signals=commands,
            scope_id=block_id,
            resource_ids=[resource_ids_by_filename[name] for name in filenames if name in resource_ids_by_filename],
            filenames=filenames,
            resource_kinds=[_resource_kind_for_filename(name, f"{heading}\n{body}", artifact_gate=artifact_gate) for name in filenames],
            dependency_groups=dependency_group_ids,
            artifact_contract=artifact_contract,
            objective=_extract_labeled_value(body.splitlines(), ("Ã§â€ºÂ®Ã§Å¡â€ž", "objective", "goal")),
            activation_reason=body.strip() or None,
        )
        bindings.append(to_plain_dict(binding))
        block_updates[block_id] = {
            "declared_binding_id": block_id,
            "command_triggers": commands,
            "artifact_role": artifact_role,
            "referenced_resources": filenames,
            "document_ids": [str(entry.get("document_id") or "") for entry in resource_entries if str(entry.get("document_id") or "")],
        }

    return dependency_groups, bindings, block_updates


def _derive_module_keywords(title: str, filename: str) -> list[str]:
    keywords = set()
    cleaned_title = re.sub(r"^\d+\.\s*", "", str(title or "").strip())
    for part in re.split(r"[()ï¼ˆï¼‰/ã€,ï¼Œ]", cleaned_title):
        normalized = _normalize_keyword(part)
        if normalized:
            keywords.add(normalized)

    stem = Path(filename).stem.lower()
    keywords.add(stem)
    keywords.add(stem.replace("_", " "))

    filename_map = {
        "observation_guide": ["observation", "細察事實", "細查事實", "观察", "觀察"],
        "identify_relationship_guide": ["identify relationships", "èªæ¸…é—œä¿‚", "é—œä¿‚"],
        "identify_relation_guide": ["identify relationships", "èªæ¸…é—œä¿‚", "é—œä¿‚"],
        "examine_structure_guide": ["examine structure", "æ³¨æ„çµæ§‹", "çµæ§‹"],
        "formulate_questions_guide": ["formulate questions", "å‹¤ç™¼å•é¡Œ", "å•é¡Œ"],
        "answer_questions_guide": ["answer questions", "é€é¡Œè§£ç­”", "è§£ç­”"],
        "summarize_meaning_guide": ["summarize meaning", "æ­¸ç´ç¸½æ„", "ç¸½æ„"],
        "identify_theme_guide": ["identify theme", "æ‰¾å‡ºä¸»é¡Œ", "ä¸»é¡Œ"],
        "write_principles_guide": ["write principles", "å¯«ä¸‹åŽŸå‰‡", "åŽŸå‰‡"],
        "list_specifics_guide": ["list specifics", "åˆ—å‡ºç´°ç¯€", "ç´°ç¯€"],
        "apply_action_guide": ["apply in action", "apply action", "èº«é«”åŠ›è¡Œ", "æ‡‰ç”¨"],
    }
    for alias in filename_map.get(stem, []):
        normalized = _normalize_keyword(alias)
        if normalized:
            keywords.add(normalized)

    return sorted(keywords)


def _classify_section_role(heading: str, body: str) -> str:
    heading_text = str(heading or "")
    body_text = str(body or "")
    declared_type = _title_declared_structure_type(heading_text)
    if declared_type == "workflow":
        return "workflow"
    if declared_type in {"module", "ambiguous"}:
        if "instruction" in heading_text.lower() or "æŒ‡ä»¤" in heading_text:
            return "instruction_module"
        if "knowledge" in heading_text.lower() or "çŸ¥è­˜" in heading_text or "çŸ¥è¯†" in heading_text:
            return "knowledge_module"
        return "module"
    if _contains_any(heading_text, RESOURCE_BINDING_TOKENS):
        return "resource_binding"
    if _contains_any(heading_text, RULE_SECTION_TOKENS):
        return "rule"
    if _contains_any(body_text, ("ä½¿ç”¨", "å•Ÿå‹•", "éµå®ˆ", "must use", "start ", "obey ")):
        return "activation"
    return "generic"


def _iter_instruction_units(markdown: str, document_registry: dict[str, Any] | None = None) -> list[Dict[str, Any]]:
    units: list[Dict[str, Any]] = []
    heading_nodes = _flatten_heading_node_dicts(_build_instruction_heading_tree(markdown))
    heading_sections = [
        (str(node.get("title") or "").strip(), str(node.get("body_text") or "").strip())
        for node in heading_nodes
        if isinstance(node, dict) and str(node.get("title") or "").strip()
    ]
    if not heading_sections:
        heading_sections = _iter_heading_sections(markdown)

    for heading, body in heading_sections:
        section_role = _classify_section_role(heading, body)
        resource_entries = _collect_resource_entries(heading, body, document_registry=document_registry)
        if not resource_entries:
            continue
        lines = [line.strip() for line in body.splitlines() if line.strip()]
        units.append(
            {
                "unit_id": _slugify_module_title(heading),
                "title": heading.strip(),
                "role": section_role,
                "resource_files": [entry["filename"] for entry in resource_entries],
                "resource_entries": resource_entries,
                "activation_signals": _extract_activation_signals(lines),
                "body": body,
            }
        )
    return units


def _extract_structural_section_candidates(markdown: str) -> list[Dict[str, Any]]:
    candidates: list[Dict[str, Any]] = []
    flat_nodes = _flatten_heading_node_dicts(_build_instruction_heading_tree(markdown))
    parent_stack: list[dict[str, Any]] = []
    for node in flat_nodes:
        level = int(node.get("level") or 0)
        while parent_stack and int(parent_stack[-1].get("level") or 0) >= level:
            parent_stack.pop()
        parent_node_id = str(parent_stack[-1].get("node_id") or "").strip() if parent_stack else None
        children = node.get("children", []) if isinstance(node.get("children"), list) else []
        body_text = str(node.get("body_text") or "").strip()
        candidates.append(
            {
                "section_id": str(node.get("node_id") or "").strip(),
                "title": str(node.get("title") or "").strip(),
                "normalized_title": str(node.get("normalized_title") or "").strip(),
                "level": level,
                "parent_section_id": parent_node_id,
                "body_text": body_text,
                "child_section_ids": [
                    str(child.get("node_id") or "").strip()
                    for child in children
                    if isinstance(child, dict) and str(child.get("node_id") or "").strip()
                ],
                "resource_refs": _extract_resource_filenames(body_text),
            }
        )
        parent_stack.append(node)
    return candidates


def _extract_structural_step_candidates(
    markdown: str,
    *,
    document_registry: dict[str, Any] | None = None,
) -> list[Dict[str, Any]]:
    candidates: list[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    for unit in _iter_instruction_units(markdown, document_registry=document_registry):
        if str(unit.get("block_type") or "").strip() != "step":
            continue
        candidate_id = str(unit.get("block_id") or "").strip()
        if not candidate_id or candidate_id in seen_ids:
            continue
        seen_ids.add(candidate_id)
        candidates.append(
            {
                "step_candidate_id": candidate_id,
                "title": str(unit.get("title") or "").strip(),
                "body_text": str(unit.get("body_text") or "").strip(),
                "linked_workflow": str(unit.get("linked_workflow") or "").strip() or None,
                "linked_step_order": unit.get("linked_step_order"),
                "resource_refs": list(unit.get("referenced_resources") or []),
                "command_triggers": list(unit.get("command_triggers") or []),
            }
        )
    for node in _flatten_heading_node_dicts(_build_instruction_heading_tree(markdown)):
        title = str(node.get("title") or "").strip()
        match = HEADING_STYLE_STEP_PATTERN.match(title)
        if not match:
            continue
        candidate_id = str(node.get("node_id") or "").strip()
        if not candidate_id or candidate_id in seen_ids:
            continue
        seen_ids.add(candidate_id)
        step_order = None
        try:
            step_order = int(match.group(1))
        except (TypeError, ValueError):
            step_order = None
        body_text = str(node.get("body_text") or "").strip()
        candidates.append(
            {
                "step_candidate_id": candidate_id,
                "title": title,
                "body_text": body_text,
                "linked_workflow": None,
                "linked_step_order": step_order,
                "resource_refs": _extract_resource_filenames(body_text),
                "command_triggers": [],
            }
        )
    return candidates


def _extract_structural_rule_candidates(markdown: str) -> list[Dict[str, Any]]:
    candidates: list[Dict[str, Any]] = []
    rule_pattern = re.compile(
        r"(?im)^\s*(if\b.*|else\b.*|then\b.*|若.*|如果.*|當.*|当.*|IF\s+.+|ELSE\s*.+|.+(?:>=|<=|->|→).+)$"
    )
    for index, match in enumerate(rule_pattern.finditer(str(markdown or "")), start=1):
        expression = str(match.group(1) or "").strip()
        if not expression:
            continue
        candidates.append(
            {
                "rule_candidate_id": f"rule_candidate:{index}",
                "expression": expression,
            }
        )
    return candidates


def _extract_structural_trigger_candidates(
    markdown: str,
    *,
    document_registry: dict[str, Any] | None = None,
) -> list[Dict[str, Any]]:
    candidates: list[Dict[str, Any]] = []
    for unit in _iter_instruction_units(markdown, document_registry=document_registry):
        activation_triggers = list(unit.get("activation_triggers") or [])
        command_triggers = list(unit.get("command_triggers") or [])
        if not activation_triggers and not command_triggers:
            continue
        candidates.append(
            {
                "trigger_candidate_id": str(unit.get("block_id") or "").strip(),
                "title": str(unit.get("title") or "").strip(),
                "activation_triggers": activation_triggers,
                "command_triggers": command_triggers,
            }
        )
    return candidates


def _extract_structural_role_candidates(markdown: str) -> list[Dict[str, Any]]:
    candidates: list[Dict[str, Any]] = []
    for node in _flatten_heading_node_dicts(_build_instruction_heading_tree(markdown)):
        title = str(node.get("title") or "").strip()
        body_text = str(node.get("body_text") or "").strip()
        normalized_title = str(node.get("normalized_title") or "").strip()
        if not _contains_any(f"{title}\n{body_text}", GLOBAL_POLICY_HEADING_TOKENS):
            continue
        if not _contains_any(f"{title}\n{body_text}", ("role", "角色", "tone", "style", "語氣", "语气", "風格", "风格")):
            continue
        candidates.append(
            {
                "role_candidate_id": str(node.get("node_id") or "").strip(),
                "title": title,
                "normalized_title": normalized_title,
                "body_text": body_text,
            }
        )
    return candidates


def _extract_structural_interaction_logic_candidates(markdown: str) -> list[Dict[str, Any]]:
    candidates: list[Dict[str, Any]] = []
    interaction_tokens = ("wait", "continue", "ask", "clarification", "等待", "繼續", "继续", "提問", "提问")
    for node in _flatten_heading_node_dicts(_build_instruction_heading_tree(markdown)):
        title = str(node.get("title") or "").strip()
        body_text = str(node.get("body_text") or "").strip()
        if not _contains_any(f"{title}\n{body_text}", interaction_tokens):
            continue
        candidates.append(
            {
                "interaction_logic_candidate_id": str(node.get("node_id") or "").strip(),
                "title": title,
                "body_text": body_text,
                "resource_refs": _extract_resource_filenames(body_text),
            }
        )
    return candidates


def _build_structural_candidate_graph(
    markdown: str,
    *,
    document_registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "heading_tree": _build_instruction_heading_tree(markdown),
        "section_candidates": _extract_structural_section_candidates(markdown),
        "step_candidates": _extract_structural_step_candidates(markdown, document_registry=document_registry),
        "resource_candidates": _extract_resource_reference_catalog(markdown, document_registry=document_registry),
        "rule_candidates": _extract_structural_rule_candidates(markdown),
        "trigger_candidates": _extract_structural_trigger_candidates(markdown, document_registry=document_registry),
        "role_candidates": _extract_structural_role_candidates(markdown),
        "interaction_logic_candidates": _extract_structural_interaction_logic_candidates(markdown),
        "parser_warnings": _extract_parser_contract_warnings(markdown),
    }


def _extract_instruction_modules(markdown: str, document_registry: dict[str, Any] | None = None) -> list[Dict[str, Any]]:
    if not markdown:
        return []

    modules: dict[str, Dict[str, Any]] = {}
    for unit in _iter_instruction_units(markdown, document_registry=document_registry):
        declared_type = _title_declared_structure_type(str(unit.get("title") or ""))
        if declared_type in {"workflow", "ambiguous"}:
            continue
        resource_entries = [
            entry
            for entry in unit.get("resource_entries", [])
            if str(entry.get("filename") or "").lower().endswith(".md")
            and str(entry.get("resource_role") or "") != "output_artifact"
        ]
        if not resource_entries:
            continue
        for entry in resource_entries:
            filename = str(entry.get("filename") or "")
            module_id = Path(filename).stem.lower()
            title = str(unit.get("title") or Path(filename).stem.replace("_", " ")).strip()
            existing = modules.get(module_id)
            if existing is None:
                modules[module_id] = {
                    "id": module_id,
                    "title": title,
                    "resource_files": [filename],
                    "primary_resource": filename,
                    "keywords": _derive_module_keywords(title, filename),
                    "role": unit.get("role"),
                    "resource_role": entry.get("resource_role"),
                    "document_id": entry.get("document_id"),
                    "file_status": entry.get("file_status"),
                    "confidence": float(entry.get("confidence") or 0.0),
                    "activation_signals": list(unit.get("activation_signals", [])),
                }
                continue
            existing["resource_files"] = sorted({*existing.get("resource_files", []), filename})
            existing["keywords"] = sorted({*existing.get("keywords", []), *_derive_module_keywords(title, filename)})
            existing["activation_signals"] = sorted(
                {*(existing.get("activation_signals") or []), *(unit.get("activation_signals") or [])}
            )

    if not modules:
        current_title = ""
        for raw_line in _split_lines(markdown):
            line = str(raw_line or "").strip()
            if not line:
                continue
            numbered = NUMBERED_ITEM_PATTERN.match(line)
            if numbered:
                current_title = numbered.group(2).strip()
                continue
            heading_match = HEADING_PATTERN.match(line)
            if heading_match:
                current_title = heading_match.group(2).strip()
            for selected in _select_resource_filenames(line, context_text=line, document_registry=document_registry):
                filename = str(selected.get("filename") or "")
                confidence = float(selected.get("confidence") or 0.0)
                if not filename.lower().endswith(".md"):
                    continue
                resource_role = _infer_resource_role(filename, line, "instruction_module")
                if resource_role == "output_artifact":
                    continue
                module_id = Path(filename).stem.lower()
                title = current_title or Path(filename).stem.replace("_", " ")
                modules[module_id] = {
                    "id": module_id,
                    "title": title,
                    "resource_files": [filename],
                    "primary_resource": filename,
                    "keywords": _derive_module_keywords(title, filename),
                    "role": "instruction_module",
                    "resource_role": resource_role,
                    "document_id": selected.get("matched_document", {}).get("id")
                    if isinstance(selected.get("matched_document"), dict)
                    else None,
                    "file_status": selected.get("matched_document", {}).get("status")
                    if isinstance(selected.get("matched_document"), dict)
                    else None,
                    "confidence": confidence,
                    "activation_signals": _extract_activation_signals([line]),
                }
    return list(modules.values())


def _extract_quoted_terms(line: str) -> list[str]:
    text = str(line or "")
    matches: list[str] = []
    for pattern in (
        r"「([^」]+)」",
        r"『([^』]+)』",
        r'\"([^\"]+)\"',
    ):
        matches.extend(re.findall(pattern, text))
    for open_marker, close_marker in (("ã€Œ", "ã€"), ("ã€Ž", "ã€")):
        start = 0
        while True:
            open_index = text.find(open_marker, start)
            if open_index < 0:
                break
            close_index = text.find(close_marker, open_index + len(open_marker))
            if close_index < 0:
                break
            candidate = text[open_index + len(open_marker) : close_index]
            if candidate:
                matches.append(candidate)
            start = close_index + len(close_marker)
    return [_normalize_keyword(match) for match in matches if _normalize_keyword(match)]


def _fallback_cjk_terms(line: str) -> list[str]:
    skip_terms = {"觸發", "触发", "回應", "回应", "輸入", "输入", "包含", "查詢", "查询", "經文模式", "模式"}
    terms: list[str] = []
    seen: set[str] = set()
    for match in re.findall(r"[\u4e00-\u9fff]{2,}", str(line or "")):
        if match in skip_terms or match in seen:
            continue
        seen.add(match)
        terms.append(match)
    return terms


def _extract_activation_signals(lines: Iterable[str]) -> list[str]:
    signals: set[str] = set()
    for raw_line in lines:
        line = str(raw_line or "").strip()
        if not line:
            continue
        lowered = line.lower()
        for token, label in MD_VERB_RULES:
            if token.lower() in lowered:
                signals.add(label)
    return sorted(signals)


def _extract_labeled_value(lines: Iterable[str], labels: Iterable[str]) -> str | None:
    label_set = {str(label or "").strip().lower() for label in labels if str(label or "").strip()}
    captured: list[str] = []
    collecting = False
    for raw_line in lines:
        line = str(raw_line or "").strip()
        if not line:
            continue
        lowered = line.lower()
        matched_label = None
        for label in label_set:
            if lowered.startswith(label):
                matched_label = label
                break
        if matched_label is not None:
            collecting = True
            value = re.split(r"[:ï¼š：]\s*", line, maxsplit=1)
            trailing = value[1].strip() if len(value) > 1 else ""
            if trailing:
                captured.append(trailing)
            continue
        if collecting and (
            "Resource/" in line
            or line.startswith(("Use ", "使用資源", "使用资源", "操作", "回應", "回应"))
            or re.search(r"\.(?:md|pdf|docx|zip)\b", line, re.IGNORECASE)
        ):
            break
        if collecting and re.match(r"^[A-Za-z\u4e00-\u9fff].*[:ï¼š：]\s*", line):
            break
        if collecting:
            captured.append(line)
    text = " ".join(part for part in captured if part).strip()
    return text or None


def _extract_mode_workflows(markdown: str) -> list[Dict[str, Any]]:
    if not markdown:
        return []

    workflows: list[Dict[str, Any]] = []
    lines = [str(raw or "") for raw in markdown.splitlines()]
    top_level_depth = _infer_top_level_heading_depth(_tokenize_heading_lines(markdown))
    in_mode_section = False
    current: Dict[str, Any] | None = None
    mode_bullet_indent: int | None = None
    mode_section_level: int | None = None

    def _finalize_mode_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
        body_lines = [str(item or "").strip() for item in payload.get("body_lines", []) or [] if str(item or "").strip()]
        triggers = [str(item).strip() for item in payload.get("triggers", []) or [] if str(item).strip()]
        workflow_name = str(payload.get("workflow_name") or "").strip() or None
        entry_response_hint = str(payload.get("entry_response_hint") or "").strip() or None

        for body_line in body_lines[1:]:
            lower_line = body_line.lower()
            if (not triggers) and (
                "includes" in lower_line
                or "trigger" in lower_line
                or "觸發" in body_line
                or "触发" in body_line
            ):
                trigger_terms = _extract_quoted_terms(body_line) or _fallback_cjk_terms(body_line)
                if trigger_terms:
                    triggers = sorted({*triggers, *[term for term in trigger_terms if term]})
            if entry_response_hint is None and (
                "response" in lower_line
                or "回應" in body_line
                or "回应" in body_line
                or (
                    lower_line.startswith("o ")
                    and any(marker in body_line for marker in ("「", "『", "ã€Œ", "ã€Ž", "\""))
                )
            ):
                response_match = re.search(r"[:ï¼š：]\s*(.+)$", body_line)
                if response_match:
                    entry_response_hint = response_match.group(1).strip()
            if workflow_name is None:
                workflow_match = re.search(r"[:ï¼š：]\s*(.+)$", body_line)
                candidate = workflow_match.group(1).strip() if workflow_match else ""
                candidate = candidate.rstrip("ã€‚ï¼Ž.;:ï¼š。．：")
                if candidate and (
                    "模組" in candidate
                    or "模块" in candidate
                    or "module" in candidate.lower()
                    or "workflow" in candidate.lower()
                    or "流程" in candidate
                ):
                    workflow_name = candidate

        finalized = dict(payload)
        finalized["triggers"] = triggers
        finalized["workflow_name"] = workflow_name
        finalized["entry_response_hint"] = entry_response_hint
        return finalized

    for raw_line in lines:
        line = _repair_mojibake_text(raw_line.strip())
        if not line:
            continue
        heading_match = HEADING_PATTERN.match(line)
        if heading_match:
            heading_level = len(heading_match.group(1))
            heading = heading_match.group(2).strip()
            lower_heading = heading.lower()
            is_mode_heading = any(
                token in heading or token in lower_heading
                for token in ("æ¨¡å¼è‡ªå‹•è­˜åˆ¥", "mode detection")
            )
            if is_mode_heading:
                in_mode_section = True
                mode_section_level = heading_level
                if current is not None:
                    workflows.append(_finalize_mode_payload(current))
                    current = None
                    mode_bullet_indent = None
            elif in_mode_section and mode_section_level is not None and heading_level <= mode_section_level:
                workflows.append(_finalize_mode_payload(current)) if current is not None else None
                current = None
                mode_bullet_indent = None
                in_mode_section = False
                mode_section_level = None
            continue
        if not in_mode_section:
            continue

        indent = len(raw_line) - len(raw_line.lstrip())
        normalized = re.sub(r"^(?:Ã¢â‚¬Â¢|â€¢|•|\?|\-|\*)\s*", "", line).strip()
        is_mode_bullet = (
            line.startswith(("â€¢", "Ã¢â‚¬Â¢", "•", "?", "-", "*"))
            or (normalized != line and not normalized.lower().startswith(("o ", "trigger:", "response:", "start ")))
        )
        mode_match = PAREN_SUFFIX_PATTERN.match(normalized)
        normalized_lower = normalized.lower()
        looks_like_mode_title = ("æ¨¡å¼" in normalized) or (" mode" in normalized_lower) or normalized_lower.endswith("mode")
        is_subordinate_line = normalized_lower.startswith(
            ("o ", "trigger:", "response:", "start ", "workflow:", "è§¸ç™¼", "å›žæ‡‰", "å•Ÿå‹•", "å¯åŠ¨")
        )
        is_outer_bullet = is_mode_bullet and (
            mode_bullet_indent is None or indent <= mode_bullet_indent
        )
        if (
            (is_outer_bullet or looks_like_mode_title)
            and normalized
            and not is_subordinate_line
        ):
            if mode_bullet_indent is None:
                mode_bullet_indent = indent
            if current is not None:
                workflows.append(_finalize_mode_payload(current))
            title = normalized
            mode_id = _slugify_module_title(mode_match.group(2) if mode_match else normalized)
            current = {
                "id": mode_id,
                "title": title,
                "triggers": [],
                "workflow_name": None,
                "entry_response_hint": None,
                "body_lines": [normalized],
            }
            continue

        if current is None:
            continue

        current.setdefault("body_lines", []).append(line)

        lower_line = line.lower()
        if "includes" in lower_line and not current.get("triggers"):
            trigger_terms = _extract_quoted_terms(line)
            if not trigger_terms:
                trigger_terms = _fallback_cjk_terms(line)
            if trigger_terms:
                current["triggers"] = sorted({*(current.get("triggers") or []), *trigger_terms})
        if "è§¸ç™¼" in line or "觸發" in line or "trigger" in lower_line:
            trigger_terms = _extract_quoted_terms(line)
            if not trigger_terms:
                trigger_terms = _fallback_cjk_terms(line)
            current["triggers"] = sorted(
                {*(current.get("triggers") or []), *[term for term in trigger_terms if term]}
            )
        if "å›žæ‡‰" in line or "回應" in line or "回应" in line or "response" in lower_line:
            response_match = re.search(r"[:ï¼š：]\s*(.+)$", line)
            if response_match:
                current["entry_response_hint"] = response_match.group(1).strip()
        elif (
            current.get("entry_response_hint") is None
            and lower_line.startswith("o ")
            and any(marker in line for marker in ("「", "『", "ã€Œ", "ã€Ž", "\""))
        ):
            response_match = re.search(r"[:ï¼š：]\s*(.+)$", line)
            if response_match:
                current["entry_response_hint"] = response_match.group(1).strip()

        workflow_match = re.search(r"[:ï¼š：]\s*(.+)$", line)
        workflow_name = workflow_match.group(1).strip() if workflow_match else ""
        workflow_name = workflow_name.rstrip("ã€‚ï¼Ž.;:ï¼š。．：")
        if workflow_name and (
            "æ¨¡çµ„" in workflow_name
            or "module" in workflow_name.lower()
            or "workflow" in workflow_name.lower()
            or "æµç¨‹" in workflow_name
        ):
            current["workflow_name"] = workflow_name

    if current is not None:
        workflows.append(_finalize_mode_payload(current))

    return workflows


def _finalize_step_payload(
    step_payload: Dict[str, Any],
    *,
    document_registry: dict[str, Any] | None = None,
) -> Dict[str, Any]:
    body_lines = step_payload.get("body_lines", [])
    body_text = "\n".join(body_lines).strip()
    step_payload["body_text"] = body_text
    step_payload["objective"] = _extract_labeled_value(body_lines, ("目的", "目标", "Ã§â€ºÂ®Ã§Å¡â€ž", "objective", "goal"))
    step_payload["operation_text"] = _extract_labeled_value(body_lines, ("操作", "操作：", "Ã¦â€œÂÃ¤Â½Å“", "operation"))
    resource_entries = _collect_resource_entries(
        str(step_payload.get("title") or ""),
        body_text,
        document_registry=document_registry,
    )
    resource_files: list[str] = []
    seen_resource_keys: set[str] = set()
    for entry in resource_entries:
        filename = str(entry.get("filename") or "").strip()
        filename_key = _normalize_filename_key(filename)
        if not filename_key or filename_key in seen_resource_keys:
            continue
        resource_files.append(filename)
        seen_resource_keys.add(filename_key)
    existing_primary = str(step_payload.get("resource_file") or "").strip()
    if existing_primary and _normalize_filename_key(existing_primary) not in seen_resource_keys:
        resource_files.insert(0, existing_primary)
    step_payload["resource_files"] = resource_files
    step_payload["resource_file"] = resource_files[0] if resource_files else (existing_primary or None)
    return step_payload


def _extract_numbered_steps(section_body: str, document_registry: dict[str, Any] | None = None) -> list[Dict[str, Any]]:
    if not section_body:
        return []

    steps: list[Dict[str, Any]] = []
    current: Dict[str, Any] | None = None

    def _finalize_step_payload(step_payload: Dict[str, Any]) -> Dict[str, Any]:
        body_lines = step_payload.get("body_lines", [])
        body_text = "\n".join(body_lines).strip()
        step_payload["body_text"] = body_text
        step_payload["objective"] = _extract_labeled_value(body_lines, ("目的", "目标", "ç›®çš„", "objective", "goal"))
        step_payload["operation_text"] = _extract_labeled_value(body_lines, ("操作", "操作：", "æ“ä½œ", "operation"))
        resource_entries = _collect_resource_entries(
            str(step_payload.get("title") or ""),
            body_text,
            document_registry=document_registry,
        )
        resource_files: list[str] = []
        seen_resource_keys: set[str] = set()
        for entry in resource_entries:
            filename = str(entry.get("filename") or "").strip()
            filename_key = _normalize_filename_key(filename)
            if not filename_key or filename_key in seen_resource_keys:
                continue
            resource_files.append(filename)
            seen_resource_keys.add(filename_key)
        existing_primary = str(step_payload.get("resource_file") or "").strip()
        if existing_primary and _normalize_filename_key(existing_primary) not in seen_resource_keys:
            resource_files.insert(0, existing_primary)
        step_payload["resource_files"] = resource_files
        step_payload["resource_file"] = resource_files[0] if resource_files else (existing_primary or None)
        return step_payload

    for raw_line in section_body.splitlines():
        line = str(raw_line or "").strip()
        if not line:
            continue

        numbered = NUMBERED_ITEM_PATTERN.match(line)
        if numbered:
            if current is not None:
                steps.append(_finalize_step_payload(current))
            current = {
                "order": int(numbered.group(1)),
                "title": numbered.group(2).strip(),
                "resource_file": None,
                "body_lines": [],
            }
            continue

        if current is None:
            continue

        current.setdefault("body_lines", []).append(line)

        if current.get("resource_file") is None:
            selected_resources = _select_resource_filenames(
                line,
                context_text=line,
                document_registry=document_registry,
            )
            if selected_resources:
                current["resource_file"] = str(selected_resources[0].get("filename") or "").strip() or None

    if current is not None:
        steps.append(_finalize_step_payload(current))
    return steps


def _extract_heading_style_steps(
    heading_node: dict[str, Any],
    *,
    document_registry: dict[str, Any] | None = None,
) -> list[Dict[str, Any]]:
    if not isinstance(heading_node, dict):
        return []

    steps: list[Dict[str, Any]] = []
    for child in heading_node.get("children", []) or []:
        if not isinstance(child, dict):
            continue
        match = HEADING_STYLE_STEP_PATTERN.match(_repair_mojibake_text(str(child.get("title") or "").strip()))
        if not match:
            continue
        step_payload = {
            "order": int(match.group(1)),
            "title": str(match.group(2) or "").strip() or str(child.get("title") or "").strip(),
            "resource_file": None,
            "body_lines": str(child.get("body_text") or "").splitlines(),
        }
        steps.append(_finalize_step_payload(step_payload, document_registry=document_registry))
    return steps


def _is_support_module_heading(heading: str) -> bool:
    lower_heading = str(heading or "").lower()
    return "support module" in lower_heading or "支援模組" in heading or "支持模組" in heading or "模組" in heading


def _looks_like_narrative_procedure_section(heading: str, body: str) -> bool:
    normalized_heading = _normalize_section_name(heading)
    if not normalized_heading:
        return False
    if HEADING_STYLE_STEP_PATTERN.match(_repair_mojibake_text(str(heading or "").strip())):
        return False
    if _is_support_module_heading(heading):
        return False
    if _contains_any(heading, OUTPUT_HEADING_TOKENS) or _contains_any(heading, STARTER_HEADING_TOKENS):
        return False
    if _contains_any(heading, RESOURCE_BINDING_TOKENS) or _contains_any(heading, RULE_SECTION_TOKENS):
        return False
    if _contains_any(f"{heading}\n{body}", ("bible-study", "bible study", "查經")) and re.search(r"^\s*1\.\s+", body, re.MULTILINE):
        return True
    return any(token in normalized_heading for token in PROCEDURE_HEADING_TOKENS)


def _extract_support_module_sections(
    markdown: str,
    *,
    document_registry: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    support_modules: list[dict[str, Any]] = []
    for heading, body in _iter_heading_sections(markdown):
        if not _is_support_module_heading(heading):
            continue
        raw_steps = _extract_numbered_steps(body, document_registry=document_registry)
        step_resource_files = {
            str(filename).strip()
            for step in raw_steps
            if isinstance(step, dict)
            for filename in step.get("resource_files", []) or []
            if str(filename).strip()
        }
        resource_entries = _collect_resource_entries(heading, body, document_registry=document_registry)
        resource_files = [
            str(entry.get("filename") or "").strip()
            for entry in resource_entries
            if str(entry.get("filename") or "").strip()
            and str(entry.get("filename") or "").strip() not in step_resource_files
        ]
        support_modules.append(
            {
                "module_id": _slugify_module_title(heading),
                "title": heading.strip(),
                "body_text": body.strip(),
                "steps": raw_steps,
                "resource_files": resource_files,
                "resource_file_keys": {_normalize_filename_key(filename) for filename in resource_files},
            }
        )
    return support_modules


def _resolve_step_activation(
    step: dict[str, Any],
    *,
    support_modules: list[dict[str, Any]],
) -> dict[str, Any]:
    resource_files = [str(item).strip() for item in step.get("resource_files", []) or [] if str(item).strip()]
    step_text_key = _normalize_text_key(
        "\n".join(
            [
                str(step.get("title") or ""),
                str(step.get("objective") or ""),
                str(step.get("operation_text") or ""),
                str(step.get("body_text") or ""),
            ]
        )
    )
    best_module: dict[str, Any] | None = None
    best_score = 0
    support_resource_files: list[str] = []

    for module in support_modules:
        title_key = _normalize_text_key(str(module.get("title") or ""))
        title_match = bool(title_key and title_key in step_text_key)
        overlaps = [
            filename
            for filename in resource_files
            if _normalize_filename_key(filename) in module.get("resource_file_keys", set())
        ]
        score = (2 if title_match else 0) + (1 if overlaps else 0)
        if score > best_score:
            best_score = score
            best_module = module
            support_resource_files = overlaps

    support_resource_keys = {_normalize_filename_key(filename) for filename in support_resource_files}
    direct_resource_files = [
        filename
        for filename in resource_files
        if _normalize_filename_key(filename) not in support_resource_keys
    ]

    return {
        "direct_resource_files": direct_resource_files,
        "primary_support_module_id": best_module.get("module_id") if isinstance(best_module, dict) and best_score > 0 else None,
        "primary_support_module_title": best_module.get("title") if isinstance(best_module, dict) and best_score > 0 else None,
        "support_resource_files": support_resource_files,
    }


def _extract_instruction_workflows(markdown: str, document_registry: dict[str, Any] | None = None) -> list[Dict[str, Any]]:
    mode_workflows = _extract_mode_workflows(markdown)
    heading_tree = _build_instruction_heading_tree(markdown)
    flattened_heading_nodes = _flatten_heading_node_dicts(heading_tree)
    section_map = {
        str(node.get("title") or "").strip(): str(node.get("body_text") or "").strip()
        for node in flattened_heading_nodes
        if isinstance(node, dict) and str(node.get("title") or "").strip()
    }
    heading_nodes = [
        node
        for node in flattened_heading_nodes
        if isinstance(node, dict) and str(node.get("title") or "").strip()
    ]
    support_modules = _extract_support_module_sections(markdown, document_registry=document_registry)

    workflows: list[Dict[str, Any]] = []
    seen_workflow_names: set[str] = set()

    def _matching_heading_node(workflow_name: str) -> dict[str, Any] | None:
        workflow_name_normalized = _normalize_section_name(workflow_name)
        for node in heading_nodes:
            heading = str(node.get("title") or "").strip()
            heading_normalized = _normalize_section_name(heading)
            if (
                heading == workflow_name
                or workflow_name in heading
                or heading in workflow_name
                or heading_normalized == workflow_name_normalized
                or workflow_name_normalized in heading_normalized
                or heading_normalized in workflow_name_normalized
            ):
                return node
        return None

    def _workflow_steps_from_payload(
        workflow_id: str,
        raw_steps: list[dict[str, Any]],
    ) -> list[Dict[str, Any]]:
        steps: list[Dict[str, Any]] = []
        for step in raw_steps:
            resource_file = step.get("resource_file")
            step_order = step.get("order")
            step_scope_id = f"step:{workflow_id}:{int(step_order or 0)}"
            activation = _resolve_step_activation(step, support_modules=support_modules)
            steps.append(
                {
                    "order": step_order,
                    "title": step.get("title"),
                    "step_scope_id": step_scope_id,
                    "resource_file": resource_file,
                    "resource_files": list(step.get("resource_files", []) or ([] if not resource_file else [resource_file])),
                    "module_id": Path(resource_file).stem.lower() if resource_file else None,
                    "objective": step.get("objective"),
                    "operation_text": step.get("operation_text"),
                    "body_text": step.get("body_text"),
                    "activation": activation,
                }
            )
        return steps

    def _should_promote_narrative_workflow_node(
        node: dict[str, Any],
        parent: dict[str, Any] | None,
    ) -> bool:
        if not isinstance(node, dict):
            return False
        heading = str(node.get("title") or "").strip()
        body = str(node.get("body_text") or "").strip()
        declared_type = _title_declared_structure_type(heading)
        if declared_type in {"module", "ambiguous"}:
            return False
        if declared_type != "workflow" and not _looks_like_narrative_procedure_section(heading, body):
            return False
        if not isinstance(parent, dict):
            return True

        parent_title = str(parent.get("title") or "").strip()
        parent_body = str(parent.get("body_text") or "").strip()
        if HEADING_STYLE_STEP_PATTERN.match(_repair_mojibake_text(parent_title)):
            return False
        if _is_support_module_section(parent_title, parent_body):
            return False
        if _is_followup_module_section(parent_title, parent_body):
            return False
        if _is_output_contract_section(parent_title, parent_body):
            return False
        if _contains_any(parent_title, RESOURCE_CATALOG_HEADING_TOKENS):
            return False
        return True

    for mode in mode_workflows:
        workflow_name = str(mode.get("workflow_name") or "").strip()
        if not workflow_name:
            continue

        heading_node = _matching_heading_node(workflow_name)
        heading_title = str(heading_node.get("title") or workflow_name).strip() if isinstance(heading_node, dict) else workflow_name
        if _title_declared_structure_type(heading_title) in {"module", "ambiguous"}:
            continue
        section_body = str(heading_node.get("body_text") or "").strip() if isinstance(heading_node, dict) else ""
        if not section_body:
            continue

        raw_steps = (
            _extract_heading_style_steps(heading_node, document_registry=document_registry)
            if isinstance(heading_node, dict)
            else []
        )
        if not raw_steps:
            raw_steps = _extract_numbered_steps(section_body, document_registry=document_registry)
        if not raw_steps:
            continue

        workflow_id = str(mode.get("id") or "").strip()
        seen_workflow_names.add(_normalize_section_name(workflow_name))
        if isinstance(heading_node, dict):
            seen_workflow_names.add(_normalize_section_name(str(heading_node.get("title") or "").strip()))
        workflows.append(
            {
                "id": workflow_id,
                "title": mode.get("title"),
                "triggers": mode.get("triggers", []),
                "workflow_name": workflow_name,
                "entry_response_hint": mode.get("entry_response_hint"),
                "body_text": "\n".join(mode.get("body_lines", [])) if isinstance(mode.get("body_lines"), list) else "",
                "steps": _workflow_steps_from_payload(workflow_id, raw_steps),
            }
        )

    narrative_nodes: list[tuple[dict[str, Any], dict[str, Any] | None]] = []

    def _collect_narrative_nodes(nodes: list[dict[str, Any]], parent: dict[str, Any] | None = None) -> None:
        for node in nodes or []:
            if not isinstance(node, dict):
                continue
            narrative_nodes.append((node, parent))
            _collect_narrative_nodes(node.get("children", []) or [], parent=node)

    _collect_narrative_nodes(heading_tree or [])

    for node, parent in narrative_nodes:
        heading = str(node.get("title") or "").strip()
        body = str(node.get("body_text") or "").strip()
        if not _should_promote_narrative_workflow_node(node, parent):
            continue
        normalized_heading = _normalize_section_name(heading)
        if normalized_heading in seen_workflow_names:
            continue
        raw_steps = _extract_heading_style_steps(node, document_registry=document_registry)
        if not raw_steps:
            raw_steps = _extract_numbered_steps(body, document_registry=document_registry)
        if not raw_steps:
            continue
        workflow_id = _slugify_module_title(heading)
        workflows.append(
            {
                "id": workflow_id,
                "title": heading.strip(),
                "triggers": [],
                "workflow_name": _strip_parenthetical_suffix(heading),
                "entry_response_hint": None,
                "body_text": body.strip(),
                "steps": _workflow_steps_from_payload(workflow_id, raw_steps),
            }
        )
        seen_workflow_names.add(normalized_heading)
    return workflows


def _resource_refs_for_heading_node(
    heading: str,
    body: str,
    *,
    document_registry: dict[str, Any] | None = None,
) -> list[str]:
    return [
        str(entry.get("filename") or "").strip()
        for entry in _collect_resource_entries(heading, body, document_registry=document_registry)
        if str(entry.get("filename") or "").strip()
    ]


def _is_support_module_section(title: str, body: str) -> bool:
    normalized = _normalize_section_name(title)
    lowered = str(title or "").lower()
    return (
        "knowledge modules" in lowered
        or "instruction modules" in lowered
        or "support module" in lowered
        or "支援模組" in title
        or "支持模組" in title
    )


def _is_followup_module_section(title: str, body: str) -> bool:
    lowered = f"{title}\n{body}".lower()
    return any(token in lowered for token in ("optimization module", "tool selection module", "配置實現支持模組", "互動邏輯支持模組", "測試與優化支持模組", "testing & optimization", "config support"))


def _is_supplementary_workflow_section(title: str, body: str) -> bool:
    lowered = f"{title}\n{body}".lower()
    return (
        "supplementary" in lowered
        or "補充" in f"{title}\n{body}"
        or "secondary" in lowered
        or ("bible-study" in lowered and "ten-step" in lowered and "section" in lowered)
        or ("查經" in title and "補充" in body)
    )


def _is_entry_mode_section(title: str, body: str) -> bool:
    lowered = f"{title}\n{body}".lower()
    return (
        "mode detection" in lowered
        or "模式自動識別" in title
        or "模式自动识别" in title
        or ("模式" in title and any(token in body for token in ("觸發", "触发", "Trigger", "trigger")))
    )


def _is_output_contract_section(title: str, body: str) -> bool:
    lowered = f"{title}\n{body}".lower()
    return any(
        token in lowered
        for token in (
            "output contract",
            "prompt 輸出",
            "prompt 输出",
            "輸出格式",
            "输出格式",
            "output format",
            "delimiter",
            "export metadata",
        )
    )


def _is_global_policy_section(title: str, body: str) -> bool:
    lowered = f"{title}\n{body}".lower()
    return any(token in lowered for token in ("protocol", "policy", "規則", "规则", "human-in-the-loop"))


def _classify_service_block_type(title: str, body: str, *, workflow_titles: set[str]) -> str:
    normalized_title = _normalize_section_name(title)
    declared_type = _title_declared_structure_type(title)
    if declared_type == "module":
        if _is_followup_module_section(title, body):
            return "followup_module"
        return "support_module"
    if declared_type == "workflow":
        if _is_supplementary_workflow_section(title, body):
            return "supplementary_workflow"
        return "primary_workflow"
    if _is_entry_mode_section(title, body):
        return "entry_mode"
    if normalized_title in workflow_titles:
        if _is_supplementary_workflow_section(title, body):
            return "supplementary_workflow"
        return "primary_workflow"
    if _is_followup_module_section(title, body):
        return "followup_module"
    if _is_support_module_section(title, body):
        return "support_module"
    if _is_output_contract_section(title, body):
        return "output_contract"
    if _is_global_policy_section(title, body):
        return "global_policy"
    return "resource_catalog" if _contains_any(title, ("resource", "catalog", "資源")) else "global_policy"


def _build_instruction_service_blocks(
    workflows: list[dict[str, Any]],
    support_modules: list[dict[str, Any]],
    *,
    heading_tree: list[dict[str, Any]],
    document_registry: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    workflow_by_title = {
        _normalize_section_name(str(workflow.get("workflow_name") or workflow.get("title") or "")): workflow
        for workflow in workflows
        if str(workflow.get("workflow_name") or workflow.get("title") or "").strip()
    }
    workflow_titles = set(workflow_by_title.keys())

    def _match_workflow_for_title(title: str) -> dict[str, Any] | None:
        normalized_title = _normalize_section_name(title)
        workflow = workflow_by_title.get(normalized_title)
        if workflow is not None:
            return workflow
        if not normalized_title:
            return None
        for candidate_title, candidate_workflow in workflow_by_title.items():
            if not candidate_title:
                continue
            if (
                candidate_title == normalized_title
                or candidate_title in normalized_title
                or normalized_title in candidate_title
            ):
                return candidate_workflow
        return None

    if not heading_tree and not workflows:
        return blocks
    def _visit(nodes: list[dict[str, Any]], parent_block_id: str | None = None) -> None:
        for node in nodes or []:
            if not isinstance(node, dict):
                continue
            title = str(node.get("title") or "").strip()
            body = str(node.get("body_text") or "").strip()
            if not title:
                continue
            if HEADING_STYLE_STEP_PATTERN.match(_repair_mojibake_text(title)):
                _visit(node.get("children", []) or [], parent_block_id=parent_block_id)
                continue

            workflow = _match_workflow_for_title(title)
            declared_type = _title_declared_structure_type(title)
            workflow_for_block = workflow if declared_type not in {"module", "ambiguous"} else None
            workflow_id = str((workflow_for_block or {}).get("id") or _slugify_module_title(title)).strip()
            if workflow_for_block is not None:
                block_type = "supplementary_workflow" if _is_supplementary_workflow_section(title, body) else "primary_workflow"
            else:
                block_type = _classify_service_block_type(title, body, workflow_titles=workflow_titles)
            trigger_phrases = [str(item).strip() for item in (workflow_for_block or {}).get("triggers", []) or [] if str(item).strip()]
            resource_refs = _resource_refs_for_heading_node(title, body, document_registry=document_registry)
            if workflow_for_block:
                resource_refs = sorted(
                    {
                        *resource_refs,
                        *[
                            str(filename).strip()
                            for step in workflow_for_block.get("steps", []) or []
                            if isinstance(step, dict)
                            for filename in step.get("resource_files", []) or []
                            if str(filename).strip()
                        ],
                    }
                )
            elif block_type == "support_module":
                support_module = next(
                    (
                        module
                        for module in support_modules
                        if _normalize_section_name(str(module.get("title") or "").strip()) == _normalize_section_name(title)
                    ),
                    None,
                )
                step_resource_files = {
                    str(filename).strip()
                    for step in (support_module or {}).get("steps", []) or []
                    if isinstance(step, dict)
                    for filename in step.get("resource_files", []) or []
                    if str(filename).strip()
                }
                if step_resource_files:
                    resource_refs = [
                        filename
                        for filename in resource_refs
                        if str(filename).strip() not in step_resource_files
                    ]
            block_id = f"{block_type}:{workflow_id}"
            blocks.append(
                {
                    "block_id": block_id,
                    "block_type": block_type,
                    "title": title,
                    "body_text": body,
                    "parent_block_id": parent_block_id,
                    "trigger_conditions": [
                        {
                            "trigger_type": "phrase",
                            "phrases": trigger_phrases,
                            "command_markers": [],
                            "artifact_roles": [],
                            "starter_prompts": [],
                        }
                    ]
                    if trigger_phrases
                    else [],
                    "required_inputs": [],
                    "resource_refs": resource_refs,
                    "policy_refs": [],
                    "is_default": False,
                }
            )
            _visit(node.get("children", []) or [], parent_block_id=block_id)

    _visit(heading_tree or [])

    primary_blocks = [block for block in blocks if block.get("block_type") == "primary_workflow" and not block.get("trigger_conditions")]
    if len(primary_blocks) == 1:
        primary_blocks[0]["is_default"] = True
    return blocks


def _build_instruction_procedures(
    workflows: list[dict[str, Any]],
    service_blocks: list[dict[str, Any]],
    *,
    support_modules: list[dict[str, Any]] | None = None,
    document_registry: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    default_block_ids = {
        str(block.get("block_id") or "").strip()
        for block in service_blocks
        if bool(block.get("is_default"))
    }
    procedures: list[dict[str, Any]] = []
    procedure_steps: list[dict[str, Any]] = []

    workflow_by_title = {
        _normalize_section_name(str(workflow.get("workflow_name") or workflow.get("title") or "")): workflow
        for workflow in workflows
        if str(workflow.get("workflow_name") or workflow.get("title") or "").strip()
    }
    support_module_by_title = {
        _normalize_section_name(str(module.get("title") or "")): module
        for module in (support_modules or [])
        if str(module.get("title") or "").strip()
    }

    interactive_step_tokens = (
        "clarify",
        "question",
        "ask ",
        "ask one",
        "wait for user",
        "user confirmation",
        "confirm the",
        "checkpoint",
        "intake",
        "discovery",
        "discover",
        "observation",
        "interpretation",
        "application",
        "澄清",
        "提問",
        "提问",
        "等待",
        "確認",
        "确认",
        "查經",
        "查经",
        "細察事實",
        "解释经文",
        "解釋經文",
        "應用反思",
        "应用反思",
    )
    bundled_step_tokens = (
        "generate",
        "draft",
        "routing",
        "route ",
        "tool pair",
        "tool and module",
        "configure",
        "configuration",
        "validate",
        "validation",
        "output",
        "assemble",
        "finalize",
        "finalise",
        "delivery package",
        "workflow execution",
        "execution flow",
        "核心流程",
        "路由",
        "配置",
        "生成",
        "驗證",
        "验证",
        "輸出",
        "输出",
        "組裝",
        "组装",
        "定稿",
    )

    def _match_workflow_for_block_title(title: str) -> dict[str, Any] | None:
        normalized_title = _normalize_section_name(title)
        workflow = workflow_by_title.get(normalized_title)
        if workflow is not None:
            return workflow
        if not normalized_title:
            return None
        for candidate_title, candidate_workflow in workflow_by_title.items():
            if not candidate_title:
                continue
            if (
                candidate_title == normalized_title
                or candidate_title in normalized_title
                or normalized_title in candidate_title
            ):
                return candidate_workflow
        return None

    def _match_support_module_for_block(block: dict[str, Any]) -> dict[str, Any] | None:
        block_title = str(block.get("title") or "").strip()
        normalized_title = _normalize_section_name(block_title)
        module = support_module_by_title.get(normalized_title)
        if module is not None:
            return module
        if not normalized_title:
            return None
        for candidate_title, candidate_module in support_module_by_title.items():
            if not candidate_title:
                continue
            if (
                candidate_title == normalized_title
                or candidate_title in normalized_title
                or normalized_title in candidate_title
            ):
                return candidate_module
        block_body = str(block.get("body_text") or "").strip()
        raw_steps = _extract_numbered_steps(block_body, document_registry=document_registry)
        if raw_steps:
            return {
                "module_id": _slugify_module_title(block_title),
                "title": block_title,
                "body_text": block_body,
                "steps": raw_steps,
                "resource_files": [],
                "resource_file_keys": set(),
            }
        return None

    def _infer_step_execution_signal(step: dict[str, Any]) -> str:
        text = "\n".join(
            [
                str(step.get("title") or ""),
                str(step.get("objective") or ""),
                str(step.get("operation_text") or ""),
                str(step.get("body_text") or ""),
            ]
        ).lower()
        if any(token in text for token in interactive_step_tokens):
            return "interactive"
        if any(token in text for token in bundled_step_tokens):
            return "bundled"
        return "interactive"

    def _decorate_step_execution_modes(steps: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        decorated: dict[str, dict[str, Any]] = {}
        if not steps:
            return decorated

        inferred_modes = [_infer_step_execution_signal(step) for step in steps]
        index = 0
        while index < len(steps):
            step = steps[index]
            step_scope_id = str(step.get("step_scope_id") or "").strip()
            if not step_scope_id:
                index += 1
                continue
            decorated[step_scope_id] = {
                "execution_mode": "interactive",
                "bundled_step_ids": [],
                "bundled_resource_refs": [],
                "stop_after_completion": False,
            }
            if inferred_modes[index] != "bundled":
                index += 1
                continue

            run_end = index
            while run_end + 1 < len(steps) and inferred_modes[run_end + 1] == "bundled":
                run_end += 1

            bundled_members = steps[index : run_end + 1]
            bundled_step_ids = [
                str(item.get("step_scope_id") or "").strip()
                for item in bundled_members
                if str(item.get("step_scope_id") or "").strip()
            ]
            bundled_resource_refs = sorted(
                {
                    str(resource).strip()
                    for item in bundled_members
                    if isinstance(item, dict)
                    for resource in item.get("resource_files", []) or []
                    if str(resource).strip()
                }
            )
            for member in bundled_members:
                member_step_scope_id = str(member.get("step_scope_id") or "").strip()
                if not member_step_scope_id:
                    continue
                decorated[member_step_scope_id] = {
                    "execution_mode": "bundled",
                    "bundled_step_ids": [],
                    "bundled_resource_refs": [],
                    "stop_after_completion": False,
                }
            entry_step_scope_id = bundled_step_ids[0] if bundled_step_ids else None
            if entry_step_scope_id:
                decorated[entry_step_scope_id] = {
                    "execution_mode": "bundled",
                    "bundled_step_ids": bundled_step_ids,
                    "bundled_resource_refs": bundled_resource_refs,
                    "stop_after_completion": run_end == len(steps) - 1,
                }
            index = run_end + 1
        return decorated

    for block in service_blocks:
        block_type = str(block.get("block_type") or "").strip()
        procedure_id = ""
        service_block_id = str(block.get("block_id") or "").strip()
        procedure_kind = "primary"
        procedure_title = ""
        step_records: list[dict[str, Any]] = []
        trigger_phrases: list[str] = []

        if block_type in {"primary_workflow", "supplementary_workflow"}:
            workflow = _match_workflow_for_block_title(str(block.get("title") or ""))
            if not workflow:
                continue
            workflow_id = str(workflow.get("id") or "").strip()
            procedure_title = str(block.get("title") or workflow.get("workflow_name") or workflow.get("title") or "").strip()
            if not workflow_id or not procedure_title:
                continue
            procedure_id = f"procedure:{workflow_id}"
            procedure_kind = "supplementary" if block_type == "supplementary_workflow" else "primary"
            trigger_phrases = [str(item).strip() for item in workflow.get("triggers", []) or [] if str(item).strip()]
            step_records = [step for step in workflow.get("steps", []) or [] if isinstance(step, dict)]
        elif block_type in {"support_module", "followup_module"}:
            support_module = _match_support_module_for_block(block)
            if not support_module:
                continue
            procedure_title = str(block.get("title") or support_module.get("title") or "").strip()
            if not procedure_title or not service_block_id:
                continue
            slug = _slugify_module_title(procedure_title)
            procedure_id = f"procedure:{block_type}_{slug}"
            procedure_kind = "followup" if block_type == "followup_module" else "supplementary"
            raw_steps = [
                step
                for step in support_module.get("steps", []) or []
                if isinstance(step, dict)
            ]
            if not raw_steps:
                continue
            module_scope = {
                "module_id": slug,
                "title": procedure_title,
                "resource_files": list(support_module.get("resource_files", []) or []),
                "resource_file_keys": set(support_module.get("resource_file_keys") or set()),
            }
            step_records = []
            for step in raw_steps:
                step_order = int(step.get("order") or 0)
                step_scope_id = f"step:{block_type}_{slug}:{step_order}"
                activation = _resolve_step_activation(step, support_modules=[module_scope])
                step_records.append(
                    {
                        "order": step_order,
                        "title": str(step.get("title") or "").strip(),
                        "step_scope_id": step_scope_id,
                        "resource_file": step.get("resource_file"),
                        "resource_files": list(step.get("resource_files", []) or []),
                        "module_id": slug,
                        "objective": step.get("objective"),
                        "operation_text": step.get("operation_text"),
                        "body_text": step.get("body_text"),
                        "activation": activation,
                    }
                )
        else:
            continue

        if not procedure_id or not procedure_title or not step_records:
            continue
        procedures.append(
            {
                "procedure_id": procedure_id,
                "service_block_id": service_block_id,
                "title": procedure_title,
                "procedure_kind": procedure_kind,
                "is_default": service_block_id in default_block_ids,
                "entry_mode_ids": [],
                "trigger_conditions": [
                    {
                        "trigger_type": "phrase",
                        "phrases": trigger_phrases,
                        "command_markers": [],
                        "artifact_roles": [],
                        "starter_prompts": [],
                    }
                ]
                if trigger_phrases
                else [],
                "step_sequence": [
                    str(step.get("step_scope_id") or "").strip()
                    for step in step_records
                    if str(step.get("step_scope_id") or "").strip()
                ],
                "output_targets": [],
            }
        )

        step_execution_metadata = _decorate_step_execution_modes(step_records)
        for step in step_records:
            if not isinstance(step, dict):
                continue
            activation = dict(step.get("activation") or {})
            step_scope_id = str(step.get("step_scope_id") or "").strip()
            if not step_scope_id:
                continue
            execution_metadata = step_execution_metadata.get(
                step_scope_id,
                {
                    "execution_mode": "interactive",
                    "bundled_step_ids": [],
                    "bundled_resource_refs": [],
                    "stop_after_completion": False,
                },
            )
            procedure_steps.append(
                {
                    "step_id": step_scope_id,
                    "procedure_id": procedure_id,
                    "order": step.get("order"),
                    "title": str(step.get("title") or "").strip(),
                    "body_text": str(step.get("body_text") or "").strip(),
                    "step_kind": None,
                    "execution_mode": execution_metadata["execution_mode"],
                    "bundled_step_ids": list(execution_metadata["bundled_step_ids"]),
                    "bundled_resource_refs": list(execution_metadata["bundled_resource_refs"]),
                    "stop_after_completion": bool(execution_metadata["stop_after_completion"]),
                    "wait_for_user": False,
                    "advance_conditions": [],
                    "resource_refs": [
                        str(item).strip()
                        for item in step.get("resource_files", []) or []
                        if str(item).strip()
                    ],
                    "primary_support_module_id": activation.get("primary_support_module_id"),
                    "step_output_role": None,
                }
            )

    return procedures, procedure_steps


def _iter_heading_sections(markdown: str) -> List[Tuple[str, str]]:
    sections: List[Tuple[str, str]] = []
    for node in _flatten_heading_node_dicts(_build_instruction_heading_tree(markdown)):
        if not isinstance(node, dict):
            continue
        heading = str(node.get("title") or "").strip()
        if not heading:
            continue
        sections.append((heading, str(node.get("body_text") or "").strip()))
    return sections


def _extract_instruction_blocks(markdown: str, document_registry: dict[str, Any] | None = None) -> list[Dict[str, Any]]:
    blocks: list[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    support_module_sections = _extract_support_module_sections(markdown, document_registry=document_registry)
    support_module_by_title = {
        _normalize_section_name(str(module.get("title") or "")): module
        for module in support_module_sections
        if str(module.get("title") or "").strip()
    }

    for workflow in _extract_instruction_workflows(markdown, document_registry=document_registry):
        mode_block_id = f"mode:{str(workflow.get('id') or '').strip()}"
        mode_block = {
            "block_id": mode_block_id,
            "block_type": "mode",
            "title": str(workflow.get("title") or "").strip(),
            "body_text": str(workflow.get("body_text") or "").strip(),
            "objective": None,
            "operation_text": None,
            "response_hint": str(workflow.get("entry_response_hint") or "").strip() or None,
            "activation_triggers": [str(item) for item in workflow.get("triggers", []) or []],
            "referenced_resources": [],
            "document_ids": [],
            "linked_mode_id": str(workflow.get("id") or "").strip() or None,
            "linked_workflow": str(workflow.get("workflow_name") or "").strip() or None,
            "linked_step_order": None,
            "linked_step_title": None,
        }
        if mode_block_id not in seen_ids:
            seen_ids.add(mode_block_id)
            blocks.append(mode_block)

        for step in workflow.get("steps", []) or []:
            if not isinstance(step, dict):
                continue
            resource_file = str(step.get("resource_file") or "").strip()
            matched_document = _resolve_builder_document(resource_file, document_registry) if resource_file else None
            block_id = f"step:{str(workflow.get('id') or '').strip()}:{int(step.get('order') or 0)}"
            if block_id in seen_ids:
                continue
            seen_ids.add(block_id)
            blocks.append(
                {
                    "block_id": block_id,
                    "block_type": "step",
                    "title": str(step.get("title") or "").strip(),
                    "body_text": str(step.get("body_text") or "").strip(),
                    "objective": str(step.get("objective") or "").strip() or None,
                    "operation_text": str(step.get("operation_text") or "").strip() or None,
                    "response_hint": None,
                    "activation_triggers": [str(item) for item in workflow.get("triggers", []) or []],
                    "referenced_resources": [resource_file] if resource_file else [],
                    "document_ids": [str(matched_document.get("id") or "").strip()] if isinstance(matched_document, dict) and str(matched_document.get("id") or "").strip() else [],
                    "linked_mode_id": str(workflow.get("id") or "").strip() or None,
                    "linked_workflow": str(workflow.get("workflow_name") or workflow.get("title") or "").strip() or None,
                    "linked_step_order": step.get("order"),
                    "linked_step_title": str(step.get("title") or "").strip() or None,
                }
            )

    for heading, body in _iter_heading_sections(markdown):
        if not _is_support_module_heading(heading):
            continue
        section_role = _classify_section_role(heading, body)
        resource_entries = _collect_resource_entries(heading, body, document_registry=document_registry)
        support_module = support_module_by_title.get(_normalize_section_name(heading), {})
        step_resource_files = {
            str(filename).strip()
            for step in support_module.get("steps", []) or []
            if isinstance(step, dict)
            for filename in step.get("resource_files", []) or []
            if str(filename).strip()
        }
        referenced_resources = [
            str(entry.get("filename") or "")
            for entry in resource_entries
            if str(entry.get("filename") or "") and str(entry.get("filename") or "") not in step_resource_files
        ]
        document_ids = [
            str(entry.get("document_id") or "")
            for entry in resource_entries
            if str(entry.get("document_id") or "") and str(entry.get("filename") or "") not in step_resource_files
        ]
        block_id = f"support:{_slugify_module_title(heading)}"
        if block_id in seen_ids:
            continue
        seen_ids.add(block_id)
        blocks.append(
            {
                "block_id": block_id,
                "block_type": "support_module",
                "title": heading.strip(),
                "body_text": body.strip(),
                "objective": _extract_labeled_value(body.splitlines(), ("ç›®çš„", "objective", "goal")),
                "operation_text": _extract_labeled_value(body.splitlines(), ("æ“ä½œ", "operation", "ä½¿ç”¨åŽŸå‰‡")),
                "response_hint": _extract_labeled_value(body.splitlines(), ("å›žæ‡‰", "response")),
                "activation_triggers": _extract_quoted_terms(body),
                "referenced_resources": referenced_resources,
                "document_ids": document_ids,
                "linked_mode_id": None,
                "linked_workflow": None,
                "linked_step_order": None,
                "linked_step_title": None,
                "role": section_role,
            }
        )
        support_slug = _slugify_module_title(heading)
        for step in support_module.get("steps", []) or []:
            if not isinstance(step, dict):
                continue
            step_order = int(step.get("order") or 0)
            step_block_id = f"step:support_module_{support_slug}:{step_order}"
            if step_block_id in seen_ids:
                continue
            seen_ids.add(step_block_id)
            step_resource_entries = _collect_resource_entries(
                str(step.get("title") or "").strip(),
                str(step.get("body_text") or "").strip(),
                document_registry=document_registry,
            )
            blocks.append(
                {
                    "block_id": step_block_id,
                    "block_type": "step",
                    "title": str(step.get("title") or "").strip(),
                    "body_text": str(step.get("body_text") or "").strip(),
                    "objective": str(step.get("objective") or "").strip() or None,
                    "operation_text": str(step.get("operation_text") or "").strip() or None,
                    "response_hint": None,
                    "activation_triggers": [],
                    "referenced_resources": [
                        str(entry.get("filename") or "").strip()
                        for entry in step_resource_entries
                        if str(entry.get("filename") or "").strip()
                    ],
                    "document_ids": [
                        str(entry.get("document_id") or "").strip()
                        for entry in step_resource_entries
                        if str(entry.get("document_id") or "").strip()
                    ],
                    "linked_mode_id": None,
                    "linked_workflow": heading.strip(),
                    "linked_step_order": step_order,
                    "linked_step_title": str(step.get("title") or "").strip() or None,
                    "role": section_role,
                }
            )

    for heading, body in _iter_heading_sections(markdown):
        section_role = _classify_section_role(heading, body)
        resource_entries = _collect_generic_binding_resources(heading, body, document_registry=document_registry)
        support_module = support_module_by_title.get(_normalize_section_name(heading), {})
        step_resource_files = {
            str(filename).strip()
            for step in support_module.get("steps", []) or []
            if isinstance(step, dict)
            for filename in step.get("resource_files", []) or []
            if str(filename).strip()
        }
        referenced_resources = [
            str(entry.get("filename") or "")
            for entry in resource_entries
            if str(entry.get("filename") or "")
            and str(entry.get("filename") or "").strip() not in step_resource_files
        ]
        document_ids = [
            str(entry.get("document_id") or "")
            for entry in resource_entries
            if str(entry.get("document_id") or "")
            and str(entry.get("filename") or "").strip() not in step_resource_files
        ]
        commands = _extract_command_triggers(f"{heading}\n{body}")
        artifact_gate = _contains_artifact_gate_language(f"{heading}\n{body}")
        trigger_type = _infer_binding_trigger_type(heading, body, section_role, commands, artifact_gate)
        if trigger_type is None:
            continue

        slug = _slugify_module_title(heading)
        if trigger_type == "command_trigger":
            block_id = f"command:{slug}"
        elif trigger_type == "artifact_gate":
            block_id = f"artifact_gate:{slug}"
        elif trigger_type == "starter":
            block_id = f"starter:{slug}"
        elif _is_support_module_heading(heading):
            block_id = f"support_module:{slug}"
        elif any(token in heading.lower() for token in OUTPUT_HEADING_TOKENS):
            block_id = f"output:{slug}"
        else:
            block_id = f"phase:{slug}"

        payload = {
            "block_id": block_id,
            "block_type": "support_module" if block_id.startswith("support_module:") else "generic",
            "title": heading.strip(),
            "body_text": body.strip(),
            "objective": _extract_labeled_value(body.splitlines(), ("Ã§â€ºÂ®Ã§Å¡â€ž", "objective", "goal")),
            "operation_text": _extract_labeled_value(body.splitlines(), ("Ã¦â€œÂÃ¤Â½Å“", "operation", "Ã¤Â½Â¿Ã§â€Â¨Ã¥Å½Å¸Ã¥â€°â€¡")),
            "response_hint": _extract_labeled_value(body.splitlines(), ("Ã¥â€ºÅ¾Ã¦â€¡â€°", "response")),
            "activation_triggers": _extract_quoted_terms(body),
            "referenced_resources": referenced_resources,
            "document_ids": document_ids,
            "linked_mode_id": None,
            "linked_workflow": None,
            "linked_step_order": None,
            "linked_step_title": None,
            "declared_binding_id": block_id,
            "command_triggers": commands,
            "artifact_role": _infer_artifact_role(heading, body, referenced_resources),
            "role": section_role,
        }
        if block_id in seen_ids:
            for block in blocks:
                if block.get("block_id") == block_id:
                    block.update(payload)
                    break
            continue
        seen_ids.add(block_id)
        blocks.append(payload)

    return blocks


def _find_section(markdown: str, *needles: str) -> str:
    lowered_needles = [needle.lower() for needle in needles if needle]
    for heading, body in _iter_heading_sections(markdown):
        normalized_heading = heading.lower()
        if any(needle in heading or needle in normalized_heading for needle in lowered_needles):
            return body
    return ""


def _extract_role_summary(markdown: str) -> str | None:
    section = _find_section(markdown, "\u89d2\u8272\u5b9a\u4f4d", "role")
    for raw_line in section.splitlines():
        line = str(raw_line or "").strip()
        if line:
            return line
    return None


def _extract_primary_objectives(markdown: str) -> list[str]:
    section = _find_section(markdown, "\u4e3b\u8981\u76ee\u6a19", "objective", "goal")
    objectives: list[str] = []
    for raw_line in section.splitlines():
        line = str(raw_line or "").strip()
        if not line:
            continue
        match = re.match(r"^(?:\d+\.\s*|[-â€¢]\s*)(.+)$", line)
        if match:
            objectives.append(match.group(1).strip())
    return objectives


def _extract_behavior_rules(markdown: str) -> list[str]:
    section = _find_section(markdown, "\u6559\u5c0e\u98a8\u683c", "teaching style", "\u6e9d\u901a\u98a8\u683c", "\u8a9e\u6c23")
    rules: list[str] = []
    for raw_line in section.splitlines():
        line = str(raw_line or "").strip()
        if not line:
            continue
        if line.startswith(("â€¢", "-", "*", "Ã¢â‚¬Â¢")):
            cleaned = re.sub(r"^[â€¢\-\*\sÃ¢â‚¬Â¢]+", "", line).strip()
            if cleaned:
                rules.append(cleaned)
    return rules


def _extract_mode_rules(markdown: str) -> list[ModeRule]:
    rules: list[ModeRule] = []
    for workflow in _extract_mode_workflows(markdown):
        if not isinstance(workflow, dict):
            continue
        rules.append(
            ModeRule(
                mode_id=str(workflow.get("id") or ""),
                title=str(workflow.get("title") or ""),
                triggers=[str(item) for item in workflow.get("triggers", []) or []],
                workflow_name=workflow.get("workflow_name"),
                entry_response_hint=workflow.get("entry_response_hint"),
            )
        )
    return rules


def _extract_progression_rules(markdown: str) -> ProgressionRules:
    section = _find_section(markdown, "\u4e92\u52d5\u8207\u7bc0\u594f\u898f\u5247", "interaction", "progression")
    text = " ".join(section.splitlines())
    wait_for_user_response = ("\u7b49\u5f85" in text and "\u56de\u61c9" in text) or ("wait" in text.lower())
    require_explicit_advance = "\u662f\u5426\u8981\u9032\u5165\u4e0b\u4e00\u6b65" in text or "next step" in text.lower()

    max_questions = 3
    min_questions = 1
    range_match = re.search(r"(\d+)\s*[â€“\-~]\s*(\d+)\s*[\u500bä¸ª]?[\u554f\u554fé¡Œ]?|\b(\d+)\s*-\s*(\d+)\b", text)
    if range_match:
        parts = [part for part in range_match.groups() if part]
        if len(parts) >= 2:
            min_questions = int(parts[0])
            max_questions = int(parts[1])

    continue_markers = []
    end_markers = []
    for marker in ("\u7e7c\u7e8c", "continue", "proceed", "next step"):
        if marker in text or marker in text.lower():
            continue_markers.append(marker)
    for marker in ("\u7d50\u675f", "end", "stop"):
        if marker in text or marker in text.lower():
            end_markers.append(marker)

    return ProgressionRules(
        wait_for_user_response=wait_for_user_response,
        require_explicit_advance=require_explicit_advance,
        min_questions_per_turn=min_questions,
        max_questions_per_turn=max_questions,
        continue_markers=continue_markers,
        end_markers=end_markers,
    )


def _extract_turn_constraints(markdown: str, progression_rules: ProgressionRules) -> TurnConstraints:
    section = _find_section(markdown, "\u4e92\u52d5\u8207\u7bc0\u594f\u898f\u5247", "interaction", "progression")
    lower = section.lower()
    return TurnConstraints(
        max_questions_per_turn=progression_rules.max_questions_per_turn,
        wait_after_questions=progression_rules.wait_for_user_response,
        avoid_answer_and_question_same_turn=("\u4e0d\u5f97\u540c\u6642" in section and "\u554f\u984c" in section and "\u7b54\u6848" in section)
        or ("same turn" in lower and "answer" in lower and "question" in lower),
    )


def _extract_response_policies(markdown: str) -> Dict[str, Any]:
    section = _find_section(markdown, "\u5b78\u54e1\u56de\u61c9\u8655\u7406\u908f\u8f2f", "response handling")
    lines = [str(raw or "").strip() for raw in section.splitlines() if str(raw or "").strip()]
    return {
        "response_handling_excerpt": lines[:12],
    }


def _build_global_instruction_context(
    *,
    role_summary: str | None,
    primary_objectives: list[str],
    behavior_rules: list[str],
    mode_rules: list[ModeRule],
    progression_rules: ProgressionRules,
    support_modules: list[SupportModuleRule],
    turn_constraints: TurnConstraints,
    response_policies: Dict[str, Any],
) -> Dict[str, Any]:
    context = GlobalInstructionContext(
        role_summary=role_summary,
        primary_objectives=[str(item).strip() for item in primary_objectives if str(item).strip()],
        behavior_rules=[str(item).strip() for item in behavior_rules if str(item).strip()],
        progression_rules=to_plain_dict(progression_rules),
        turn_constraints=to_plain_dict(turn_constraints),
        response_policies=dict(response_policies or {}),
        mode_summaries=[
            {
                "mode_id": str(rule.mode_id or "").strip(),
                "title": str(rule.title or "").strip(),
                "triggers": [str(item).strip() for item in rule.triggers if str(item).strip()][:8],
                "entry_response_hint": str(rule.entry_response_hint or "").strip() or None,
            }
            for rule in mode_rules
        ],
        support_module_summaries=[
            {
                "module_id": str(module.module_id or "").strip(),
                "title": str(module.title or "").strip(),
                "activation_triggers": [str(item).strip() for item in module.activation_triggers if str(item).strip()][:8],
                "notes": str(module.notes or "").strip() or None,
            }
            for module in support_modules
        ],
    )
    return to_plain_dict(context)


def _load_full_instruction_text(builder_instructions: Any) -> str:
    return str(builder_instructions or "").strip()


def _apply_compiled_instruction_understanding(
    registry: Dict[str, Any],
    *,
    compiled_contract: Dict[str, Any],
    fallback_instruction_text: str,
) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    full_instruction_text = str(
        compiled_contract.get("full_instruction_text") or _load_full_instruction_text(fallback_instruction_text)
    )
    instruction_runtime_model = dict(compiled_contract.get("instruction_runtime_model") or {})
    global_instruction_context = dict(compiled_contract.get("global_instruction_context") or {})
    presentation_policy_hints = dict(compiled_contract.get("presentation_policy_hints") or {})
    registry["full_instruction_text"] = full_instruction_text
    registry["instruction_scope_candidates"] = list(compiled_contract.get("instruction_scope_candidates") or [])
    registry["resource_reference_catalog"] = list(compiled_contract.get("resource_reference_catalog") or [])
    registry["presentation_policy_hints"] = presentation_policy_hints
    registry["instruction_units"] = list(compiled_contract.get("instruction_units") or [])
    registry["instruction_blocks"] = list(compiled_contract.get("instruction_blocks") or [])
    registry["instruction_modules"] = list(compiled_contract.get("instruction_modules") or [])
    registry["instruction_workflows"] = list(compiled_contract.get("instruction_workflows") or [])
    registry["instruction_runtime_model"] = instruction_runtime_model
    registry["instruction_heading_tree"] = list(compiled_contract.get("instruction_heading_tree") or [])
    registry["instruction_service_blocks"] = list(compiled_contract.get("instruction_service_blocks") or [])
    registry["instruction_procedures"] = list(compiled_contract.get("instruction_procedures") or [])
    registry["procedure_steps"] = list(compiled_contract.get("procedure_steps") or [])
    registry["support_modules_v2"] = list(compiled_contract.get("support_modules_v2") or [])
    registry["followup_modules"] = list(compiled_contract.get("followup_modules") or [])
    registry["global_policies"] = list(compiled_contract.get("global_policies") or [])
    registry["global_instruction_context"] = global_instruction_context
    return registry, instruction_runtime_model, global_instruction_context, presentation_policy_hints


def _extract_instruction_scope_candidates(
    markdown: str,
    *,
    instruction_blocks: list[dict[str, Any]] | None = None,
    document_registry: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    full_text = _load_full_instruction_text(markdown)
    if full_text:
        candidates.append(
            {
                "scope_id": "global:instructions",
                "scope_type": "global",
                "title": "Application Instructions",
                "body_text": full_text,
                "referenced_resources": [
                    str(item.get("filename") or "").strip()
                    for item in _collect_resource_entries("Application Instructions", full_text, document_registry=document_registry)
                    if str(item.get("filename") or "").strip()
                ],
            }
        )
        seen_ids.add("global:instructions")

    workflows = _extract_instruction_workflows(markdown, document_registry=document_registry)
    for workflow in workflows:
        workflow_id = str(workflow.get("id") or "").strip()
        workflow_name = str(workflow.get("workflow_name") or workflow.get("title") or "").strip()
        scope_id = f"workflow:{workflow_id}" if workflow_id else f"workflow:{_slugify_module_title(workflow_name)}"
        if not workflow_name or scope_id in seen_ids:
            continue
        candidates.append(
            {
                "scope_id": scope_id,
                "scope_type": "workflow",
                "title": workflow_name,
                "body_text": str(workflow.get("body_text") or "").strip(),
                "response_hint": str(workflow.get("entry_response_hint") or "").strip() or None,
                "activation_triggers": [str(item).strip() for item in workflow.get("triggers", []) or [] if str(item).strip()],
                "step_records": [
                    {
                        "step_scope_id": str(step.get("step_scope_id") or "").strip(),
                        "step_scope_type": "step",
                        "step_order": step.get("order"),
                        "step_title": str(step.get("title") or "").strip() or None,
                        "referenced_resources": list(step.get("resource_files", []) or []),
                        "activation": dict(step.get("activation") or {}),
                    }
                    for step in workflow.get("steps", []) or []
                    if isinstance(step, dict)
                ],
                "referenced_resources": sorted(
                    {
                        str(filename).strip()
                        for step in workflow.get("steps", []) or []
                        if isinstance(step, dict)
                        for filename in step.get("resource_files", []) or []
                        if str(filename).strip()
                    }
                ),
            }
        )
        seen_ids.add(scope_id)

    blocks = instruction_blocks or _extract_instruction_blocks(markdown, document_registry=document_registry)
    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_id = str(block.get("block_id") or "").strip()
        if not block_id or block_id in seen_ids:
            continue
        candidates.append(
            {
                "scope_id": block_id,
                "scope_type": str(block.get("block_type") or "generic"),
                "title": str(block.get("title") or "").strip() or None,
                "body_text": str(block.get("body_text") or "").strip(),
                "objective": str(block.get("objective") or "").strip() or None,
                "operation_text": str(block.get("operation_text") or "").strip() or None,
                "response_hint": str(block.get("response_hint") or "").strip() or None,
                "referenced_resources": list(block.get("referenced_resources") or []),
                "document_ids": list(block.get("document_ids") or []),
            }
        )
        seen_ids.add(block_id)

    for unit in _iter_instruction_units(markdown, document_registry=document_registry):
        if not isinstance(unit, dict):
            continue
        heading = str(unit.get("title") or "").strip()
        body = str(unit.get("body") or "").strip()
        normalized_heading = _normalize_section_name(heading)
        if not normalized_heading:
            continue
        if not (
            "å­¸å“¡å›žæ‡‰è™•ç†é‚è¼¯" in heading
            or "å­¦ç”Ÿå›žåº”å¤„ç†é€»è¾‘" in heading
            or _contains_any(heading, ("response handling", "response logic", "presentation", "visibility"))
        ):
            continue
        scope_id = f"section:{_slugify_module_title(heading)}"
        if scope_id in seen_ids:
            continue
        candidates.append(
            {
                "scope_id": scope_id,
                "scope_type": "response_logic",
                "title": heading,
                "body_text": body,
                "referenced_resources": [
                    str(item.get("filename") or "").strip()
                    for item in _collect_resource_entries(heading, body, document_registry=document_registry)
                    if str(item.get("filename") or "").strip()
                ],
            }
        )
        seen_ids.add(scope_id)
    return candidates


def _extract_presentation_policy_hints(markdown: str) -> dict[str, Any]:
    text = str(markdown or "")
    lowered = text.lower()
    return {
        "may_hide_intermediate_outputs": any(token in lowered for token in ("ä¸éœ€è¦é¡¯ç¤º", "ä¸å¿…é¡¯ç¤º", "internal", "hidden", "summary only")),
        "may_show_final_only": any(token in lowered for token in ("åªé¡¯ç¤ºæœ€çµ‚", "final only", "final output only")),
        "may_show_step_summaries": any(token in lowered for token in ("éšŽæ®µæ‘˜è¦", "step summary", "summary")),
    }


def _extract_resource_reference_catalog(
    markdown: str,
    *,
    document_registry: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for unit in _iter_instruction_units(markdown, document_registry=document_registry):
        if not isinstance(unit, dict):
            continue
        heading = str(unit.get("title") or "").strip()
        body = str(unit.get("body") or "").strip()
        for entry in _collect_resource_entries(heading, body, document_registry=document_registry):
            filename = str(entry.get("filename") or "").strip()
            if not filename:
                continue
            key = (filename.lower(), _normalize_section_name(heading))
            if key in seen:
                continue
            catalog.append(
                {
                    "filename": filename,
                    "parsed_filename": str(entry.get("parsed_filename") or filename),
                    "resource_role": str(entry.get("resource_role") or "instruction_source"),
                    "document_id": entry.get("document_id"),
                    "file_status": entry.get("file_status"),
                    "source_heading": heading,
                    "confidence": float(entry.get("confidence") or 0.0),
                }
            )
            seen.add(key)
    return catalog


def _extract_support_modules(
    markdown: str,
    resources: list[InstructionResourceBinding],
    document_registry: dict[str, Any] | None = None,
) -> list[SupportModuleRule]:
    resource_ids_by_filename = {resource.filename: resource.resource_id for resource in resources}
    support_modules: list[SupportModuleRule] = []
    for heading, body in _iter_heading_sections(markdown):
        lower_heading = heading.lower()
        if "\u652f\u63f4\u6a21\u7d44" not in heading and "support module" not in lower_heading:
            continue
        raw_steps = _extract_numbered_steps(body, document_registry=document_registry)
        step_resource_filenames = {
            str(filename).strip()
            for step in raw_steps
            if isinstance(step, dict)
            for filename in step.get("resource_files", []) or []
            if str(filename).strip()
        }
        filenames = [
            str(selected.get("filename") or "")
            for selected in _select_resource_filenames(
                body,
                context_text=f"{heading}\n{body}",
                document_registry=document_registry,
            )
            if str(selected.get("filename") or "").strip() not in step_resource_filenames
        ]
        support_modules.append(
            SupportModuleRule(
                module_id=_slugify_module_title(heading),
                title=heading,
                activation_triggers=_extract_quoted_terms(body),
                resource_ids=[resource_ids_by_filename[name] for name in filenames if name in resource_ids_by_filename],
                referenced_resources=filenames,
                notes=body.splitlines()[0].strip() if body.splitlines() else None,
            )
        )
    return support_modules


def _build_instruction_resources(markdown: str, document_registry: dict[str, Any] | None = None) -> list[InstructionResourceBinding]:
    resources: dict[str, InstructionResourceBinding] = {}

    for workflow in _extract_instruction_workflows(markdown, document_registry=document_registry):
        mode_id = str(workflow.get("id") or "") or None
        workflow_name = str(workflow.get("workflow_name") or "") or None
        for step in workflow.get("steps", []) or []:
            filename = str(step.get("resource_file") or "").strip()
            if not filename:
                continue
            resource_id = Path(filename).stem.lower()
            resource_role = _infer_resource_role(filename, f"{workflow_name or ''}\n{step.get('title') or ''}", "instruction_module")
            matched_document = _resolve_builder_document(filename, document_registry)
            resources[resource_id] = InstructionResourceBinding(
                resource_id=resource_id,
                title=str(step.get("title") or Path(filename).stem.replace("_", " ")),
                filename=filename,
                domain=resource_role,
                document_id=matched_document.get("id") if isinstance(matched_document, dict) else None,
                file_status=matched_document.get("status") if isinstance(matched_document, dict) else None,
                use_type="primary",
                linked_mode_id=mode_id,
                linked_workflow=workflow_name,
                linked_step_order=step.get("order"),
                linked_step_title=step.get("title"),
                source_section_role="workflow_step",
                triggers=_derive_module_keywords(str(step.get("title") or ""), filename),
            )

    for module in _extract_instruction_modules(markdown, document_registry=document_registry):
        filename = str(module.get("primary_resource") or "").strip()
        if not filename:
            continue
        resource_id = Path(filename).stem.lower()
        resource_role = str(module.get("resource_role") or _infer_resource_role(filename, str(module.get("title") or ""), str(module.get("role") or "")))
        existing = resources.get(resource_id)
        if existing is None:
            resources[resource_id] = InstructionResourceBinding(
                resource_id=resource_id,
                title=str(module.get("title") or Path(filename).stem.replace("_", " ")),
                filename=filename,
                domain=resource_role,
                document_id=module.get("document_id"),
                file_status=module.get("file_status"),
                use_type="primary",
                confidence=float(module.get("confidence") or 1.0),
                source_section_role=str(module.get("role") or "") or None,
                activation_signals=[str(item) for item in module.get("activation_signals", []) or []],
                triggers=[str(item) for item in module.get("keywords", []) or []],
            )
        else:
            existing.triggers = sorted({*existing.triggers, *[str(item) for item in module.get("keywords", []) or []]})

    for heading, body in _iter_heading_sections(markdown):
        context_title = heading.strip()
        use_type = "support" if ("\u652f\u63f4\u6a21\u7d44" in heading or "support module" in heading.lower()) else "auxiliary"
        section_role = _classify_section_role(heading, body)
        for entry in _collect_resource_entries(heading, body, document_registry=document_registry):
            filename = str(entry.get("filename") or "")
            confidence = float(entry.get("confidence") or 0.0)
            resource_id = Path(filename).stem.lower()
            if resource_id in resources:
                continue
            resource_role = str(entry.get("resource_role") or _infer_resource_role(filename, f"{heading}\n{body}", section_role))
            resources[resource_id] = InstructionResourceBinding(
                resource_id=resource_id,
                title=context_title or Path(filename).stem.replace("_", " "),
                filename=filename,
                domain=resource_role,
                document_id=entry.get("document_id"),
                file_status=entry.get("file_status"),
                use_type=use_type,
                confidence=confidence,
                description=context_title,
                source_section_role=section_role,
                activation_signals=_extract_activation_signals(body.splitlines()),
            )

    return list(resources.values())


def _build_instruction_runtime_model(markdown: str, document_registry: dict[str, Any] | None = None) -> Dict[str, Any]:
    heading_tree = _build_instruction_heading_tree(markdown)
    workflows = _extract_instruction_workflows(markdown, document_registry=document_registry)
    resources = _build_instruction_resources(markdown, document_registry=document_registry)
    instruction_blocks = _extract_instruction_blocks(markdown, document_registry=document_registry)
    dependency_groups, phase_resource_bindings, block_updates = _build_generic_phase_bindings(
        markdown,
        resources,
        document_registry=document_registry,
    )
    for block in instruction_blocks:
        block_id = str(block.get("block_id") or "").strip()
        if block_id and block_id in block_updates:
            block.update(block_updates[block_id])
    role_summary = _extract_role_summary(markdown)
    primary_objectives = _extract_primary_objectives(markdown)
    behavior_rules = _extract_behavior_rules(markdown)
    mode_rules = _extract_mode_rules(markdown)
    progression_rules = _extract_progression_rules(markdown)
    support_module_rules = _extract_support_modules(markdown, resources, document_registry=document_registry)
    support_module_sections = _extract_support_module_sections(markdown, document_registry=document_registry)
    instruction_service_blocks = _build_instruction_service_blocks(
        workflows,
        support_module_sections,
        heading_tree=heading_tree,
        document_registry=document_registry,
    )
    instruction_procedures, procedure_steps = _build_instruction_procedures(
        workflows,
        instruction_service_blocks,
        support_modules=support_module_sections,
        document_registry=document_registry,
    )
    legacy_support_module_map = {
        str(rule.module_id or "").strip(): rule
        for rule in support_module_rules
        if str(rule.module_id or "").strip()
    }
    support_modules = [
        SupportModuleRule(
            module_id=_slugify_module_title(str(block.get("title") or "")),
            title=str(block.get("title") or "").strip(),
            is_default=bool(block.get("is_default")),
            activation_triggers=[
                str(phrase).strip()
                for condition in block.get("trigger_conditions", []) or []
                if isinstance(condition, dict)
                for phrase in condition.get("phrases", []) or []
                if str(phrase).strip()
            ],
            resource_ids=[
                str(resource_id).strip()
                for resource_id in (
                    legacy_support_module_map.get(_slugify_module_title(str(block.get("title") or "").strip())).resource_ids
                    if legacy_support_module_map.get(_slugify_module_title(str(block.get("title") or "").strip()))
                    else []
                )
                if str(resource_id).strip()
            ],
            referenced_resources=[
                str(item).strip()
                for item in block.get("resource_refs", []) or []
                if str(item).strip()
            ],
            parent_block_id=str(block.get("parent_block_id") or "").strip() or None,
            required_inputs=[
                str(item).strip()
                for item in block.get("required_inputs", []) or []
                if str(item).strip()
            ],
            policy_refs=[
                str(item).strip()
                for item in block.get("policy_refs", []) or []
                if str(item).strip()
            ],
            notes=str(block.get("body_text") or "").strip() or None,
        )
        for block in instruction_service_blocks
        if str(block.get("block_type") or "").strip() == "support_module"
    ]
    if not support_modules:
        support_modules = support_module_rules
    followup_modules = [
        block
        for block in instruction_service_blocks
        if str(block.get("block_type") or "").strip() == "followup_module"
    ]
    global_policies = [
        block
        for block in instruction_service_blocks
        if str(block.get("block_type") or "").strip() == "global_policy"
    ]
    turn_constraints = _extract_turn_constraints(markdown, progression_rules)
    response_policies = _extract_response_policies(markdown)
    global_instruction_context = _build_global_instruction_context(
        role_summary=role_summary,
        primary_objectives=primary_objectives,
        behavior_rules=behavior_rules,
        mode_rules=mode_rules,
        progression_rules=progression_rules,
        support_modules=support_modules,
        turn_constraints=turn_constraints,
        response_policies=response_policies,
    )
    runtime_model = InstructionRuntimeModel(
        role_summary=role_summary,
        primary_objectives=primary_objectives,
        behavior_rules=behavior_rules,
        mode_rules=mode_rules,
        instruction_blocks=instruction_blocks,
        instruction_heading_tree=heading_tree,
        instruction_service_blocks=instruction_service_blocks,
        instruction_procedures=instruction_procedures,
        procedure_steps=procedure_steps,
        progression_rules=progression_rules,
        instruction_resources=resources,
        dependency_groups=dependency_groups,
        phase_resource_bindings=phase_resource_bindings,
        support_modules=support_modules,
        followup_modules=followup_modules,
        global_policies=global_policies,
        turn_constraints=turn_constraints,
        response_policies=response_policies,
        global_instruction_context=global_instruction_context,
    )
    return to_plain_dict(runtime_model)


def run(
    state: GraphState,
    *,
    domains_base_dir: Path = DOMAINS_BASE_DIR,
    prompts_dir: Path = PROMPTS_DIR,
) -> GraphState:
    """Load template registry assets into state.

    Input contract:
    - state["domain"] optional
    - state["template_version"] required (frozen at session create time)

    Output contract:
    - state["template_registry"] with domain JSON assets + prompt templates
    """
    if "template_version" not in state:
        raise ValueError("template_version is required and must be frozen at session level.")

    domain_dir, effective_domain = _resolve_domain_dir(state.get("domain"), base_dir=domains_base_dir)

    existing_registry = dict(state.get("template_registry", {}) or {})
    registry: Dict[str, Any] = {
        **existing_registry,
        "domain": effective_domain,
        "template_version": state["template_version"],
    }

    for filename in DOMAIN_JSON_FILES:
        key = filename.replace(".json", "")
        registry[key] = _load_json_or_empty(domain_dir / filename)

    registry["prompt_templates"] = _load_prompt_templates(prompts_dir=prompts_dir)
    builder_instructions = str(existing_registry.get("builder_instructions") or "")
    full_instruction_text = _load_full_instruction_text(builder_instructions)
    document_registry = _build_builder_document_registry(existing_registry.get("builder_documents", []))
    registry["builder_document_registry"] = {
        "documents": [
            {
                "id": document.get("id"),
                "filename": document.get("filename"),
                "mime_type": document.get("mime_type"),
                "status": document.get("status"),
            }
            for document in document_registry.get("documents", [])
            if isinstance(document, dict)
        ]
    }
    compiled_contract = (
        existing_registry.get("compiled_instruction_understanding")
        if isinstance(existing_registry.get("compiled_instruction_understanding"), dict)
        else {}
    )
    if compiled_contract and compiled_contract.get("instruction_runtime_model"):
        registry, instruction_runtime_model, global_instruction_context, presentation_policy_hints = (
            _apply_compiled_instruction_understanding(
                registry,
                compiled_contract=compiled_contract,
                fallback_instruction_text=builder_instructions,
            )
        )
        full_instruction_text = str(registry.get("full_instruction_text") or full_instruction_text)
        instruction_scope_candidates = list(registry.get("instruction_scope_candidates") or [])
    else:
        instruction_runtime_model = _build_instruction_runtime_model(builder_instructions, document_registry=document_registry)
        instruction_blocks = _extract_instruction_blocks(builder_instructions, document_registry=document_registry)
        instruction_scope_candidates = _extract_instruction_scope_candidates(
            builder_instructions,
            instruction_blocks=instruction_blocks,
            document_registry=document_registry,
        )
        resource_reference_catalog = _extract_resource_reference_catalog(
            builder_instructions,
            document_registry=document_registry,
        )
        presentation_policy_hints = _extract_presentation_policy_hints(builder_instructions)
        global_instruction_context = dict(instruction_runtime_model.get("global_instruction_context") or {})
        registry["full_instruction_text"] = full_instruction_text
        registry["instruction_scope_candidates"] = instruction_scope_candidates
        registry["resource_reference_catalog"] = resource_reference_catalog
        registry["presentation_policy_hints"] = presentation_policy_hints
        registry["instruction_units"] = _iter_instruction_units(builder_instructions, document_registry=document_registry)
        registry["instruction_blocks"] = instruction_blocks
        registry["instruction_modules"] = _extract_instruction_modules(builder_instructions, document_registry=document_registry)
        registry["instruction_workflows"] = _extract_instruction_workflows(builder_instructions, document_registry=document_registry)
        registry["instruction_runtime_model"] = instruction_runtime_model
        registry["instruction_heading_tree"] = instruction_runtime_model.get("instruction_heading_tree", [])
        registry["instruction_service_blocks"] = instruction_runtime_model.get("instruction_service_blocks", [])
        registry["instruction_procedures"] = instruction_runtime_model.get("instruction_procedures", [])
        registry["procedure_steps"] = instruction_runtime_model.get("procedure_steps", [])
        registry["support_modules_v2"] = instruction_runtime_model.get("support_modules", [])
        registry["followup_modules"] = instruction_runtime_model.get("followup_modules", [])
        registry["global_policies"] = instruction_runtime_model.get("global_policies", [])
        registry["global_instruction_context"] = global_instruction_context
    state["template_registry"] = registry
    state["full_instruction_text"] = full_instruction_text
    state["instruction_scope_candidates"] = instruction_scope_candidates
    state["instruction_runtime_model"] = instruction_runtime_model
    state["global_instruction_context"] = global_instruction_context
    state["presentation_policy"] = presentation_policy_hints
    workflow_progress = state.get("workflow_progress", {}) if isinstance(state.get("workflow_progress"), dict) else {}
    existing_session_state = (
        state.get("session_execution_state", {})
        if isinstance(state.get("session_execution_state"), dict)
        else {}
    )
    assembly_state = (
        existing_session_state.get("assembly_state", {})
        if isinstance(existing_session_state.get("assembly_state"), dict)
        else state.get("assembly_state", {})
        if isinstance(state.get("assembly_state"), dict)
        else {}
    )
    state["session_execution_state"] = to_plain_dict(
        SessionExecutionState(
            active_role_id=str(existing_session_state.get("active_role_id") or "") or None,
            active_mode=str(existing_session_state.get("active_mode") or workflow_progress.get("workflow_id") or "") or None,
            active_workflow=str(existing_session_state.get("active_workflow") or workflow_progress.get("workflow_title") or "") or None,
            active_step_order=existing_session_state.get("active_step_order", workflow_progress.get("step_order")),
            active_step_title=str(existing_session_state.get("active_step_title") or workflow_progress.get("step_title") or "") or None,
            active_execution_mode=existing_session_state.get("active_execution_mode"),
            active_bundled_step_ids=[
                str(item).strip()
                for item in existing_session_state.get("active_bundled_step_ids", []) or []
                if str(item).strip()
            ],
            bundled_execution_completed=bool(existing_session_state.get("bundled_execution_completed")),
            bundled_entry_step_id=str(existing_session_state.get("bundled_entry_step_id") or "") or None,
            active_service_block_type=str(existing_session_state.get("active_service_block_type") or "") or None,
            active_service_block_id=str(existing_session_state.get("active_service_block_id") or "") or None,
            active_service_block_title=str(existing_session_state.get("active_service_block_title") or "") or None,
            primary_scope_id=str(existing_session_state.get("primary_scope_id") or "") or None,
            primary_scope_type=str(existing_session_state.get("primary_scope_type") or "") or None,
            primary_scope_title=str(existing_session_state.get("primary_scope_title") or "") or None,
            active_step_scope_id=str(existing_session_state.get("active_step_scope_id") or "") or None,
            primary_support_module_id=str(existing_session_state.get("primary_support_module_id") or "") or None,
            primary_support_module_title=str(existing_session_state.get("primary_support_module_title") or "") or None,
            selected_routing_rule_id=str(existing_session_state.get("selected_routing_rule_id") or "") or None,
            active_module_queue=[
                str(item).strip()
                for item in existing_session_state.get("active_module_queue", []) or []
                if str(item).strip()
            ],
            current_module_index=int(existing_session_state.get("current_module_index") or 0),
            clarification_gate_status=dict(existing_session_state.get("clarification_gate_status") or {}),
            procedure_step_activation=existing_session_state.get("procedure_step_activation"),
            primary_support_module_activation=existing_session_state.get("primary_support_module_activation"),
            execution_status=str(existing_session_state.get("execution_status") or ("guiding" if workflow_progress else "idle")),
            last_input_type=str(existing_session_state.get("last_input_type") or "") or None,
            active_instruction_resources=(
                [
                    str(item).strip()
                    for item in existing_session_state.get("active_instruction_resources", []) or []
                    if str(item).strip()
                ]
                or ([workflow_progress.get("resource_file")] if workflow_progress.get("resource_file") else [])
            ),
            active_support_resources=[
                str(item).strip()
                for item in existing_session_state.get("active_support_resources", []) or []
                if str(item).strip()
            ],
            active_template_resources=[
                str(item).strip()
                for item in existing_session_state.get("active_template_resources", []) or []
                if str(item).strip()
            ],
            active_session_upload_ids=[
                str(item).strip()
                for item in existing_session_state.get("active_session_upload_ids", []) or []
                if str(item).strip()
            ],
            output_artifact_targets=[
                str(item).strip()
                for item in existing_session_state.get("output_artifact_targets", []) or []
                if str(item).strip()
            ],
            pending_prompt_type=str(existing_session_state.get("pending_prompt_type") or "") or None,
            last_turn_action=str(existing_session_state.get("last_turn_action") or "") or None,
            active_scope_ids=[
                str(item).strip()
                for item in existing_session_state.get("active_scope_ids", []) or []
                if str(item).strip()
            ],
            active_binding_ids=[
                str(item).strip()
                for item in existing_session_state.get("active_binding_ids", []) or []
                if str(item).strip()
            ],
            active_dependency_group_ids=[
                str(item).strip()
                for item in existing_session_state.get("active_dependency_group_ids", []) or []
                if str(item).strip()
            ],
            active_artifact_roles=[
                str(item).strip()
                for item in existing_session_state.get("active_artifact_roles", []) or []
                if str(item).strip()
            ],
            artifact_gate_status=dict(existing_session_state.get("artifact_gate_status") or {}),
            intermediate_output_ids=[
                str(item).strip()
                for item in existing_session_state.get("intermediate_output_ids", []) or []
                if str(item).strip()
            ],
            pending_question_ids=[
                str(item).strip()
                for item in existing_session_state.get("pending_question_ids", []) or []
                if str(item).strip()
            ],
            assembly_state=assembly_state,
            workflow_progress=workflow_progress,
        )
    )
    return state

