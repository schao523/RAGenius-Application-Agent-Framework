import json
import sys
import unittest
import uuid
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.chat_repos import InstructionUnderstandingRepo
from backend.app.instruction_understanding_service import (
    INSTRUCTION_UNDERSTANDING_COMPILE_PROMPT,
    INSTRUCTION_UNDERSTANDING_REVIEW_PROMPT,
    _build_hybrid_runtime_model,
    _compile_contract,
    _project_compatibility_instruction_runtime_model,
    _snapshot_fallback_root,
    _hydrate_compiled_from_snapshot,
    approve_instruction_understanding_findings,
    build_instruction_understanding_compiler,
    build_instruction_understanding_reviewer,
    build_instruction_understanding_reviser,
    compile_instruction_understanding,
    compute_instruction_source_hash,
    compute_resource_catalog_hash,
    ensure_compiled_instruction_understanding,
    evaluate_instruction_understanding_cache,
    force_recompile_instruction_understanding,
    force_review_instruction_understanding,
    get_instruction_understanding_status,
    load_instruction_understanding_detail,
    prepare_instruction_understanding,
    revise_instruction_understanding,
    review_instruction_understanding,
    _validate_semantic_compile_candidate,
)


class _StubBuilderStore:
    def __init__(self, root: Path, *, instruction_text: str, documents: list[dict]):
        self.db_path = root / "rag_app.db"
        self.db_path.write_text("", encoding="utf-8")
        self._instruction_text = instruction_text
        self._documents = documents

    def get_instructions(self, app_id: str):
        return {
            "content": self._instruction_text,
            "uri": f"instructions/{app_id}/instructions.md",
            "version": 3,
        }

    def list_documents(self, _app_id: str):
        return list(self._documents)

    def set_instruction_text(self, instruction_text: str) -> None:
        self._instruction_text = instruction_text


class InstructionUnderstandingServiceTests(unittest.TestCase):
    def _tmp_root(self, name: str) -> Path:
        root = Path(__file__).resolve().parent / "_tmp" / name / str(uuid.uuid4())
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _cleanup_root(self, root: Path) -> None:
        if root.exists():
            for path in sorted(root.glob("**/*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()

    def _markdown(self) -> str:
        return """
## Interaction Logic & Execution Flow
### Step 0: Clarification
Ask one clarification question and wait.

## Knowledge Modules
Use template_library.md
Use prompt_design_rules.md
""".strip()

    def _documents(self) -> list[dict]:
        return [
            {
                "id": "doc-1",
                "filename": "template_library.md",
                "mime_type": "text/markdown",
                "status": "ready",
                "file_path": "C:/tmp/template_library.md",
            },
            {
                "id": "doc-2",
                "filename": "prompt_design_rules.md",
                "mime_type": "text/markdown",
                "status": "ready",
                "file_path": "C:/tmp/prompt_design_rules.md",
            },
        ]

    def _markdown_variant(self) -> str:
        return """
## Interaction Logic & Execution Flow
### Step 0: Clarification
Ask two clarification questions and wait.

## Knowledge Modules
Use template_library.md
Use prompt_design_rules.md
""".strip()

    def _church_ministry_markdown(self) -> str:
        return """
## Interaction Logic & Execution Flow
0. Clarify the Ministry Goal
Ask one question to clarify the ministry request before drafting anything.
Use Ministry_Discovery_Questions.md.

1. Confirm the Ministry Constraints
Wait for user confirmation on denomination, audience, and ministry tone.
Use Ministry_Constraint_Checklist.md.

2. Generate the Ministry Prompt Draft
Generate the first structured ministry prompt using Ministry_Prompt_Framework.md.

3. Route the Tool and Module Pair
Route the prompt through the correct tool pair using template_library.md and tool_selection_map.md.

## Optimization Module
Optimize the ministry prompt using dynamic_prompt_optimizer.md and Optimization Strategy Library.md.

4. Validate the Prompt Output
Use ministry_output_rules.md and ministry_prompt_guardrails.md to validate the draft.

5. Finalize the Delivery Package
Assemble the final delivery package using delivery_package_template.md.
""".strip()

    def _church_ministry_documents(self) -> list[dict]:
        filenames = [
            "Ministry_Discovery_Questions.md",
            "Ministry_Constraint_Checklist.md",
            "Ministry_Prompt_Framework.md",
            "template_library.md",
            "dynamic_prompt_optimizer.md",
            "Optimization Strategy Library.md",
            "tool_selection_map.md",
            "ministry_output_rules.md",
            "ministry_prompt_guardrails.md",
            "delivery_package_template.md",
        ]
        return [
            {
                "id": f"doc-{index}",
                "filename": filename,
                "mime_type": "text/markdown",
                "status": "ready",
                "file_path": f"C:/tmp/{filename}",
            }
            for index, filename in enumerate(filenames, start=1)
        ]

    def _grow_with_child_markdown(self) -> str:
        return """
## è§’è‰²èˆ‡ä»»å‹™
ä½ æ˜¯ä¸€ä½å®¶åº­æˆé•·æ•™ç·´ï¼ŒæŒ‰ä½¿ç”¨è€…éœ€è¦åˆ‡æ›åˆé©è§’è‰²èˆ‡èªžæ°£ã€‚

## æ¨¡å¼åˆ¤æ–·è¦å‰‡
å¦‚æžœä½¿ç”¨è€…åªæ˜¯è¦ç°¡å–®å»ºè­°ï¼Œä½¿ç”¨ 3x1 å»ºè­°æ¸…å–®æ³•ã€‚
å¦‚æžœä½¿ç”¨è€…éœ€è¦åˆ†æ­¥é™ªä¼´èˆ‡è¿½å•ï¼Œä½¿ç”¨ æŒ‰æ­¥å°±ç­æ³•ã€‚
å¦‚æžœä½¿ç”¨è€…è¦æ±‚æ·±å…¥åˆ†æžå­©å­è¡Œç‚ºèˆ‡å®¶åº­äº’å‹•ï¼Œä½¿ç”¨ æ·±åº¦è§£æžæ³•ã€‚

## å¤šé‡éœ€æ±‚åˆ†å±¤è¦å‰‡
è‹¥åŒæ™‚æ¶‰åŠæƒ…ç·’ã€ç•Œç·šèˆ‡æºé€šå•é¡Œï¼Œå¯ä¾åºçµ„åˆå¤šå€‹åˆ†æžæ¨¡çµ„ã€‚

## 3x1 å»ºè­°æ¸…å–®æ³•
å…ˆç°¡è¿°å•é¡Œï¼Œå†æä¾›ä¸‰å€‹å»ºè­°èˆ‡ä¸€å€‹ç«‹å³è¡Œå‹•ã€‚
Use advice_checklist.md.

## æŒ‰æ­¥å°±ç­æ³•
å…ˆç¢ºèªå­©å­å¹´é½¡èˆ‡æƒ…å¢ƒï¼Œå†é€æ­¥é™ªä¼´å®¶é•·è™•ç†å•é¡Œã€‚
Use step_by_step_guide.md.

## æ·±åº¦è§£æžæ³•
å¾žå­©å­ç‹€æ…‹ã€çˆ¶æ¯å›žæ‡‰èˆ‡å®¶åº­é—œä¿‚ä¸‰æ–¹é¢æ·±å…¥è§£æžã€‚
Use deep_analysis_framework.md.
Use emotion_signal_map.md.
Use boundary_conversation_prompts.md.
""".strip()

    def _grow_with_child_documents(self) -> list[dict]:
        filenames = [
            "advice_checklist.md",
            "step_by_step_guide.md",
            "deep_analysis_framework.md",
            "emotion_signal_map.md",
            "boundary_conversation_prompts.md",
        ]
        return [
            {
                "id": f"grow-doc-{index}",
                "filename": filename,
                "mime_type": "text/markdown",
                "status": "ready",
                "file_path": f"C:/tmp/{filename}",
            }
            for index, filename in enumerate(filenames, start=1)
        ]

    def _gpt_design_assistant_markdown(self) -> str:
        return """
## Global Mission
å”åŠ©ä½¿ç”¨è€…æŠŠ GPT æ‡‰ç”¨æƒ³æ³•æ•´ç†æˆå¯åŸ·è¡Œçš„è¨­è¨ˆèˆ‡å»ºç½®è¦æ ¼ã€‚

## æ¨¡çµ„èª¿åº¦è¦å‰‡ï¼ˆModule Orchestrationï¼‰
Assistant å¿…é ˆï¼š
1. æ ¹æ“šèªžæ„è‡ªå‹•é¸æ“‡æ¨¡çµ„
2. ä¸ä¾è³´ Starter æ‰èƒ½å•Ÿå‹•
3. å¿…è¦æ™‚ä¸»å‹•å»ºè­°æ¨¡çµ„
4. å¯çµ„åˆå¤šæ¨¡çµ„

ä»»å‹™å°æ‡‰æ¨¡çµ„:
- æ¨¡ç³Šæƒ³æ³• â†’ Use Case Writing Support Module
- æž¶æ§‹è¨­è¨ˆ â†’ MODULE_GENERATOR
- è³‡æºå•é¡Œ â†’ RESOURCE_MANIFEST_SUPPORT
- æ¨¡çµ„è³‡æº â†’ RESOURCE_BINDING
- è¨­å®šå•é¡Œ â†’ Configuration Support Module
- äº’å‹•å•é¡Œ â†’ Interaction Mode Support Module
- æ¸¬è©¦ â†’ Testing & Optimization Support Module

## Use Case Writing Support Module
å”åŠ©æŠŠæ¨¡ç³Šéœ€æ±‚è½‰æˆæ¸…æ¥š use caseã€‚
Use use_case_writing.md.

## MODULE_GENERATOR
æ ¹æ“š use case ç”¢å‡ºæ¨¡çµ„æž¶æ§‹è¨­è¨ˆã€‚
Use module_generator.md.

## RESOURCE_MANIFEST_SUPPORT
æ•´ç†æ‡‰ç”¨æ‰€éœ€è³‡æºèˆ‡ manifestã€‚
Use resource_manifest_support.md.

## RESOURCE_BINDING
æ±ºå®šæ¨¡çµ„èˆ‡è³‡æºå¦‚ä½•ç¶å®šã€‚
Use resource_binding.md.

## Configuration Support Module
è™•ç†è¨­å®šèˆ‡åƒæ•¸å»ºè­°ã€‚
Use configuration_support.md.

## Interaction Mode Support Module
è¨­è¨ˆäº’å‹•æµç¨‹èˆ‡æ¨¡å¼åˆ‡æ›ã€‚
Use interaction_mode_support.md.

## Testing & Optimization Support Module
æª¢æŸ¥æ¸¬è©¦èˆ‡å„ªåŒ–æ–¹å‘ã€‚
Use testing_optimization_support.md.
""".strip()

    def _gpt_design_assistant_documents(self) -> list[dict]:
        filenames = [
            "use_case_writing.md",
            "module_generator.md",
            "resource_manifest_support.md",
            "resource_binding.md",
            "configuration_support.md",
            "interaction_mode_support.md",
            "testing_optimization_support.md",
        ]
        return [
            {
                "id": f"design-doc-{index}",
                "filename": filename,
                "mime_type": "text/markdown",
                "status": "ready",
                "file_path": f"C:/tmp/{filename}",
            }
            for index, filename in enumerate(filenames, start=1)
        ]

    def _bible_tutor_markdown(self) -> str:
        return """
## 模式自動識別（Mode Detection）
根據使用者輸入關鍵字自動辨識並切換教學模式。

## 查經互動模組
1. 細察事實
Use observation_guide.md.

2. 認清關係
Use identify_relationships_guide.md.

## 釋經支援模組
Use 合法處境補充材料.pdf.
""".strip()

    def _bible_tutor_documents(self) -> list[dict]:
        filenames = [
            "observation_guide.md",
            "identify_relationships_guide.md",
            "合法處境補充材料.pdf",
        ]
        mime_types = {
            "pdf": "application/pdf",
            "md": "text/markdown",
        }
        docs: list[dict] = []
        for index, filename in enumerate(filenames, start=1):
            ext = filename.rsplit(".", 1)[-1]
            docs.append(
                {
                    "id": f"bible-doc-{index}",
                    "filename": filename,
                    "mime_type": mime_types.get(ext, "text/plain"),
                    "status": "ready",
                    "file_path": f"C:/tmp/{filename}",
                }
            )
        return docs

    def test_compile_instruction_understanding_persists_record_and_snapshots(self):
        root = self._tmp_root("instruction_understanding_service")
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")
            snapshot_root = root / "snapshots"
            record = compile_instruction_understanding(
                app_id="app-1",
                instruction_text=self._markdown(),
                instruction_uri="instructions/app-1/instructions.md",
                instruction_source_version=3,
                documents=self._documents(),
                repo=repo,
                snapshot_root=snapshot_root,
            )

            active = repo.get_active_compiled("app-1")
            self.assertIsNotNone(active)
            self.assertEqual(active["id"], record["id"])
            self.assertEqual(active["compiled_status"], "ready")
            self.assertTrue(active["compiled_contract"]["instruction_service_blocks"])
            self.assertIn("instruction_runtime_model", active["compiled_contract"])
            self.assertIn("structural_candidate_graph", active["compiled_contract"])
            self.assertTrue(active["compiled_contract"]["section_candidates"])
            self.assertTrue(active["compiled_contract"]["step_candidates"])
            self.assertTrue((snapshot_root / "app-1" / "understanding.json").exists())
            self.assertTrue((snapshot_root / "app-1" / "understanding.md").exists())

            payload = json.loads((snapshot_root / "app-1" / "understanding.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["instruction_source_hash"], record["instruction_source_hash"])
        finally:
            self._cleanup_root(root)

    def test_compile_instruction_understanding_persists_raw_semantic_result_when_missing_model(self):
        root = self._tmp_root("instruction_understanding_raw_semantic")
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")
            record = compile_instruction_understanding(
                app_id="app-1",
                instruction_text=self._markdown(),
                instruction_uri="instructions/app-1/instructions.md",
                instruction_source_version=3,
                documents=self._documents(),
                repo=repo,
                snapshot_root=root / "snapshots",
                semantic_compiler=lambda _context: {},
            )

            semantic_compile = record["compiled_contract"]["semantic_compile"]
            self.assertEqual(semantic_compile["raw_result"], {})
            self.assertIn(
                "semantic compiler payload missing app_semantic_model object",
                semantic_compile["errors"],
            )
            self.assertFalse(semantic_compile["validation"]["valid"])
        finally:
            self._cleanup_root(root)

    def test_compile_instruction_understanding_falls_back_when_snapshot_root_is_unwritable(self):
        root = self._tmp_root("instruction_understanding_snapshot_fallback")
        fallback_dir = (
            Path(__file__).resolve().parents[1]
            / "backend"
            / ".state"
            / "instruction_understanding_snapshots"
            / "app-fallback"
        )
        try:
            snapshot_root = root / "blocked"
            snapshot_root.write_text("not-a-directory", encoding="utf-8")
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")
            record = compile_instruction_understanding(
                app_id="app-fallback",
                instruction_text=self._markdown(),
                instruction_uri="instructions/app-fallback/instructions.md",
                instruction_source_version=3,
                documents=self._documents(),
                repo=repo,
                snapshot_root=snapshot_root,
            )

            self.assertEqual(record["compiled_status"], "ready")
            self.assertTrue((fallback_dir / "understanding.json").exists())
            payload = json.loads((fallback_dir / "understanding.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["id"], record["id"])
        finally:
            if fallback_dir.exists():
                for path in sorted(fallback_dir.glob("**/*"), reverse=True):
                    if path.is_file():
                        path.unlink()
                    elif path.is_dir():
                        path.rmdir()
                if fallback_dir.exists():
                    fallback_dir.rmdir()
            self._cleanup_root(root)

    def test_cache_evaluation_marks_stale_inputs(self):
        active_record = {
            "instruction_source_hash": "hash-a",
            "parser_contract_version": "parser-a",
            "binding_logic_version": "binding-a",
            "resource_catalog_hash": "docs-a",
            "compiled_status": "ready",
        }
        stale = evaluate_instruction_understanding_cache(
            active_record,
            instruction_source_hash="hash-b",
            parser_contract_version="parser-a",
            binding_logic_version="binding-a",
            resource_catalog_hash="docs-a",
        )
        self.assertEqual(stale["cache_status"], "stale_instructions")
        self.assertEqual(stale["stale_reasons"], ["instruction_source_hash"])

    def test_ensure_compiled_instruction_understanding_reuses_hot_record(self):
        root = self._tmp_root("instruction_understanding_service")
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")
            store = _StubBuilderStore(root, instruction_text=self._markdown(), documents=self._documents())
            first = ensure_compiled_instruction_understanding(
                app_id="app-1",
                builder_store=store,
                repo=repo,
                snapshot_root=root / "snapshots",
            )
            second = ensure_compiled_instruction_understanding(
                app_id="app-1",
                builder_store=store,
                repo=repo,
                snapshot_root=root / "snapshots",
            )

            self.assertEqual(first["record"]["id"], second["record"]["id"])
            self.assertEqual(second["cache_status"], "hot")
            self.assertEqual(second["stale_reasons"], [])
        finally:
            self._cleanup_root(root)

    def test_review_and_status_surface_are_persisted(self):
        root = self._tmp_root("instruction_understanding_service")
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")
            store = _StubBuilderStore(root, instruction_text=self._markdown(), documents=self._documents())
            compiled = ensure_compiled_instruction_understanding(
                app_id="app-1",
                builder_store=store,
                repo=repo,
                snapshot_root=root / "snapshots",
            )["record"]

            review = review_instruction_understanding(
                app_id="app-1",
                compiled_record=compiled,
                repo=repo,
                reviewer=lambda record: {
                    "review_status": "reviewed_with_warnings",
                    "review_confidence": 0.61,
                    "review_findings": {"warnings": ["Check trigger specificity"]},
                    "review_summary_md": "# Review\n\nWarning present.\n",
                    "review_recommendations": {"next_step": "manual review"},
                },
                review_model="fake-reviewer",
            )
            status = get_instruction_understanding_status(
                app_id="app-1",
                builder_store=store,
                repo=repo,
            )

            self.assertEqual(review["review_status"], "reviewed_with_warnings")
            self.assertEqual(status["cache_status"], "hot")
            self.assertEqual(status["review_status"], "reviewed_with_warnings")
            self.assertEqual(status["compiled_status"], "ready")
        finally:
            self._cleanup_root(root)

    def test_prepare_instruction_understanding_runs_auto_review_only_when_compile_changes(self):
        root = self._tmp_root("instruction_understanding_service")
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")
            instructions = {
                "content": self._markdown(),
                "uri": "instructions/app-1/instructions.md",
                "version": 3,
            }
            review_calls = []

            def reviewer(record):
                review_calls.append(record["instruction_source_hash"])
                return {
                    "review_status": "reviewed_ok",
                    "review_confidence": 0.8,
                    "review_findings": {"ok": True},
                    "review_summary_md": "# Review\n",
                    "review_recommendations": {"action": "none"},
                }

            first = prepare_instruction_understanding(
                app_id="app-1",
                instructions=instructions,
                documents=self._documents(),
                repo=repo,
                snapshot_root=root / "snapshots",
                reviewer=reviewer,
                review_model="fake-reviewer",
            )
            second = prepare_instruction_understanding(
                app_id="app-1",
                instructions=instructions,
                documents=self._documents(),
                repo=repo,
                snapshot_root=root / "snapshots",
                reviewer=reviewer,
                review_model="fake-reviewer",
            )

            self.assertEqual(first["status"]["review_status"], "reviewed_ok")
            self.assertEqual(second["status"]["cache_status"], "hot")
            self.assertEqual(second["status"]["review_status"], "reviewed_ok")
            self.assertEqual(len(review_calls), 1)
        finally:
            self._cleanup_root(root)

    def test_prepare_instruction_understanding_recompiles_when_semantic_compiler_version_changes(self):
        root = self._tmp_root("instruction_understanding_semantic_cache")
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")
            instructions = {
                "content": self._markdown(),
                "uri": "instructions/app-1/instructions.md",
                "version": 3,
            }

            def semantic_compiler(_context):
                return {
                    "app_semantic_model": {
                        "primary_service_mode": "single_default_workflow",
                        "default_workflow_id": "workflow:default",
                        "service_blocks": [
                            {
                                "block_id": "workflow:default",
                                "block_type": "primary_workflow",
                                "title": "Interaction Logic & Execution Flow",
                                "is_default": True,
                            }
                        ],
                        "procedures": [],
                        "procedure_steps": [],
                        "role_profiles": [],
                        "routing_rules": [],
                        "clarification_gate_rules": [],
                    }
                }

            first = prepare_instruction_understanding(
                app_id="app-1",
                instructions=instructions,
                documents=self._documents(),
                repo=repo,
                snapshot_root=root / "snapshots",
                semantic_compiler=semantic_compiler,
                semantic_compiler_version="semantic-v1",
            )
            second = prepare_instruction_understanding(
                app_id="app-1",
                instructions=instructions,
                documents=self._documents(),
                repo=repo,
                snapshot_root=root / "snapshots",
                semantic_compiler=semantic_compiler,
                semantic_compiler_version="semantic-v2",
            )

            self.assertEqual(first["cache_status"], "hot")
            self.assertEqual(second["cache_status"], "hot")
            self.assertNotEqual(first["record"]["id"], second["record"]["id"])
            self.assertEqual(
                second["record"]["compiled_contract"]["semantic_compile"]["semantic_compiler_version"],
                "semantic-v2",
            )
        finally:
            self._cleanup_root(root)

    def test_load_instruction_understanding_detail_returns_compiled_and_review_sections(self):
        root = self._tmp_root("instruction_understanding_service")
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")
            store = _StubBuilderStore(root, instruction_text=self._markdown(), documents=self._documents())
            compiled = ensure_compiled_instruction_understanding(
                app_id="app-1",
                builder_store=store,
                repo=repo,
                snapshot_root=root / "snapshots",
            )["record"]
            review = review_instruction_understanding(
                app_id="app-1",
                compiled_record=compiled,
                repo=repo,
                reviewer=lambda _record: {
                    "review_status": "reviewed_ok",
                    "review_confidence": 0.91,
                    "review_findings": {"ok": True},
                    "review_summary_md": "# Review\n\nLooks good.\n",
                    "review_recommendations": {"action": "none"},
                },
            )

            detail = load_instruction_understanding_detail(
                app_id="app-1",
                builder_store=store,
                repo=repo,
            )

            self.assertEqual(detail["app_id"], "app-1")
            self.assertEqual(detail["compiled"]["id"], compiled["id"])
            self.assertEqual(detail["review"]["id"], review["id"])
            self.assertEqual(detail["status"]["compiled_status"], "ready")
            self.assertEqual(detail["status"]["review_status"], "reviewed_ok")
        finally:
            self._cleanup_root(root)

    def test_force_review_instruction_understanding_raises_when_no_reviewer(self):
        root = self._tmp_root("instruction_understanding_service")
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")
            store = _StubBuilderStore(root, instruction_text=self._markdown(), documents=self._documents())
            ensure_compiled_instruction_understanding(
                app_id="app-1",
                builder_store=store,
                repo=repo,
                snapshot_root=root / "snapshots",
            )

            with self.assertRaisesRegex(ValueError, "reviewer"):
                force_review_instruction_understanding(
                    app_id="app-1",
                    builder_store=store,
                    repo=repo,
                    reviewer=None,
                )
        finally:
            self._cleanup_root(root)

    def test_force_recompile_instruction_understanding_can_be_called_directly(self):
        root = self._tmp_root("instruction_understanding_service")
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")
            store = _StubBuilderStore(root, instruction_text=self._markdown(), documents=self._documents())
            result = force_recompile_instruction_understanding(
                app_id="app-1",
                builder_store=store,
                repo=repo,
                snapshot_root=root / "snapshots",
            )

            self.assertEqual(result["record"]["compiled_status"], "ready")
            self.assertEqual(result["cache_status"], "recompiled")
            self.assertEqual(result["stale_reasons"], ["forced_recompile"])
            self.assertTrue(result["record"]["compiled_contract"]["instruction_service_blocks"])
        finally:
            self._cleanup_root(root)

    def test_force_recompile_instruction_understanding_returns_active_valid_record_when_new_semantic_attempt_is_invalid(self):
        root = self._tmp_root("instruction_understanding_service")
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")
            store = _StubBuilderStore(root, instruction_text=self._markdown(), documents=self._documents())
            first = force_recompile_instruction_understanding(
                app_id="app-1",
                builder_store=store,
                repo=repo,
                snapshot_root=root / "snapshots",
                semantic_compiler=lambda _context: {
                    "app_semantic_model": {
                        "primary_service_mode": "single_default_workflow",
                        "default_workflow_id": "workflow:default",
                        "service_blocks": [
                            {
                                "block_id": "workflow:default",
                                "block_type": "primary_workflow",
                                "title": "Interaction Logic & Execution Flow",
                                "is_default": True,
                            }
                        ],
                        "procedures": [],
                        "procedure_steps": [],
                        "role_profiles": [],
                        "routing_rules": [],
                        "clarification_gate_rules": [],
                    }
                },
            )
            second = force_recompile_instruction_understanding(
                app_id="app-1",
                builder_store=store,
                repo=repo,
                snapshot_root=root / "snapshots",
                semantic_compiler=lambda _context: {},
            )

            self.assertEqual(second["record"]["id"], first["record"]["id"])
            self.assertIn("attempt_record", second)
            self.assertFalse(second["attempt_record"]["is_active"])
            self.assertEqual(second["attempt_record"]["metadata"]["publish_status"], "diagnostic_only")
            self.assertEqual(second["status"]["compiled_status"], "ready")
        finally:
            self._cleanup_root(root)

    def test_recompile_without_reviewer_does_not_surface_stale_prior_review_as_current(self):
        root = self._tmp_root("instruction_understanding_service")
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")
            store = _StubBuilderStore(root, instruction_text=self._markdown(), documents=self._documents())
            first = prepare_instruction_understanding(
                app_id="app-1",
                instructions=store.get_instructions("app-1"),
                documents=store.list_documents("app-1"),
                repo=repo,
                snapshot_root=root / "snapshots",
                reviewer=lambda _record: {
                    "review_status": "reviewed_ok",
                    "review_confidence": 0.88,
                    "review_findings": {"ok": True},
                    "review_summary_md": "# Review\n",
                    "review_recommendations": {"action": "none"},
                },
            )

            store.set_instruction_text(self._markdown_variant())
            second = prepare_instruction_understanding(
                app_id="app-1",
                instructions=store.get_instructions("app-1"),
                documents=store.list_documents("app-1"),
                repo=repo,
                snapshot_root=root / "snapshots",
                reviewer=None,
            )
            detail = load_instruction_understanding_detail(
                app_id="app-1",
                builder_store=store,
                repo=repo,
            )

            self.assertEqual(first["status"]["review_status"], "reviewed_ok")
            self.assertEqual(second["status"]["compiled_status"], "ready")
            self.assertEqual(second["status"]["review_status"], "not_reviewed")
            self.assertIsNone(second["review"])
            self.assertNotEqual(first["record"]["instruction_source_hash"], second["record"]["instruction_source_hash"])
            self.assertEqual(detail["status"]["review_status"], "not_reviewed")
            self.assertIsNone(detail["review"])
        finally:
            self._cleanup_root(root)

    def test_resource_catalog_recompile_without_reviewer_does_not_surface_stale_prior_review(self):
        root = self._tmp_root("instruction_understanding_service")
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")
            store = _StubBuilderStore(root, instruction_text=self._markdown(), documents=self._documents())
            first = prepare_instruction_understanding(
                app_id="app-1",
                instructions=store.get_instructions("app-1"),
                documents=store.list_documents("app-1"),
                repo=repo,
                snapshot_root=root / "snapshots",
                reviewer=lambda _record: {
                    "review_status": "reviewed_ok",
                    "review_confidence": 0.82,
                    "review_findings": {"ok": True},
                    "review_summary_md": "# Review\n",
                    "review_recommendations": {"action": "none"},
                },
            )
            mutated_documents = self._documents() + [
                {
                    "id": "doc-3",
                    "filename": "resource_map.md",
                    "mime_type": "text/markdown",
                    "status": "ready",
                    "file_path": "C:/tmp/resource_map.md",
                }
            ]
            second = prepare_instruction_understanding(
                app_id="app-1",
                instructions=store.get_instructions("app-1"),
                documents=mutated_documents,
                repo=repo,
                snapshot_root=root / "snapshots",
                reviewer=None,
            )

            self.assertEqual(first["status"]["review_status"], "reviewed_ok")
            self.assertEqual(second["status"]["compiled_status"], "ready")
            self.assertEqual(second["status"]["review_status"], "not_reviewed")
            self.assertIsNone(second["review"])
            self.assertNotEqual(
                first["status"]["resource_catalog_hash"],
                second["status"]["resource_catalog_hash"],
            )
        finally:
            self._cleanup_root(root)

    def test_binding_logic_recompile_without_reviewer_does_not_surface_stale_prior_review(self):
        root = self._tmp_root("instruction_understanding_service")
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")
            store = _StubBuilderStore(root, instruction_text=self._markdown(), documents=self._documents())
            first = prepare_instruction_understanding(
                app_id="app-1",
                instructions=store.get_instructions("app-1"),
                documents=store.list_documents("app-1"),
                repo=repo,
                snapshot_root=root / "snapshots",
                binding_logic_version="binding-logic-a",
                reviewer=lambda _record: {
                    "review_status": "reviewed_ok",
                    "review_confidence": 0.84,
                    "review_findings": {"ok": True},
                    "review_summary_md": "# Review\n",
                    "review_recommendations": {"action": "none"},
                },
            )
            second = prepare_instruction_understanding(
                app_id="app-1",
                instructions=store.get_instructions("app-1"),
                documents=store.list_documents("app-1"),
                repo=repo,
                snapshot_root=root / "snapshots",
                binding_logic_version="binding-logic-b",
                reviewer=None,
            )

            self.assertEqual(first["status"]["review_status"], "reviewed_ok")
            self.assertEqual(second["status"]["compiled_status"], "ready")
            self.assertEqual(second["status"]["review_status"], "not_reviewed")
            self.assertIsNone(second["review"])
            self.assertEqual(
                first["status"]["instruction_source_hash"],
                second["status"]["instruction_source_hash"],
            )
            self.assertEqual(
                first["status"]["parser_contract_version"],
                second["status"]["parser_contract_version"],
            )
            self.assertNotEqual(
                first["status"]["binding_logic_version"],
                second["status"]["binding_logic_version"],
            )
        finally:
            self._cleanup_root(root)

    def test_malformed_reviewer_output_does_not_persist_reviewed_ok(self):
        root = self._tmp_root("instruction_understanding_service")
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")
            store = _StubBuilderStore(root, instruction_text=self._markdown(), documents=self._documents())
            compiled = ensure_compiled_instruction_understanding(
                app_id="app-1",
                builder_store=store,
                repo=repo,
                snapshot_root=root / "snapshots",
            )["record"]

            review = review_instruction_understanding(
                app_id="app-1",
                compiled_record=compiled,
                repo=repo,
                reviewer=lambda _record: "not-a-dict",
            )
            detail = load_instruction_understanding_detail(
                app_id="app-1",
                builder_store=store,
                repo=repo,
            )

            self.assertEqual(review["review_status"], "review_failed")
            self.assertEqual(detail["status"]["review_status"], "review_failed")
            self.assertEqual(detail["review"]["review_status"], "review_failed")
        finally:
            self._cleanup_root(root)

    def test_build_instruction_understanding_reviewer_uses_llm_task_callable_when_available(self):
        state = {"config_json": {"meta": {"llm_settings": {"provider": "deepseek", "model": "x"}}}}

        def fake_llm(prompt, tools, context):
            self.assertIn("compiled understanding of application instructions", prompt)
            self.assertEqual(tools[0]["name"], "create_instruction_understanding_review")
            self.assertIn("compiled_contract", context)
            return {
                "review_status": "reviewed_with_warnings",
                "review_confidence": 0.55,
                "review_findings": {"warnings": ["ambiguous trigger"]},
                "review_summary_md": "# Review\n",
                "review_recommendations": {"next_step": "inspect"},
            }

        with mock.patch(
            "backend.app.instruction_understanding_service.maybe_build_task_callable",
            side_effect=lambda _state, task: fake_llm if task == "instruction_understanding_review" else None,
        ):
            reviewer = build_instruction_understanding_reviewer(state)

        self.assertIsNotNone(reviewer)
        result = reviewer({"compiled_contract": {}, "metadata": {}, "app_id": "app-1"})
        self.assertEqual(result["review_status"], "reviewed_with_warnings")

    def test_build_instruction_understanding_compiler_uses_llm_task_callable_when_available(self):
        state = {"config_json": {"meta": {"llm_settings": {"provider": "deepseek", "model": "x"}}}}

        def fake_llm(prompt, tools, context):
            self.assertIn("compiling semantic application understanding", prompt)
            self.assertEqual(tools[0]["name"], "create_instruction_understanding_compile")
            self.assertIn("structural_candidate_graph", context)
            return {
                "app_semantic_model": {
                    "primary_service_mode": "single_default_workflow",
                    "default_workflow_id": "workflow:default",
                    "service_blocks": [
                        {"block_id": "workflow:default", "block_type": "primary_workflow", "is_default": True}
                    ],
                    "procedures": [],
                    "procedure_steps": [],
                    "role_profiles": [],
                    "routing_rules": [],
                    "clarification_gate_rules": [],
                }
            }

        with mock.patch(
            "backend.app.instruction_understanding_service.maybe_build_task_callable",
            side_effect=lambda _state, task: fake_llm if task == "instruction_understanding_compile" else None,
        ):
            compiler = build_instruction_understanding_compiler(state)

        self.assertIsNotNone(compiler)
        result = compiler({"structural_candidate_graph": {}, "resource_reference_catalog": []})
        self.assertEqual(result["app_semantic_model"]["default_workflow_id"], "workflow:default")

    def test_build_instruction_understanding_reviewer_prompt_calls_out_known_failure_modes(self):
        self.assertIn("false trigger extraction", INSTRUCTION_UNDERSTANDING_REVIEW_PROMPT)
        self.assertIn("phantom resources", INSTRUCTION_UNDERSTANDING_REVIEW_PROMPT)
        self.assertIn("default-workflow assumptions", INSTRUCTION_UNDERSTANDING_REVIEW_PROMPT)
        self.assertIn("examples, illustrations, or body text", INSTRUCTION_UNDERSTANDING_REVIEW_PROMPT)

    def test_build_instruction_understanding_compile_prompt_requires_executable_targets(self):
        self.assertIn("routing path must resolve to executable workflow or module targets", INSTRUCTION_UNDERSTANDING_COMPILE_PROMPT)
        self.assertIn("role must point to concrete executable workflows or modules", INSTRUCTION_UNDERSTANDING_COMPILE_PROMPT)

    def test_compile_instruction_understanding_attaches_semantic_compile_when_compiler_present(self):
        root = self._tmp_root("instruction_understanding_semantic_compile")
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")
            record = compile_instruction_understanding(
                app_id="app-1",
                instruction_text=self._markdown(),
                instruction_uri="instructions/app-1/instructions.md",
                instruction_source_version=3,
                documents=self._documents(),
                repo=repo,
                snapshot_root=root / "snapshots",
                semantic_compiler=lambda context: {
                    "app_semantic_model": {
                        "primary_service_mode": "single_default_workflow",
                        "default_workflow_id": "workflow:church-default",
                        "global_app_contract": {"mission": "Help users design prompts"},
                        "interaction_logic_blocks": [],
                        "role_profiles": [],
                        "routing_rules": [],
                        "module_orchestration": None,
                        "service_blocks": [
                            {
                                "block_id": "workflow:church-default",
                                "block_type": "primary_workflow",
                                "title": "Interaction Logic & Execution Flow",
                                "is_default": True,
                            }
                        ],
                        "procedures": [],
                        "procedure_steps": [],
                        "clarification_gate_rules": [],
                        "resource_bindings": [],
                        "semantic_warnings": [],
                        "semantic_confidence": 0.8,
                    }
                },
            )
            self.assertTrue(record["metadata"]["semantic_compile_attached"])
            self.assertIn("semantic_compile", record["compiled_contract"])
            self.assertIn("hybrid_instruction_runtime_model", record["compiled_contract"])
            self.assertEqual(
                record["compiled_contract"]["hybrid_instruction_runtime_model"]["default_workflow_id"],
                "workflow:church-default",
            )
        finally:
            self._cleanup_root(root)

    def test_compile_instruction_understanding_persists_diagnostic_attempt_when_semantic_compiler_raises(self):
        root = self._tmp_root("instruction_understanding_semantic_compile_exception")
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")

            def semantic_compiler(_context):
                raise RuntimeError("LLM response contained no text content.")

            record = compile_instruction_understanding(
                app_id="app-1",
                instruction_text=self._markdown(),
                instruction_uri="instructions/app-1/instructions.md",
                instruction_source_version=3,
                documents=self._documents(),
                repo=repo,
                snapshot_root=root / "snapshots",
                semantic_compiler=semantic_compiler,
            )

            semantic_compile = record["compiled_contract"]["semantic_compile"]
            self.assertEqual(record["metadata"]["publish_status"], "diagnostic_only")
            self.assertFalse(record["is_active"])
            self.assertTrue(record["metadata"]["semantic_compile_attached"])
            self.assertFalse(record["metadata"]["semantic_compile_valid"])
            self.assertIn("semantic compiler call failed", semantic_compile["errors"][0])
            self.assertIn("LLM response contained no text content.", semantic_compile["errors"][0])
            self.assertFalse(semantic_compile["validation"]["valid"])
        finally:
            self._cleanup_root(root)

    def test_force_recompile_instruction_understanding_keeps_prior_active_when_semantic_compiler_raises(self):
        root = self._tmp_root("instruction_understanding_force_recompile_exception")
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")
            builder_store = _StubBuilderStore(root, instruction_text=self._markdown(), documents=self._documents())

            first = force_recompile_instruction_understanding(
                app_id="app-1",
                builder_store=builder_store,
                repo=repo,
                snapshot_root=root / "snapshots",
                semantic_compiler=lambda _context: {
                    "app_semantic_model": {
                        "primary_service_mode": "single_default_workflow",
                        "default_workflow_id": "workflow:default",
                        "service_blocks": [
                            {
                                "block_id": "workflow:default",
                                "block_type": "primary_workflow",
                                "title": "Interaction Logic & Execution Flow",
                                "is_default": True,
                            }
                        ],
                        "procedures": [],
                        "procedure_steps": [],
                        "role_profiles": [],
                        "routing_rules": [],
                        "clarification_gate_rules": [],
                    }
                },
            )
            active_before = first["record"]

            second = force_recompile_instruction_understanding(
                app_id="app-1",
                builder_store=builder_store,
                repo=repo,
                snapshot_root=root / "snapshots",
                semantic_compiler=lambda _context: (_ for _ in ()).throw(
                    RuntimeError("LLM response contained no text content.")
                ),
            )

            self.assertEqual(second["record"]["id"], active_before["id"])
            self.assertIsNotNone(second["attempt_record"])
            self.assertEqual(second["attempt_record"]["metadata"]["publish_status"], "diagnostic_only")
            self.assertFalse(second["attempt_record"]["metadata"]["semantic_compile_valid"])
            self.assertIn(
                "semantic compiler call failed",
                second["attempt_record"]["compiled_contract"]["semantic_compile"]["errors"][0],
            )
        finally:
            self._cleanup_root(root)

    def test_compile_instruction_understanding_filters_phantom_resource_catalog_entries_before_semantic_context(self):
        root = self._tmp_root("instruction_understanding_phantom_resources")
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")
            seen_context = {}

            def semantic_compiler(context):
                seen_context["resource_reference_catalog"] = list(context.get("resource_reference_catalog", []))
                return {
                    "app_semantic_model": {
                        "primary_service_mode": "single_default_workflow",
                        "default_workflow_id": "workflow:default",
                        "service_blocks": [
                            {
                                "block_id": "workflow:default",
                                "block_type": "primary_workflow",
                                "title": "Interaction Logic & Execution Flow",
                                "is_default": True,
                            }
                        ],
                        "procedures": [],
                        "procedure_steps": [],
                        "role_profiles": [],
                        "routing_rules": [],
                        "clarification_gate_rules": [],
                    }
                }

            record = compile_instruction_understanding(
                app_id="app-1",
                instruction_text=self._markdown(),
                instruction_uri="instructions/app-1/instructions.md",
                instruction_source_version=3,
                documents=self._documents()
                + [
                    {
                        "id": "doc-phantom",
                        "filename": "",
                        "mime_type": "application/pdf",
                        "status": "ready",
                        "file_path": "C:/tmp/phantom.pdf",
                    }
                ],
                repo=repo,
                snapshot_root=root / "snapshots",
                semantic_compiler=semantic_compiler,
            )

            filenames = {
                str(item.get("filename") or "").strip()
                for item in seen_context["resource_reference_catalog"]
                if isinstance(item, dict)
            }
            self.assertNotIn("", filenames)
            self.assertTrue(record["compiled_contract"]["resource_reference_catalog"])
        finally:
            self._cleanup_root(root)

    def test_validate_semantic_compile_candidate_accepts_intent_routed_multi_workflow_without_default(self):
        deterministic_contract = {
            "resource_reference_catalog": [],
        }
        semantic_model = {
            "primary_service_mode": "intent_routed_multi_workflow",
            "default_workflow_id": None,
            "service_blocks": [
                {"block_id": "workflow:advice", "block_type": "primary_workflow", "title": "Advice"},
                {"block_id": "workflow:bible", "block_type": "primary_workflow", "title": "Bible Study"},
                {"block_id": "module:checklist", "block_type": "support_module", "title": "Checklist"},
            ],
            "procedures": [],
            "procedure_steps": [],
            "role_profiles": [
                {
                    "role_id": "role:mentor",
                    "name": "Mentor",
                    "target_workflow_ids": ["workflow:advice"],
                    "allowed_module_ids": ["module:checklist"],
                }
            ],
            "routing_rules": [
                {
                    "rule_id": "rule:advice",
                    "target_workflow_id": "workflow:advice",
                    "target_role_id": "role:mentor",
                    "target_module_ids": ["module:checklist"],
                }
            ],
            "module_orchestration": {
                "composition_mode": "ordered_sequential",
                "task_module_mappings": [
                    {
                        "mapping_id": "map:1",
                        "target_module_ids": ["module:checklist"],
                    }
                ],
            },
            "clarification_gate_rules": [],
        }

        validation = _validate_semantic_compile_candidate(
            semantic_model=semantic_model,
            deterministic_contract=deterministic_contract,
        )

        self.assertTrue(validation["valid"])
        self.assertEqual(validation["normalized"]["primary_service_mode"], "intent_routed_multi_workflow")
        self.assertIsNone(validation["normalized"]["default_workflow_id"])

    def test_validate_semantic_compile_candidate_rejects_missing_routing_rules_for_intent_routed_app(self):
        validation = _validate_semantic_compile_candidate(
            semantic_model={
                "primary_service_mode": "intent_routed_multi_workflow",
                "service_blocks": [
                    {"block_id": "workflow:advice", "block_type": "primary_workflow", "title": "Advice"},
                ],
                "procedures": [],
                "procedure_steps": [],
                "role_profiles": [],
                "routing_rules": [],
                "clarification_gate_rules": [],
            },
            deterministic_contract={"resource_reference_catalog": []},
        )

        self.assertFalse(validation["valid"])
        self.assertIn("intent_routed_multi_workflow requires routing_rules", validation["errors"])

    def test_validate_semantic_compile_candidate_accepts_intent_routed_interaction_logic_without_primary_workflow_or_steps(self):
        validation = _validate_semantic_compile_candidate(
            semantic_model={
                "primary_service_mode": "intent_routed_interaction_logic",
                "service_blocks": [],
                "procedures": [],
                "procedure_steps": [],
                "role_profiles": [
                    {
                        "role_id": "role:partner",
                        "name": "Partner",
                    }
                ],
                "routing_rules": [
                    {
                        "rule_id": "route:partner",
                        "target_role_id": "role:partner",
                    }
                ],
                "interaction_logic_blocks": [
                    {
                        "block_id": "logic:partner_mode",
                        "title": "五重角色模式",
                        "entry_response_contract": {
                            "opening_prompt": "Use partner tone and select the appropriate interaction mode."
                        },
                    },
                    {
                        "block_id": "logic:layered_rules",
                        "title": "多重需求分層規則",
                        "body_text": "Handle layered parenting needs through rule-based role switching.",
                    },
                ],
                "clarification_gate_rules": [],
            },
            deterministic_contract={"resource_reference_catalog": []},
        )

        self.assertTrue(validation["valid"], validation["errors"])
        self.assertEqual(
            validation["normalized"]["primary_service_mode"],
            "intent_routed_interaction_logic",
        )

    def test_validate_semantic_compile_candidate_rejects_intent_routed_interaction_logic_without_routing_or_logic(self):
        validation = _validate_semantic_compile_candidate(
            semantic_model={
                "primary_service_mode": "intent_routed_interaction_logic",
                "service_blocks": [],
                "procedures": [],
                "procedure_steps": [],
                "role_profiles": [],
                "routing_rules": [],
                "interaction_logic_blocks": [],
                "clarification_gate_rules": [],
            },
            deterministic_contract={"resource_reference_catalog": []},
        )

        self.assertFalse(validation["valid"])
        self.assertIn(
            "intent_routed_interaction_logic requires routing_rules or interaction_logic_blocks",
            validation["errors"],
        )

    def test_validate_semantic_compile_candidate_accepts_logic_routed_parenting_shape_without_top_level_executable_steps(self):
        semantic_model = {
            "primary_service_mode": "intent_routed_interaction_logic",
            "service_blocks": [
                {
                    "block_id": "workflow:按步就班法",
                    "block_type": "primary_workflow",
                    "title": "按步就班法流程",
                },
                {
                    "block_id": "module:bible_study",
                    "block_type": "support_module",
                    "title": "查經互動模組",
                },
            ],
            "procedures": [],
            "procedure_steps": [],
            "role_profiles": [
                {
                    "role_id": "role:partner",
                    "name": "Partner",
                    "target_workflow_ids": ["workflow:按步就班法"],
                    "allowed_module_ids": ["module:bible_study"],
                }
            ],
            "routing_rules": [
                {
                    "rule_id": "route:partner",
                    "target_role_id": "role:partner",
                    "target_workflow_id": "workflow:按步就班法",
                },
                {
                    "rule_id": "route:scripture",
                    "target_module_id": "module:bible_study",
                },
            ],
            "interaction_logic_blocks": [
                {
                    "block_id": "logic:roles",
                    "title": "五重角色模式",
                    "body_text": "Partner uses 按步就班法流程 + 行動提醒延伸 for 親子靈修 support.",
                },
                {
                    "block_id": "logic:switching",
                    "title": "模式切換邏輯",
                    "body_text": "Route by use case and role fit rather than forcing workflow execution.",
                },
                {
                    "block_id": "logic:layered",
                    "title": "多重需求分層規則",
                    "body_text": "Use layered routing rules to select the correct role or module.",
                },
            ],
            "clarification_gate_rules": [],
        }

        validation = _validate_semantic_compile_candidate(
            semantic_model=semantic_model,
            deterministic_contract={"resource_reference_catalog": []},
        )

        self.assertTrue(validation["valid"], validation["errors"])
        self.assertEqual(
            validation["normalized"]["primary_service_mode"],
            "intent_routed_interaction_logic",
        )

    def test_validate_semantic_compile_candidate_rejects_role_routed_app_without_executable_targets(self):
        validation = _validate_semantic_compile_candidate(
            semantic_model={
                "primary_service_mode": "intent_routed_multi_workflow",
                "service_blocks": [
                    {
                        "block_id": "wf_multi_layer_response",
                        "block_type": "primary_workflow",
                        "title": "å¤šé‡éœ€æ±‚åˆ†å±¤è¦å‰‡",
                        "is_default": True,
                    }
                ],
                "procedures": [
                    {
                        "procedure_id": "wf_multi_layer_response",
                        "service_block_id": "wf_multi_layer_response",
                        "title": "å¤šé‡éœ€æ±‚åˆ†å±¤è¦å‰‡",
                    }
                ],
                "procedure_steps": [],
                "role_profiles": [
                    {
                        "role_id": "role:mentor",
                        "name": "Mentor",
                    }
                ],
                "routing_rules": [
                    {
                        "rule_id": "route_to_mentor",
                        "target_role_id": "role:mentor",
                    }
                ],
                "clarification_gate_rules": [],
            },
            deterministic_contract={"resource_reference_catalog": []},
        )

        self.assertFalse(validation["valid"])
        self.assertIn(
            "intent_routed_multi_workflow routing rules must resolve to executable workflow or module targets",
            validation["errors"],
        )
        self.assertIn(
            "intent_routed_multi_workflow requires executable procedure_steps",
            validation["errors"],
        )

    def test_validate_semantic_compile_candidate_rejects_unknown_role_and_workflow_references(self):
        validation = _validate_semantic_compile_candidate(
            semantic_model={
                "primary_service_mode": "intent_routed_multi_workflow",
                "service_blocks": [
                    {"block_id": "workflow:advice", "block_type": "primary_workflow", "title": "Advice"},
                    {"block_id": "module:checklist", "block_type": "support_module", "title": "Checklist"},
                ],
                "procedures": [],
                "procedure_steps": [],
                "role_profiles": [
                    {
                        "role_id": "role:mentor",
                        "name": "Mentor",
                        "target_workflow_ids": ["workflow:missing"],
                    }
                ],
                "routing_rules": [
                    {
                        "rule_id": "rule:bad",
                        "target_workflow_id": "workflow:missing",
                        "target_role_id": "role:missing",
                        "target_module_ids": ["module:missing"],
                    }
                ],
                "clarification_gate_rules": [],
            },
            deterministic_contract={"resource_reference_catalog": []},
        )

        self.assertFalse(validation["valid"])
        self.assertIn("role references unknown workflow id: workflow:missing", validation["errors"])
        self.assertIn("routing rule references unknown workflow id: workflow:missing", validation["errors"])
        self.assertIn("routing rule references unknown role id: role:missing", validation["errors"])
        self.assertIn("routing rule references unknown module id: module:missing", validation["errors"])

    def test_validate_semantic_compile_candidate_accepts_ordered_sequential_multi_module_mapping(self):
        validation = _validate_semantic_compile_candidate(
            semantic_model={
                "primary_service_mode": "intent_routed_multi_workflow",
                "service_blocks": [
                    {"block_id": "workflow:designer", "block_type": "primary_workflow", "title": "Designer"},
                    {"block_id": "module:use-case", "block_type": "support_module", "title": "Use Case"},
                    {"block_id": "module:generator", "block_type": "support_module", "title": "Generator"},
                ],
                "procedures": [],
                "procedure_steps": [],
                "role_profiles": [],
                "routing_rules": [
                    {
                        "rule_id": "rule:design",
                        "target_workflow_id": "workflow:designer",
                        "target_module_ids": ["module:use-case", "module:generator"],
                    }
                ],
                "module_orchestration": {
                    "composition_mode": "ordered_sequential",
                    "task_module_mappings": [
                        {
                            "mapping_id": "map:design",
                            "target_module_ids": ["module:use-case", "module:generator"],
                        }
                    ],
                },
                "clarification_gate_rules": [],
            },
            deterministic_contract={"resource_reference_catalog": []},
        )

        self.assertTrue(validation["valid"])
        self.assertEqual(
            validation["normalized"]["module_orchestration"]["composition_mode"],
            "ordered_sequential",
        )

    def test_validate_semantic_compile_candidate_rejects_non_sequential_module_orchestration(self):
        validation = _validate_semantic_compile_candidate(
            semantic_model={
                "primary_service_mode": "intent_routed_multi_workflow",
                "service_blocks": [
                    {"block_id": "workflow:designer", "block_type": "primary_workflow", "title": "Designer"},
                    {"block_id": "module:use-case", "block_type": "support_module", "title": "Use Case"},
                ],
                "procedures": [],
                "procedure_steps": [],
                "role_profiles": [],
                "routing_rules": [
                    {"rule_id": "rule:design", "target_workflow_id": "workflow:designer"}
                ],
                "module_orchestration": {
                    "composition_mode": "parallel",
                    "task_module_mappings": [
                        {"mapping_id": "map:design", "target_module_id": "module:use-case"}
                    ],
                },
                "clarification_gate_rules": [],
            },
            deterministic_contract={"resource_reference_catalog": []},
        )

        self.assertFalse(validation["valid"])
        self.assertIn(
            "module_orchestration only supports ordered_sequential composition_mode",
            validation["errors"],
        )

    def test_validate_semantic_compile_candidate_rejects_single_default_workflow_with_multiple_workflows_and_routing(self):
        validation = _validate_semantic_compile_candidate(
            semantic_model={
                "primary_service_mode": "single_default_workflow",
                "default_workflow_id": "workflow:advice",
                "service_blocks": [
                    {
                        "block_id": "workflow:advice",
                        "block_type": "primary_workflow",
                        "title": "Advice",
                        "is_default": True,
                    },
                    {
                        "block_id": "workflow:deep-analysis",
                        "block_type": "primary_workflow",
                        "title": "Deep Analysis",
                    },
                ],
                "procedures": [],
                "procedure_steps": [],
                "role_profiles": [],
                "routing_rules": [
                    {
                        "rule_id": "route:deep-analysis",
                        "target_workflow_id": "workflow:deep-analysis",
                    }
                ],
                "clarification_gate_rules": [],
            },
            deterministic_contract={"resource_reference_catalog": []},
        )

        self.assertFalse(validation["valid"])
        self.assertIn(
            "single_default_workflow must not define routing_rules for alternate workflows",
            validation["errors"],
        )

    def test_validate_semantic_compile_candidate_warns_when_procedure_has_no_steps(self):
        validation = _validate_semantic_compile_candidate(
            semantic_model={
                "primary_service_mode": "single_default_workflow",
                "default_workflow_id": "workflow:default",
                "service_blocks": [
                    {
                        "block_id": "workflow:default",
                        "block_type": "primary_workflow",
                        "title": "Default Workflow",
                        "is_default": True,
                    }
                ],
                "procedures": [
                    {
                        "procedure_id": "procedure:default",
                        "service_block_id": "workflow:default",
                        "title": "Default Workflow",
                    }
                ],
                "procedure_steps": [],
                "role_profiles": [],
                "routing_rules": [],
                "clarification_gate_rules": [],
            },
            deterministic_contract={"resource_reference_catalog": []},
        )

        self.assertTrue(validation["valid"])
        self.assertIn("procedure has no executable steps: procedure:default", validation["warnings"])

    def test_validate_semantic_compile_candidate_warns_when_step_has_empty_execution_semantics(self):
        validation = _validate_semantic_compile_candidate(
            semantic_model={
                "primary_service_mode": "single_default_workflow",
                "default_workflow_id": "workflow:default",
                "service_blocks": [
                    {
                        "block_id": "workflow:default",
                        "block_type": "primary_workflow",
                        "title": "Default Workflow",
                        "is_default": True,
                    }
                ],
                "procedures": [
                    {
                        "procedure_id": "procedure:default",
                        "service_block_id": "workflow:default",
                        "title": "Default Workflow",
                    }
                ],
                "procedure_steps": [
                    {
                        "step_id": "step:default:1",
                        "procedure_id": "procedure:default",
                        "execution_mode": "interactive",
                    }
                ],
                "role_profiles": [],
                "routing_rules": [],
                "clarification_gate_rules": [],
            },
            deterministic_contract={"resource_reference_catalog": []},
        )

        self.assertTrue(validation["valid"])
        self.assertIn(
            "step has empty execution semantics: step:default:1",
            validation["warnings"],
        )

    def test_compile_instruction_understanding_church_ministry_shape_builds_hybrid_runtime(self):
        root = self._tmp_root("instruction_understanding_church_ministry")
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")

            def semantic_compiler(context):
                filenames = {
                    str(item.get("filename") or "").strip()
                    for item in context.get("resource_reference_catalog", [])
                    if isinstance(item, dict)
                }
                self.assertIn("Ministry_Prompt_Framework.md", filenames)
                self.assertIn("delivery_package_template.md", filenames)
                self.assertTrue(context.get("instruction_procedures"))
                self.assertTrue(context.get("procedure_steps"))
                return {
                    "app_semantic_model": {
                        "primary_service_mode": "single_default_workflow",
                        "default_workflow_id": "workflow:interaction_logic_execution_flow",
                        "global_app_contract": {"mission": "Design a church ministry prompt"},
                        "interaction_logic_blocks": [
                            {
                                "block_id": "logic:global",
                                "title": "Interaction Logic & Execution Flow",
                            }
                        ],
                        "role_profiles": [],
                        "routing_rules": [],
                        "module_orchestration": None,
                        "service_blocks": [
                            {
                                "block_id": "workflow:interaction_logic_execution_flow",
                                "block_type": "primary_workflow",
                                "title": "Interaction Logic & Execution Flow",
                                "is_default": True,
                            }
                        ],
                        "procedures": [
                            {
                                "procedure_id": "procedure:interaction_logic_execution_flow",
                                "service_block_id": "workflow:interaction_logic_execution_flow",
                                "title": "Interaction Logic & Execution Flow",
                            }
                        ],
                        "procedure_steps": [
                            {
                                "step_id": "step:interaction_logic_execution_flow:0",
                                "procedure_id": "procedure:interaction_logic_execution_flow",
                                "title": "Clarify the Ministry Goal",
                                "execution_mode": "interactive",
                                "resource_refs": ["Ministry_Discovery_Questions.md"],
                            },
                            {
                                "step_id": "step:interaction_logic_execution_flow:2",
                                "procedure_id": "procedure:interaction_logic_execution_flow",
                                "title": "Generate the Ministry Prompt Draft",
                                "execution_mode": "bundled",
                                "bundled_step_ids": [
                                    "step:interaction_logic_execution_flow:2",
                                    "step:interaction_logic_execution_flow:3",
                                    "step:interaction_logic_execution_flow:4",
                                    "step:interaction_logic_execution_flow:5",
                                ],
                                "bundled_resource_refs": [
                                    "Ministry_Prompt_Framework.md",
                                    "template_library.md",
                                    "dynamic_prompt_optimizer.md",
                                    "tool_selection_map.md",
                                    "ministry_output_rules.md",
                                    "ministry_prompt_guardrails.md",
                                    "delivery_package_template.md",
                                ],
                            },
                            {
                                "step_id": "step:interaction_logic_execution_flow:3",
                                "procedure_id": "procedure:interaction_logic_execution_flow",
                                "title": "Route the Tool and Module Pair",
                                "execution_mode": "bundled",
                                "bundled_step_ids": [
                                    "step:interaction_logic_execution_flow:2",
                                    "step:interaction_logic_execution_flow:3",
                                    "step:interaction_logic_execution_flow:4",
                                    "step:interaction_logic_execution_flow:5",
                                ],
                            },
                            {
                                "step_id": "step:interaction_logic_execution_flow:4",
                                "procedure_id": "procedure:interaction_logic_execution_flow",
                                "title": "Validate the Prompt Output",
                                "execution_mode": "bundled",
                                "bundled_step_ids": [
                                    "step:interaction_logic_execution_flow:2",
                                    "step:interaction_logic_execution_flow:3",
                                    "step:interaction_logic_execution_flow:4",
                                    "step:interaction_logic_execution_flow:5",
                                ],
                            },
                            {
                                "step_id": "step:interaction_logic_execution_flow:5",
                                "procedure_id": "procedure:interaction_logic_execution_flow",
                                "title": "Finalize the Delivery Package",
                                "execution_mode": "bundled",
                                "bundled_step_ids": [
                                    "step:interaction_logic_execution_flow:2",
                                    "step:interaction_logic_execution_flow:3",
                                    "step:interaction_logic_execution_flow:4",
                                    "step:interaction_logic_execution_flow:5",
                                ],
                            },
                        ],
                        "clarification_gate_rules": [
                            {
                                "gate_rule_id": "gate:ministry",
                                "procedure_id": "procedure:interaction_logic_execution_flow",
                                "clarification_step_id": "step:interaction_logic_execution_flow:0",
                                "completion_step_id": "step:interaction_logic_execution_flow:2",
                                "minimum_filled_slots": 2,
                            }
                        ],
                        "resource_bindings": [],
                        "semantic_warnings": [],
                        "semantic_confidence": 0.9,
                    }
                }

            record = compile_instruction_understanding(
                app_id="app-1",
                instruction_text=self._church_ministry_markdown(),
                instruction_uri="instructions/app-1/instructions.md",
                instruction_source_version=3,
                documents=self._church_ministry_documents(),
                repo=repo,
                snapshot_root=root / "snapshots",
                semantic_compiler=semantic_compiler,
            )

            hybrid = record["compiled_contract"]["hybrid_instruction_runtime_model"]
            self.assertEqual(hybrid["default_workflow_id"], "workflow:interaction_logic_execution_flow")
            self.assertEqual(hybrid["primary_service_mode"], "single_default_workflow")
            self.assertEqual(len(hybrid["clarification_gate_rules"]), 1)
            self.assertEqual(
                hybrid["clarification_gate_rules"][0]["completion_step_id"],
                "step:interaction_logic_execution_flow:2",
            )
            bundled_steps = [
                item for item in hybrid["procedure_steps"] if item.get("execution_mode") == "bundled"
            ]
            self.assertTrue(bundled_steps)
            self.assertIn(
                "delivery_package_template.md",
                bundled_steps[0].get("bundled_resource_refs", []),
            )
        finally:
            self._cleanup_root(root)

    def test_compile_instruction_understanding_grow_with_child_shape_supports_intent_routed_no_default(self):
        root = self._tmp_root("instruction_understanding_grow_with_child")
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")

            def semantic_compiler(context):
                service_blocks = context.get("instruction_service_blocks", [])
                self.assertTrue(service_blocks)
                filenames = {
                    str(item.get("filename") or "").strip()
                    for item in context.get("resource_reference_catalog", [])
                    if isinstance(item, dict)
                }
                self.assertIn("advice_checklist.md", filenames)
                self.assertIn("deep_analysis_framework.md", filenames)
                return {
                    "app_semantic_model": {
                        "primary_service_mode": "intent_routed_multi_workflow",
                        "default_workflow_id": None,
                        "global_app_contract": {
                            "mission": "Support parents with different levels of guidance",
                            "tone_policy": "role-sensitive",
                        },
                        "interaction_logic_blocks": [
                            {
                                "block_id": "logic:routing",
                                "title": "æ¨¡å¼åˆ¤æ–·è¦å‰‡",
                            }
                        ],
                        "role_profiles": [
                            {
                                "role_id": "role:coach",
                                "name": "å®¶åº­æˆé•·æ•™ç·´",
                                "target_workflow_ids": ["workflow:advice", "workflow:stepwise", "workflow:deep-analysis"],
                                "allowed_module_ids": ["module:emotion", "module:boundary"],
                            }
                        ],
                        "routing_rules": [
                            {
                                "rule_id": "route:advice",
                                "target_workflow_id": "workflow:advice",
                                "target_role_id": "role:coach",
                            },
                            {
                                "rule_id": "route:stepwise",
                                "target_workflow_id": "workflow:stepwise",
                                "target_role_id": "role:coach",
                            },
                            {
                                "rule_id": "route:deep-analysis",
                                "target_workflow_id": "workflow:deep-analysis",
                                "target_role_id": "role:coach",
                                "target_module_ids": ["module:emotion", "module:boundary"],
                            },
                        ],
                        "module_orchestration": {
                            "composition_mode": "ordered_sequential",
                            "task_module_mappings": [
                                {
                                    "mapping_id": "map:deep-analysis",
                                    "target_module_ids": ["module:emotion", "module:boundary"],
                                }
                            ],
                        },
                        "service_blocks": [
                            {
                                "block_id": "workflow:advice",
                                "block_type": "primary_workflow",
                                "title": "3x1 å»ºè­°æ¸…å–®æ³•",
                            },
                            {
                                "block_id": "workflow:stepwise",
                                "block_type": "primary_workflow",
                                "title": "æŒ‰æ­¥å°±ç­æ³•",
                            },
                            {
                                "block_id": "workflow:deep-analysis",
                                "block_type": "primary_workflow",
                                "title": "æ·±åº¦è§£æžæ³•",
                            },
                            {
                                "block_id": "module:emotion",
                                "block_type": "support_module",
                                "title": "æƒ…ç·’åˆ†æžæ¨¡çµ„",
                            },
                            {
                                "block_id": "module:boundary",
                                "block_type": "support_module",
                                "title": "ç•Œç·šæºé€šæ¨¡çµ„",
                            },
                        ],
                        "procedures": [
                            {
                                "procedure_id": "procedure:advice",
                                "service_block_id": "workflow:advice",
                                "title": "3x1 å»ºè­°æ¸…å–®æ³•",
                            },
                            {
                                "procedure_id": "procedure:stepwise",
                                "service_block_id": "workflow:stepwise",
                                "title": "æŒ‰æ­¥å°±ç­æ³•",
                            },
                            {
                                "procedure_id": "procedure:deep-analysis",
                                "service_block_id": "workflow:deep-analysis",
                                "title": "æ·±åº¦è§£æžæ³•",
                            },
                        ],
                        "procedure_steps": [
                            {
                                "step_id": "step:advice:1",
                                "procedure_id": "procedure:advice",
                                "title": "Provide 3x1 guidance",
                                "execution_mode": "interactive",
                                "resource_refs": ["advice_checklist.md"],
                            },
                            {
                                "step_id": "step:stepwise:1",
                                "procedure_id": "procedure:stepwise",
                                "title": "Guide step by step",
                                "execution_mode": "interactive",
                                "resource_refs": ["step_by_step_guide.md"],
                            },
                            {
                                "step_id": "step:deep-analysis:1",
                                "procedure_id": "procedure:deep-analysis",
                                "title": "Run deep analysis",
                                "execution_mode": "bundled",
                                "bundled_step_ids": ["step:deep-analysis:1"],
                                "bundled_resource_refs": [
                                    "deep_analysis_framework.md",
                                    "emotion_signal_map.md",
                                    "boundary_conversation_prompts.md",
                                ],
                            },
                        ],
                        "clarification_gate_rules": [],
                        "resource_bindings": [],
                        "semantic_warnings": [],
                        "semantic_confidence": 0.92,
                    }
                }

            record = compile_instruction_understanding(
                app_id="app-1",
                instruction_text=self._grow_with_child_markdown(),
                instruction_uri="instructions/app-1/instructions.md",
                instruction_source_version=3,
                documents=self._grow_with_child_documents(),
                repo=repo,
                snapshot_root=root / "snapshots",
                semantic_compiler=semantic_compiler,
            )

            hybrid = record["compiled_contract"]["hybrid_instruction_runtime_model"]
            self.assertEqual(hybrid["primary_service_mode"], "intent_routed_multi_workflow")
            self.assertIsNone(hybrid["default_workflow_id"])
            self.assertEqual(len(hybrid["routing_rules"]), 3)
            self.assertEqual(len(hybrid["role_profiles"]), 1)
            self.assertEqual(
                hybrid["module_orchestration"]["composition_mode"],
                "ordered_sequential",
            )
            bundled_steps = [
                item for item in hybrid["procedure_steps"] if item.get("execution_mode") == "bundled"
            ]
            self.assertEqual(len(bundled_steps), 1)
            self.assertIn(
                "deep_analysis_framework.md",
                bundled_steps[0].get("bundled_resource_refs", []),
            )
        finally:
            self._cleanup_root(root)

    def test_compile_instruction_understanding_bible_tutor_logic_first_shape_reclassifies_to_interaction_logic(self):
        root = self._tmp_root("instruction_understanding_bible_tutor_reclassify")
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")

            def semantic_compiler(context):
                self.assertTrue(context.get("instruction_service_blocks"))
                return {
                    "app_semantic_model": {
                        "primary_service_mode": "intent_routed_multi_workflow",
                        "default_workflow_id": None,
                        "global_app_contract": {
                            "mission": "Teach scripture through guided conversation",
                        },
                        "interaction_logic_blocks": [
                            {
                                "block_id": "interaction_logic:mode_detection",
                                "title": "模式自動識別（Mode Detection）",
                                "mode_behaviors": [
                                    {
                                        "mode_id": "mode:bible_study",
                                        "mode_title": "查考經文模式（Bible Study）",
                                        "entry_response": "好的，我們一起用歸納釋經法查考經文。請問想從哪一段開始？",
                                        "target_module_id": "module:查經互動模組",
                                    }
                                ],
                            }
                        ],
                        "role_profiles": [{"role_id": "role:tutor", "name": "Tutor"}],
                        "routing_rules": [
                            {
                                "rule_id": "routing:keyword_bible_study",
                                "target_interaction_logic_id": "interaction_logic:mode_detection",
                                "target_role_id": "role:tutor",
                            }
                        ],
                        "module_orchestration": None,
                        "service_blocks": [],
                        "procedures": [],
                        "procedure_steps": [],
                        "clarification_gate_rules": [],
                        "resource_bindings": [],
                        "semantic_warnings": [],
                        "semantic_confidence": 0.91,
                    }
                }

            record = compile_instruction_understanding(
                app_id="app-1",
                instruction_text=self._bible_tutor_markdown(),
                instruction_uri="instructions/app-1/instructions.md",
                instruction_source_version=3,
                documents=self._bible_tutor_documents(),
                repo=repo,
                snapshot_root=root / "snapshots",
                semantic_compiler=semantic_compiler,
            )

            hybrid = record["compiled_contract"]["hybrid_instruction_runtime_model"]
            self.assertEqual(hybrid["primary_service_mode"], "intent_routed_interaction_logic")
            self.assertTrue(hybrid["interaction_logic_blocks"])
            self.assertTrue(
                any(str(item.get("target_interaction_logic_id") or "").strip() for item in hybrid["routing_rules"])
            )
        finally:
            self._cleanup_root(root)

    def test_compile_instruction_understanding_bible_tutor_logic_shape_seeds_executable_support_modules(self):
        root = self._tmp_root("instruction_understanding_bible_tutor_logic_first")
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")

            def semantic_compiler(context):
                self.assertTrue(context.get("instruction_service_blocks"))
                self.assertTrue(context.get("procedure_steps"))
                return {
                    "app_semantic_model": {
                        "primary_service_mode": "intent_routed_interaction_logic",
                        "default_workflow_id": None,
                        "global_app_contract": {
                            "mission": "Teach scripture through guided conversation",
                        },
                        "interaction_logic_blocks": [
                            {
                                "block_id": "interaction_logic:mode_detection",
                                "title": "模式自動識別（Mode Detection）",
                                "mode_behaviors": [
                                    {
                                        "mode_id": "mode:bible_study",
                                        "mode_title": "查考經文模式（Bible Study）",
                                        "entry_response": "好的，我們一起用歸納釋經法查考經文。請問想從哪一段開始？",
                                        "target_module_id": "module:查經互動模組",
                                    }
                                ],
                            }
                        ],
                        "role_profiles": [
                            {"role_id": "role:tutor", "name": "Tutor"},
                        ],
                        "routing_rules": [
                            {
                                "rule_id": "routing:keyword_bible_study",
                                "target_interaction_logic_id": "interaction_logic:mode_detection",
                                "target_role_id": "role:tutor",
                            }
                        ],
                        "module_orchestration": None,
                        "service_blocks": [],
                        "procedures": [],
                        "procedure_steps": [],
                        "clarification_gate_rules": [],
                        "resource_bindings": [],
                        "semantic_warnings": [],
                        "semantic_confidence": 0.95,
                    }
                }

            record = compile_instruction_understanding(
                app_id="app-1",
                instruction_text=self._bible_tutor_markdown(),
                instruction_uri="instructions/app-1/instructions.md",
                instruction_source_version=3,
                documents=self._bible_tutor_documents(),
                repo=repo,
                snapshot_root=root / "snapshots",
                semantic_compiler=semantic_compiler,
            )

            hybrid = record["compiled_contract"]["hybrid_instruction_runtime_model"]
            self.assertEqual(hybrid["primary_service_mode"], "intent_routed_interaction_logic")
            block_ids = {
                str(item.get("block_id") or "").strip()
                for item in hybrid["instruction_service_blocks"]
                if isinstance(item, dict)
            }
            support_module_ids = {
                str(item.get("module_id") or "").strip()
                for item in hybrid.get("support_modules", [])
                if isinstance(item, dict)
            }
            self.assertIn("support_module:查經互動模組", block_ids)
            self.assertIn("support_module:查經互動模組", support_module_ids)
            procedure_ids = {
                str(item.get("procedure_id") or "").strip()
                for item in hybrid["instruction_procedures"]
                if isinstance(item, dict)
            }
            self.assertIn("procedure:support_module_查經互動模組", procedure_ids)
            step_titles = [
                str(item.get("title") or "").strip()
                for item in hybrid["procedure_steps"]
                if isinstance(item, dict)
                and str(item.get("procedure_id") or "").strip() == "procedure:support_module_查經互動模組"
            ]
            self.assertIn("細察事實", step_titles)
        finally:
            self._cleanup_root(root)

    def test_compile_instruction_understanding_bible_tutor_nested_runtime_projects_module_step_resources(self):
        root = self._tmp_root("instruction_understanding_bible_tutor_nested_projection")
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")

            def semantic_compiler(_context):
                return {
                    "app_semantic_model": {
                        "primary_service_mode": "intent_routed_interaction_logic",
                        "default_workflow_id": None,
                        "global_app_contract": {"mission": "Teach scripture step by step"},
                        "interaction_logic_blocks": [
                            {
                                "block_id": "logic:bible_study_mode",
                                "title": "查考經文模式",
                                "subordinate_target": {
                                    "target_type": "support_module",
                                    "target_id": "support_module:查經互動模組",
                                },
                            }
                        ],
                        "routing_rules": [
                            {
                                "rule_id": "route:bible_study",
                                "trigger_keywords": ["查考", "經文"],
                                "target_logic_block_id": "logic:bible_study_mode",
                                "target_module_id": "support_module:查經互動模組",
                            }
                        ],
                        "service_blocks": [
                            {
                                "block_id": "support_module:查經互動模組",
                                "block_type": "support_module",
                                "title": "查經互動模組",
                            }
                        ],
                        "procedures": [
                            {
                                "procedure_id": "procedure:support_module_查經互動模組",
                                "service_block_id": "support_module:查經互動模組",
                                "title": "查經互動模組",
                            }
                        ],
                        "procedure_steps": [
                            {
                                "procedure_id": "procedure:support_module_查經互動模組",
                                "step_id": "step:support_module_查經互動模組:1",
                                "title": "細察事實",
                                "order": 1,
                                "execution_mode": "interactive",
                                "resource_refs": ["observation_guide.md"],
                            },
                            {
                                "procedure_id": "procedure:support_module_查經互動模組",
                                "step_id": "step:support_module_查經互動模組:2",
                                "title": "認清關係",
                                "order": 2,
                                "execution_mode": "interactive",
                                "resource_refs": ["identify_relationships_guide.md"],
                            },
                        ],
                        "role_profiles": [],
                        "clarification_gate_rules": [],
                    }
                }

            record = compile_instruction_understanding(
                app_id="app-1",
                instruction_text=self._bible_tutor_markdown(),
                instruction_uri="instructions/app-1/instructions.md",
                instruction_source_version=3,
                documents=self._bible_tutor_documents(),
                repo=repo,
                snapshot_root=root / "snapshots",
                semantic_compiler=semantic_compiler,
            )

            nested = record["compiled_contract"]["instruction_runtime_model"]
            support_module = next(
                item
                for item in nested["support_modules"]
                if str(item.get("module_id") or "").strip() == "support_module:查經互動模組"
            )
            self.assertEqual(support_module.get("resource_ids"), [])
            self.assertNotIn("formulate_questions_guide.md", str(support_module.get("notes") or ""))

            step_blocks = [
                item for item in nested["instruction_blocks"]
                if isinstance(item, dict) and str(item.get("block_type") or "").strip() == "step"
            ]
            observation = next(
                item
                for item in step_blocks
                if int(item.get("linked_step_order") or 0) == 1
            )
            self.assertEqual(observation.get("referenced_resources"), ["observation_guide.md"])
        finally:
            self._cleanup_root(root)

    def test_compile_instruction_understanding_bible_tutor_hybrid_runtime_backfills_step_resource_refs_from_deterministic_steps(self):
        root = self._tmp_root("instruction_understanding_bible_tutor_hybrid_step_refs")
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")

            def semantic_compiler(_context):
                return {
                    "app_semantic_model": {
                        "primary_service_mode": "intent_routed_interaction_logic",
                        "default_workflow_id": None,
                        "global_app_contract": {"mission": "Teach scripture step by step"},
                        "interaction_logic_blocks": [
                            {
                                "block_id": "logic:bible_study_mode",
                                "title": "查考經文模式",
                                "subordinate_target": {
                                    "target_type": "support_module",
                                    "target_id": "support_module:查經互動模組",
                                },
                            }
                        ],
                        "routing_rules": [
                            {
                                "rule_id": "route:bible_study",
                                "trigger_keywords": ["查考", "經文"],
                                "target_logic_block_id": "logic:bible_study_mode",
                                "target_module_id": "support_module:查經互動模組",
                            }
                        ],
                        "service_blocks": [
                            {
                                "block_id": "support_module:查經互動模組",
                                "block_type": "support_module",
                                "title": "查經互動模組",
                            }
                        ],
                        "procedures": [
                            {
                                "procedure_id": "procedure:support_module_查經互動模組",
                                "service_block_id": "support_module:查經互動模組",
                                "title": "查經互動模組",
                            }
                        ],
                        "procedure_steps": [
                            {
                                "procedure_id": "procedure:support_module_查經互動模組",
                                "step_id": "step:support_module_查經互動模組:1",
                                "title": "細察事實",
                                "order": 1,
                                "execution_mode": "interactive",
                                "resource_refs": [],
                            },
                            {
                                "procedure_id": "procedure:support_module_查經互動模組",
                                "step_id": "step:support_module_查經互動模組:2",
                                "title": "認清關係",
                                "order": 2,
                                "execution_mode": "interactive",
                                "resource_refs": [],
                            },
                        ],
                        "role_profiles": [],
                        "clarification_gate_rules": [],
                    }
                }

            record = compile_instruction_understanding(
                app_id="app-1",
                instruction_text=self._bible_tutor_markdown(),
                instruction_uri="instructions/app-1/instructions.md",
                instruction_source_version=3,
                documents=self._bible_tutor_documents(),
                repo=repo,
                snapshot_root=root / "snapshots",
                semantic_compiler=semantic_compiler,
            )

            hybrid = record["compiled_contract"]["hybrid_instruction_runtime_model"]
            step_refs = {
                str(item.get("step_id") or "").strip(): list(item.get("resource_refs") or [])
                for item in (hybrid.get("procedure_steps") or [])
                if isinstance(item, dict)
            }
            self.assertEqual(
                step_refs.get("step:support_module_查經互動模組:1"),
                ["observation_guide.md"],
            )
            self.assertEqual(
                step_refs.get("step:support_module_查經互動模組:2"),
                ["identify_relationships_guide.md"],
            )
        finally:
            self._cleanup_root(root)

    def test_compile_instruction_understanding_parenting_shape_infers_interaction_logic_when_mode_missing(self):
        root = self._tmp_root("instruction_understanding_parenting_missing_mode")
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")

            def semantic_compiler(context):
                self.assertTrue(context.get("instruction_service_blocks"))
                return {
                    "app_semantic_model": {
                        "default_workflow_id": None,
                        "global_app_contract": {
                            "mission": "Support parents with role-sensitive guidance",
                        },
                        "interaction_logic_blocks": [
                            {
                                "block_id": "logic:role_routing",
                                "title": "五重角色模式",
                                "body_text": "Route by role fit and user need.",
                                "mode_behaviors": [
                                    {
                                        "mode_id": "mode:mentor",
                                        "mode_title": "Mentor",
                                        "target_workflow_id": "workflow:深度解析法",
                                    },
                                    {
                                        "mode_id": "mode:tutor",
                                        "mode_title": "Tutor",
                                        "target_module_id": "module:查經互動模組",
                                    },
                                ],
                            },
                            {
                                "block_id": "logic:layered_needs",
                                "title": "多重需求分層規則",
                                "body_text": "Layer emotional, behavioral, and scripture needs sequentially.",
                                "layers": [
                                    {"layer_order": 1, "workflow_id": "workflow:深度解析法"},
                                    {"layer_order": 2, "workflow_options": ["workflow:按步就班法", "workflow:3x1建議清單法"]},
                                    {"layer_order": 3, "subordinate_modules": ["module:查經互動模組"]},
                                ],
                            },
                        ],
                        "role_profiles": [
                            {"role_id": "role:mentor", "name": "Mentor"},
                            {"role_id": "role:consultant", "name": "Consultant"},
                            {"role_id": "role:coach", "name": "Coach"},
                            {"role_id": "role:partner", "name": "Partner"},
                            {"role_id": "role:tutor", "name": "Tutor"},
                        ],
                        "routing_rules": [
                            {
                                "rule_id": "route:mentor",
                                "target_role_id": "role:mentor",
                                "target_workflow_id": "workflow:深度解析法",
                            },
                            {
                                "rule_id": "route:consultant",
                                "target_role_id": "role:consultant",
                                "target_workflow_id": "workflow:3x1建議清單法",
                            },
                            {
                                "rule_id": "route:coach",
                                "target_role_id": "role:coach",
                                "target_workflow_id": "workflow:按步就班法",
                            },
                            {
                                "rule_id": "route:tutor",
                                "target_role_id": "role:tutor",
                                "target_module_id": "module:查經互動模組",
                            },
                            {
                                "rule_id": "route:layered",
                                "target_interaction_logic_id": "logic:layered_needs",
                            },
                        ],
                        "module_orchestration": None,
                        "service_blocks": [
                            {"block_id": "workflow:深度解析法", "block_type": "primary_workflow", "title": "深度解析法流程"},
                            {"block_id": "workflow:3x1建議清單法", "block_type": "primary_workflow", "title": "3x1 建議清單流程"},
                            {"block_id": "workflow:按步就班法", "block_type": "primary_workflow", "title": "按步就班法流程"},
                            {"block_id": "module:查經互動模組", "block_type": "support_module", "title": "查經互動模組（歸納釋經法）"},
                        ],
                        "procedures": [
                            {"procedure_id": "procedure:mentor", "service_block_id": "workflow:深度解析法", "title": "深度解析法流程"},
                            {"procedure_id": "procedure:consultant", "service_block_id": "workflow:3x1建議清單法", "title": "3x1 建議清單流程"},
                            {"procedure_id": "procedure:coach", "service_block_id": "workflow:按步就班法", "title": "按步就班法流程"},
                            {"procedure_id": "procedure:tutor", "service_block_id": "module:查經互動模組", "title": "查經互動模組（歸納釋經法）"},
                        ],
                        "procedure_steps": [
                            {"step_id": "step:mentor:1", "procedure_id": "procedure:mentor", "title": "深度解析法流程", "execution_mode": "interactive"},
                            {"step_id": "step:consultant:1", "procedure_id": "procedure:consultant", "title": "3x1 建議清單流程", "execution_mode": "interactive"},
                            {"step_id": "step:coach:1", "procedure_id": "procedure:coach", "title": "按步就班法流程", "execution_mode": "interactive"},
                            {"step_id": "step:tutor:1", "procedure_id": "procedure:tutor", "title": "查經互動模組（歸納釋經法）", "execution_mode": "interactive"},
                        ],
                        "clarification_gate_rules": [],
                        "resource_bindings": [],
                        "semantic_warnings": [],
                        "semantic_confidence": 0.92,
                    }
                }

            record = compile_instruction_understanding(
                app_id="app-1",
                instruction_text=self._grow_with_child_markdown(),
                instruction_uri="instructions/app-1/instructions.md",
                instruction_source_version=3,
                documents=self._grow_with_child_documents(),
                repo=repo,
                snapshot_root=root / "snapshots",
                semantic_compiler=semantic_compiler,
            )

            hybrid = record["compiled_contract"]["hybrid_instruction_runtime_model"]
            self.assertEqual(hybrid["primary_service_mode"], "intent_routed_interaction_logic")
        finally:
            self._cleanup_root(root)

    def test_build_hybrid_runtime_model_projects_top_level_routing_rules_from_logic_blocks(self):
        hybrid = _build_hybrid_runtime_model(
            {
                "primary_service_mode": "intent_routed_interaction_logic",
                "default_workflow_id": None,
                "global_app_contract": {},
                "interaction_logic_blocks": [
                    {
                        "block_id": "logic:mode_detection",
                        "title": "模式自動識別（Mode Detection）",
                        "routing_rules": [
                            {
                                "rule_id": "route:bible_study",
                                "priority": 1,
                                "trigger_keywords": ["查考", "研經", "經文"],
                                "target_logic_id": "logic:mode_bible_study",
                                "entry_response": "好的，我們一起用歸納釋經法查考經文。請問想從哪一段開始？",
                            }
                        ],
                    }
                ],
                "role_profiles": [],
                "routing_rules": [],
                "module_orchestration": None,
                "support_modules": [],
                "followup_modules": [],
                "service_blocks": [],
                "procedures": [],
                "procedure_steps": [],
                "clarification_gate_rules": [],
                "resource_bindings": [],
                "semantic_warnings": [],
                "semantic_confidence": 0.95,
            },
            {},
            {"valid": True, "errors": [], "warnings": [], "normalized": {}},
        )

        self.assertTrue(hybrid["routing_rules"])
        first_rule = hybrid["routing_rules"][0]
        self.assertEqual(first_rule.get("target_interaction_logic_id"), "logic:mode_bible_study")

    def test_project_compatibility_instruction_runtime_model_overwrites_stale_top_level_runtime_fields(self):
        compatibility = _project_compatibility_instruction_runtime_model(
            {
                "primary_service_mode": "single_default_workflow",
                "default_workflow_id": "workflow:legacy_default",
                "global_app_contract": {"mission": "legacy"},
                "module_orchestration": {"composition_mode": "legacy_parallel"},
                "semantic_confidence": 0.11,
                "deterministic_contract_summary": {"service_block_count": 1},
                "routing_rules": [{"rule_id": "legacy"}],
            },
            {
                "primary_service_mode": "intent_routed_interaction_logic",
                "default_workflow_id": None,
                "global_app_contract": {"mission": "canonical"},
                "module_orchestration": None,
                "semantic_confidence": 0.95,
                "deterministic_contract_summary": {"service_block_count": 3},
                "interaction_logic_blocks": [],
                "role_profiles": [],
                "routing_rules": [{"rule_id": "route:canonical"}],
                "support_modules": [],
                "followup_modules": [],
                "instruction_service_blocks": [],
                "instruction_procedures": [],
                "procedure_steps": [],
            },
        )

        self.assertEqual(compatibility["primary_service_mode"], "intent_routed_interaction_logic")
        self.assertIsNone(compatibility["default_workflow_id"])
        self.assertEqual(compatibility["global_app_contract"], {"mission": "canonical"})
        self.assertIsNone(compatibility["module_orchestration"])
        self.assertEqual(compatibility["semantic_confidence"], 0.95)
        self.assertEqual(
            compatibility["deterministic_contract_summary"],
            {"service_block_count": 3},
        )
        self.assertEqual(compatibility["routing_rules"], [{"rule_id": "route:canonical"}])

    def test_project_compatibility_instruction_runtime_model_dedupes_module_aliases_by_canonical_identity(self):
        compatibility = _project_compatibility_instruction_runtime_model(
            {
                "support_modules": [
                    {
                        "module_id": "查經互動模組",
                        "title": "Legacy Bible Study Module",
                    }
                ],
                "followup_modules": [
                    {
                        "module_id": "optimization_module",
                        "title": "Legacy Optimization Module",
                    }
                ],
            },
            {
                "primary_service_mode": "intent_routed_interaction_logic",
                "default_workflow_id": None,
                "global_app_contract": {},
                "module_orchestration": None,
                "semantic_confidence": 0.95,
                "deterministic_contract_summary": {},
                "interaction_logic_blocks": [],
                "role_profiles": [],
                "routing_rules": [],
                "support_modules": [
                    {
                        "module_id": "support_module:查經互動模組",
                        "title": "Canonical Bible Study Module",
                    }
                ],
                "followup_modules": [
                    {
                        "module_id": "followup_module:optimization_module",
                        "title": "Canonical Optimization Module",
                    }
                ],
                "instruction_service_blocks": [],
                "instruction_procedures": [],
                "procedure_steps": [],
            },
        )

        self.assertEqual(
            compatibility["support_modules"],
            [{"module_id": "support_module:查經互動模組", "title": "Canonical Bible Study Module"}],
        )
        self.assertEqual(
            compatibility["followup_modules"],
            [{"module_id": "followup_module:optimization_module", "title": "Canonical Optimization Module"}],
        )

    def test_project_compatibility_instruction_runtime_model_keeps_church_ministry_core_scope_narrow(self):
        compatibility = _project_compatibility_instruction_runtime_model(
            {
                "primary_service_mode": "single_default_workflow",
                "default_workflow_id": "primary_workflow:interaction_logic_execution_flow",
                "global_app_contract": {"mission": "legacy"},
                "module_orchestration": None,
                "semantic_confidence": 0.41,
                "deterministic_contract_summary": {"service_block_count": 1},
                "routing_rules": [],
                "instruction_service_blocks": [
                    {
                        "block_id": "primary_workflow:interaction_logic_execution_flow",
                        "block_type": "primary_workflow",
                        "title": "Interaction Logic & Execution Flow",
                        "resource_refs": [
                            "Ministry_Discovery_Questions.md",
                            "Ministry_Constraint_Checklist.md",
                            "Ministry_Prompt_Framework.md",
                            "template_library.md",
                            "dynamic_prompt_optimizer.md",
                            "tool_selection_map.md",
                        ],
                    }
                ],
                "instruction_procedures": [
                    {
                        "procedure_id": "procedure:interaction_logic_execution_flow",
                        "service_block_id": "primary_workflow:interaction_logic_execution_flow",
                        "title": "Interaction Logic & Execution Flow",
                    }
                ],
                "procedure_steps": [
                    {
                        "step_id": "step:clarification",
                        "procedure_id": "procedure:interaction_logic_execution_flow",
                        "title": "Clarification",
                        "resource_refs": ["Ministry_Discovery_Questions.md"],
                    },
                    {
                        "step_id": "step:core_workflow_execution",
                        "procedure_id": "procedure:interaction_logic_execution_flow",
                        "title": "Core Workflow",
                        "resource_refs": ["Ministry_Prompt_Framework.md"],
                        "bundled_resource_refs": [
                            "Ministry_Prompt_Framework.md",
                            "template_library.md",
                            "dynamic_prompt_optimizer.md",
                            "tool_selection_map.md",
                        ],
                    },
                ],
            },
            {
                "primary_service_mode": "single_default_workflow",
                "default_workflow_id": "primary_workflow:interaction_logic_execution_flow",
                "global_app_contract": {"mission": "canonical"},
                "module_orchestration": None,
                "semantic_confidence": 0.95,
                "deterministic_contract_summary": {"service_block_count": 2},
                "interaction_logic_blocks": [],
                "role_profiles": [],
                "routing_rules": [],
                "support_modules": [],
                "followup_modules": [
                    {
                        "module_id": "followup_module:optimization_module",
                        "title": "Optimization Module",
                    }
                ],
                "instruction_service_blocks": [
                    {
                        "block_id": "primary_workflow:interaction_logic_execution_flow",
                        "block_type": "primary_workflow",
                        "title": "Interaction Logic & Execution Flow",
                        "resource_refs": [
                            "Ministry_Discovery_Questions.md",
                            "Ministry_Constraint_Checklist.md",
                            "Ministry_Prompt_Framework.md",
                        ],
                    },
                    {
                        "block_id": "followup_module:optimization_module",
                        "block_type": "followup_module",
                        "title": "Optimization Module",
                        "resource_refs": [
                            "dynamic_prompt_optimizer.md",
                            "Optimization Strategy Library.md",
                        ],
                    },
                ],
                "instruction_procedures": [
                    {
                        "procedure_id": "procedure:interaction_logic_execution_flow",
                        "service_block_id": "primary_workflow:interaction_logic_execution_flow",
                        "title": "Interaction Logic & Execution Flow",
                    },
                    {
                        "procedure_id": "procedure:optimization_module",
                        "service_block_id": "followup_module:optimization_module",
                        "title": "Optimization Module",
                    },
                ],
                "procedure_steps": [
                    {
                        "step_id": "step:clarification",
                        "procedure_id": "procedure:interaction_logic_execution_flow",
                        "title": "Clarification",
                        "resource_refs": ["Ministry_Discovery_Questions.md"],
                    },
                    {
                        "step_id": "step:core_workflow_execution",
                        "procedure_id": "procedure:interaction_logic_execution_flow",
                        "title": "Core Workflow",
                        "resource_refs": ["Ministry_Prompt_Framework.md"],
                    },
                    {
                        "step_id": "step:optimization_module:1",
                        "procedure_id": "procedure:optimization_module",
                        "title": "Optimization Module",
                        "resource_refs": [
                            "dynamic_prompt_optimizer.md",
                            "Optimization Strategy Library.md",
                        ],
                    },
                ],
            },
        )

        step_map = {
            str(item.get("step_id") or "").strip(): item
            for item in (compatibility.get("procedure_steps") or [])
            if isinstance(item, dict)
        }
        core_step = step_map["step:core_workflow_execution"]
        self.assertEqual(core_step.get("resource_refs"), ["Ministry_Prompt_Framework.md"])
        self.assertFalse(core_step.get("bundled_resource_refs"))
        self.assertIn("step:optimization_module:1", step_map)

    def test_compile_instruction_understanding_projects_bible_tutor_runtime_routing_triggers_from_logic_blocks(self):
        root = self._tmp_root("instruction_understanding_bible_tutor_runtime_routing_triggers")
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")

            def semantic_compiler(_context):
                return {
                    "app_semantic_model": {
                        "primary_service_mode": "intent_routed_interaction_logic",
                        "default_workflow_id": None,
                        "global_app_contract": {"mission": "Teach scripture step by step"},
                        "interaction_logic_blocks": [
                            {
                                "block_id": "logic:mode_detection",
                                "title": "\u6a21\u5f0f\u81ea\u52d5\u8b58\u5225\uff08Mode Detection\uff09",
                                "routing_rules": [
                                    {
                                        "rule_id": "route:bible_study",
                                        "priority": 1,
                                        "trigger_keywords": ["\u67e5\u8003", "\u7814\u7d93", "\u7d93\u6587"],
                                        "target_logic_id": "logic:mode_bible_study",
                                    }
                                ],
                            },
                            {
                                "block_id": "logic:mode_bible_study",
                                "title": "\u67e5\u8003\u7d93\u6587\u6a21\u5f0f\uff08Bible Study\uff09",
                                "subordinate_target": {
                                    "target_type": "support_module",
                                    "target_id": "support_module:\u67e5\u7d93\u4e92\u52d5\u6a21\u7d44",
                                },
                            },
                        ],
                        "routing_rules": [],
                        "service_blocks": [
                            {
                                "block_id": "support_module:\u67e5\u7d93\u4e92\u52d5\u6a21\u7d44",
                                "block_type": "support_module",
                                "title": "\u67e5\u7d93\u4e92\u52d5\u6a21\u7d44",
                            }
                        ],
                        "procedures": [],
                        "procedure_steps": [],
                        "role_profiles": [],
                        "clarification_gate_rules": [],
                    }
                }

            record = compile_instruction_understanding(
                app_id="app-1",
                instruction_text=self._bible_tutor_markdown(),
                instruction_uri="instructions/app-1/instructions.md",
                instruction_source_version=3,
                documents=self._bible_tutor_documents(),
                repo=repo,
                snapshot_root=root / "snapshots",
                semantic_compiler=semantic_compiler,
            )

            runtime_rules = record["compiled_contract"]["instruction_runtime_model"].get("routing_rules") or []
            self.assertTrue(runtime_rules)
            bible_rule = next(
                item
                for item in runtime_rules
                if isinstance(item, dict) and str(item.get("rule_id") or "").strip() == "route:bible_study"
            )
            self.assertEqual(
                bible_rule.get("trigger_keywords"),
                ["\u67e5\u8003", "\u7814\u7d93", "\u7d93\u6587"],
            )
        finally:
            self._cleanup_root(root)

    def test_compile_instruction_understanding_projects_parenting_role_routes_into_runtime_bindable_targets(self):
        root = self._tmp_root("instruction_understanding_parenting_runtime_bindable_targets")
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")

            def semantic_compiler(_context):
                return {
                    "app_semantic_model": {
                        "primary_service_mode": "intent_routed_interaction_logic",
                        "default_workflow_id": None,
                        "global_app_contract": {
                            "mission": "Support parents with role-sensitive guidance",
                        },
                        "interaction_logic_blocks": [
                            {
                                "block_id": "logic:role_routing",
                                "title": "\u4e94\u91cd\u89d2\u8272\u6a21\u5f0f",
                                "body_text": "Route by role fit and user need.",
                            }
                        ],
                        "role_profiles": [
                            {
                                "role_id": "role:consultant",
                                "name": "Consultant",
                                "allowed_workflow_ids": ["workflow:3x1\u5efa\u8b70\u6e05\u55ae\u6cd5"],
                            },
                            {
                                "role_id": "role:tutor",
                                "name": "Tutor",
                                "allowed_module_ids": ["module:\u67e5\u7d93\u4e92\u52d5\u6a21\u7d44"],
                            },
                        ],
                        "routing_rules": [
                            {
                                "rule_id": "route:consultant",
                                "target_role_id": "role:consultant",
                            },
                            {
                                "rule_id": "route:tutor",
                                "target_role_id": "role:tutor",
                            },
                        ],
                        "service_blocks": [
                            {
                                "block_id": "workflow:3x1\u5efa\u8b70\u6e05\u55ae\u6cd5",
                                "block_type": "primary_workflow",
                                "title": "3x1 \u5efa\u8b70\u6e05\u55ae\u6d41\u7a0b",
                            },
                            {
                                "block_id": "module:\u67e5\u7d93\u4e92\u52d5\u6a21\u7d44",
                                "block_type": "support_module",
                                "title": "\u67e5\u7d93\u4e92\u52d5\u6a21\u7d44\uff08\u6b78\u7d0d\u91cb\u7d93\u6cd5\uff09",
                            },
                        ],
                        "procedures": [
                            {
                                "procedure_id": "procedure:consultant",
                                "service_block_id": "workflow:3x1\u5efa\u8b70\u6e05\u55ae\u6cd5",
                                "title": "3x1 \u5efa\u8b70\u6e05\u55ae\u6d41\u7a0b",
                            },
                            {
                                "procedure_id": "procedure:tutor",
                                "service_block_id": "module:\u67e5\u7d93\u4e92\u52d5\u6a21\u7d44",
                                "title": "\u67e5\u7d93\u4e92\u52d5\u6a21\u7d44\uff08\u6b78\u7d0d\u91cb\u7d93\u6cd5\uff09",
                            },
                        ],
                        "procedure_steps": [
                            {
                                "step_id": "step:consultant:1",
                                "procedure_id": "procedure:consultant",
                                "order": 1,
                                "title": "\u63d0\u4f9b\u4e09\u500b\u5efa\u8b70\u8207\u4e00\u500b\u7acb\u5373\u884c\u52d5",
                                "execution_mode": "interactive",
                            },
                            {
                                "step_id": "step:tutor:1",
                                "procedure_id": "procedure:tutor",
                                "order": 1,
                                "title": "\u7d30\u5bdf\u4e8b\u5be6",
                                "execution_mode": "interactive",
                            },
                        ],
                        "clarification_gate_rules": [],
                    }
                }

            record = compile_instruction_understanding(
                app_id="app-1",
                instruction_text=self._grow_with_child_markdown(),
                instruction_uri="instructions/app-1/instructions.md",
                instruction_source_version=3,
                documents=self._grow_with_child_documents(),
                repo=repo,
                snapshot_root=root / "snapshots",
                semantic_compiler=semantic_compiler,
            )

            hybrid_runtime = record["compiled_contract"]["hybrid_instruction_runtime_model"]
            runtime_rules = record["compiled_contract"]["instruction_runtime_model"].get("routing_rules") or []
            service_block_ids = {
                str(item.get("block_id") or "").strip()
                for item in (hybrid_runtime.get("instruction_service_blocks") or [])
                if isinstance(item, dict)
            }
            self.assertIn("workflow:3x1\u5efa\u8b70\u6e05\u55ae\u6cd5", service_block_ids)
            self.assertIn("support_module:\u67e5\u7d93\u4e92\u52d5\u6a21\u7d44", service_block_ids)
            self.assertTrue(runtime_rules)
            route_targets = {
                str(
                    item.get("target_service_block_id")
                    or item.get("target_workflow_id")
                    or item.get("target_module_id")
                    or ""
                ).strip()
                for item in runtime_rules
                if isinstance(item, dict)
            }
            self.assertIn("workflow:3x1\u5efa\u8b70\u6e05\u55ae\u6cd5", route_targets)
            self.assertIn("support_module:\u67e5\u7d93\u4e92\u52d5\u6a21\u7d44", route_targets)
            self.assertTrue(route_targets <= service_block_ids)
        finally:
            self._cleanup_root(root)

    def test_compile_instruction_understanding_keeps_church_ministry_followup_module_canonical_across_runtime_surfaces(self):
        root = self._tmp_root("instruction_understanding_church_ministry_followup_canonical")
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")

            def semantic_compiler(_context):
                return {
                    "app_semantic_model": {
                        "primary_service_mode": "single_default_workflow",
                        "default_workflow_id": "primary_workflow:interaction_logic_execution_flow",
                        "primary_workflow": [
                            {
                                "workflow_id": "primary_workflow:interaction_logic_execution_flow",
                                "workflow_title": "Interaction Logic & Execution Flow",
                                "is_default": True,
                                "step_sequence": [
                                    {
                                        "order": 1,
                                        "step_id": "step:clarification",
                                        "title": "Clarification",
                                        "execution_mode": "interactive",
                                    },
                                    {
                                        "order": 2,
                                        "step_id": "step:core_workflow_execution",
                                        "title": "Core Workflow",
                                        "execution_mode": "bundled",
                                        "resource_refs": ["template_library.md"],
                                    },
                                ],
                            }
                        ],
                        "support_modules": [
                            {
                                "module_id": "support_module:knowledge",
                                "module_title": "Knowledge Modules",
                            }
                        ],
                        "followup_modules": [
                            {
                                "module_id": "followup_module:optimization_module",
                                "module_title": "Optimization Module",
                            }
                        ],
                    }
                }

            record = compile_instruction_understanding(
                app_id="app-1",
                instruction_text=self._church_ministry_markdown(),
                instruction_uri="instructions/app-1/instructions.md",
                instruction_source_version=3,
                documents=self._church_ministry_documents(),
                repo=repo,
                snapshot_root=root / "snapshots",
                semantic_compiler=semantic_compiler,
            )

            hybrid_runtime = record["compiled_contract"]["hybrid_instruction_runtime_model"]
            nested_runtime = record["compiled_contract"]["instruction_runtime_model"]
            hybrid_followups = {
                str(item.get("module_id") or "").strip()
                for item in (hybrid_runtime.get("followup_modules") or [])
                if isinstance(item, dict)
            }
            hybrid_support_modules = {
                str(item.get("module_id") or "").strip()
                for item in (hybrid_runtime.get("support_modules") or [])
                if isinstance(item, dict)
            }
            nested_followups = {
                str(item.get("module_id") or "").strip()
                for item in (nested_runtime.get("followup_modules") or [])
                if isinstance(item, dict)
            }
            service_block_ids = {
                str(item.get("block_id") or "").strip()
                for item in (hybrid_runtime.get("instruction_service_blocks") or [])
                if isinstance(item, dict) and str(item.get("block_type") or "").strip() == "followup_module"
            }

            self.assertEqual(hybrid_support_modules, {"support_module:knowledge"})
            self.assertEqual(hybrid_followups, {"followup_module:optimization_module"})
            self.assertEqual(nested_followups, {"followup_module:optimization_module"})
            self.assertEqual(service_block_ids, {"followup_module:optimization_module"})
        finally:
            self._cleanup_root(root)

    def test_compile_instruction_understanding_church_ministry_projects_core_step_resources_and_followup_block_from_primary_workflow(self):
        root = self._tmp_root("instruction_understanding_church_ministry_primary_workflow_projection")
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")

            def semantic_compiler(_context):
                return {
                    "app_semantic_model": {
                        "primary_service_mode": "single_default_workflow",
                        "default_workflow_id": "wf:interaction_logic_execution_flow",
                        "primary_workflow": [
                            {
                                "workflow_id": "wf:interaction_logic_execution_flow",
                                "workflow_title": "Interaction Logic & Execution Flow",
                                "is_default": True,
                                "step_sequence": [
                                    {
                                        "order": 1,
                                        "step_id": "step:clarification",
                                        "title": "Clarification",
                                        "execution_mode": "interactive",
                                    },
                                    {
                                        "order": 2,
                                        "step_id": "step:core_workflow_execution",
                                        "title": "Core Workflow",
                                        "execution_mode": "bundled",
                                        "resource_refs": ["template_library.md"],
                                    },
                                ],
                            }
                        ],
                        "support_modules": [
                            {
                                "module_id": "support_module:knowledge",
                                "module_title": "Knowledge Modules",
                            }
                        ],
                        "followup_modules": [
                            {
                                "module_id": "followup_module:optimization_module",
                                "module_title": "Optimization Module",
                            }
                        ],
                    }
                }

            record = compile_instruction_understanding(
                app_id="app-1",
                instruction_text=self._church_ministry_markdown(),
                instruction_uri="instructions/app-1/instructions.md",
                instruction_source_version=3,
                documents=self._church_ministry_documents(),
                repo=repo,
                snapshot_root=root / "snapshots",
                semantic_compiler=semantic_compiler,
            )

            hybrid = record["compiled_contract"]["hybrid_instruction_runtime_model"]
            step_refs = {
                str(item.get("step_id") or "").strip(): (
                    list(item.get("bundled_resource_refs") or [])
                    or list(item.get("resource_refs") or [])
                )
                for item in (hybrid.get("procedure_steps") or [])
                if isinstance(item, dict)
            }
            followup_block_ids = {
                str(item.get("block_id") or "").strip(): list(item.get("resource_refs") or [])
                for item in (hybrid.get("instruction_service_blocks") or [])
                if isinstance(item, dict) and str(item.get("block_type") or "").strip() == "followup_module"
            }
            self.assertEqual(
                step_refs.get("step:clarification"),
                ["Ministry_Discovery_Questions.md"],
            )
            self.assertEqual(
                step_refs.get("step:core_workflow_execution"),
                ["template_library.md"],
            )
            self.assertEqual(set(followup_block_ids), {"followup_module:optimization_module"})
            self.assertEqual(
                followup_block_ids["followup_module:optimization_module"],
                ["dynamic_prompt_optimizer.md", "Optimization Strategy Library.md"],
            )
        finally:
            self._cleanup_root(root)

    def test_validate_semantic_compile_candidate_rewrites_bible_tutor_logic_primary_workflow_id_to_executable_block(self):
        validation = _validate_semantic_compile_candidate(
            semantic_model={
                "primary_service_mode": "intent_routed_interaction_logic",
                "default_workflow_id": None,
                "interaction_logic_blocks": [
                    {
                        "block_id": "logic:mode_bible_study",
                        "title": "查考經文模式（Bible Study）",
                        "behavior_policy": {
                            "primary_workflow_id": "workflow:bible_study_10_step",
                        },
                    }
                ],
                "role_profiles": [],
                "routing_rules": [],
                "service_blocks": [
                    {
                        "block_id": "workflow:歸納釋經法",
                        "block_type": "primary_workflow",
                        "title": "查經互動模組 — 十步歸納釋經流程",
                    }
                ],
                "procedures": [
                    {
                        "procedure_id": "procedure:workflow_歸納釋經法",
                        "service_block_id": "workflow:歸納釋經法",
                        "title": "查經互動模組 — 十步歸納釋經流程",
                    }
                ],
                "procedure_steps": [
                    {
                        "procedure_id": "procedure:workflow_歸納釋經法",
                        "step_id": "step:observation",
                        "title": "細察事實 (Observation)",
                        "order": 1,
                        "execution_mode": "interactive",
                    }
                ],
                "clarification_gate_rules": [],
            },
            deterministic_contract={
                "instruction_service_blocks": [
                    {
                        "block_id": "workflow:歸納釋經法",
                        "block_type": "primary_workflow",
                        "title": "查經互動模組 — 十步歸納釋經流程",
                    }
                ],
                "instruction_workflows": [
                    {
                        "id": "bible_study_10_step",
                        "title": "查經互動模組 — 十步歸納釋經流程",
                        "body_text": "完整十步歸納釋經流程。",
                        "steps": [
                            {
                                "step_id": "step:observation",
                                "order": 1,
                                "title": "細察事實 (Observation)",
                                "resource_ref": "observation_guide.md",
                            }
                        ],
                    }
                ],
                "instruction_modules": [],
                "instruction_procedures": [],
                "procedure_steps": [],
                "resource_reference_catalog": [{"filename": "observation_guide.md"}],
            },
        )

        self.assertTrue(validation["valid"], validation["errors"])
        logic_blocks = [
            item for item in validation["normalized"]["interaction_logic_blocks"]
            if isinstance(item, dict)
        ]
        self.assertTrue(logic_blocks)
        self.assertEqual(
            logic_blocks[0].get("behavior_policy", {}).get("primary_workflow_id"),
            "workflow:歸納釋經法",
        )

    def test_build_hybrid_runtime_model_copies_step_resource_refs_from_deterministic_step_metadata(self):
        hybrid = _build_hybrid_runtime_model(
            {
                "primary_service_mode": "intent_routed_interaction_logic",
                "default_workflow_id": None,
                "global_app_contract": {},
                "interaction_logic_blocks": [],
                "role_profiles": [],
                "routing_rules": [],
                "module_orchestration": None,
                "support_modules": [],
                "followup_modules": [],
                "service_blocks": [
                    {
                        "block_id": "workflow:歸納釋經法",
                        "block_type": "primary_workflow",
                        "title": "查經互動模組 — 十步歸納釋經流程",
                    }
                ],
                "procedures": [
                    {
                        "procedure_id": "procedure:workflow_歸納釋經法",
                        "service_block_id": "workflow:歸納釋經法",
                        "title": "查經互動模組 — 十步歸納釋經流程",
                    }
                ],
                "procedure_steps": [
                    {
                        "procedure_id": "procedure:workflow_歸納釋經法",
                        "step_id": "step:observation",
                        "title": "細察事實 (Observation)",
                        "order": 1,
                        "execution_mode": "interactive",
                        "resource_refs": [],
                    }
                ],
                "clarification_gate_rules": [],
                "resource_bindings": [],
                "semantic_warnings": [],
                "semantic_confidence": 0.95,
            },
            {
                "procedure_steps": [],
                "instruction_workflows": [
                    {
                        "id": "bible_study_10_step",
                        "title": "查經互動模組 — 十步歸納釋經流程",
                        "steps": [
                            {
                                "step_id": "step:observation",
                                "order": 1,
                                "title": "細察事實 (Observation)",
                                "resource_ref": "observation_guide.md",
                            }
                        ],
                    }
                ],
                "primary_workflow": {
                    "workflow_id": "workflow:bible_study_10_step",
                    "steps": [
                        {
                            "step_id": "step:observation",
                            "order": 1,
                            "title": "細察事實 (Observation)",
                            "resource_ref": "observation_guide.md",
                        }
                    ],
                },
            },
            {"valid": True, "errors": [], "warnings": [], "normalized": {}},
        )

        observation_step = next(
            item
            for item in hybrid["procedure_steps"]
            if isinstance(item, dict) and str(item.get("step_id") or "").strip() == "step:observation"
        )
        self.assertEqual(observation_step.get("resource_refs"), ["observation_guide.md"])

    def test_project_compatibility_instruction_runtime_model_preserves_bible_tutor_active_step_scope(self):
        instruction_runtime_model = _project_compatibility_instruction_runtime_model(
            {
                "primary_service_mode": "intent_routed_interaction_logic",
                "default_workflow_id": None,
                "global_app_contract": {"mission": "legacy"},
                "module_orchestration": None,
                "semantic_confidence": 0.22,
                "deterministic_contract_summary": {},
                "routing_rules": [
                    {
                        "rule_id": "route:bible_study",
                        "target_service_block_id": "support_module:\u67e5\u7d93\u4e92\u52d5\u6a21\u7d44",
                    }
                ],
                "instruction_service_blocks": [
                    {
                        "block_id": "support_module:\u67e5\u7d93\u4e92\u52d5\u6a21\u7d44",
                        "block_type": "support_module",
                        "title": "\u67e5\u7d93\u4e92\u52d5\u6a21\u7d44",
                    }
                ],
                "instruction_procedures": [
                    {
                        "procedure_id": "procedure:support_module_\u67e5\u7d93\u4e92\u52d5\u6a21\u7d44",
                        "service_block_id": "support_module:\u67e5\u7d93\u4e92\u52d5\u6a21\u7d44",
                        "title": "\u67e5\u7d93\u4e92\u52d5\u6a21\u7d44",
                    }
                ],
                "procedure_steps": [
                    {
                        "step_id": "step:observation",
                        "procedure_id": "procedure:support_module_\u67e5\u7d93\u4e92\u52d5\u6a21\u7d44",
                        "title": "\u7d30\u5bdf\u4e8b\u5be6",
                        "resource_refs": [
                            "observation_guide.md",
                            "identify_relationships_guide.md",
                        ],
                    },
                    {
                        "step_id": "step:identify_relationships",
                        "procedure_id": "procedure:support_module_\u67e5\u7d93\u4e92\u52d5\u6a21\u7d44",
                        "title": "\u8a8d\u6e05\u95dc\u4fc2",
                        "resource_refs": [
                            "observation_guide.md",
                            "identify_relationships_guide.md",
                        ],
                    },
                ],
            },
            {
                "primary_service_mode": "intent_routed_interaction_logic",
                "default_workflow_id": None,
                "global_app_contract": {"mission": "canonical"},
                "module_orchestration": None,
                "semantic_confidence": 0.95,
                "deterministic_contract_summary": {},
                "interaction_logic_blocks": [],
                "role_profiles": [],
                "routing_rules": [
                    {
                        "rule_id": "route:bible_study",
                        "target_service_block_id": "support_module:\u67e5\u7d93\u4e92\u52d5\u6a21\u7d44",
                    }
                ],
                "support_modules": [],
                "followup_modules": [],
                "instruction_service_blocks": [
                    {
                        "block_id": "support_module:\u67e5\u7d93\u4e92\u52d5\u6a21\u7d44",
                        "block_type": "support_module",
                        "title": "\u67e5\u7d93\u4e92\u52d5\u6a21\u7d44",
                    }
                ],
                "instruction_procedures": [
                    {
                        "procedure_id": "procedure:support_module_\u67e5\u7d93\u4e92\u52d5\u6a21\u7d44",
                        "service_block_id": "support_module:\u67e5\u7d93\u4e92\u52d5\u6a21\u7d44",
                        "title": "\u67e5\u7d93\u4e92\u52d5\u6a21\u7d44",
                    }
                ],
                "procedure_steps": [
                    {
                        "step_id": "step:observation",
                        "procedure_id": "procedure:support_module_\u67e5\u7d93\u4e92\u52d5\u6a21\u7d44",
                        "title": "\u7d30\u5bdf\u4e8b\u5be6",
                        "resource_refs": ["observation_guide.md"],
                    },
                    {
                        "step_id": "step:identify_relationships",
                        "procedure_id": "procedure:support_module_\u67e5\u7d93\u4e92\u52d5\u6a21\u7d44",
                        "title": "\u8a8d\u6e05\u95dc\u4fc2",
                        "resource_refs": ["identify_relationships_guide.md"],
                    },
                ],
            },
        )

        step_map = {
            str(item.get("step_id") or "").strip(): list(item.get("resource_refs") or [])
            for item in (instruction_runtime_model.get("procedure_steps") or [])
            if isinstance(item, dict)
        }
        self.assertEqual(
            step_map["step:observation"],
            ["observation_guide.md"],
        )
        self.assertEqual(
            step_map["step:identify_relationships"],
            ["identify_relationships_guide.md"],
        )

    def test_compile_instruction_understanding_bible_tutor_instruction_runtime_model_preserves_hybrid_step_owned_refs_for_active_route(self):
        root = self._tmp_root("instruction_understanding_bible_tutor_runtime_active_step_scope")
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")

            def semantic_compiler(_context):
                return {
                    "app_semantic_model": {
                        "primary_service_mode": "intent_routed_interaction_logic",
                        "default_workflow_id": None,
                        "global_app_contract": {"mission": "Teach scripture step by step"},
                        "interaction_logic_blocks": [
                            {
                                "block_id": "logic:bible_study_mode",
                                "title": "查考經文模式",
                                "subordinate_target": {
                                    "target_type": "support_module",
                                    "target_id": "support_module:查經互動模組",
                                },
                            }
                        ],
                        "routing_rules": [
                            {
                                "rule_id": "route:bible_study",
                                "trigger_keywords": ["查考", "經文"],
                                "target_logic_block_id": "logic:bible_study_mode",
                                "target_module_id": "support_module:查經互動模組",
                            }
                        ],
                        "service_blocks": [
                            {
                                "block_id": "support_module:查經互動模組",
                                "block_type": "support_module",
                                "title": "查經互動模組",
                            }
                        ],
                        "procedures": [
                            {
                                "procedure_id": "procedure:support_module_查經互動模組",
                                "service_block_id": "support_module:查經互動模組",
                                "title": "查經互動模組",
                            }
                        ],
                        "procedure_steps": [
                            {
                                "procedure_id": "procedure:support_module_查經互動模組",
                                "step_id": "step:observation",
                                "title": "細察事實",
                                "order": 1,
                                "execution_mode": "interactive",
                                "resource_refs": [],
                            },
                            {
                                "procedure_id": "procedure:support_module_查經互動模組",
                                "step_id": "step:identify_relationships",
                                "title": "認清關係",
                                "order": 2,
                                "execution_mode": "interactive",
                                "resource_refs": [],
                            },
                        ],
                        "role_profiles": [],
                        "clarification_gate_rules": [],
                    }
                }

            record = compile_instruction_understanding(
                app_id="app-1",
                instruction_text=self._bible_tutor_markdown(),
                instruction_uri="instructions/app-1/instructions.md",
                instruction_source_version=3,
                documents=self._bible_tutor_documents(),
                repo=repo,
                snapshot_root=root / "snapshots",
                semantic_compiler=semantic_compiler,
            )

            hybrid_steps = {
                str(item.get("step_id") or "").strip(): list(item.get("resource_refs") or [])
                for item in (record["compiled_contract"]["hybrid_instruction_runtime_model"].get("procedure_steps") or [])
                if isinstance(item, dict)
            }
            runtime_steps = {
                str(item.get("step_id") or "").strip(): list(item.get("resource_refs") or [])
                for item in (record["compiled_contract"]["instruction_runtime_model"].get("procedure_steps") or [])
                if isinstance(item, dict)
            }

            self.assertEqual(
                hybrid_steps["step:observation"],
                ["observation_guide.md"],
            )
            self.assertEqual(
                hybrid_steps["step:identify_relationships"],
                ["identify_relationships_guide.md"],
            )
            self.assertEqual(
                runtime_steps["step:observation"],
                ["observation_guide.md"],
            )
            self.assertEqual(
                runtime_steps["step:identify_relationships"],
                ["identify_relationships_guide.md"],
            )
        finally:
            self._cleanup_root(root)

    def test_compile_instruction_understanding_church_ministry_hybrid_runtime_keeps_narrow_core_scope(self):
        root = self._tmp_root("instruction_understanding_church_ministry_hybrid_narrow_core_scope")
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")

            def semantic_compiler(_context):
                return {
                    "app_semantic_model": {
                        "primary_service_mode": "single_default_workflow",
                        "default_workflow_id": "wf:interaction_logic_execution_flow",
                        "primary_workflow": [
                            {
                                "workflow_id": "wf:interaction_logic_execution_flow",
                                "workflow_title": "Interaction Logic & Execution Flow",
                                "is_default": True,
                                "step_sequence": [
                                    {
                                        "order": 1,
                                        "step_id": "step:clarification",
                                        "title": "Clarification",
                                        "execution_mode": "interactive",
                                    },
                                    {
                                        "order": 2,
                                        "step_id": "step:core_workflow_execution",
                                        "title": "Core Workflow",
                                        "execution_mode": "bundled",
                                        "resource_refs": ["template_library.md"],
                                    },
                                ],
                            }
                        ],
                        "support_modules": [
                            {
                                "module_id": "support_module:knowledge",
                                "module_title": "Knowledge Modules",
                            }
                        ],
                        "followup_modules": [
                            {
                                "module_id": "followup_module:optimization_module",
                                "module_title": "Optimization Module",
                            }
                        ],
                    }
                }

            record = compile_instruction_understanding(
                app_id="app-1",
                instruction_text=self._church_ministry_markdown(),
                instruction_uri="instructions/app-1/instructions.md",
                instruction_source_version=3,
                documents=self._church_ministry_documents(),
                repo=repo,
                snapshot_root=root / "snapshots",
                semantic_compiler=semantic_compiler,
            )

            hybrid = record["compiled_contract"]["hybrid_instruction_runtime_model"]
            step_map = {
                str(item.get("step_id") or "").strip(): item
                for item in (hybrid.get("procedure_steps") or [])
                if isinstance(item, dict)
            }
            self.assertEqual(
                step_map["step:clarification"].get("resource_refs"),
                ["Ministry_Discovery_Questions.md"],
            )
            self.assertEqual(
                step_map["step:core_workflow_execution"].get("resource_refs"),
                ["template_library.md"],
            )
            self.assertFalse(
                step_map["step:core_workflow_execution"].get("bundled_resource_refs")
            )
        finally:
            self._cleanup_root(root)

    def test_compile_instruction_understanding_church_ministry_hybrid_runtime_projects_executable_optimization_module_block(self):
        root = self._tmp_root("instruction_understanding_church_ministry_hybrid_optimization_block")
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")

            def semantic_compiler(_context):
                return {
                    "app_semantic_model": {
                        "primary_service_mode": "single_default_workflow",
                        "default_workflow_id": "wf:interaction_logic_execution_flow",
                        "primary_workflow": [
                            {
                                "workflow_id": "wf:interaction_logic_execution_flow",
                                "workflow_title": "Interaction Logic & Execution Flow",
                                "is_default": True,
                                "step_sequence": [
                                    {
                                        "order": 1,
                                        "step_id": "step:clarification",
                                        "title": "Clarification",
                                        "execution_mode": "interactive",
                                    },
                                    {
                                        "order": 2,
                                        "step_id": "step:core_workflow_execution",
                                        "title": "Core Workflow",
                                        "execution_mode": "bundled",
                                        "resource_refs": ["template_library.md"],
                                    },
                                ],
                            }
                        ],
                        "support_modules": [
                            {
                                "module_id": "support_module:knowledge",
                                "module_title": "Knowledge Modules",
                            }
                        ],
                        "followup_modules": [
                            {
                                "module_id": "followup_module:optimization_module",
                                "module_title": "Optimization Module",
                            }
                        ],
                    }
                }

            record = compile_instruction_understanding(
                app_id="app-1",
                instruction_text=self._church_ministry_markdown(),
                instruction_uri="instructions/app-1/instructions.md",
                instruction_source_version=3,
                documents=self._church_ministry_documents(),
                repo=repo,
                snapshot_root=root / "snapshots",
                semantic_compiler=semantic_compiler,
            )

            hybrid = record["compiled_contract"]["hybrid_instruction_runtime_model"]
            service_blocks = {
                str(item.get("block_id") or "").strip(): item
                for item in (hybrid.get("instruction_service_blocks") or [])
                if isinstance(item, dict)
            }
            procedures = {
                str(item.get("service_block_id") or "").strip(): item
                for item in (hybrid.get("instruction_procedures") or [])
                if isinstance(item, dict)
            }
            optimization_block = service_blocks["followup_module:optimization_module"]
            self.assertEqual(
                optimization_block.get("resource_refs"),
                ["dynamic_prompt_optimizer.md", "Optimization Strategy Library.md"],
            )
            self.assertIn("followup_module:optimization_module", procedures)
        finally:
            self._cleanup_root(root)

    def test_compile_instruction_understanding_preserves_grow_with_child_runtime_bindable_paths(self):
        root = self._tmp_root("instruction_understanding_grow_with_child_runtime_bindable_paths")
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")

            def semantic_compiler(_context):
                return {
                    "app_semantic_model": {
                        "primary_service_mode": "intent_routed_interaction_logic",
                        "default_workflow_id": None,
                        "global_app_contract": {
                            "mission": "Support parents with role-sensitive guidance",
                        },
                        "interaction_logic_blocks": [
                            {
                                "block_id": "logic:role_routing",
                                "title": "五重角色模式",
                                "body_text": "Route by role fit and user need.",
                            }
                        ],
                        "role_profiles": [
                            {
                                "role_id": "role:consultant",
                                "name": "Consultant",
                                "allowed_workflow_ids": ["workflow:3x1建議清單法"],
                            },
                            {
                                "role_id": "role:tutor",
                                "name": "Tutor",
                                "allowed_module_ids": ["module:查經互動模組"],
                            },
                        ],
                        "routing_rules": [
                            {
                                "rule_id": "route:consultant",
                                "target_role_id": "role:consultant",
                            },
                            {
                                "rule_id": "route:tutor",
                                "target_role_id": "role:tutor",
                            },
                        ],
                        "service_blocks": [
                            {
                                "block_id": "workflow:3x1建議清單法",
                                "block_type": "primary_workflow",
                                "title": "3x1 建議清單流程",
                            },
                            {
                                "block_id": "module:查經互動模組",
                                "block_type": "support_module",
                                "title": "查經互動模組（歸納釋經法）",
                            },
                        ],
                        "procedures": [
                            {
                                "procedure_id": "procedure:consultant",
                                "service_block_id": "workflow:3x1建議清單法",
                                "title": "3x1 建議清單流程",
                            },
                            {
                                "procedure_id": "procedure:tutor",
                                "service_block_id": "module:查經互動模組",
                                "title": "查經互動模組（歸納釋經法）",
                            },
                        ],
                        "procedure_steps": [
                            {
                                "step_id": "step:consultant:1",
                                "procedure_id": "procedure:consultant",
                                "order": 1,
                                "title": "提供三個建議與一個立即行動",
                                "execution_mode": "interactive",
                            },
                            {
                                "step_id": "step:tutor:1",
                                "procedure_id": "procedure:tutor",
                                "order": 1,
                                "title": "細察事實",
                                "execution_mode": "interactive",
                            },
                        ],
                        "clarification_gate_rules": [],
                    }
                }

            record = compile_instruction_understanding(
                app_id="app-1",
                instruction_text=self._grow_with_child_markdown(),
                instruction_uri="instructions/app-1/instructions.md",
                instruction_source_version=3,
                documents=self._grow_with_child_documents(),
                repo=repo,
                snapshot_root=root / "snapshots",
                semantic_compiler=semantic_compiler,
            )

            hybrid_runtime = record["compiled_contract"]["hybrid_instruction_runtime_model"]
            runtime_model = record["compiled_contract"]["instruction_runtime_model"]
            hybrid_service_block_ids = {
                str(item.get("block_id") or "").strip()
                for item in (hybrid_runtime.get("instruction_service_blocks") or [])
                if isinstance(item, dict)
            }
            service_block_ids = {
                str(item.get("block_id") or "").strip()
                for item in (runtime_model.get("instruction_service_blocks") or [])
                if isinstance(item, dict)
            }
            hybrid_route_targets = {
                str(item.get("target_service_block_id") or "").strip(): item
                for item in (hybrid_runtime.get("routing_rules") or [])
                if isinstance(item, dict)
            }
            procedure_owner_ids = {
                str(item.get("service_block_id") or "").strip()
                for item in (runtime_model.get("instruction_procedures") or [])
                if isinstance(item, dict)
            }
            route_targets = {
                str(item.get("target_service_block_id") or "").strip(): item
                for item in (runtime_model.get("routing_rules") or [])
                if isinstance(item, dict)
            }

            self.assertEqual(
                hybrid_route_targets["workflow:3x1建議清單法"].get("target_workflow_id"),
                "workflow:3x1建議清單法",
            )
            self.assertEqual(
                hybrid_route_targets["support_module:查經互動模組"].get("target_module_id"),
                "support_module:查經互動模組",
            )
            self.assertTrue(hybrid_route_targets.keys() <= hybrid_service_block_ids)
            self.assertEqual(
                route_targets["workflow:3x1建議清單法"].get("target_workflow_id"),
                "workflow:3x1建議清單法",
            )
            self.assertEqual(
                route_targets["support_module:查經互動模組"].get("target_module_id"),
                "support_module:查經互動模組",
            )
            self.assertTrue(route_targets.keys() <= service_block_ids)
            self.assertTrue(route_targets.keys() <= procedure_owner_ids)
        finally:
            self._cleanup_root(root)

    def test_compile_instruction_understanding_gpt_design_assistant_supports_ordered_module_orchestration(self):
        root = self._tmp_root("instruction_understanding_gpt_design_assistant")
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")

            def semantic_compiler(context):
                filenames = {
                    str(item.get("filename") or "").strip()
                    for item in context.get("resource_reference_catalog", [])
                    if isinstance(item, dict)
                }
                self.assertIn("use_case_writing.md", filenames)
                self.assertIn("testing_optimization_support.md", filenames)
                return {
                    "app_semantic_model": {
                        "primary_service_mode": "intent_routed_multi_workflow",
                        "default_workflow_id": None,
                        "global_app_contract": {
                            "mission": "Turn GPT app ideas into executable design specs",
                        },
                        "interaction_logic_blocks": [
                            {
                                "block_id": "logic:orchestration",
                                "title": "Module Orchestration",
                            }
                        ],
                        "role_profiles": [
                            {
                                "role_id": "role:designer",
                                "name": "GPT Application Design Assistant",
                                "target_workflow_ids": ["workflow:design-assistant"],
                                "allowed_module_ids": [
                                    "module:use-case",
                                    "module:generator",
                                    "module:resource-manifest",
                                    "module:resource-binding",
                                    "module:configuration",
                                    "module:interaction-mode",
                                    "module:testing",
                                ],
                            }
                        ],
                        "routing_rules": [
                            {
                                "rule_id": "route:design",
                                "target_workflow_id": "workflow:design-assistant",
                                "target_role_id": "role:designer",
                                "target_module_ids": [
                                    "module:use-case",
                                    "module:generator",
                                    "module:resource-manifest",
                                    "module:resource-binding",
                                ],
                            }
                        ],
                        "module_orchestration": {
                            "composition_mode": "ordered_sequential",
                            "task_module_mappings": [
                                {
                                    "mapping_id": "map:idea-to-architecture",
                                    "target_module_ids": [
                                        "module:use-case",
                                        "module:generator",
                                        "module:resource-manifest",
                                        "module:resource-binding",
                                    ],
                                },
                                {
                                    "mapping_id": "map:interaction-and-quality",
                                    "target_module_ids": [
                                        "module:interaction-mode",
                                        "module:testing",
                                    ],
                                },
                            ],
                        },
                        "service_blocks": [
                            {
                                "block_id": "workflow:design-assistant",
                                "block_type": "primary_workflow",
                                "title": "GPT Application Design Assistant",
                            },
                            {"block_id": "module:use-case", "block_type": "support_module", "title": "Use Case Writing Support Module"},
                            {"block_id": "module:generator", "block_type": "support_module", "title": "MODULE_GENERATOR"},
                            {"block_id": "module:resource-manifest", "block_type": "support_module", "title": "RESOURCE_MANIFEST_SUPPORT"},
                            {"block_id": "module:resource-binding", "block_type": "support_module", "title": "RESOURCE_BINDING"},
                            {"block_id": "module:configuration", "block_type": "support_module", "title": "Configuration Support Module"},
                            {"block_id": "module:interaction-mode", "block_type": "support_module", "title": "Interaction Mode Support Module"},
                            {"block_id": "module:testing", "block_type": "support_module", "title": "Testing & Optimization Support Module"},
                        ],
                        "procedures": [
                            {
                                "procedure_id": "procedure:design-assistant",
                                "service_block_id": "workflow:design-assistant",
                                "title": "GPT Application Design Assistant",
                            }
                        ],
                        "procedure_steps": [
                            {
                                "step_id": "step:design-assistant:1",
                                "procedure_id": "procedure:design-assistant",
                                "title": "Run ordered module composition",
                                "execution_mode": "interactive",
                                "resource_refs": ["use_case_writing.md", "module_generator.md"],
                            }
                        ],
                        "clarification_gate_rules": [],
                        "resource_bindings": [],
                        "semantic_warnings": [],
                        "semantic_confidence": 0.94,
                    }
                }

            record = compile_instruction_understanding(
                app_id="app-1",
                instruction_text=self._gpt_design_assistant_markdown(),
                instruction_uri="instructions/app-1/instructions.md",
                instruction_source_version=3,
                documents=self._gpt_design_assistant_documents(),
                repo=repo,
                snapshot_root=root / "snapshots",
                semantic_compiler=semantic_compiler,
            )

            hybrid = record["compiled_contract"]["hybrid_instruction_runtime_model"]
            self.assertEqual(hybrid["primary_service_mode"], "intent_routed_multi_workflow")
            self.assertIsNone(hybrid["default_workflow_id"])
            self.assertEqual(len(hybrid["role_profiles"]), 1)
            self.assertEqual(len(hybrid["routing_rules"]), 1)
            self.assertEqual(
                hybrid["module_orchestration"]["composition_mode"],
                "ordered_sequential",
            )
            mappings = hybrid["module_orchestration"]["task_module_mappings"]
            self.assertEqual(
                mappings[0]["target_module_ids"],
                [
                    "support_module:use-case",
                    "support_module:generator",
                    "support_module:resource-manifest",
                    "support_module:resource-binding",
                ],
            )
            self.assertEqual(
                mappings[1]["target_module_ids"],
                ["support_module:interaction-mode", "support_module:testing"],
            )
        finally:
            self._cleanup_root(root)

    def test_approve_and_revise_instruction_understanding_flow(self):
        root = self._tmp_root("instruction_understanding_revision_flow")
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")
            store = _StubBuilderStore(root, instruction_text=self._markdown(), documents=self._documents())
            compiled = ensure_compiled_instruction_understanding(
                app_id="app-1",
                builder_store=store,
                repo=repo,
                snapshot_root=root / "snapshots",
            )["record"]
            review_instruction_understanding(
                app_id="app-1",
                compiled_record=compiled,
                repo=repo,
                reviewer=lambda _record: {
                    "review_status": "reviewed_with_warnings",
                    "review_confidence": 0.73,
                    "review_findings": {"critical": ["missing role profile"]},
                    "review_summary_md": "# Review\n",
                    "review_recommendations": {"action": "revise"},
                },
            )
            approval = approve_instruction_understanding_findings(
                app_id="app-1",
                repo=repo,
                approved_findings=[{"finding_id": "f1", "decision": "approve", "approved_revision_note": "add role"}],
                approver="tester",
            )
            revision = revise_instruction_understanding(
                app_id="app-1",
                repo=repo,
                reviser=lambda _context: {
                    "revised_semantic_model": {
                        "primary_service_mode": "single_default_workflow",
                        "default_workflow_id": "workflow:church-default",
                        "role_profiles": [{"role_id": "role:coach", "name": "Coach"}],
                        "service_blocks": [
                            {
                                "block_id": "workflow:church-default",
                                "block_type": "primary_workflow",
                                "title": "Interaction Logic & Execution Flow",
                                "is_default": True,
                            }
                        ],
                        "procedures": [],
                        "procedure_steps": [],
                        "routing_rules": [],
                        "clarification_gate_rules": [],
                    },
                    "revision_notes": ["Added role profile"],
                    "preserved_ids": [],
                    "changed_ids": ["role:coach"],
                    "revision_confidence": 0.7,
                },
            )
            self.assertEqual(approval["approval"]["approver"], "tester")
            self.assertEqual(revision["revision"]["revision_status"], "validated")
            self.assertEqual(revision["revision"]["changed_ids"], ["role:coach"])
        finally:
            self._cleanup_root(root)

    def test_hash_helpers_are_stable(self):
        instruction_hash = compute_instruction_source_hash("a\r\nb\r\n")
        self.assertEqual(instruction_hash, compute_instruction_source_hash("a\nb\n"))
        self.assertEqual(
            compute_resource_catalog_hash(self._documents()),
            compute_resource_catalog_hash(list(reversed(self._documents()))),
        )

    def test_structural_candidate_graph_is_exposed_in_compiled_contract(self):
        root = self._tmp_root("instruction_understanding_candidates")
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")
            record = compile_instruction_understanding(
                app_id="app-1",
                instruction_text=self._markdown(),
                instruction_uri="instructions/app-1/instructions.md",
                instruction_source_version=3,
                documents=self._documents(),
                repo=repo,
                snapshot_root=root / "snapshots",
            )
            graph = record["compiled_contract"]["structural_candidate_graph"]
            self.assertIn("heading_tree", graph)
            self.assertIn("section_candidates", graph)
            self.assertIn("step_candidates", graph)
            self.assertIn("resource_candidates", graph)
            self.assertIn("rule_candidates", graph)
            self.assertIn("trigger_candidates", graph)
            self.assertIn("role_candidates", graph)
            self.assertIn("interaction_logic_candidates", graph)
        finally:
            self._cleanup_root(root)

    def test_compile_instruction_understanding_persists_empty_semantic_raw_result_diagnostics(self):
        root = self._tmp_root("instruction_understanding_semantic_diagnostics")
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")
            record = compile_instruction_understanding(
                app_id="app-1",
                instruction_text=self._markdown(),
                instruction_uri="instructions/app-1/instructions.md",
                instruction_source_version=3,
                documents=self._documents(),
                repo=repo,
                snapshot_root=root / "snapshots",
                semantic_compiler=lambda _context: {},
            )

            semantic = record["compiled_contract"]["semantic_compile"]
            self.assertEqual(semantic["raw_result"], {})
            self.assertEqual(
                semantic["errors"],
                ["semantic compiler payload missing app_semantic_model object"],
            )
            self.assertFalse(semantic["validation"]["valid"])
            self.assertTrue(record["metadata"]["semantic_compile_attached"])
            self.assertFalse(record["metadata"]["semantic_compile_valid"])
            self.assertTrue(record["metadata"]["semantic_compile_empty"])
        finally:
            self._cleanup_root(root)

    def test_compile_instruction_understanding_keeps_last_valid_active_record_when_new_semantic_attempt_is_invalid(self):
        root = self._tmp_root("instruction_understanding_semantic_diagnostics")
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")
            first = compile_instruction_understanding(
                app_id="app-1",
                instruction_text=self._markdown(),
                instruction_uri="instructions/app-1/instructions.md",
                instruction_source_version=3,
                documents=self._documents(),
                repo=repo,
                snapshot_root=root / "snapshots",
                semantic_compiler=lambda _context: {
                    "app_semantic_model": {
                        "primary_service_mode": "single_default_workflow",
                        "default_workflow_id": "workflow:default",
                        "service_blocks": [
                            {
                                "block_id": "workflow:default",
                                "block_type": "primary_workflow",
                                "title": "Interaction Logic & Execution Flow",
                                "is_default": True,
                            }
                        ],
                        "procedures": [],
                        "procedure_steps": [],
                        "role_profiles": [],
                        "routing_rules": [],
                        "clarification_gate_rules": [],
                    }
                },
            )
            second = compile_instruction_understanding(
                app_id="app-1",
                instruction_text=self._markdown(),
                instruction_uri="instructions/app-1/instructions.md",
                instruction_source_version=3,
                documents=self._documents(),
                repo=repo,
                snapshot_root=root / "snapshots",
                semantic_compiler=lambda _context: {},
            )

            active = repo.get_active_compiled("app-1")
            latest = repo.get_latest_compiled("app-1")

            self.assertTrue(first["is_active"])
            self.assertFalse(second["is_active"])
            self.assertEqual(second["metadata"]["publish_status"], "diagnostic_only")
            self.assertEqual(active["id"], first["id"])
            self.assertEqual(latest["id"], second["id"])
            self.assertTrue(active["metadata"]["semantic_compile_valid"])
            self.assertFalse(second["metadata"]["semantic_compile_valid"])
        finally:
            self._cleanup_root(root)

    def test_compile_instruction_understanding_falls_back_when_primary_snapshot_root_is_locked(self):
        root = self._tmp_root("instruction_understanding_snapshot_fallback")
        primary_snapshot_root = root / "snapshots"
        fallback_snapshot_root = _snapshot_fallback_root()
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")
            app_dir = primary_snapshot_root / "app-1"
            real_write_text = Path.write_text

            def guarded_write_text(path_obj, data, *args, **kwargs):
                if Path(path_obj) == app_dir / "understanding.json":
                    raise PermissionError("locked primary snapshot root")
                return real_write_text(path_obj, data, *args, **kwargs)

            with mock.patch("pathlib.Path.write_text", new=guarded_write_text):
                record = compile_instruction_understanding(
                    app_id="app-1",
                    instruction_text=self._markdown(),
                    instruction_uri="instructions/app-1/instructions.md",
                    instruction_source_version=3,
                    documents=self._documents(),
                    repo=repo,
                    snapshot_root=primary_snapshot_root,
                )

            self.assertEqual(record["metadata"]["snapshot_root_status"], "fallback")
            self.assertEqual(
                Path(record["metadata"]["snapshot_root_used"]),
                fallback_snapshot_root,
            )
            self.assertFalse((primary_snapshot_root / "app-1" / "understanding.json").exists())
            self.assertTrue((fallback_snapshot_root / "app-1" / "understanding.json").exists())
            self.assertTrue((fallback_snapshot_root / "app-1" / "understanding.md").exists())
        finally:
            fallback_app_dir = fallback_snapshot_root / "app-1"
            if fallback_app_dir.exists():
                for path in sorted(fallback_app_dir.glob("**/*"), reverse=True):
                    if path.is_file():
                        path.unlink()
                    elif path.is_dir():
                        path.rmdir()
                if fallback_app_dir.exists():
                    fallback_app_dir.rmdir()
            self._cleanup_root(root)

    def test_invalid_compile_attempt_writes_diagnostic_snapshot_without_overwriting_active_snapshot(self):
        root = self._tmp_root("instruction_understanding_snapshot_publish_contract")
        snapshot_root = root / "snapshots"
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")
            valid_record = compile_instruction_understanding(
                app_id="app-1",
                instruction_text=self._markdown(),
                instruction_uri="instructions/app-1/instructions.md",
                instruction_source_version=3,
                documents=self._documents(),
                repo=repo,
                snapshot_root=snapshot_root,
                semantic_compiler=lambda _context: {
                    "app_semantic_model": {
                        "primary_service_mode": "single_default_workflow",
                        "default_workflow_id": "workflow:default",
                        "service_blocks": [
                            {
                                "block_id": "workflow:default",
                                "block_type": "primary_workflow",
                                "title": "Interaction Logic & Execution Flow",
                                "is_default": True,
                            }
                        ],
                        "procedures": [],
                        "procedure_steps": [],
                        "role_profiles": [],
                        "routing_rules": [],
                        "clarification_gate_rules": [],
                    }
                },
            )
            active_snapshot_path = snapshot_root / "app-1" / "understanding.json"
            original_payload = json.loads(active_snapshot_path.read_text(encoding="utf-8"))

            invalid_record = compile_instruction_understanding(
                app_id="app-1",
                instruction_text=self._markdown_variant(),
                instruction_uri="instructions/app-1/instructions.md",
                instruction_source_version=4,
                documents=self._documents(),
                repo=repo,
                snapshot_root=snapshot_root,
                semantic_compiler=lambda _context: {},
            )

            self.assertFalse(invalid_record["is_active"])
            self.assertEqual(invalid_record["metadata"]["publish_status"], "diagnostic_only")
            current_active_payload = json.loads(active_snapshot_path.read_text(encoding="utf-8"))
            self.assertEqual(current_active_payload["id"], valid_record["id"])
            self.assertEqual(current_active_payload["instruction_source_version"], 3)
            self.assertEqual(original_payload["id"], current_active_payload["id"])

            attempt_dir = Path(invalid_record["metadata"]["attempt_snapshot_dir_used"])
            self.assertTrue(attempt_dir.exists())
            latest_attempt_payload = json.loads((attempt_dir / "understanding.json").read_text(encoding="utf-8"))
            self.assertEqual(latest_attempt_payload["id"], invalid_record["id"])
            self.assertEqual(invalid_record["metadata"]["snapshot_publish_mode"], "attempt_only")
        finally:
            self._cleanup_root(root)

    def test_invalid_semantic_compile_without_prior_valid_model_stays_diagnostic_only(self):
        root = self._tmp_root("instruction_understanding_invalid_without_prior_valid")
        snapshot_root = root / "snapshots"
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")

            invalid_record = compile_instruction_understanding(
                app_id="app-1",
                instruction_text=self._markdown(),
                instruction_uri="instructions/app-1/instructions.md",
                instruction_source_version=3,
                documents=self._documents(),
                repo=repo,
                snapshot_root=snapshot_root,
                semantic_compiler=lambda _context: {},
            )

            self.assertFalse(invalid_record["is_active"])
            self.assertEqual(invalid_record["metadata"]["publish_status"], "diagnostic_only")
            self.assertFalse(invalid_record["metadata"]["semantic_compile_valid"])
            self.assertIsNone(repo.get_active_compiled("app-1"))
            latest = repo.get_latest_compiled("app-1")
            self.assertEqual(latest["id"], invalid_record["id"])
            self.assertEqual(invalid_record["metadata"]["snapshot_publish_mode"], "attempt_only")
            self.assertFalse((snapshot_root / "app-1" / "understanding.json").exists())
            attempt_dir = Path(invalid_record["metadata"]["attempt_snapshot_dir_used"])
            self.assertTrue((attempt_dir / "understanding.json").exists())
        finally:
            self._cleanup_root(root)

    def test_snapshot_hydration_prefers_newest_valid_snapshot_across_primary_and_fallback_roots(self):
        root = self._tmp_root("instruction_understanding_snapshot_selection")
        primary_snapshot_root = root / "snapshots"
        fallback_snapshot_root = _snapshot_fallback_root()
        app_id = f"snapshot-choice-{uuid.uuid4()}"
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")
            compile_instruction_understanding(
                app_id=app_id,
                instruction_text=self._markdown(),
                instruction_uri=f"instructions/{app_id}/instructions.md",
                instruction_source_version=3,
                documents=self._documents(),
                repo=repo,
                snapshot_root=primary_snapshot_root,
                semantic_compiler=lambda _context: {
                    "app_semantic_model": {
                        "primary_service_mode": "single_default_workflow",
                        "default_workflow_id": "workflow:primary",
                        "service_blocks": [
                            {
                                "block_id": "workflow:primary",
                                "block_type": "primary_workflow",
                                "title": "Primary Snapshot Workflow",
                                "is_default": True,
                            }
                        ],
                        "procedures": [],
                        "procedure_steps": [],
                        "role_profiles": [],
                        "routing_rules": [],
                        "clarification_gate_rules": [],
                    }
                },
            )
            compile_instruction_understanding(
                app_id=app_id,
                instruction_text=self._markdown_variant(),
                instruction_uri=f"instructions/{app_id}/instructions.md",
                instruction_source_version=4,
                documents=self._documents(),
                repo=repo,
                snapshot_root=fallback_snapshot_root,
                semantic_compiler=lambda _context: {
                    "app_semantic_model": {
                        "primary_service_mode": "single_default_workflow",
                        "default_workflow_id": "workflow:fallback",
                        "service_blocks": [
                            {
                                "block_id": "workflow:fallback",
                                "block_type": "primary_workflow",
                                "title": "Fallback Snapshot Workflow",
                                "is_default": True,
                            }
                        ],
                        "procedures": [],
                        "procedure_steps": [],
                        "role_profiles": [],
                        "routing_rules": [],
                        "clarification_gate_rules": [],
                    }
                },
            )
            repo.reset()

            restored = _hydrate_compiled_from_snapshot(
                app_id=app_id,
                repo=repo,
                snapshot_root=primary_snapshot_root,
            )

            self.assertIsNotNone(restored)
            self.assertEqual(restored["instruction_source_version"], 4)
            self.assertEqual(
                restored["compiled_contract"]["hybrid_instruction_runtime_model"]["default_workflow_id"],
                "workflow:fallback",
            )
            self.assertEqual(
                Path(restored["metadata"]["snapshot_root_used"]),
                fallback_snapshot_root,
            )
        finally:
            fallback_app_dir = fallback_snapshot_root / app_id
            if fallback_app_dir.exists():
                for path in sorted(fallback_app_dir.glob("**/*"), reverse=True):
                    if path.is_file():
                        path.unlink()
                    elif path.is_dir():
                        path.rmdir()
                if fallback_app_dir.exists():
                    fallback_app_dir.rmdir()
            self._cleanup_root(root)

    def test_snapshot_hydration_prefers_valid_snapshot_over_newer_invalid_snapshot(self):
        root = self._tmp_root("instruction_understanding_snapshot_validity")
        primary_snapshot_root = root / "snapshots"
        fallback_snapshot_root = _snapshot_fallback_root()
        app_id = f"snapshot-validity-{uuid.uuid4()}"
        try:
            repo = InstructionUnderstandingRepo(root / "runtime_state.db")
            compile_instruction_understanding(
                app_id=app_id,
                instruction_text=self._markdown(),
                instruction_uri=f"instructions/{app_id}/instructions.md",
                instruction_source_version=3,
                documents=self._documents(),
                repo=repo,
                snapshot_root=fallback_snapshot_root,
                semantic_compiler=lambda _context: {
                    "app_semantic_model": {
                        "primary_service_mode": "single_default_workflow",
                        "default_workflow_id": "workflow:valid",
                        "service_blocks": [
                            {
                                "block_id": "workflow:valid",
                                "block_type": "primary_workflow",
                                "title": "Valid Fallback Workflow",
                                "is_default": True,
                            }
                        ],
                        "procedures": [],
                        "procedure_steps": [],
                        "role_profiles": [],
                        "routing_rules": [],
                        "clarification_gate_rules": [],
                    }
                },
            )
            compile_instruction_understanding(
                app_id=app_id,
                instruction_text=self._markdown_variant(),
                instruction_uri=f"instructions/{app_id}/instructions.md",
                instruction_source_version=4,
                documents=self._documents(),
                repo=repo,
                snapshot_root=primary_snapshot_root,
                semantic_compiler=lambda _context: {},
            )
            repo.reset()

            restored = _hydrate_compiled_from_snapshot(
                app_id=app_id,
                repo=repo,
                snapshot_root=primary_snapshot_root,
            )

            self.assertIsNotNone(restored)
            self.assertEqual(restored["instruction_source_version"], 3)
            self.assertTrue(restored["metadata"]["semantic_compile_valid"])
            self.assertEqual(
                restored["compiled_contract"]["hybrid_instruction_runtime_model"]["default_workflow_id"],
                "workflow:valid",
            )
            self.assertEqual(
                Path(restored["metadata"]["snapshot_root_used"]),
                fallback_snapshot_root,
            )
        finally:
            fallback_app_dir = fallback_snapshot_root / app_id
            if fallback_app_dir.exists():
                for path in sorted(fallback_app_dir.glob("**/*"), reverse=True):
                    if path.is_file():
                        path.unlink()
                    elif path.is_dir():
                        path.rmdir()
                if fallback_app_dir.exists():
                    fallback_app_dir.rmdir()
            self._cleanup_root(root)

    def test_validate_semantic_compile_candidate_normalizes_provider_workflow_shape(self):
        semantic_model = {
            "primary_service_mode": "intent_routed_multi_workflow",
            "roles": [
                {
                    "role_id": "church_ministry_prompt_designer",
                    "role_name": "Church Ministry Prompt Designer",
                }
            ],
            "primary_workflows": [
                {
                    "workflow_id": "prompt_generation",
                    "workflow_name": "Interaction Logic & Execution Flow",
                    "is_default": True,
                    "step_sequence": [
                        {
                            "order": 0,
                            "step_id": "clarification",
                            "title": "Clarification",
                            "execution_mode": "interactive",
                        },
                        {
                            "order": 1,
                            "step_id": "core_workflow_execution",
                            "title": "Core Workflow",
                            "execution_mode": "bundled",
                            "bundled_steps": ["routing", "prompt_output"],
                        },
                        {
                            "order": 2,
                            "step_id": "routing",
                            "title": "Routing",
                            "execution_mode": "sequential_fallback",
                        },
                        {
                            "order": 3,
                            "step_id": "prompt_output",
                            "title": "Prompt Output",
                            "execution_mode": "bundled",
                        },
                    ],
                },
                {
                    "workflow_id": "prompt_optimization",
                    "workflow_name": "Optimization",
                    "is_default": False,
                    "step_sequence": [],
                },
                {
                    "workflow_id": "tool_selection",
                    "workflow_name": "Tool Selection",
                    "is_default": False,
                    "step_sequence": [],
                },
            ],
            "routing_rules": [
                {
                    "rule_id": "route_to_optimization",
                    "target_workflow_id": "prompt_optimization",
                },
                {
                    "rule_id": "route_to_tool_selection",
                    "target_workflow_id": "tool_selection",
                },
                {
                    "rule_id": "route_to_prompt_generation",
                    "target_workflow_id": "prompt_generation",
                },
            ],
        }
        validation = _validate_semantic_compile_candidate(
            semantic_model=semantic_model,
            deterministic_contract={
                "resource_reference_catalog": [],
            },
        )
        self.assertTrue(validation["valid"], validation["errors"])
        normalized = validation["normalized"]
        self.assertEqual(len(normalized["service_blocks"]), 3)
        self.assertEqual(len(normalized["role_profiles"]), 1)
        self.assertEqual(len(normalized["procedures"]), 3)
        self.assertTrue(
            any(
                item.get("clarification_step_id") == "clarification"
                and item.get("completion_step_id") == "core_workflow_execution"
                for item in normalized["clarification_gate_rules"]
            )
        )
        core_step = next(
            item for item in normalized["procedure_steps"] if item.get("step_id") == "core_workflow_execution"
        )
        self.assertIn("core_workflow_execution", core_step.get("bundled_step_ids", []))

    def test_validate_semantic_compile_candidate_normalizes_singular_provider_workflow_shape(self):
        semantic_model = {
            "primary_service_mode": "single_default_workflow",
            "global_roles": [
                {
                    "role_id": "role:church",
                    "title": "Church Ministry Prompt Designer",
                    "boundary": {
                        "allowed": ["æ•™æœƒ"],
                        "forbidden": ["æ”¿æ²»"],
                    },
                }
            ],
            "primary_workflow": {
                "workflow_id": "workflow:interaction_logic_execution_flow",
                "title": "Interaction Logic & Execution Flow",
                "is_default": True,
                "steps": [
                    {
                        "step_order": 1,
                        "step_id": "step:clarification",
                        "title": "Clarification",
                        "execution_mode": "interactive",
                    },
                    {
                        "step_order": 2,
                        "step_id": "step:core_workflow_execution",
                        "title": "Core Workflow",
                        "execution_mode": "bundled",
                        "bundled_child_steps": ["step:routing", "step:prompt_output"],
                        "bundled_resource_refs": ["template_library.md"],
                    },
                ],
            },
        }
        validation = _validate_semantic_compile_candidate(
            semantic_model=semantic_model,
            deterministic_contract={
                "resource_reference_catalog": [{"filename": "template_library.md"}],
            },
        )
        self.assertTrue(validation["valid"], validation["errors"])
        normalized = validation["normalized"]
        self.assertEqual(normalized["default_workflow_id"], "workflow:interaction_logic_execution_flow")
        self.assertEqual(len(normalized["service_blocks"]), 1)
        self.assertEqual(len(normalized["role_profiles"]), 1)
        self.assertEqual(len(normalized["procedure_steps"]), 2)

    def test_validate_semantic_compile_candidate_normalizes_list_form_primary_workflow_and_modules(self):
        semantic_model = {
            "primary_service_mode": "single_default_workflow",
            "default_workflow_id": "primary_workflow:interaction_logic_execution_flow",
            "primary_workflow": [
                {
                    "workflow_id": "primary_workflow:interaction_logic_execution_flow",
                    "workflow_title": "Interaction Logic & Execution Flow",
                    "is_default": True,
                    "step_sequence": [
                        {
                            "order": 1,
                            "step_id": "step:clarification",
                            "title": "Clarification",
                            "execution_mode": "interactive",
                        },
                        {
                            "order": 2,
                            "step_id": "step:core_workflow_execution",
                            "title": "Core Workflow",
                            "execution_mode": "bundled",
                            "resource_refs": ["template_library.md"],
                        },
                    ],
                }
            ],
            "support_modules": [
                {
                    "module_id": "support_module:knowledge",
                    "module_title": "Knowledge Modules",
                }
            ],
            "followup_modules": [
                {
                    "module_id": "followup_module:optimization",
                    "module_title": "Optimization Module",
                }
            ],
        }
        validation = _validate_semantic_compile_candidate(
            semantic_model=semantic_model,
            deterministic_contract={
                "resource_reference_catalog": [{"filename": "template_library.md"}],
            },
        )
        self.assertTrue(validation["valid"], validation["errors"])
        normalized = validation["normalized"]
        self.assertEqual(normalized["default_workflow_id"], "primary_workflow:interaction_logic_execution_flow")
        block_ids = {item.get("block_id") for item in normalized["service_blocks"]}
        self.assertIn("primary_workflow:interaction_logic_execution_flow", block_ids)
        self.assertIn("support_module:knowledge", block_ids)
        self.assertIn("followup_module:optimization", block_ids)
        workflow_block = next(
            item for item in normalized["service_blocks"]
            if item.get("block_id") == "primary_workflow:interaction_logic_execution_flow"
        )
        self.assertEqual(workflow_block.get("title"), "Interaction Logic & Execution Flow")

    def test_validate_semantic_compile_candidate_grounds_intent_routed_workflows_from_deterministic_modules(self):
        semantic_model = {
            "primary_service_mode": "intent_routed_multi_workflow",
            "routing_rules": [
                {
                    "rule_id": "route:advice",
                    "target_workflow_id": "wf_3x1_suggestion",
                    "target_role_id": "role_mentor",
                },
                {
                    "rule_id": "route:stepwise",
                    "target_workflow_id": "wf_step_by_step",
                    "target_role_id": "role_coach",
                },
                {
                    "rule_id": "route:deep",
                    "target_workflow_id": "wf_deep_analysis",
                    "target_role_id": "role_partner",
                },
            ],
            "service_blocks": [],
            "procedures": [],
            "procedure_steps": [],
            "role_profiles": [],
            "clarification_gate_rules": [],
        }
        deterministic_contract = {
            "instruction_modules": [
                {
                    "id": "advice_checklist",
                    "title": "3x1 建議清單法",
                    "resource_files": ["advice_checklist.md"],
                    "keywords": ["3x1 建議清單法", "advice checklist"],
                },
                {
                    "id": "step_by_step_guide",
                    "title": "按步就班法",
                    "resource_files": ["step_by_step_guide.md"],
                    "keywords": ["按步就班法", "step by step guide"],
                },
                {
                    "id": "deep_analysis_framework",
                    "title": "深度解析法",
                    "resource_files": [
                        "deep_analysis_framework.md",
                        "emotion_signal_map.md",
                        "boundary_conversation_prompts.md",
                    ],
                    "keywords": ["深度解析法", "deep analysis framework"],
                },
            ],
            "instruction_service_blocks": [],
            "resource_reference_catalog": [
                {"filename": "advice_checklist.md"},
                {"filename": "step_by_step_guide.md"},
                {"filename": "deep_analysis_framework.md"},
                {"filename": "emotion_signal_map.md"},
                {"filename": "boundary_conversation_prompts.md"},
            ],
        }
        validation = _validate_semantic_compile_candidate(
            semantic_model=semantic_model,
            deterministic_contract=deterministic_contract,
        )
        self.assertTrue(validation["valid"], validation["errors"])
        normalized = validation["normalized"]
        workflow_ids = {
            item.get("block_id")
            for item in normalized["service_blocks"]
            if item.get("block_type") == "primary_workflow"
        }
        self.assertIn("workflow:3x1建議清單法", workflow_ids)
        self.assertIn("workflow:按步就班法", workflow_ids)
        self.assertIn("workflow:深度解析法", workflow_ids)
        role_ids = {item.get("role_id") for item in normalized["role_profiles"]}
        self.assertIn("role_mentor", role_ids)
        self.assertIn("role_coach", role_ids)
        self.assertIn("role_partner", role_ids)
        deep_step = next(
            item
            for item in normalized["procedure_steps"]
            if item.get("title") == "深度解析法"
        )
        self.assertEqual(deep_step.get("execution_mode"), "bundled")
        self.assertIn("deep_analysis_framework.md", deep_step.get("bundled_resource_refs", []))

    def test_validate_semantic_compile_candidate_grounds_cross_language_workflow_aliases(self):
        semantic_model = {
            "primary_service_mode": "intent_routed_multi_workflow",
            "routing_rules": [
                {
                    "rule_id": "route:mentor",
                    "target_workflow_id": "wf_deep_analysis",
                    "target_role_id": "role:mentor",
                },
                {
                    "rule_id": "route:tutor",
                    "target_module_id": "module:bible_study",
                    "target_role_id": "role:tutor",
                },
                {
                    "rule_id": "route:multi",
                    "target_workflow_id": "wf_multi_layer_orchestration",
                },
            ],
            "service_blocks": [{"block_id": "module:bible_study", "block_type": "support_module", "title": "??????"}],
            "procedures": [],
            "procedure_steps": [],
            "role_profiles": [
                {"role_id": "role:mentor", "name": "Mentor"},
                {"role_id": "role:tutor", "name": "Tutor"},
            ],
            "clarification_gate_rules": [],
        }
        deterministic_contract = {
            "instruction_modules": [
                {
                    "id": "deep_analysis_framework",
                    "title": "深度解析法",
                    "resource_files": ["deep_analysis_framework.md"],
                    "keywords": ["深度解析法", "deep analysis framework"],
                }
            ],
            "instruction_service_blocks": [
                {
                    "block_id": "primary_workflow:多重需求分層規則",
                    "block_type": "primary_workflow",
                    "title": "多重需求分層規則",
                    "body_text": "採分層回應流程。",
                    "resource_refs": [],
                },
                {
                    "block_id": "supplementary_workflow:查經互動模組",
                    "block_type": "supplementary_workflow",
                    "title": "查經互動模組（歸納釋經法）",
                    "body_text": "適用於查經與歸納釋經法。",
                    "resource_refs": ["歸納釋經法 102025.pdf"],
                },
            ],
            "instruction_procedures": [],
            "procedure_steps": [],
            "resource_reference_catalog": [
                {"filename": "deep_analysis_framework.md"},
                {"filename": "歸納釋經法 102025.pdf"},
            ],
        }
        validation = _validate_semantic_compile_candidate(
            semantic_model=semantic_model,
            deterministic_contract=deterministic_contract,
        )
        self.assertTrue(validation["valid"], validation["errors"])
        workflow_ids = {
            item.get("block_id")
            for item in validation["normalized"]["service_blocks"]
            if item.get("block_type") == "primary_workflow"
        }
        self.assertIn("workflow:深度解析法", workflow_ids)
        self.assertNotIn("workflow:multi_layer_orchestration", workflow_ids)
        module_ids = {
            item.get("block_id")
            for item in validation["normalized"]["service_blocks"]
            if item.get("block_type") == "support_module"
        }
        self.assertIn("support_module:bible_study", module_ids)
        logic_titles = {
            str(item.get("title") or "").strip()
            for item in validation["normalized"]["interaction_logic_blocks"]
            if isinstance(item, dict)
        }
        self.assertIn("多重需求分層規則", logic_titles)
        role_ids = {item.get("role_id") for item in validation["normalized"]["role_profiles"]}
        self.assertIn("role:mentor", role_ids)
        self.assertIn("role:tutor", role_ids)


    def test_validate_semantic_compile_candidate_keeps_multi_layer_orchestration_in_logic_and_distinct_child_workflows(self):
        semantic_model = {
            "primary_service_mode": "intent_routed_multi_workflow",
            "routing_rules": [
                {"rule_id": "route:mentor", "target_role_id": "role:mentor", "target_workflow_id": "wf:deep_analysis"},
                {"rule_id": "route:coach", "target_role_id": "role:coach", "target_workflow_id": "wf:coach_step_by_step"},
                {"rule_id": "route:consultant", "target_role_id": "role:consultant", "target_workflow_id": "wf:consultant_3x1"},
                {"rule_id": "route:tutor", "target_role_id": "role:tutor", "target_module_id": "module:bible_study"},
                {"rule_id": "route:orchestrator", "target_workflow_id": "workflow:多重需求分層規則"},
            ],
            "service_blocks": [{"block_id": "module:bible_study", "block_type": "support_module", "title": "??????"}],
            "procedures": [],
            "procedure_steps": [],
            "role_profiles": [
                {"role_id": "role:mentor", "name": "Mentor"},
                {"role_id": "role:coach", "name": "Coach"},
                {"role_id": "role:consultant", "name": "Consultant"},
                {"role_id": "role:tutor", "name": "Tutor"},
            ],
            "clarification_gate_rules": [],
        }
        deterministic_contract = {
            "instruction_workflows": [
                {
                    "id": "多重需求分層規則",
                    "title": "多重需求分層規則",
                    "workflow_name": "多重需求分層規則",
                    "steps": [
                        {"order": 1, "title": "Mentor 層"},
                        {"order": 2, "title": "Coach/Consultant 層"},
                        {"order": 3, "title": "Tutor/Partner 層"},
                    ],
                }
            ],
            "instruction_modules": [
                {
                    "id": "deep_analysis_framework",
                    "title": "深度解析法",
                    "resource_files": [
                        "deep_analysis_framework.md",
                        "emotion_signal_map.md",
                        "boundary_conversation_prompts.md",
                    ],
                    "keywords": ["深度解析法", "deep analysis framework"],
                },
                {
                    "id": "step_by_step_guide",
                    "title": "按步就班法",
                    "resource_files": ["step_by_step_guide.md"],
                    "keywords": ["按步就班法", "step by step guide"],
                },
                {
                    "id": "advice_checklist",
                    "title": "3x1 建議清單法",
                    "resource_files": ["advice_checklist.md"],
                    "keywords": ["3x1 建議清單法", "advice checklist"],
                },
            ],
            "instruction_service_blocks": [
                {
                    "block_id": "supplementary_workflow:查經互動模組",
                    "block_type": "supplementary_workflow",
                    "title": "查經互動模組（歸納釋經法的十個步驟）",
                    "body_text": "適用於查經與歸納釋經法。",
                    "resource_refs": ["歸納釋經法 102025.pdf"],
                }
            ],
            "instruction_procedures": [],
            "procedure_steps": [],
            "resource_reference_catalog": [
                {"filename": "deep_analysis_framework.md"},
                {"filename": "emotion_signal_map.md"},
                {"filename": "boundary_conversation_prompts.md"},
                {"filename": "step_by_step_guide.md"},
                {"filename": "advice_checklist.md"},
                {"filename": "歸納釋經法 102025.pdf"},
            ],
        }

        validation = _validate_semantic_compile_candidate(
            semantic_model=semantic_model,
            deterministic_contract=deterministic_contract,
        )

        self.assertTrue(validation["valid"], validation["errors"])
        blocks = {
            item.get("block_id"): item
            for item in validation["normalized"]["service_blocks"]
            if isinstance(item, dict)
        }
        self.assertNotIn("workflow:多重需求分層規則", blocks)
        self.assertEqual(blocks["workflow:深度解析法"]["title"], "深度解析法")
        self.assertEqual(blocks["workflow:按步就班法"]["title"], "按步就班法")
        self.assertEqual(blocks["workflow:3x1建議清單法"]["title"], "3x1 建議清單法")
        self.assertEqual(blocks["support_module:bible_study"]["title"], "bible_study")
        logic_titles = {
            str(item.get("title") or "").strip()
            for item in validation["normalized"]["interaction_logic_blocks"]
            if isinstance(item, dict)
        }
        self.assertIn("多重需求分層規則", logic_titles)
        self.assertFalse(
            any(
                isinstance(item, dict) and str(item.get("rule_id") or "").strip() == "route:orchestrator"
                for item in validation["normalized"]["routing_rules"]
            )
        )


    def test_validate_semantic_compile_candidate_normalizes_failed_wf_alias_routes_to_grounded_child_workflows(self):
        semantic_model = {
            "primary_service_mode": "intent_routed_multi_workflow",
            "routing_rules": [
                {"rule_id": "route:mentor", "target_role_id": "role:mentor", "target_workflow_id": "wf:deep_analysis"},
                {"rule_id": "route:coach", "target_role_id": "role:coach", "target_workflow_id": "wf:coach_step_by_step"},
                {"rule_id": "route:consultant", "target_role_id": "role:consultant", "target_workflow_id": "wf:consultant_3x1"},
                {"rule_id": "route:partner", "target_role_id": "role:partner", "target_workflow_id": "wf:partner_step_by_step_plus"},
                {"rule_id": "route:tutor", "target_role_id": "role:tutor", "target_module_id": "module:bible_study"},
            ],
            "service_blocks": [{"block_id": "module:bible_study", "block_type": "support_module", "title": "??????"}],
            "procedures": [],
            "procedure_steps": [],
            "role_profiles": [
                {"role_id": "role:mentor", "name": "Mentor"},
                {"role_id": "role:coach", "name": "Coach"},
                {"role_id": "role:consultant", "name": "Consultant"},
                {"role_id": "role:partner", "name": "Partner"},
                {"role_id": "role:tutor", "name": "Tutor"},
            ],
            "clarification_gate_rules": [],
        }
        deterministic_contract = {
            "instruction_modules": [
                {
                    "id": "deep_analysis_framework",
                    "title": "深度解析法",
                    "resource_files": [
                        "deep_analysis_framework.md",
                        "emotion_signal_map.md",
                        "boundary_conversation_prompts.md",
                    ],
                    "keywords": ["深度解析法", "deep analysis framework"],
                },
                {
                    "id": "step_by_step_guide",
                    "title": "按步就班法",
                    "resource_files": ["step_by_step_guide.md"],
                    "keywords": ["按步就班法", "step by step guide"],
                },
                {
                    "id": "advice_checklist",
                    "title": "3x1 建議清單法",
                    "resource_files": ["advice_checklist.md"],
                    "keywords": ["3x1 建議清單法", "advice checklist"],
                },
            ],
            "instruction_service_blocks": [
                {
                    "block_id": "supplementary_workflow:查經互動模組",
                    "block_type": "supplementary_workflow",
                    "title": "查經互動模組（歸納釋經法的十個步驟）",
                    "body_text": "適用於查經與歸納釋經法。",
                    "resource_refs": ["歸納釋經法 102025.pdf"],
                }
            ],
            "instruction_procedures": [],
            "procedure_steps": [],
            "resource_reference_catalog": [
                {"filename": "deep_analysis_framework.md"},
                {"filename": "emotion_signal_map.md"},
                {"filename": "boundary_conversation_prompts.md"},
                {"filename": "step_by_step_guide.md"},
                {"filename": "advice_checklist.md"},
                {"filename": "歸納釋經法 102025.pdf"},
            ],
        }

        validation = _validate_semantic_compile_candidate(
            semantic_model=semantic_model,
            deterministic_contract=deterministic_contract,
        )

        self.assertTrue(validation["valid"], validation["errors"])
        blocks = {
            item.get("block_id"): item
            for item in validation["normalized"]["service_blocks"]
            if isinstance(item, dict)
        }
        self.assertIn("workflow:深度解析法", blocks)
        self.assertIn("workflow:按步就班法", blocks)
        self.assertIn("workflow:3x1建議清單法", blocks)
        self.assertIn("support_module:bible_study", blocks)
        self.assertEqual(blocks["workflow:按步就班法"]["title"], "按步就班法")
        self.assertEqual(blocks["workflow:3x1建議清單法"]["title"], "3x1 建議清單法")
        self.assertEqual(blocks["support_module:bible_study"]["title"], "bible_study")

        route_targets = {
            str(item.get("rule_id") or "").strip(): str(item.get("target_workflow_id") or "").strip()
            for item in validation["normalized"]["routing_rules"]
            if isinstance(item, dict)
        }
        self.assertEqual(route_targets["route:mentor"], "workflow:深度解析法")
        self.assertEqual(route_targets["route:coach"], "workflow:按步就班法")
        self.assertEqual(route_targets["route:consultant"], "workflow:3x1建議清單法")
        self.assertEqual(route_targets["route:partner"], "workflow:按步就班法")
        self.assertEqual(
            next(
                str(item.get("target_module_id") or "").strip()
                for item in validation["normalized"]["routing_rules"]
                if str(item.get("rule_id") or "").strip() == "route:tutor"
            ),
            "support_module:bible_study",
        )


    def test_validate_semantic_compile_candidate_accepts_new_workflow_aliases_for_3x1_and_step_by_step(self):
        semantic_model = {
            "primary_service_mode": "intent_routed_multi_workflow",
            "routing_rules": [
                {
                    "rule_id": "route:consultant",
                    "target_role_id": "role:consultant",
                    "target_workflow_id": "workflow:3x1_advice",
                },
                {
                    "rule_id": "route:coach",
                    "target_role_id": "role:coach",
                    "target_workflow_id": "workflow:step_by_step",
                },
                {
                    "rule_id": "route:partner",
                    "target_role_id": "role:partner",
                    "target_workflow_id": "workflow:step_by_step",
                },
            ],
            "service_blocks": [],
            "procedures": [],
            "procedure_steps": [],
            "role_profiles": [],
            "clarification_gate_rules": [],
        }
        deterministic_contract = {
            "instruction_modules": [
                {
                    "id": "step_by_step_guide",
                    "title": "按步就班法",
                    "resource_files": ["step_by_step_guide.md"],
                    "keywords": ["按步就班法", "step by step guide"],
                },
                {
                    "id": "advice_checklist",
                    "title": "3x1 建議清單法",
                    "resource_files": ["advice_checklist.md"],
                    "keywords": ["3x1 建議清單法", "advice checklist"],
                },
            ],
            "instruction_service_blocks": [],
            "instruction_procedures": [],
            "procedure_steps": [],
            "resource_reference_catalog": [
                {"filename": "step_by_step_guide.md"},
                {"filename": "advice_checklist.md"},
            ],
        }

        validation = _validate_semantic_compile_candidate(
            semantic_model=semantic_model,
            deterministic_contract=deterministic_contract,
        )

        self.assertTrue(validation["valid"], validation["errors"])
        blocks = {
            item.get("block_id"): item
            for item in validation["normalized"]["service_blocks"]
            if isinstance(item, dict)
        }
        self.assertIn("workflow:3x1建議清單法", blocks)
        self.assertIn("workflow:按步就班法", blocks)
        self.assertEqual(blocks["workflow:3x1建議清單法"]["title"], "3x1 建議清單法")
        self.assertEqual(blocks["workflow:按步就班法"]["title"], "按步就班法")

    def test_validate_semantic_compile_candidate_accepts_suggestion_list_and_step_by_step_method_aliases(self):
        semantic_model = {
            "primary_service_mode": "intent_routed_multi_workflow",
            "routing_rules": [
                {
                    "rule_id": "route:consultant",
                    "target_role_id": "role:consultant",
                    "target_workflow_id": "workflow:3x1_suggestion_list",
                },
                {
                    "rule_id": "route:coach",
                    "target_role_id": "role:coach",
                    "target_workflow_id": "workflow:step_by_step_method",
                },
            ],
            "service_blocks": [],
            "procedures": [],
            "procedure_steps": [],
            "role_profiles": [],
            "clarification_gate_rules": [],
        }
        deterministic_contract = {
            "instruction_modules": [
                {
                    "id": "step_by_step_guide",
                    "title": "按步就班法",
                    "resource_files": ["step_by_step_guide.md"],
                    "keywords": ["按步就班法", "step by step guide"],
                },
                {
                    "id": "advice_checklist",
                    "title": "3x1 建議清單法",
                    "resource_files": ["advice_checklist.md"],
                    "keywords": ["3x1 建議清單法", "advice checklist"],
                },
            ],
            "instruction_service_blocks": [],
            "instruction_procedures": [],
            "procedure_steps": [],
            "resource_reference_catalog": [
                {"filename": "step_by_step_guide.md"},
                {"filename": "advice_checklist.md"},
            ],
        }

        validation = _validate_semantic_compile_candidate(
            semantic_model=semantic_model,
            deterministic_contract=deterministic_contract,
        )

        self.assertTrue(validation["valid"], validation["errors"])
        blocks = {
            item.get("block_id"): item
            for item in validation["normalized"]["service_blocks"]
            if isinstance(item, dict)
        }
        self.assertIn("workflow:3x1建議清單法", blocks)
        self.assertIn("workflow:按步就班法", blocks)
        self.assertEqual(blocks["workflow:3x1建議清單法"]["title"], "3x1 建議清單法")
        self.assertEqual(blocks["workflow:按步就班法"]["title"], "按步就班法")

    def test_validate_semantic_compile_candidate_resolves_partner_route_to_explicit_base_workflow_when_no_family_workflow_exists(self):
        semantic_model = {
            "primary_service_mode": "intent_routed_multi_workflow",
            "routing_rules": [
                {
                    "rule_id": "route:coach",
                    "target_role_id": "role:coach",
                    "target_workflow_id": "wf:step_by_step_helper",
                },
                {
                    "rule_id": "route:partner",
                    "target_role_id": "role:partner",
                    "target_workflow_id": "wf:partner_step_by_step_plus",
                },
            ],
            "service_blocks": [],
            "procedures": [],
            "procedure_steps": [],
            "role_profiles": [],
            "clarification_gate_rules": [],
        }
        deterministic_contract = {
            "instruction_modules": [],
            "instruction_workflows": [
                {
                    "id": "互動模式與流程",
                    "title": "互動模式與流程",
                    "workflow_name": "互動模式與流程",
                    "steps": [
                        {"order": 1, "title": "按步就班法流程（循序反思模式）"},
                    ],
                },
            ],
            "instruction_service_blocks": [],
            "instruction_procedures": [],
            "procedure_steps": [],
            "resource_reference_catalog": [],
        }

        validation = _validate_semantic_compile_candidate(
            semantic_model=semantic_model,
            deterministic_contract=deterministic_contract,
        )

        self.assertTrue(validation["valid"], validation["errors"])
        route_targets = {
            str(item.get("rule_id") or "").strip(): str(item.get("target_workflow_id") or "").strip()
            for item in validation["normalized"]["routing_rules"]
            if isinstance(item, dict)
        }
        self.assertEqual(route_targets["route:coach"], "workflow:按步就班法")
        self.assertEqual(route_targets["route:partner"], "workflow:按步就班法")
        blocks = {
            item.get("block_id"): item
            for item in validation["normalized"]["service_blocks"]
            if isinstance(item, dict)
        }
        self.assertIn("workflow:按步就班法", blocks)
        self.assertNotIn("workflow:親子靈修", blocks)

    def test_validate_semantic_compile_candidate_prefers_explicit_family_workflow_when_authored(self):
        semantic_model = {
            "primary_service_mode": "intent_routed_multi_workflow",
            "routing_rules": [
                {
                    "rule_id": "route:partner",
                    "target_role_id": "role:partner",
                    "target_workflow_id": "wf:partner_step_by_step_plus",
                },
            ],
            "service_blocks": [],
            "procedures": [],
            "procedure_steps": [],
            "role_profiles": [],
            "clarification_gate_rules": [],
        }
        deterministic_contract = {
            "instruction_modules": [],
            "instruction_workflows": [
                {
                    "id": "互動模式與流程",
                    "title": "互動模式與流程",
                    "workflow_name": "互動模式與流程",
                    "steps": [
                        {"order": 1, "title": "按步就班法流程（循序反思模式）"},
                        {"order": 2, "title": "親子靈修流程（家庭活動模式）"},
                    ],
                },
            ],
            "instruction_service_blocks": [],
            "instruction_procedures": [],
            "procedure_steps": [],
            "resource_reference_catalog": [],
        }

        validation = _validate_semantic_compile_candidate(
            semantic_model=semantic_model,
            deterministic_contract=deterministic_contract,
        )

        self.assertTrue(validation["valid"], validation["errors"])
        route_targets = {
            str(item.get("rule_id") or "").strip(): str(item.get("target_workflow_id") or "").strip()
            for item in validation["normalized"]["routing_rules"]
            if isinstance(item, dict)
        }
        self.assertEqual(route_targets["route:partner"], "workflow:親子靈修")
        blocks = {
            item.get("block_id"): item
            for item in validation["normalized"]["service_blocks"]
            if isinstance(item, dict)
        }
        self.assertIn("workflow:親子靈修", blocks)

    def test_validate_semantic_compile_candidate_leaves_ambiguous_unresolved_alias_failing_clearly(self):
        semantic_model = {
            "primary_service_mode": "intent_routed_multi_workflow",
            "routing_rules": [
                {
                    "rule_id": "route:coach",
                    "target_role_id": "role:coach",
                    "target_workflow_id": "wf:unmapped_growth_path",
                }
            ],
            "service_blocks": [],
            "procedures": [],
            "procedure_steps": [],
            "role_profiles": [],
            "clarification_gate_rules": [],
        }
        deterministic_contract = {
            "instruction_modules": [
                {
                    "id": "step_by_step_guide",
                    "title": "?????",
                    "resource_files": ["step_by_step_guide.md"],
                    "keywords": ["?????", "step by step guide"],
                },
                {
                    "id": "guided_path",
                    "title": "?????",
                    "resource_files": ["guided_path.md"],
                    "keywords": ["?????", "guided step by step"],
                },
            ],
            "instruction_service_blocks": [],
            "instruction_procedures": [],
            "procedure_steps": [],
            "resource_reference_catalog": [
                {"filename": "step_by_step_guide.md"},
                {"filename": "guided_path.md"},
            ],
        }

        validation = _validate_semantic_compile_candidate(
            semantic_model=semantic_model,
            deterministic_contract=deterministic_contract,
        )

        self.assertFalse(validation["valid"])
        self.assertIn(
            "routing rule references unknown workflow id: workflow:unmapped_growth_path",
            validation["errors"],
        )


    def test_validate_semantic_compile_candidate_rewrites_semantic_proc_ids_to_canonical_procedure_ids(self):
        semantic_model = {
            "primary_service_mode": "intent_routed_multi_workflow",
            "routing_rules": [
                {"rule_id": "route:consultant", "target_role_id": "role:consultant", "target_workflow_id": "workflow:3x1_suggestion_list"},
                {"rule_id": "route:coach", "target_role_id": "role:coach", "target_workflow_id": "workflow:step_by_step_method"},
                {"rule_id": "route:mentor", "target_role_id": "role:mentor", "target_workflow_id": "workflow:deep_analysis"},
            ],
            "service_blocks": [],
            "procedures": [],
            "procedure_steps": [
                {"procedure_id": "proc_3x1_suggestion", "step_id": "step:3x1:1", "title": "3x1 advice", "order": 1, "execution_mode": "interactive", "resource_refs": ["advice_checklist.md"]},
                {"procedure_id": "proc_step_by_step", "step_id": "step:stepwise:1", "title": "Step by step", "order": 1, "execution_mode": "interactive", "resource_refs": ["step_by_step_guide.md"]},
                {"procedure_id": "proc_deep_analysis", "step_id": "step:deep:1", "title": "Deep analysis", "order": 1, "execution_mode": "bundled", "bundled_step_ids": ["step:deep:1"], "bundled_resource_refs": ["deep_analysis_framework.md", "emotion_signal_map.md"]},
            ],
            "role_profiles": [],
            "clarification_gate_rules": [],
        }
        deterministic_contract = {
            "instruction_modules": [
                {"id": "step_by_step_guide", "title": "按步就班法", "resource_files": ["step_by_step_guide.md"], "keywords": ["按步就班法", "step by step guide"]},
                {"id": "advice_checklist", "title": "3x1 建議清單法", "resource_files": ["advice_checklist.md"], "keywords": ["3x1 建議清單法", "advice checklist"]},
                {"id": "deep_analysis_framework", "title": "深度解析法", "resource_files": ["deep_analysis_framework.md", "emotion_signal_map.md"], "keywords": ["深度解析法", "deep analysis framework"]},
            ],
            "instruction_service_blocks": [],
            "instruction_procedures": [],
            "procedure_steps": [],
            "resource_reference_catalog": [
                {"filename": "step_by_step_guide.md"},
                {"filename": "advice_checklist.md"},
                {"filename": "deep_analysis_framework.md"},
                {"filename": "emotion_signal_map.md"},
            ],
        }

        validation = _validate_semantic_compile_candidate(
            semantic_model=semantic_model,
            deterministic_contract=deterministic_contract,
        )

        self.assertTrue(validation["valid"], validation["errors"])
        procedures = {
            item.get("procedure_id"): item
            for item in validation["normalized"]["procedures"]
            if isinstance(item, dict)
        }
        self.assertIn("procedure:workflow_3x1建議清單法", procedures)
        self.assertIn("procedure:workflow_按步就班法", procedures)
        self.assertIn("procedure:workflow_深度解析法", procedures)
        step_proc_ids = {
            str(item.get("procedure_id") or "").strip()
            for item in validation["normalized"]["procedure_steps"]
            if isinstance(item, dict)
        }
        self.assertIn("procedure:workflow_按步就班法", step_proc_ids)
        self.assertIn("procedure:workflow_深度解析法", step_proc_ids)
        self.assertIn("procedure:workflow_3x1建議清單法", step_proc_ids)


    def test_mixed_mode_validator_allows_conversational_route_without_procedure_steps_when_interaction_logic_exists(self):
        semantic_model = {
            "primary_service_mode": "intent_routed_multi_workflow",
            "service_blocks": [
                {
                    "block_id": "wf_theology_discussion",
                    "block_type": "primary_workflow",
                    "title": "Theology Discussion",
                }
            ],
            "procedures": [],
            "procedure_steps": [],
            "routing_rules": [
                {
                    "rule_id": "route:theology_discussion",
                    "target_workflow_id": "wf_theology_discussion",
                }
            ],
            "interaction_logic_blocks": [
                {
                    "block_id": "mode:theology_discussion",
                    "title": "Theology Discussion",
                    "entry_response_contract": {
                        "opening_prompt": "Clarify the theological question before answering."
                    },
                }
            ],
            "role_profiles": [],
            "clarification_gate_rules": [],
        }
        deterministic_contract = {
            "instruction_modules": [],
            "instruction_service_blocks": [
                {
                    "block_id": "primary_workflow:Theology Discussion",
                    "block_type": "primary_workflow",
                    "title": "Theology Discussion",
                    "body_text": "Use contextual theological discussion with user interaction logic.",
                    "resource_refs": ["theology_discussion_guide.md"],
                }
            ],
            "instruction_procedures": [],
            "procedure_steps": [],
            "resource_reference_catalog": [{"filename": "theology_discussion_guide.md"}],
        }

        validation = _validate_semantic_compile_candidate(
            semantic_model=semantic_model,
            deterministic_contract=deterministic_contract,
        )
        self.assertTrue(validation["valid"], validation["errors"])

    def test_mixed_mode_validator_grounds_procedural_route_from_deterministic_block_when_alias_matches(self):
        semantic_model = {
            "primary_service_mode": "intent_routed_multi_workflow",
            "service_blocks": [
                {
                    "block_id": "wf_bible_study",
                    "block_type": "primary_workflow",
                    "title": "Bible Study",
                }
            ],
            "procedures": [
                {
                    "procedure_id": "wf_bible_study",
                    "service_block_id": "wf_bible_study",
                    "title": "Bible Study",
                }
            ],
            "procedure_steps": [],
            "routing_rules": [
                {
                    "rule_id": "route:bible_study",
                    "target_workflow_id": "wf_bible_study",
                }
            ],
            "interaction_logic_blocks": [],
            "role_profiles": [],
            "clarification_gate_rules": [],
        }
        deterministic_contract = {
            "instruction_modules": [],
            "instruction_service_blocks": [
                {
                    "block_id": "primary_workflow:Bible Study",
                    "block_type": "primary_workflow",
                    "title": "Bible Study",
                    "body_text": "Follow the full inductive Bible study workflow.",
                    "resource_refs": ["observation_guide.md"],
                }
            ],
            "instruction_procedures": [
                {
                    "procedure_id": "procedure:bible_study",
                    "service_block_id": "primary_workflow:Bible Study",
                    "title": "Bible Study",
                }
            ],
            "procedure_steps": [],
            "resource_reference_catalog": [{"filename": "observation_guide.md"}],
        }

        validation = _validate_semantic_compile_candidate(
            semantic_model=semantic_model,
            deterministic_contract=deterministic_contract,
        )
        self.assertTrue(validation["valid"], validation["errors"])
        workflow_ids = {
            item.get("block_id")
            for item in validation["normalized"]["service_blocks"]
            if item.get("block_type") == "primary_workflow"
        }
        self.assertIn("workflow:bible_study", workflow_ids)
        step_ids = {
            item.get("step_id")
            for item in validation["normalized"]["procedure_steps"]
            if isinstance(item, dict)
        }
        self.assertIn("step:workflow_bible_study:1", step_ids)

    def test_compile_contract_treats_module_title_marker_as_authoritative(self):
        contract = _compile_contract(
            """
## æ¥ç¶äºåæ¨¡çµ
1. è§å¯ç¶æ
Use observation_guide.md.
2. è§£éç¶æ
Use interpretation_guide.md.
""".strip(),
            [
                {"filename": "observation_guide.md"},
                {"filename": "interpretation_guide.md"},
            ],
        )

        workflow_titles = {
            str(item.get("title") or "").strip()
            for item in contract.get("instruction_workflows", []) or []
            if isinstance(item, dict)
        }
        self.assertNotIn("查經互動模組", workflow_titles)
        block_types = {
            str(item.get("title") or "").strip(): str(item.get("block_type") or "").strip()
            for item in contract.get("instruction_service_blocks", []) or []
            if isinstance(item, dict)
        }
        self.assertEqual(block_types.get("查經互動模組"), "support_module")

    def test_compile_contract_treats_workflow_title_marker_as_authoritative(self):
        contract = _compile_contract(
            """
## 深度解析流程
1. 先觀察情境
Use deep_analysis_framework.md.
2. 再整理建議
Use advice_checklist.md.
""".strip(),
            [
                {"filename": "deep_analysis_framework.md"},
                {"filename": "advice_checklist.md"},
            ],
        )

        workflow_titles = {
            str(item.get("title") or "").strip()
            for item in contract.get("instruction_workflows", []) or []
            if isinstance(item, dict)
        }
        self.assertIn("深度解析流程", workflow_titles)
        block_types = {
            str(item.get("title") or "").strip(): str(item.get("block_type") or "").strip()
            for item in contract.get("instruction_service_blocks", []) or []
            if isinstance(item, dict)
        }
        self.assertEqual(block_types.get("深度解析流程"), "primary_workflow")

    def test_validate_semantic_compile_candidate_rejects_ambiguous_module_workflow_title_markers(self):
        contract = _compile_contract(
            """
## 查經互動模組 Workflow
1. 觀察經文
Use observation_guide.md.
2. 解釋經文
Use interpretation_guide.md.
""".strip(),
            [
                {"filename": "observation_guide.md"},
                {"filename": "interpretation_guide.md"},
            ],
        )

        validation = _validate_semantic_compile_candidate(
            semantic_model={
                "primary_service_mode": "single_default_workflow",
                "default_workflow_id": "workflow:default",
                "service_blocks": [
                    {
                        "block_id": "workflow:default",
                        "block_type": "primary_workflow",
                        "title": "Default Workflow",
                        "is_default": True,
                    }
                ],
                "procedures": [
                    {
                        "procedure_id": "procedure:default",
                        "service_block_id": "workflow:default",
                        "title": "Default Workflow",
                    }
                ],
                "procedure_steps": [
                    {
                        "step_id": "step:default:1",
                        "procedure_id": "procedure:default",
                        "title": "Default Step",
                        "execution_mode": "interactive",
                        "resource_refs": ["observation_guide.md"],
                    }
                ],
                "role_profiles": [],
                "routing_rules": [],
                "clarification_gate_rules": [],
            },
            deterministic_contract=contract,
        )

        self.assertFalse(validation["valid"])
        self.assertIn(
            "ambiguous section title contains both module and workflow markers: 查經互動模組 Workflow",
            validation["errors"],
        )


    def test_validate_semantic_compile_candidate_synthesizes_steps_for_workflow_titled_routes(self):
        contract = _compile_contract(
            """
## 3x1 建議清單法流程
1. 提供建議技巧
Use advice_checklist.md.
2. 立即行動
Use action_reminder.md.

## 按步就班法流程
1. 現況
Use step_by_step_guide.md.
2. 行動
Use family_plan_template.md.

## 深度解析法流程
1. 敘述經驗
Use deep_analysis_framework.md.
2. 信仰對話
Use scripture_reflection.md.
""".strip(),
            [
                {"filename": "advice_checklist.md"},
                {"filename": "action_reminder.md"},
                {"filename": "step_by_step_guide.md"},
                {"filename": "family_plan_template.md"},
                {"filename": "deep_analysis_framework.md"},
                {"filename": "scripture_reflection.md"},
            ],
        )

        validation = _validate_semantic_compile_candidate(
            semantic_model={
                "primary_service_mode": "intent_routed_multi_workflow",
                "service_blocks": [
                    {"block_id": "workflow:3x1_advice", "block_type": "primary_workflow", "title": "3x1 建議清單流程"},
                    {"block_id": "workflow:step_by_step", "block_type": "primary_workflow", "title": "按步就班法流程"},
                    {"block_id": "workflow:deep_analysis", "block_type": "primary_workflow", "title": "深度解析法流程"},
                ],
                "procedures": [
                    {"procedure_id": "proc_3x1", "service_block_id": "workflow:3x1_advice", "title": "3x1 建議清單流程"},
                    {"procedure_id": "proc_stepwise", "service_block_id": "workflow:step_by_step", "title": "按步就班法流程"},
                    {"procedure_id": "proc_deep", "service_block_id": "workflow:deep_analysis", "title": "深度解析法流程"},
                ],
                "procedure_steps": [],
                "role_profiles": [
                    {"role_id": "role:consultant", "name": "Consultant"},
                    {"role_id": "role:coach", "name": "Coach"},
                    {"role_id": "role:mentor", "name": "Mentor"},
                ],
                "routing_rules": [
                    {"rule_id": "route:consultant", "target_role_id": "role:consultant", "target_workflow_id": "workflow:3x1_advice"},
                    {"rule_id": "route:coach", "target_role_id": "role:coach", "target_workflow_id": "workflow:step_by_step"},
                    {"rule_id": "route:mentor", "target_role_id": "role:mentor", "target_workflow_id": "workflow:deep_analysis"},
                ],
                "clarification_gate_rules": [],
            },
            deterministic_contract=contract,
        )

        self.assertTrue(validation["valid"], validation["errors"])
        normalized_step_ids = {
            str(item.get("step_id") or "").strip()
            for item in validation["normalized"]["procedure_steps"]
            if isinstance(item, dict)
        }
        self.assertIn("step:workflow_3x1建議清單法:1", normalized_step_ids)
        self.assertIn("step:workflow_按步就班法:1", normalized_step_ids)
        self.assertIn("step:workflow_深度解析法:1", normalized_step_ids)


    def test_validate_semantic_compile_candidate_preserves_module_owned_procedure_for_executable_module_route(self):
        contract = _compile_contract(
            """
## 查經互動模組
1. 觀察經文
Use observation_guide.md.
2. 解釋經文
Use interpretation_guide.md.
""".strip(),
            [
                {"filename": "observation_guide.md"},
                {"filename": "interpretation_guide.md"},
            ],
        )

        validation = _validate_semantic_compile_candidate(
            semantic_model={
                "primary_service_mode": "intent_routed_multi_workflow",
                "service_blocks": [
                    {"block_id": "workflow:deep_analysis", "block_type": "primary_workflow", "title": "深度解析法流程"},
                    {"block_id": "module_查經互動模組", "block_type": "support_module", "title": "查經互動模組"},
                ],
                "procedures": [
                    {"procedure_id": "proc_deep_analysis", "service_block_id": "workflow:deep_analysis", "title": "深度解析法流程"},
                    {"procedure_id": "procedure:module_查經互動模組", "service_block_id": "module_查經互動模組", "title": "查經互動模組"},
                ],
                "procedure_steps": [],
                "role_profiles": [
                    {"role_id": "role:tutor", "name": "Tutor"},
                    {"role_id": "role:mentor", "name": "Mentor"},
                ],
                "routing_rules": [
                    {"rule_id": "route:mentor", "target_role_id": "role:mentor", "target_workflow_id": "workflow:deep_analysis"},
                    {"rule_id": "route:tutor", "target_role_id": "role:tutor", "target_module_id": "module_查經互動模組"},
                ],
                "clarification_gate_rules": [],
            },
            deterministic_contract=contract,
        )

        self.assertTrue(validation["valid"], validation["errors"])
        procedure_block_ids = {
            str(item.get("service_block_id") or "").strip()
            for item in validation["normalized"]["procedures"]
            if isinstance(item, dict)
        }
        self.assertIn("support_module:查經互動模組", procedure_block_ids)
        procedure_ids = {
            str(item.get("procedure_id") or "").strip()
            for item in validation["normalized"]["procedures"]
            if isinstance(item, dict)
        }
        self.assertIn("procedure:support_module_查經互動模組", procedure_ids)
        self.assertEqual(
            [
                str(item.get("target_module_id") or "").strip()
                for item in validation["normalized"]["routing_rules"]
                if isinstance(item, dict)
                and str(item.get("target_module_id") or "").strip()
            ],
            ["support_module:查經互動模組"],
        )


    def test_validate_semantic_compile_candidate_normalizes_workflow_and_module_ids_consistently(self):
        contract = _compile_contract(
            """
## 深度解析法流程
1. 敘述經驗
Use deep_analysis_framework.md.

## 查經互動模組
1. 觀察經文
Use observation_guide.md.
""".strip(),
            [
                {"filename": "deep_analysis_framework.md"},
                {"filename": "observation_guide.md"},
            ],
        )

        validation = _validate_semantic_compile_candidate(
            semantic_model={
                "primary_service_mode": "intent_routed_multi_workflow",
                "service_blocks": [
                    {"block_id": "workflow_深度解析法流程", "block_type": "primary_workflow", "title": "深度解析法流程"},
                    {"block_id": "module_查經互動模組", "block_type": "support_module", "title": "查經互動模組"},
                ],
                "procedures": [
                    {"procedure_id": "procedure:workflow_深度解析法流程", "service_block_id": "workflow_深度解析法流程", "title": "深度解析法流程"},
                    {"procedure_id": "procedure:module_查經互動模組", "service_block_id": "module_查經互動模組", "title": "查經互動模組"},
                ],
                "procedure_steps": [
                    {"procedure_id": "procedure:workflow_深度解析法流程", "step_id": "step:workflow_深度解析法流程:1", "title": "深度解析法流程", "order": 1, "execution_mode": "interactive", "resource_refs": ["deep_analysis_framework.md"]},
                    {"procedure_id": "procedure:module_查經互動模組", "step_id": "step:module_查經互動模組:1", "title": "查經互動模組", "order": 1, "execution_mode": "interactive", "resource_refs": ["observation_guide.md"]},
                ],
                "role_profiles": [
                    {"role_id": "role:mentor", "name": "Mentor"},
                    {"role_id": "role:tutor", "name": "Tutor"},
                ],
                "routing_rules": [
                    {"rule_id": "route:mentor", "target_role_id": "role:mentor", "target_workflow_id": "workflow_深度解析法流程"},
                    {"rule_id": "route:tutor", "target_role_id": "role:tutor", "target_module_id": "module_查經互動模組"},
                ],
                "clarification_gate_rules": [],
            },
            deterministic_contract=contract,
        )

        self.assertTrue(validation["valid"], validation["errors"])
        normalized_block_ids = {
            str(item.get("block_id") or "").strip()
            for item in validation["normalized"]["service_blocks"]
            if isinstance(item, dict)
        }
        self.assertIn("workflow:深度解析法", normalized_block_ids)
        self.assertIn("support_module:查經互動模組", normalized_block_ids)
        self.assertFalse(any(block_id.startswith("workflow_") for block_id in normalized_block_ids))
        self.assertFalse(any(block_id.startswith("module_") for block_id in normalized_block_ids))

    def test_compile_contract_and_validation_preserve_stepwise_bible_study_module_steps(self):
        contract = _compile_contract(
            """
## 模式自動識別（Mode Detection）
- 查考經文模式
  - 觸發：輸入含「查考」「研經」「經文」等字。
  - 回應：「好的，我們一起用歸納釋經法查考經文。請問想從哪一段開始？」
  - 啟動完整十步歸納釋經流程: 查經互動模組。

## 查經互動模組
1. 細察事實
使用資源： Resource/ observation_guide.md

2. 認清關係
使用資源： Resource/ identify_relationships_guide.md

## 釋經支援模組（八種合法處境）
使用資源： Resource/ 合法處境補充材料.pdf
""".strip(),
            [
                {"filename": "observation_guide.md"},
                {"filename": "identify_relationships_guide.md"},
                {"filename": "合法處境補充材料.pdf"},
            ],
        )

        compiled_steps = [
            item
            for item in contract.get("procedure_steps", []) or []
            if isinstance(item, dict)
            and str(item.get("procedure_id") or "").strip() == "procedure:support_module_查經互動模組"
        ]
        self.assertEqual(
            [str(item.get("title") or "").strip() for item in compiled_steps],
            ["細察事實", "認清關係"],
        )

        validation = _validate_semantic_compile_candidate(
            semantic_model={
                "primary_service_mode": "intent_routed_interaction_logic",
                "service_blocks": [
                    {
                        "block_id": "support_module:查經互動模組",
                        "block_type": "support_module",
                        "title": "查經互動模組",
                    }
                ],
                "procedures": [
                    {
                        "procedure_id": "procedure:support_module_查經互動模組",
                        "service_block_id": "support_module:查經互動模組",
                        "title": "查經互動模組",
                    }
                ],
                "procedure_steps": list(compiled_steps),
                "role_profiles": [],
                "routing_rules": [
                    {
                        "rule_id": "route:bible_study",
                        "target": "interaction_logic_block:mode_bible_study",
                        "entry_response": "好的，我們一起用歸納釋經法查考經文。請問想從哪一段開始？",
                    }
                ],
                "interaction_logic_blocks": [
                    {
                        "block_id": "interaction_logic_block:mode_bible_study",
                        "title": "查考經文模式（Bible Study）",
                        "subordinate_modules": ["support_module:查經互動模組"],
                    }
                ],
                "clarification_gate_rules": [],
            },
            deterministic_contract=contract,
        )

        self.assertTrue(validation["valid"], validation["errors"])
        normalized_steps = [
            item
            for item in validation["normalized"]["procedure_steps"]
            if isinstance(item, dict)
            and str(item.get("procedure_id") or "").strip() == "procedure:support_module_查經互動模組"
        ]
        self.assertEqual(
            [str(item.get("title") or "").strip() for item in normalized_steps],
            ["細察事實", "認清關係"],
        )
        self.assertEqual(
            [list(item.get("resource_refs") or []) for item in normalized_steps],
            [["observation_guide.md"], ["identify_relationships_guide.md"]],
        )


    def test_validate_semantic_compile_candidate_rewrites_direct_module_alias_to_canonical_module_id(self):
        validation = _validate_semantic_compile_candidate(
            semantic_model={
                "primary_service_mode": "intent_routed_multi_workflow",
                "service_blocks": [
                    {
                        "block_id": "workflow:deep_analysis",
                        "block_type": "primary_workflow",
                        "title": "深度解析法流程",
                    },
                    {
                        "block_id": "module:inductive_bible_study",
                        "block_type": "support_module",
                        "title": "查經互動模組（歸納釋經法）",
                    }
                ],
                "procedures": [
                    {
                        "procedure_id": "procedure:workflow_deep_analysis",
                        "service_block_id": "workflow:deep_analysis",
                        "title": "深度解析法流程",
                    }
                ],
                "procedure_steps": [
                    {
                        "procedure_id": "procedure:workflow_deep_analysis",
                        "step_id": "step:workflow_deep_analysis:1",
                        "title": "深度解析法流程",
                        "order": 1,
                        "execution_mode": "interactive",
                    }
                ],
                "role_profiles": [
                    {"role_id": "role:mentor", "name": "Mentor"},
                    {"role_id": "role:tutor", "name": "Tutor"},
                ],
                "routing_rules": [
                    {
                        "rule_id": "route:mentor",
                        "target_role_id": "role:mentor",
                        "target_workflow_id": "workflow:deep_analysis",
                    },
                    {
                        "rule_id": "route:tutor",
                        "target_role_id": "role:tutor",
                        "target_module_id": "module:查經互動模組",
                    }
                ],
                "clarification_gate_rules": [],
            },
            deterministic_contract={
                "resource_reference_catalog": [
                    {"filename": "歸納釋經法 102025.pdf"},
                ],
                "instruction_service_blocks": [
                    {
                        "block_id": "support_module:查經互動模組",
                        "block_type": "support_module",
                        "title": "查經互動模組（歸納釋經法）",
                        "body_text": "使用歸納釋經法引導查經。",
                        "resource_refs": ["歸納釋經法 102025.pdf"],
                    }
                ],
                "instruction_modules": [],
                "instruction_workflows": [],
                "instruction_procedures": [],
                "procedure_steps": [],
            },
        )

        self.assertTrue(validation["valid"], validation["errors"])
        rewritten = next(
            item
            for item in validation["normalized"]["routing_rules"]
            if isinstance(item, dict) and item.get("rule_id") == "route:tutor"
        )
        self.assertEqual(rewritten.get("target_module_id"), "support_module:inductive_bible_study")

    def test_validate_semantic_compile_candidate_rewrites_direct_module_alias_from_existing_service_block_title(self):
        validation = _validate_semantic_compile_candidate(
            semantic_model={
                "primary_service_mode": "intent_routed_interaction_logic",
                "service_blocks": [
                    {
                        "block_id": "module:bible_study",
                        "block_type": "support_module",
                        "title": "查經互動模組（歸納釋經法）",
                    }
                ],
                "procedures": [],
                "procedure_steps": [],
                "role_profiles": [
                    {"role_id": "role:tutor", "name": "Tutor"},
                ],
                "routing_rules": [
                    {
                        "rule_id": "route:tutor",
                        "target_role_id": "role:tutor",
                        "target_module_id": "module:查經互動模組",
                    }
                ],
                "interaction_logic_blocks": [
                    {
                        "block_id": "logic:tutor_mode",
                        "title": "五重角色模式",
                        "body_text": "Tutor routes scripture requests into the Bible-study module.",
                    }
                ],
                "clarification_gate_rules": [],
            },
            deterministic_contract={
                "resource_reference_catalog": [
                    {"filename": "歸納釋經法 102025.pdf"},
                ],
                "instruction_service_blocks": [],
                "instruction_modules": [],
                "instruction_workflows": [],
                "instruction_procedures": [],
                "procedure_steps": [],
            },
        )

        self.assertTrue(validation["valid"], validation["errors"])
        rewritten = next(
            item
            for item in validation["normalized"]["routing_rules"]
            if isinstance(item, dict) and item.get("rule_id") == "route:tutor"
        )
        self.assertEqual(rewritten.get("target_module_id"), "support_module:bible_study")

    def test_validate_semantic_compile_candidate_rewrites_bare_module_title_alias_from_existing_service_block_title(self):
        validation = _validate_semantic_compile_candidate(
            semantic_model={
                "primary_service_mode": "intent_routed_interaction_logic",
                "service_blocks": [
                    {
                        "block_id": "module:bible_study",
                        "block_type": "support_module",
                        "title": "查經互動模組（歸納釋經法的十個步驟）",
                    }
                ],
                "procedures": [],
                "procedure_steps": [],
                "role_profiles": [
                    {"role_id": "role:tutor", "name": "Tutor"},
                ],
                "routing_rules": [
                    {
                        "rule_id": "route:tutor",
                        "target_role_id": "role:tutor",
                        "target_module_id": "查經互動模組_歸納釋經法的十個步驟",
                    }
                ],
                "interaction_logic_blocks": [
                    {
                        "block_id": "logic:tutor_mode",
                        "title": "模式自動識別",
                        "body_text": "Bible-study requests route to the scripture study module.",
                    }
                ],
                "clarification_gate_rules": [],
            },
            deterministic_contract={
                "resource_reference_catalog": [
                    {"filename": "歸納釋經法 102025.pdf"},
                ],
                "instruction_service_blocks": [],
                "instruction_modules": [],
                "instruction_workflows": [],
                "instruction_procedures": [],
                "procedure_steps": [],
            },
        )

        self.assertTrue(validation["valid"], validation["errors"])
        rewritten = next(
            item
            for item in validation["normalized"]["routing_rules"]
            if isinstance(item, dict) and item.get("rule_id") == "route:tutor"
        )
        self.assertEqual(rewritten.get("target_module_id"), "support_module:bible_study")

    def test_validate_semantic_compile_candidate_rewrites_bible_tutor_workflow_alias_to_existing_support_module_block(self):
        validation = _validate_semantic_compile_candidate(
            semantic_model={
                "primary_service_mode": "intent_routed_interaction_logic",
                "service_blocks": [
                    {
                        "block_id": "support_module:查經互動模組",
                        "block_type": "support_module",
                        "title": "查經互動模組（歸納釋經法的十個步驟）",
                    },
                    {
                        "block_id": "support_module:釋經支援模組_exegesis_support_module_八種合法處境",
                        "block_type": "support_module",
                        "title": "釋經支援模組（Exegesis Support Module：八種合法處境）",
                    },
                ],
                "procedures": [],
                "procedure_steps": [],
                "role_profiles": [
                    {"role_id": "role:tutor", "name": "Tutor"},
                ],
                "interaction_logic_blocks": [
                    {
                        "block_id": "interaction_logic_block:mode_bible_study",
                        "title": "模式自動識別",
                        "body_text": "根據使用者問題進入查經互動模式。",
                        "subordinate_modules": ["support_module:查經互動模組"],
                    }
                ],
                "routing_rules": [
                    {
                        "rule_id": "route:bible_study",
                        "target_role_id": "role:tutor",
                        "target_workflow_id": "workflow:bible_study_inductive_10_step",
                    },
                    {
                        "rule_id": "route:exegesis",
                        "target_role_id": "role:tutor",
                        "target_module_id": "module:exegesis_support_8_contexts",
                    },
                ],
                "clarification_gate_rules": [],
            },
            deterministic_contract={
                "resource_reference_catalog": [
                    {"filename": "observation_guide.md"},
                    {"filename": "合法處境補充材料.pdf"},
                ],
                "instruction_service_blocks": [
                    {
                        "block_id": "support_module:查經互動模組",
                        "block_type": "support_module",
                        "title": "查經互動模組（歸納釋經法的十個步驟）",
                        "body_text": "使用歸納釋經法引導查經。",
                        "resource_refs": ["observation_guide.md"],
                    },
                    {
                        "block_id": "support_module:釋經支援模組_exegesis_support_module_八種合法處境",
                        "block_type": "support_module",
                        "title": "釋經支援模組（Exegesis Support Module：八種合法處境）",
                        "body_text": "釐清歷史、文化、文學與神學處境。",
                        "resource_refs": ["合法處境補充材料.pdf"],
                    },
                ],
                "instruction_modules": [],
                "instruction_workflows": [],
                "instruction_procedures": [],
                "procedure_steps": [],
            },
        )

        self.assertTrue(validation["valid"], validation["errors"])
        rewritten_rules = {
            str(item.get("rule_id") or "").strip(): item
            for item in validation["normalized"]["routing_rules"]
            if isinstance(item, dict)
        }
        self.assertEqual(
            rewritten_rules["route:bible_study"].get("target_module_id"),
            "support_module:查經互動模組",
        )
        self.assertNotIn("target_workflow_id", rewritten_rules["route:bible_study"])
        self.assertEqual(
            rewritten_rules["route:exegesis"].get("target_module_id"),
            "support_module:釋經支援模組_exegesis_support_module_八種合法處境",
        )

    def test_validate_semantic_compile_candidate_preserves_bible_tutor_module_owned_procedure_instead_of_sibling_workflow(self):
        contract = _compile_contract(
            """
## 模式自動識別（Mode Detection）
- 查考經文模式
  - 觸發：輸入含「查考」「研經」「經文」等字。
  - 回應：「好的，我們一起用歸納釋經法查考經文。請問想從哪一段開始？」
  - 啟動完整十步歸納釋經流程: 查經互動模組。

## 查經互動模組
1. 細察事實
使用資源： Resource/ observation_guide.md

2. 認清關係
使用資源： Resource/ identify_relationships_guide.md

## 釋經支援模組（八種合法處境）
使用資源： Resource/ 合法處境補充材料.pdf
""".strip(),
            [
                {"filename": "observation_guide.md"},
                {"filename": "identify_relationships_guide.md"},
                {"filename": "合法處境補充材料.pdf"},
            ],
        )

        validation = _validate_semantic_compile_candidate(
            semantic_model={
                "primary_service_mode": "intent_routed_interaction_logic",
                "interaction_logic_blocks": [
                    {
                        "block_id": "logic:bible_study_mode",
                        "title": "查考經文模式（Bible Study）",
                        "subordinate_target": {
                            "target_type": "support_module",
                            "target_id": "module:查經互動模組",
                        },
                    }
                ],
                "routing_rules": [
                    {
                        "rule_id": "route:bible_study",
                        "trigger_keywords": ["查考", "經文"],
                        "target_logic_block_id": "logic:bible_study_mode",
                        "target_module_id": "module:查經互動模組",
                    }
                ],
                "service_blocks": [
                    {
                        "block_id": "workflow:歸納釋經法",
                        "block_type": "primary_workflow",
                        "title": "查經互動模組 — 十步歸納釋經流程",
                    },
                    {
                        "block_id": "module:釋經支援模組_exegesis_support_module_八種合法處境",
                        "block_type": "support_module",
                        "title": "釋經支援模組（Exegesis Support Module — 八種合法處境）",
                    },
                ],
                "procedures": [
                    {
                        "procedure_id": "procedure:workflow_歸納釋經法",
                        "service_block_id": "workflow:歸納釋經法",
                        "title": "查經互動模組 — 十步歸納釋經流程",
                    },
                    {
                        "procedure_id": "procedure:module_釋經支援模組_exegesis_support_module_八種合法處境",
                        "service_block_id": "module:釋經支援模組_exegesis_support_module_八種合法處境",
                        "title": "釋經支援模組（Exegesis Support Module — 八種合法處境）",
                    },
                ],
                "procedure_steps": [
                    {
                        "procedure_id": "procedure:workflow_歸納釋經法",
                        "step_id": "step:observation",
                        "title": "細察事實",
                        "order": 1,
                        "execution_mode": "interactive",
                    },
                    {
                        "procedure_id": "procedure:workflow_歸納釋經法",
                        "step_id": "step:identify_relationships",
                        "title": "認清關係",
                        "order": 2,
                        "execution_mode": "interactive",
                    },
                ],
                "role_profiles": [],
                "clarification_gate_rules": [],
            },
            deterministic_contract=contract,
        )

        self.assertTrue(validation["valid"], validation["errors"])
        normalized = validation["normalized"]
        block_ids = {
            str(item.get("block_id") or "").strip()
            for item in normalized["service_blocks"]
            if isinstance(item, dict)
        }
        self.assertIn("support_module:查經互動模組", block_ids)
        self.assertNotIn("workflow:歸納釋經法", block_ids)
        procedure_owner_ids = {
            str(item.get("service_block_id") or "").strip()
            for item in normalized["procedures"]
            if isinstance(item, dict)
        }
        self.assertIn("support_module:查經互動模組", procedure_owner_ids)
        self.assertNotIn("workflow:歸納釋經法", procedure_owner_ids)
        bible_route = next(
            item
            for item in normalized["routing_rules"]
            if isinstance(item, dict) and str(item.get("rule_id") or "").strip() == "route:bible_study"
        )
        self.assertEqual(bible_route.get("target_module_id"), "support_module:查經互動模組")
        self.assertNotIn("target_workflow_id", bible_route)

    def test_validate_semantic_compile_candidate_rewrites_parenting_module_aliases_to_existing_executable_block_id(self):
        validation = _validate_semantic_compile_candidate(
            semantic_model={
                "primary_service_mode": "intent_routed_interaction_logic",
                "service_blocks": [
                    {
                        "block_id": "module:inductive_bible_study",
                        "block_type": "support_module",
                        "title": "查經互動模組（歸納釋經法）",
                    }
                ],
                "procedures": [],
                "procedure_steps": [],
                "role_profiles": [
                    {"role_id": "role:tutor", "name": "Tutor"},
                ],
                "routing_rules": [
                    {
                        "rule_id": "route:title_alias",
                        "target_role_id": "role:tutor",
                        "target_module_id": "module:查經互動模組",
                    },
                    {
                        "rule_id": "route:underscore_alias",
                        "target_role_id": "role:tutor",
                        "target_module_id": "module_inductive_bible_study",
                    },
                ],
                "interaction_logic_blocks": [
                    {
                        "block_id": "logic:tutor_mode",
                        "title": "五重角色模式",
                        "body_text": "Tutor 路由到查經模組。",
                    }
                ],
                "clarification_gate_rules": [],
            },
            deterministic_contract={
                "resource_reference_catalog": [{"filename": "歸納釋經法 102025.pdf"}],
                "instruction_service_blocks": [
                    {
                        "block_id": "support_module:查經互動模組",
                        "block_type": "support_module",
                        "title": "查經互動模組（歸納釋經法）",
                        "body_text": "用於深入查經。",
                        "resource_refs": ["歸納釋經法 102025.pdf"],
                    }
                ],
                "instruction_modules": [],
                "instruction_workflows": [],
                "instruction_procedures": [],
                "procedure_steps": [],
            },
        )

        self.assertTrue(validation["valid"], validation["errors"])
        rewritten_rules = {
            str(item.get("rule_id") or "").strip(): item
            for item in validation["normalized"]["routing_rules"]
            if isinstance(item, dict)
        }
        self.assertEqual(
            rewritten_rules["route:title_alias"].get("target_module_id"),
            "support_module:inductive_bible_study",
        )
        self.assertEqual(
            rewritten_rules["route:underscore_alias"].get("target_module_id"),
            "support_module:inductive_bible_study",
        )

    def test_validate_semantic_compile_candidate_preserves_existing_support_module_ids_for_cross_app_routes(self):
        validation = _validate_semantic_compile_candidate(
            semantic_model={
                "primary_service_mode": "intent_routed_interaction_logic",
                "service_blocks": [
                    {
                        "block_id": "support_module:church_ministry_prompt_designer_tool_selection_support_module",
                        "block_type": "support_module",
                        "title": "Church Ministry Prompt Designer Tool Selection Support Module",
                    },
                    {
                        "block_id": "support_module:gpt_application_design_assistant_support_module",
                        "block_type": "support_module",
                        "title": "GPT Application Design Assistant Support Module",
                    },
                ],
                "procedures": [],
                "procedure_steps": [],
                "role_profiles": [
                    {"role_id": "role:church_ministry_prompt_designer", "name": "Church Ministry Prompt Designer"},
                    {"role_id": "role:gpt_application_design_assistant", "name": "GPT Application Design Assistant"},
                ],
                "routing_rules": [
                    {
                        "rule_id": "route:church",
                        "target_role_id": "role:church_ministry_prompt_designer",
                        "target_module_id": "support_module:church_ministry_prompt_designer_tool_selection_support_module",
                    },
                    {
                        "rule_id": "route:gpt",
                        "target_role_id": "role:gpt_application_design_assistant",
                        "target_module_id": "support_module:gpt_application_design_assistant_support_module",
                    },
                ],
                "interaction_logic_blocks": [{"block_id": "logic:routing", "title": "Routing Logic"}],
                "clarification_gate_rules": [],
            },
            deterministic_contract={
                "resource_reference_catalog": [],
                "instruction_service_blocks": [],
                "instruction_modules": [],
                "instruction_workflows": [],
                "instruction_procedures": [],
                "procedure_steps": [],
            },
        )

        self.assertTrue(validation["valid"], validation["errors"])
        rewritten_rules = {
            str(item.get("rule_id") or "").strip(): item
            for item in validation["normalized"]["routing_rules"]
            if isinstance(item, dict)
        }
        self.assertEqual(
            rewritten_rules["route:church"].get("target_module_id"),
            "support_module:church_ministry_prompt_designer_tool_selection_support_module",
        )
        self.assertEqual(
            rewritten_rules["route:gpt"].get("target_module_id"),
            "support_module:gpt_application_design_assistant_support_module",
        )

    def test_validate_semantic_compile_candidate_strips_orchestration_owned_procedure_artifacts(self):
        validation = _validate_semantic_compile_candidate(
            semantic_model={
                "primary_service_mode": "intent_routed_multi_workflow",
                "service_blocks": [
                    {
                        "block_id": "workflow:多重需求分層規則",
                        "block_type": "primary_workflow",
                        "title": "多重需求分層規則",
                    },
                    {
                        "block_id": "workflow:深度解析法",
                        "block_type": "primary_workflow",
                        "title": "深度解析法流程",
                    },
                ],
                "procedures": [
                    {
                        "procedure_id": "procedure:workflow_多重需求分層規則",
                        "service_block_id": "workflow:多重需求分層規則",
                        "title": "多重需求分層規則",
                    },
                    {
                        "procedure_id": "procedure:workflow_深度解析法",
                        "service_block_id": "workflow:深度解析法",
                        "title": "深度解析法流程",
                    },
                ],
                "procedure_steps": [
                    {
                        "procedure_id": "procedure:workflow_多重需求分層規則",
                        "step_id": "step:workflow_多重需求分層規則:1",
                        "title": "多重需求分層規則",
                        "order": 1,
                        "execution_mode": "interactive",
                    },
                    {
                        "procedure_id": "procedure:workflow_深度解析法",
                        "step_id": "step:workflow_深度解析法:1",
                        "title": "深度解析法流程",
                        "order": 1,
                        "execution_mode": "interactive",
                    },
                ],
                "role_profiles": [
                    {"role_id": "role:mentor", "name": "Mentor"},
                ],
                "routing_rules": [
                    {
                        "rule_id": "route:mentor",
                        "target_role_id": "role:mentor",
                        "target_workflow_id": "workflow:深度解析法",
                    },
                    {
                        "rule_id": "route:orchestration",
                        "target_workflow_id": "workflow:多重需求分層規則",
                    },
                ],
                "clarification_gate_rules": [],
            },
            deterministic_contract={
                "resource_reference_catalog": [],
                "instruction_workflows": [
                    {
                        "id": "多重需求分層規則",
                        "title": "多重需求分層規則",
                        "body_text": "依序執行 Mentor、Coach／Consultant、Tutor／Partner 層。",
                        "steps": [{"order": 1, "title": "Mentor 層"}],
                    }
                ],
                "instruction_modules": [
                    {
                        "id": "deep_analysis_framework",
                        "title": "深度解析法",
                        "resource_files": ["deep_analysis_framework.md"],
                        "keywords": ["深度解析法", "deep analysis framework"],
                    }
                ],
                "instruction_service_blocks": [],
                "instruction_procedures": [],
                "procedure_steps": [],
            },
        )

        self.assertTrue(validation["valid"], validation["errors"])
        logic_titles = {
            str(item.get("title") or "").strip()
            for item in validation["normalized"]["interaction_logic_blocks"]
            if isinstance(item, dict)
        }
        self.assertIn("多重需求分層規則", logic_titles)
        procedure_block_ids = {
            str(item.get("service_block_id") or "").strip()
            for item in validation["normalized"]["procedures"]
            if isinstance(item, dict)
        }
        self.assertNotIn("workflow:多重需求分層規則", procedure_block_ids)
        self.assertIn("workflow:深度解析法", procedure_block_ids)


    def test_validate_semantic_compile_candidate_prevents_interaction_logic_titles_from_leaking_into_workflows(self):
        validation = _validate_semantic_compile_candidate(
            semantic_model={
                "primary_service_mode": "intent_routed_multi_workflow",
                "service_blocks": [
                    {
                        "block_id": "wf:deep_reflection",
                        "block_type": "primary_workflow",
                        "title": "深度解析法流程",
                    },
                    {
                        "block_id": "workflow:深度解析法",
                        "block_type": "primary_workflow",
                        "title": "互動模式與流程",
                    },
                    {
                        "block_id": "workflow:親子靈修",
                        "block_type": "primary_workflow",
                        "title": "模式切換邏輯",
                    },
                    {
                        "block_id": "module:bible_study",
                        "block_type": "support_module",
                        "title": "查經互動模組（歸納釋經法）",
                    },
                ],
                "procedures": [
                    {
                        "procedure_id": "procedure:wf_deep_reflection",
                        "service_block_id": "wf:deep_reflection",
                        "title": "深度解析法流程",
                    },
                    {
                        "procedure_id": "procedure:workflow_深度解析法",
                        "service_block_id": "workflow:深度解析法",
                        "title": "互動模式與流程",
                    },
                    {
                        "procedure_id": "procedure:workflow_親子靈修",
                        "service_block_id": "workflow:親子靈修",
                        "title": "模式切換邏輯",
                    },
                ],
                "procedure_steps": [
                    {
                        "procedure_id": "procedure:wf_deep_reflection",
                        "step_id": "step:wf_deep_reflection:1",
                        "title": "深度解析法流程",
                        "order": 1,
                        "execution_mode": "interactive",
                    },
                    {
                        "procedure_id": "procedure:workflow_深度解析法",
                        "step_id": "step:workflow_深度解析法:1",
                        "title": "互動模式與流程",
                        "order": 1,
                        "execution_mode": "interactive",
                    },
                    {
                        "procedure_id": "procedure:workflow_親子靈修",
                        "step_id": "step:workflow_親子靈修:1",
                        "title": "模式切換邏輯",
                        "order": 1,
                        "execution_mode": "interactive",
                    },
                ],
                "role_profiles": [
                    {"role_id": "role:mentor", "name": "Mentor"},
                    {"role_id": "role:partner", "name": "Partner"},
                    {"role_id": "role:tutor", "name": "Tutor"},
                ],
                "routing_rules": [
                    {
                        "rule_id": "route:mentor",
                        "target_role_id": "role:mentor",
                        "target_workflow_id": "workflow:深度解析法",
                    },
                    {
                        "rule_id": "route:partner",
                        "target_role_id": "role:partner",
                        "target_workflow_id": "workflow:親子靈修",
                    },
                    {
                        "rule_id": "route:tutor",
                        "target_role_id": "role:tutor",
                        "target_module_id": "module:bible_study",
                    },
                ],
                "interaction_logic_blocks": [
                    {"title": "模式切換邏輯", "body_text": "依照需求切換角色。"},
                    {"title": "多重需求分層規則", "body_text": "分層回應。"},
                ],
                "clarification_gate_rules": [],
            },
            deterministic_contract={
                "resource_reference_catalog": [
                    {"filename": "歸納釋經法 102025.pdf"},
                ],
                "instruction_workflows": [
                    {
                        "id": "互動模式與流程",
                        "title": "互動模式與流程",
                        "workflow_name": "互動模式與流程",
                        "steps": [
                            {"order": 1, "title": "3x1 建議清單流程（快速回應模式）"},
                            {"order": 2, "title": "按步就班法流程（循序反思模式）"},
                            {"order": 3, "title": "深度解析法流程（輔導反思模式）"},
                        ],
                    },
                    {
                        "id": "多重需求分層規則",
                        "title": "多重需求分層規則",
                        "workflow_name": "多重需求分層規則",
                        "steps": [
                            {"order": 1, "title": "Mentor 層：處理情緒與信仰。"},
                            {"order": 2, "title": "Coach／Consultant 層：處理行為與計畫。"},
                        ],
                    },
                ],
                "instruction_modules": [],
                "instruction_service_blocks": [
                    {
                        "block_id": "global_policy:模式切換邏輯",
                        "block_type": "global_policy",
                        "title": "模式切換邏輯",
                    },
                    {
                        "block_id": "support_module:查經互動模組",
                        "block_type": "support_module",
                        "title": "查經互動模組",
                        "resource_refs": ["歸納釋經法 102025.pdf"],
                    },
                ],
                "instruction_procedures": [],
                "procedure_steps": [],
            },
        )

        self.assertTrue(validation["valid"], validation["errors"])
        blocks = {
            str(item.get("block_id") or "").strip(): item
            for item in validation["normalized"]["service_blocks"]
            if isinstance(item, dict)
        }
        self.assertIn("workflow:深度解析法", blocks)
        self.assertIn("workflow:按步就班法", blocks)
        self.assertNotIn("wf:deep_reflection", blocks)
        self.assertNotIn("workflow:親子靈修", blocks)
        self.assertNotEqual(str(blocks["workflow:深度解析法"].get("title") or "").strip(), "互動模式與流程")
        self.assertNotEqual(str(blocks["workflow:按步就班法"].get("title") or "").strip(), "模式切換邏輯")
        logic_titles = {
            str(item.get("title") or "").strip()
            for item in validation["normalized"]["interaction_logic_blocks"]
            if isinstance(item, dict)
        }
        workflow_titles = {
            str(item.get("title") or "").strip()
            for item in validation["normalized"]["service_blocks"]
            if isinstance(item, dict) and str(item.get("block_type") or "").strip() == "primary_workflow"
        }
        self.assertFalse(logic_titles & workflow_titles)

    def test_validate_semantic_compile_candidate_reconciles_procedure_owner_ids_with_existing_service_block_aliases(self):
        validation = _validate_semantic_compile_candidate(
            semantic_model={
                "primary_service_mode": "intent_routed_interaction_logic",
                "service_blocks": [
                    {
                        "block_id": "workflow:3x1建議清單流程",
                        "block_type": "primary_workflow",
                        "title": "3x1建議清單法流程",
                    },
                    {
                        "block_id": "workflow:按步就班法流程",
                        "block_type": "primary_workflow",
                        "title": "按步就班法流程",
                    },
                    {
                        "block_id": "module:查經互動模組",
                        "block_type": "support_module",
                        "title": "歸納釋經法",
                    },
                ],
                "procedures": [
                    {
                        "procedure_id": "procedure:workflow_3x1建議清單法",
                        "service_block_id": "workflow:3x1建議清單法",
                        "title": "3x1建議清單法",
                    },
                    {
                        "procedure_id": "procedure:workflow_按步就班法",
                        "service_block_id": "workflow:按步就班法",
                        "title": "按步就班法",
                    },
                    {
                        "procedure_id": "procedure:support_module_查經互動模組",
                        "service_block_id": "support_module:查經互動模組",
                        "title": "查經互動模組",
                    },
                ],
                "procedure_steps": [
                    {
                        "procedure_id": "procedure:workflow_3x1建議清單法",
                        "step_id": "step:workflow_3x1建議清單法:1",
                        "title": "3x1建議清單法",
                        "order": 1,
                        "execution_mode": "interactive",
                    },
                    {
                        "procedure_id": "procedure:workflow_按步就班法",
                        "step_id": "step:workflow_按步就班法:1",
                        "title": "按步就班法",
                        "order": 1,
                        "execution_mode": "interactive",
                    },
                    {
                        "procedure_id": "procedure:support_module_查經互動模組",
                        "step_id": "step:support_module_查經互動模組:1",
                        "title": "細察事實",
                        "order": 1,
                        "execution_mode": "interactive",
                    },
                ],
                "role_profiles": [{"role_id": "role:tutor", "name": "Tutor"}],
                "routing_rules": [
                    {"rule_id": "route:consultant", "target_workflow_id": "workflow:3x1建議清單法"},
                    {"rule_id": "route:coach", "target_workflow_id": "workflow:按步就班法"},
                    {"rule_id": "route:tutor", "target_role_id": "role:tutor", "target_module_id": "module:查經互動模組"},
                ],
                "interaction_logic_blocks": [
                    {
                        "block_id": "logic:five_roles",
                        "title": "五重角色模式",
                        "body_text": "依照需求切換角色。",
                        "routing_rules": [
                            {"rule_id": "logic:tutor", "target_module_id": "module:查經互動模組"},
                        ],
                    }
                ],
                "clarification_gate_rules": [],
            },
            deterministic_contract={
                "resource_reference_catalog": [{"filename": "歸納釋經法 102025.pdf"}],
                "instruction_workflows": [
                    {
                        "id": "互動模式與流程",
                        "title": "互動模式與流程",
                        "workflow_name": "互動模式與流程",
                        "steps": [
                            {"order": 1, "title": "3x1建議清單法流程（快速回應模式）"},
                            {"order": 2, "title": "按步就班法流程（循序反思模式）"},
                        ],
                    }
                ],
                "instruction_service_blocks": [
                    {
                        "block_id": "support_module:查經互動模組",
                        "block_type": "support_module",
                        "title": "查經互動模組",
                        "resource_refs": ["歸納釋經法 102025.pdf"],
                    }
                ],
                "instruction_modules": [],
                "instruction_procedures": [],
                "procedure_steps": [],
            },
        )

        self.assertTrue(validation["valid"], validation["errors"])
        block_ids = {
            str(item.get("block_id") or "").strip()
            for item in validation["normalized"]["service_blocks"]
            if isinstance(item, dict)
        }
        self.assertIn("workflow:3x1建議清單法", block_ids)
        self.assertIn("workflow:按步就班法", block_ids)
        self.assertIn("support_module:查經互動模組", block_ids)
        self.assertNotIn("workflow:3x1建議清單流程", block_ids)
        self.assertNotIn("workflow:按步就班法流程", block_ids)
        procedure_block_ids = {
            str(item.get("service_block_id") or "").strip()
            for item in validation["normalized"]["procedures"]
            if isinstance(item, dict)
        }
        self.assertTrue(procedure_block_ids <= block_ids)

    def test_validate_semantic_compile_candidate_rewrites_module_like_route_workflow_target_to_target_module_id(self):
        validation = _validate_semantic_compile_candidate(
            semantic_model={
                "primary_service_mode": "intent_routed_interaction_logic",
                "service_blocks": [
                    {
                        "block_id": "support_module:查經互動模組",
                        "block_type": "support_module",
                        "title": "查經互動模組",
                    }
                ],
                "procedures": [
                    {
                        "procedure_id": "procedure:support_module_查經互動模組",
                        "service_block_id": "support_module:查經互動模組",
                        "title": "查經互動模組",
                    }
                ],
                "procedure_steps": [
                    {
                        "procedure_id": "procedure:support_module_查經互動模組",
                        "step_id": "step:support_module_查經互動模組:1",
                        "title": "細察事實",
                        "order": 1,
                        "execution_mode": "interactive",
                    }
                ],
                "role_profiles": [],
                "routing_rules": [
                    {
                        "rule_id": "route:tutor",
                        "target_workflow_id": "support_module:查經互動模組",
                    }
                ],
                "interaction_logic_blocks": [],
                "clarification_gate_rules": [],
            },
            deterministic_contract={
                "resource_reference_catalog": [{"filename": "歸納釋經法 102025.pdf"}],
                "instruction_service_blocks": [
                    {
                        "block_id": "support_module:查經互動模組",
                        "block_type": "support_module",
                        "title": "查經互動模組",
                        "resource_refs": ["歸納釋經法 102025.pdf"],
                    }
                ],
                "instruction_modules": [],
                "instruction_workflows": [],
                "instruction_procedures": [],
                "procedure_steps": [],
            },
        )

        self.assertTrue(validation["valid"], validation["errors"])
        rule = next(
            item
            for item in validation["normalized"]["routing_rules"]
            if isinstance(item, dict) and str(item.get("rule_id") or "").strip() == "route:tutor"
        )
        self.assertEqual(rule.get("target_module_id"), "support_module:查經互動模組")
        self.assertNotIn("target_workflow_id", rule)


if __name__ == "__main__":
    unittest.main()



