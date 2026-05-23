import unittest
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from workflows.nodes import retrieve


def _workspace_tempdir(name: str) -> Path:
    base = Path(__file__).resolve().parent / "_tmp" / name
    if base.exists():
        shutil.rmtree(base, ignore_errors=True)
    base.mkdir(parents=True, exist_ok=True)
    return base


class RetrieveNodeTests(unittest.TestCase):
    def test_bypasses_retrieval_for_general_out_of_scope_question(self):
        state = {
            "user_query": "Explain Python dataclass",
            "retrieval_plan": {"query_text": "Explain Python dataclass", "top_k": 3, "filters": {"app_id": "app-1"}},
            "turn_execution_plan": {
                "turn_intent": "general_out_of_scope_question",
                "resource_requests": [],
                "actions": [{"action_type": "respond_to_user", "params": {}}],
            },
        }
        calls = {"count": 0}

        def fake_retrieve(_query_text, _top_k, _filters):
            calls["count"] += 1
            return {"results": [{"doc_id": "d1"}], "debug_trace": {"source": "mock"}}

        out = retrieve.run(state, retrieve_fn=fake_retrieve)
        self.assertEqual(calls["count"], 0)
        self.assertEqual(out["raw_evidence"], [])
        self.assertEqual(out["compressed_knowledge_evidence"], [])
        self.assertTrue(out["retrieval_debug_trace"]["retrieval_bypassed"])
        self.assertEqual(out["retrieval_debug_trace"]["bypass_reason"], "general_out_of_scope_question")

    def test_general_out_of_scope_bypass_keeps_prepared_input_artifact_gate_status_consistent(self):
        state = {
            "user_query": "Explain Python dataclass",
            "session_execution_state": {
                "active_binding_ids": ["binding-director-bundle"],
                "artifact_gate_status": {},
            },
            "retrieval_plan": {"query_text": "Explain Python dataclass", "top_k": 3, "filters": {"app_id": "app-1"}},
            "turn_execution_plan": {
                "turn_intent": "general_out_of_scope_question",
                "resource_requests": [
                    {
                        "resource_role": "knowledge_source",
                        "binding_id": "binding-director-bundle",
                        "artifact_role": "director_bundle",
                        "required_for_progression": True,
                        "purpose": "session_upload",
                        "filename": "Director Bundle.md",
                    }
                ],
                "actions": [{"action_type": "respond_to_user", "params": {}}],
            },
        }

        out = retrieve.run(state, retrieve_fn=lambda *_args, **_kwargs: {"results": [], "debug_trace": {"source": "mock"}})
        expected_status = {
            "director_bundle": {
                "status": "blocked",
                "reason": "missing_required_artifact",
                "binding_id": "binding-director-bundle",
                "required_for_progression": True,
                "filename": "Director Bundle.md",
            }
        }
        self.assertEqual(out["retrieval_debug_trace"]["artifact_gate_status"], expected_status)
        self.assertEqual(out["prepared_inputs"]["artifact_gate_status"], expected_status)

    def test_calls_retriever_with_retrieval_plan_only(self):
        state = {"retrieval_plan": {"query_text": "policy", "top_k": 3, "filters": {"domain": "general"}}}
        calls = {}

        def fake_retrieve(query_text, top_k, filters):
            calls["query_text"] = query_text
            calls["top_k"] = top_k
            calls["filters"] = filters
            return {"results": [{"doc_id": "d1"}], "debug_trace": {"source": "mock"}}

        out = retrieve.run(state, retrieve_fn=fake_retrieve)
        self.assertEqual(calls, {"query_text": "policy", "top_k": 3, "filters": {"domain": "general"}})
        self.assertEqual(out["raw_evidence"][0]["doc_id"], "d1")
        self.assertEqual(out["raw_evidence"][0]["retrieval_domain"], "knowledge_source")
        self.assertEqual(out["raw_evidence"][0]["retrieval_query"], "policy")
        self.assertEqual(out["raw_evidence"][0]["retrieval_attempt"], 0)
        self.assertEqual(out["retrieval_debug_trace"]["source"], "mock")
        self.assertEqual(out["retrieval_debug_trace"]["domains"]["knowledge_source"]["source"], "mock")
        self.assertEqual(
            out["retrieval_debug_trace"]["domains"]["knowledge_source"]["executed_queries"],
            ["policy"],
        )

    def test_requires_query_text_and_top_k(self):
        with self.assertRaises(ValueError):
            retrieve.run({"retrieval_plan": {"top_k": 2, "filters": {}}}, retrieve_fn=lambda *_: {})

    def test_merges_instruction_resource_filters(self):
        state = {
            "retrieval_plan": {"query_text": "policy", "top_k": 3, "filters": {"app_id": "app-1"}},
            "instruction_resource_filters": {"filename": "observation_guide.md"},
        }
        calls = {}

        def fake_retrieve(query_text, top_k, filters):
            calls["query_text"] = query_text
            calls["top_k"] = top_k
            calls["filters"] = filters
            return {"results": [], "debug_trace": {"source": "mock"}}

        retrieve.run(state, retrieve_fn=fake_retrieve)
        self.assertEqual(
            calls["filters"],
            {"app_id": "app-1", "filename": "observation_guide.md"},
        )

    def test_uses_dual_domain_turn_execution_plan_and_merges_results(self):
        state = {
            "user_query": "What does this word mean?",
            "retrieval_plan": {"query_text": "What does this word mean?", "top_k": 3, "filters": {"app_id": "app-1"}},
            "turn_execution_plan": {
                "resource_requests": [
                    {
                        "filename": "observation_guide.md",
                        "resource_role": "instruction_source",
                        "query_text": "instruction guidance action guide step observation",
                        "context_hints": ["What does this word mean?"],
                        "load_strategy_hint": "vector_retrieve",
                    },
                    {
                        "filename": "lexical_support.md",
                        "resource_role": "instruction_source",
                        "query_text": "instruction guidance action guide step observation",
                        "load_strategy_hint": "vector_retrieve",
                    },
                    {
                        "filename": "knowledge.pdf",
                        "resource_role": "knowledge_source",
                        "query_text": "What does this word mean?",
                    },
                ],
                "actions": [
                    {
                        "action_type": "retrieve_knowledge",
                        "params": {
                            "query_text": "What does this word mean?",
                            "filename_filters": ["knowledge.pdf"],
                        },
                    }
                ],
            },
        }
        calls = []

        def fake_retrieve(query_text, top_k, filters):
            calls.append({"query_text": query_text, "top_k": top_k, "filters": filters})
            if filters.get("filename_in") == ["observation_guide.md", "lexical_support.md"]:
                return {"results": [{"doc_id": "d-instruction"}], "debug_trace": {"route": {"model": "instruction"}}}
            return {"results": [{"doc_id": "d-knowledge"}], "debug_trace": {"route": {"model": "knowledge"}}}

        out = retrieve.run(state, retrieve_fn=fake_retrieve)
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0]["filters"]["filename_in"], ["observation_guide.md", "lexical_support.md"])
        self.assertEqual(calls[0]["query_text"], "instruction guidance action guide step observation")
        self.assertEqual(calls[1]["query_text"], "What does this word mean?")
        self.assertEqual(calls[2]["filters"]["filename"], "knowledge.pdf")
        self.assertEqual(out["raw_evidence"][0]["retrieval_domain"], "instruction_source")
        self.assertEqual(out["raw_evidence"][-1]["retrieval_domain"], "knowledge_source")
        self.assertEqual(out["retrieval_debug_trace"]["domains"]["instruction_source"]["route"]["model"], "instruction")
        self.assertEqual(out["retrieval_debug_trace"]["domains"]["knowledge_source"]["route"]["model"], "knowledge")
        self.assertEqual(
            out["retrieval_debug_trace"]["domains"]["instruction_source"]["executed_queries"],
            ["instruction guidance action guide step observation", "What does this word mean?"],
        )
        self.assertEqual(
            out["retrieval_debug_trace"]["domains"]["knowledge_source"]["executed_queries"],
            ["What does this word mean?"],
        )

    def test_retrieves_templates_separately_and_excludes_output_artifacts(self):
        state = {
            "user_query": "Generate director bundle",
            "retrieval_plan": {"query_text": "Generate director bundle", "top_k": 3, "filters": {"app_id": "app-1"}},
            "turn_execution_plan": {
                "resource_requests": [
                    {
                        "filename": "Director_Bundle_Spec.md",
                        "resource_role": "output_template",
                        "query_text": "output template for director bundle",
                        "load_strategy_hint": "vector_retrieve",
                    },
                    {
                        "filename": "Director_Bundle_Spec.md",
                        "resource_role": "output_template",
                        "query_text": "director bundle spec",
                        "load_strategy_hint": "vector_retrieve",
                    },
                ],
            },
        }
        calls = []

        def fake_retrieve(query_text, top_k, filters):
            calls.append({"query_text": query_text, "top_k": top_k, "filters": filters})
            return {"results": [{"doc_id": "d-template"}], "debug_trace": {"route": {"model": "template"}}}

        out = retrieve.run(state, retrieve_fn=fake_retrieve)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["filters"]["filename"], "Director_Bundle_Spec.md")
        self.assertEqual(calls[0]["query_text"], "output template for director bundle")
        self.assertEqual(out["raw_evidence"][0]["retrieval_domain"], "output_template")
        self.assertEqual(out["retrieval_debug_trace"]["domains"]["output_template"]["route"]["model"], "template")
        self.assertEqual(
            out["retrieval_debug_trace"]["domains"]["output_template"]["executed_queries"],
            ["output template for director bundle", "director bundle spec"],
        )

    def test_directly_loads_small_template_markdown_without_vector_retrieval(self):
        tmpdir = _workspace_tempdir("retrieve_template_inline_full")
        try:
            template_path = tmpdir / "answer_format_template.md"
            template_path.write_text("# Template\n## Observation\n## Meaning\n## Application", encoding="utf-8")
            state = {
                "user_query": "Format the answer clearly",
                "template_resource_load_plan": [
                    {
                        "filename": "answer_format_template.md",
                        "load_strategy": "inline_full",
                        "resource_role": "output_template",
                        "document_id": "tpl-1",
                    }
                ],
                "template_registry": {
                    "builder_documents": [
                        {
                            "id": "tpl-1",
                            "filename": "answer_format_template.md",
                            "file_path": str(template_path),
                            "size_bytes": template_path.stat().st_size,
                            "status": "ready",
                        }
                    ]
                },
                "retrieval_plan": {"query_text": "Format the answer clearly", "top_k": 3, "filters": {"app_id": "app-1"}},
                "turn_action_plan": {
                    "instruction_retrieval": {"enabled": False},
                    "knowledge_retrieval": {"enabled": False},
                    "template_retrieval": {"enabled": False},
                },
            }

            def fake_retrieve(_query_text, _top_k, _filters):
                return {"results": [], "debug_trace": {"route": {"model": "knowledge"}}}

            out = retrieve.run(state, retrieve_fn=fake_retrieve)
            self.assertEqual(out["raw_evidence"][0]["retrieval_domain"], "output_template")
            self.assertEqual(out["template_resource_context"][0]["filename"], "answer_format_template.md")
            self.assertEqual(out["template_resource_context"][0]["load_strategy"], "inline_full")
            self.assertEqual(out["retrieval_debug_trace"]["domains"]["output_template"]["route"]["model"], "direct_load")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_direct_load_preserves_step_and_support_module_provenance_in_prepared_inputs_and_debug(self):
        tmpdir = _workspace_tempdir("retrieve_instruction_provenance")
        try:
            guide_path = tmpdir / "routing_guide.md"
            guide_path.write_text("# Routing\nFollow the procedure step carefully.", encoding="utf-8")
            state = {
                "user_query": "Use the routing guide",
                "template_registry": {
                    "builder_documents": [
                        {
                            "id": "doc-routing",
                            "filename": "routing_guide.md",
                            "file_path": str(guide_path),
                            "size_bytes": guide_path.stat().st_size,
                            "status": "ready",
                        }
                    ]
                },
                "retrieval_plan": {"query_text": "Use the routing guide", "top_k": 3, "filters": {"app_id": "app-1"}},
                "turn_execution_plan": {
                    "resource_requests": [
                        {
                            "filename": "routing_guide.md",
                            "resource_role": "instruction_source",
                            "load_strategy_hint": "inline_full",
                            "binding_id": "binding:procedure-routing",
                            "source_layer": "procedure_step",
                            "step_scope_id": "step:routing",
                            "support_module_id": "module:knowledge",
                        }
                    ]
                },
            }

            out = retrieve.run(state, retrieve_fn=lambda *_args, **_kwargs: {"results": [], "debug_trace": {"route": {"model": "mock"}}})

            self.assertEqual(out["prepared_inputs"]["resource_requests"][0]["source_layer"], "procedure_step")
            self.assertEqual(out["prepared_inputs"]["resource_requests"][0]["step_scope_id"], "step:routing")
            self.assertEqual(out["prepared_inputs"]["resource_requests"][0]["support_module_id"], "module:knowledge")
            self.assertEqual(out["instruction_resource_context"][0]["source_layer"], "procedure_step")
            self.assertEqual(out["instruction_resource_context"][0]["step_scope_id"], "step:routing")
            self.assertEqual(out["instruction_resource_context"][0]["support_module_id"], "module:knowledge")
            self.assertEqual(
                out["retrieval_debug_trace"]["domains"]["instruction_source"]["resource_requests"][0]["source_layer"],
                "procedure_step",
            )
            self.assertEqual(
                out["retrieval_debug_trace"]["domains"]["instruction_source"]["loaded_resources"][0]["support_module_id"],
                "module:knowledge",
            )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_bundled_instruction_direct_load_merges_unique_files_and_preserves_bundle_provenance(self):
        tmpdir = _workspace_tempdir("retrieve_bundled_instruction_direct_load")
        try:
            rules_path = tmpdir / "ministry_output_rules.md"
            rules_path.write_text("# Rules\nApply output rules.", encoding="utf-8")
            template_path = tmpdir / "delivery_package_template.md"
            template_path.write_text("# Template\nUse the delivery package template.", encoding="utf-8")
            state = {
                "user_query": "Continue the bundled ministry workflow",
                "template_registry": {
                    "builder_documents": [
                        {
                            "id": "doc-rules",
                            "filename": "ministry_output_rules.md",
                            "file_path": str(rules_path),
                            "size_bytes": rules_path.stat().st_size,
                            "status": "ready",
                        },
                        {
                            "id": "doc-template",
                            "filename": "delivery_package_template.md",
                            "file_path": str(template_path),
                            "size_bytes": template_path.stat().st_size,
                            "status": "ready",
                        },
                    ]
                },
                "retrieval_plan": {
                    "query_text": "Continue the bundled ministry workflow",
                    "top_k": 3,
                    "filters": {"app_id": "app-1"},
                },
                "turn_execution_plan": {
                    "active_execution_mode": "bundled",
                    "active_bundled_step_ids": [
                        "step:interaction_logic_execution_flow:2",
                        "step:interaction_logic_execution_flow:3",
                        "step:interaction_logic_execution_flow:4",
                        "step:interaction_logic_execution_flow:5",
                    ],
                    "bundled_entry_step_id": "step:interaction_logic_execution_flow:2",
                    "resource_requests": [
                        {
                            "filename": "ministry_output_rules.md",
                            "resource_role": "instruction_source",
                            "load_strategy_hint": "inline_full",
                            "source_layer": "procedure_step",
                            "step_scope_id": "step:interaction_logic_execution_flow:2",
                        },
                        {
                            "filename": "ministry_output_rules.md",
                            "resource_role": "instruction_source",
                            "load_strategy_hint": "inline_full",
                            "source_layer": "procedure_step",
                            "step_scope_id": "step:interaction_logic_execution_flow:2",
                        },
                        {
                            "filename": "delivery_package_template.md",
                            "resource_role": "instruction_source",
                            "load_strategy_hint": "inline_full",
                            "source_layer": "procedure_step",
                            "step_scope_id": "step:interaction_logic_execution_flow:2",
                        },
                    ],
                },
            }

            out = retrieve.run(
                state,
                retrieve_fn=lambda *_args, **_kwargs: {"results": [], "debug_trace": {"route": {"model": "mock"}}},
            )

            self.assertEqual(
                [item["filename"] for item in out["instruction_resource_context"]],
                ["ministry_output_rules.md", "delivery_package_template.md"],
            )
            self.assertEqual(
                [item["filename"] for item in out["retrieval_debug_trace"]["domains"]["instruction_source"]["loaded_resources"]],
                ["ministry_output_rules.md", "delivery_package_template.md"],
            )
            self.assertEqual(out["prepared_inputs"]["bundled_execution"]["active_execution_mode"], "bundled")
            self.assertEqual(
                out["prepared_inputs"]["bundled_execution"]["active_bundled_step_ids"],
                [
                    "step:interaction_logic_execution_flow:2",
                    "step:interaction_logic_execution_flow:3",
                    "step:interaction_logic_execution_flow:4",
                    "step:interaction_logic_execution_flow:5",
                ],
            )
            self.assertEqual(
                out["retrieval_debug_trace"]["bundled_execution"]["bundled_entry_step_id"],
                "step:interaction_logic_execution_flow:2",
            )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_bundled_direct_load_same_filename_preserves_multi_step_bundle_provenance(self):
        tmpdir = _workspace_tempdir("retrieve_bundled_instruction_shared_file")
        try:
            shared_path = tmpdir / "shared_guardrails.md"
            shared_path.write_text("# Guardrails\nShared bundled guidance.", encoding="utf-8")
            state = {
                "user_query": "Continue the bundled ministry workflow",
                "template_registry": {
                    "builder_documents": [
                        {
                            "id": "doc-shared",
                            "filename": "shared_guardrails.md",
                            "file_path": str(shared_path),
                            "size_bytes": shared_path.stat().st_size,
                            "status": "ready",
                        },
                    ]
                },
                "retrieval_plan": {
                    "query_text": "Continue the bundled ministry workflow",
                    "top_k": 3,
                    "filters": {"app_id": "app-1"},
                },
                "turn_execution_plan": {
                    "active_execution_mode": "bundled",
                    "active_bundled_step_ids": [
                        "step:interaction_logic_execution_flow:2",
                        "step:interaction_logic_execution_flow:3",
                    ],
                    "bundled_entry_step_id": "step:interaction_logic_execution_flow:2",
                    "resource_requests": [
                        {
                            "filename": "shared_guardrails.md",
                            "resource_role": "instruction_source",
                            "load_strategy_hint": "inline_full",
                            "source_layer": "procedure_step",
                            "step_scope_id": "step:interaction_logic_execution_flow:2",
                        },
                        {
                            "filename": "shared_guardrails.md",
                            "resource_role": "instruction_source",
                            "load_strategy_hint": "inline_full",
                            "source_layer": "procedure_step",
                            "step_scope_id": "step:interaction_logic_execution_flow:3",
                        },
                    ],
                },
            }

            out = retrieve.run(
                state,
                retrieve_fn=lambda *_args, **_kwargs: {"results": [], "debug_trace": {"route": {"model": "mock"}}},
            )

            self.assertEqual([item["filename"] for item in out["instruction_resource_context"]], ["shared_guardrails.md"])
            self.assertEqual(
                out["instruction_resource_context"][0]["bundled_step_scope_ids"],
                [
                    "step:interaction_logic_execution_flow:2",
                    "step:interaction_logic_execution_flow:3",
                ],
            )
            self.assertEqual(
                out["retrieval_debug_trace"]["domains"]["instruction_source"]["loaded_resources"][0]["bundled_step_scope_ids"],
                [
                    "step:interaction_logic_execution_flow:2",
                    "step:interaction_logic_execution_flow:3",
                ],
            )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_vector_retrieval_debug_trace_preserves_request_provenance_for_knowledge_requests(self):
        state = {
            "user_query": "Retrieve theological support",
            "retrieval_plan": {"query_text": "Retrieve theological support", "top_k": 3, "filters": {"app_id": "app-1"}},
            "turn_execution_plan": {
                "resource_requests": [
                    {
                        "filename": "theology_notes.pdf",
                        "resource_role": "knowledge_source",
                        "query_text": "Retrieve theological support",
                        "load_strategy_hint": "vector_retrieve",
                        "binding_id": "binding:step-support",
                        "source_layer": "support_module",
                        "step_scope_id": "step:theology-check",
                        "support_module_id": "module:theology-alignment",
                    }
                ]
            },
        }
        calls = []

        def fake_retrieve(query_text, top_k, filters):
            calls.append({"query_text": query_text, "top_k": top_k, "filters": dict(filters)})
            return {"results": [{"doc_id": "doc-theology", "title": "Theology Notes", "snippet": "Guardrails", "score": 0.8}], "debug_trace": {"route": {"model": "knowledge"}}}

        out = retrieve.run(state, retrieve_fn=fake_retrieve)

        self.assertEqual(len(calls), 1)
        self.assertEqual(out["prepared_inputs"]["resource_requests"][0]["source_layer"], "support_module")
        self.assertEqual(out["prepared_inputs"]["resource_requests"][0]["step_scope_id"], "step:theology-check")
        self.assertEqual(out["prepared_inputs"]["resource_requests"][0]["support_module_id"], "module:theology-alignment")
        self.assertEqual(
            out["retrieval_debug_trace"]["domains"]["knowledge_source"]["resource_requests"][0]["source_layer"],
            "support_module",
        )
        self.assertEqual(
            out["retrieval_debug_trace"]["domains"]["knowledge_source"]["resource_requests"][0]["support_module_id"],
            "module:theology-alignment",
        )

    def test_bundled_knowledge_requests_merge_unique_filename_filters_and_preserve_bundle_provenance(self):
        state = {
            "user_query": "Continue the bundled theology workflow",
            "retrieval_plan": {
                "query_text": "Continue the bundled theology workflow",
                "top_k": 3,
                "filters": {"app_id": "app-1"},
            },
            "turn_execution_plan": {
                "active_execution_mode": "bundled",
                "active_bundled_step_ids": [
                    "step:interaction_logic_execution_flow:2",
                    "step:interaction_logic_execution_flow:3",
                ],
                "bundled_entry_step_id": "step:interaction_logic_execution_flow:2",
                "resource_requests": [
                    {
                        "filename": "theology_notes.pdf",
                        "resource_role": "knowledge_source",
                        "query_text": "Continue the bundled theology workflow",
                        "load_strategy_hint": "vector_retrieve",
                        "source_layer": "procedure_step",
                        "step_scope_id": "step:interaction_logic_execution_flow:2",
                    },
                    {
                        "filename": "theology_notes.pdf",
                        "resource_role": "knowledge_source",
                        "query_text": "Continue the bundled theology workflow",
                        "load_strategy_hint": "vector_retrieve",
                        "source_layer": "procedure_step",
                        "step_scope_id": "step:interaction_logic_execution_flow:2",
                    },
                    {
                        "filename": "delivery_examples.pdf",
                        "resource_role": "knowledge_source",
                        "query_text": "Continue the bundled theology workflow",
                        "load_strategy_hint": "vector_retrieve",
                        "source_layer": "procedure_step",
                        "step_scope_id": "step:interaction_logic_execution_flow:2",
                    },
                ],
            },
        }
        calls = []

        def fake_retrieve(query_text, top_k, filters):
            calls.append({"query_text": query_text, "top_k": top_k, "filters": dict(filters)})
            return {"results": [], "debug_trace": {"route": {"model": "knowledge"}}}

        out = retrieve.run(state, retrieve_fn=fake_retrieve)

        self.assertEqual(len(calls), 1)
        self.assertEqual(
            calls[0]["filters"]["filename_in"],
            ["theology_notes.pdf", "delivery_examples.pdf"],
        )
        self.assertEqual(
            out["retrieval_debug_trace"]["bundled_execution"]["active_bundled_step_ids"],
            [
                "step:interaction_logic_execution_flow:2",
                "step:interaction_logic_execution_flow:3",
            ],
        )
        self.assertEqual(
            out["retrieval_debug_trace"]["domains"]["knowledge_source"]["resource_requests"][0]["step_scope_id"],
            "step:interaction_logic_execution_flow:2",
        )

    def test_retries_knowledge_retrieval_with_query_variants_when_initial_query_is_weak(self):
        state = {
            "user_query": "Summarize John 17 prayer focus and structure",
            "retrieval_plan": {"query_text": "Summarize John 17 prayer focus and structure", "top_k": 3, "filters": {"app_id": "app-1"}},
            "turn_execution_plan": {
                "actions": [
                    {
                        "action_type": "retrieve_knowledge",
                        "params": {
                            "query_text": "Summarize John 17 prayer focus and structure",
                            "query_variants": ["John 17 prayer focus", "John 17 structure"],
                            "fallback_queries": ["John 17"],
                            "retry_on_weak_results": True,
                        },
                    }
                ],
            },
        }
        calls = []

        def fake_retrieve(query_text, top_k, filters):
            calls.append({"query_text": query_text, "top_k": top_k, "filters": filters})
            if query_text == "Summarize John 17 prayer focus and structure":
                return {"results": [], "debug_trace": {"route": {"model": "primary"}}}
            if query_text == "John 17 prayer focus":
                return {"results": [{"doc_id": "d-focus", "chunk_id": "c1", "text": "Focus", "metadata": {"title": "Focus"}}], "debug_trace": {"route": {"model": "focus"}}}
            return {"results": [{"doc_id": "d-structure", "chunk_id": "c2", "text": "Structure", "metadata": {"title": "Structure"}}], "debug_trace": {"route": {"model": "structure"}}}

        out = retrieve.run(state, retrieve_fn=fake_retrieve)
        self.assertEqual(
            [call["query_text"] for call in calls],
            [
                "Summarize John 17 prayer focus and structure",
                "John 17 prayer focus",
                "John 17 structure",
                "John 17",
            ],
        )
        self.assertEqual(len(out["raw_evidence"]), 2)
        self.assertEqual(out["raw_evidence"][0]["retrieval_domain"], "knowledge_source")
        self.assertTrue(out["retrieval_debug_trace"]["domains"]["knowledge_source"]["weak_retry_triggered"])
        self.assertEqual(out["retrieval_debug_trace"]["domains"]["knowledge_source"]["attempt_count"], 4)

    def test_reranks_multi_query_knowledge_results_by_query_match_and_attempt_priority(self):
        state = {
            "user_query": "John 17 prayer focus and structure",
            "retrieval_plan": {"query_text": "John 17 prayer focus and structure", "top_k": 3, "filters": {"app_id": "app-1"}},
            "turn_execution_plan": {
                "actions": [
                    {
                        "action_type": "retrieve_knowledge",
                        "params": {
                            "query_text": "John 17 prayer focus and structure",
                            "query_variants": ["John 17 prayer focus", "John 17 structure"],
                            "retry_on_weak_results": True,
                        },
                    }
                ],
            },
        }

        def fake_retrieve(query_text, top_k, filters):
            _ = (top_k, filters)
            if query_text == "John 17 prayer focus and structure":
                return {"results": [], "debug_trace": {"route": {"model": "primary"}}}
            if query_text == "John 17 prayer focus":
                return {
                    "results": [
                        {"doc_id": "d-generic", "chunk_id": "c-generic", "title": "Generic Overview", "snippet": "John 17 overview", "score": 0.7},
                        {"doc_id": "d-focus", "chunk_id": "c-focus", "title": "Prayer Focus", "snippet": "John 17 prayer focus for disciples", "score": 0.65},
                    ],
                    "debug_trace": {"route": {"model": "focus"}},
                }
            return {
                "results": [
                    {"doc_id": "d-structure", "chunk_id": "c-structure", "title": "Structure Outline", "snippet": "John 17 structure and divisions", "score": 0.66},
                ],
                "debug_trace": {"route": {"model": "structure"}},
            }

        out = retrieve.run(state, retrieve_fn=fake_retrieve)
        self.assertEqual(out["raw_evidence"][0]["title"], "Prayer Focus")
        self.assertEqual(out["raw_evidence"][1]["title"], "Structure Outline")
        self.assertEqual(out["raw_evidence"][2]["title"], "Generic Overview")

    def test_appends_session_upload_evidence_without_rag_retrieval(self):
        state = {
            "user_query": "Analyze this uploaded file",
            "session_uploads": [
                {
                    "id": "upload-1",
                    "filename": "artifact.md",
                    "mime_type": "text/markdown",
                    "size_bytes": 42,
                    "file_path": "C:/tmp/artifact.md",
                    "text_content": "# Draft\nArtifact body",
                }
            ],
            "retrieval_plan": {"query_text": "Analyze this uploaded file", "top_k": 3, "filters": {"app_id": "app-1"}},
            "turn_action_plan": {
                "response_style": {
                    "use_session_upload_evidence": True,
                    "session_upload_ids": ["upload-1"],
                },
                "knowledge_retrieval": {
                    "enabled": False,
                },
            },
        }

        def fake_retrieve(_query_text, _top_k, _filters):
            return {"results": [], "debug_trace": {"route": {"model": "knowledge"}}}

        out = retrieve.run(state, retrieve_fn=fake_retrieve)
        self.assertEqual(out["raw_evidence"][0]["retrieval_domain"], "session_upload")
        self.assertEqual(out["raw_evidence"][0]["doc_id"], "upload-1")
        self.assertEqual(out["retrieval_debug_trace"]["domains"]["session_upload"]["route"]["model"], "session_upload")

    def test_directly_loads_small_instruction_markdown_without_vector_retrieval(self):
        tmpdir = _workspace_tempdir("retrieve_inline_full")
        try:
            guide_path = tmpdir / "observation_guide.md"
            guide_path.write_text("# Observation\nAsk 1-3 observation questions and wait for the learner response.", encoding="utf-8")
            state = {
                "user_query": "Study this passage",
                "selected_instruction_block": {"title": "細察事實 (Observation)", "objective": "Observe the passage"},
                "selected_instruction_block_text": "Use observation guidance for this turn.",
                "instruction_resource_load_plan": [
                    {
                        "filename": "observation_guide.md",
                        "load_strategy": "inline_full",
                        "resource_role": "instruction_source",
                        "document_id": "doc-1",
                    }
                ],
                "template_registry": {
                    "builder_documents": [
                        {
                            "id": "doc-1",
                            "filename": "observation_guide.md",
                            "file_path": str(guide_path),
                            "size_bytes": guide_path.stat().st_size,
                            "status": "ready",
                        }
                    ]
                },
                "retrieval_plan": {"query_text": "Study this passage", "top_k": 3, "filters": {"app_id": "app-1"}},
                "turn_action_plan": {
                    "instruction_retrieval": {"enabled": False},
                    "knowledge_retrieval": {"enabled": False},
                    "template_retrieval": {"enabled": False},
                },
            }

            calls = []

            def fake_retrieve(query_text, top_k, filters):
                calls.append({"query_text": query_text, "top_k": top_k, "filters": filters})
                return {"results": [], "debug_trace": {"route": {"model": "knowledge"}}}

            out = retrieve.run(state, retrieve_fn=fake_retrieve)
            self.assertEqual(out["raw_evidence"][0]["retrieval_domain"], "instruction_source")
            self.assertIn("Ask 1-3 observation questions", out["raw_evidence"][0]["snippet"])
            self.assertEqual(out["instruction_resource_context"][0]["filename"], "observation_guide.md")
            self.assertEqual(out["instruction_resource_context"][0]["load_strategy"], "inline_full")
            self.assertEqual(out["retrieval_debug_trace"]["domains"]["instruction_source"]["route"]["model"], "direct_load")
            self.assertEqual(calls[0]["query_text"], "Study this passage")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_section_filters_large_instruction_markdown(self):
        tmpdir = _workspace_tempdir("retrieve_section_filter")
        try:
            guide_path = tmpdir / "large_guide.md"
            guide_path.write_text(
                "# Observation\nAsk observation questions.\n\n"
                "# Application\nHelp the learner apply the passage.\n\n"
                "# Lexical Notes\nExplain original language details when needed.",
                encoding="utf-8",
            )
            state = {
                "user_query": "Help me apply this passage",
                "selected_instruction_block": {"title": "身體力行 (Apply in Action)", "objective": "Apply the passage"},
                "selected_instruction_block_text": "Focus on application and concrete action.",
                "instruction_resource_load_plan": [
                    {
                        "filename": "large_guide.md",
                        "load_strategy": "section_filter",
                        "resource_role": "instruction_source",
                        "document_id": "doc-2",
                    }
                ],
                "template_registry": {
                    "builder_documents": [
                        {
                            "id": "doc-2",
                            "filename": "large_guide.md",
                            "file_path": str(guide_path),
                            "size_bytes": guide_path.stat().st_size,
                            "status": "ready",
                        }
                    ]
                },
                "retrieval_plan": {"query_text": "Help me apply this passage", "top_k": 3, "filters": {"app_id": "app-1"}},
                "turn_action_plan": {
                    "instruction_retrieval": {"enabled": False},
                    "knowledge_retrieval": {"enabled": False},
                    "template_retrieval": {"enabled": False},
                },
            }

            calls = []

            def fake_retrieve(query_text, top_k, filters):
                calls.append({"query_text": query_text, "top_k": top_k, "filters": filters})
                return {"results": [], "debug_trace": {"route": {"model": "knowledge"}}}

            out = retrieve.run(state, retrieve_fn=fake_retrieve)
            self.assertEqual(out["raw_evidence"][0]["retrieval_domain"], "instruction_source")
            self.assertIn("apply the passage", out["raw_evidence"][0]["snippet"].lower())
            self.assertNotIn("original language", out["raw_evidence"][0]["snippet"].lower())
            self.assertEqual(out["instruction_resource_context"][0]["filename"], "large_guide.md")
            self.assertEqual(out["instruction_resource_context"][0]["load_strategy"], "section_filter")
            self.assertIn("Application", out["instruction_resource_context"][0]["section_titles"])
            section_titles = out["retrieval_debug_trace"]["domains"]["instruction_source"]["loaded_resources"][0]["section_titles"]
            self.assertIn("Application", section_titles)
            self.assertNotIn("Lexical Notes", section_titles)
            self.assertEqual(calls[0]["query_text"], "Help me apply this passage")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_section_filters_large_template_markdown(self):
        tmpdir = _workspace_tempdir("retrieve_template_section_filter")
        try:
            template_path = tmpdir / "large_template.md"
            template_path.write_text(
                "# Observation Format\nUse observation headings.\n\n"
                "# Application Format\nUse application steps and action bullets.\n\n"
                "# Appendix\nOptional notes.",
                encoding="utf-8",
            )
            state = {
                "user_query": "Give me an application-focused output format",
                "selected_instruction_block": {"title": "Apply in Action", "objective": "Application"},
                "selected_instruction_block_text": "Focus on application output.",
                "template_resource_load_plan": [
                    {
                        "filename": "large_template.md",
                        "load_strategy": "section_filter",
                        "resource_role": "output_template",
                        "document_id": "tpl-2",
                    }
                ],
                "template_registry": {
                    "builder_documents": [
                        {
                            "id": "tpl-2",
                            "filename": "large_template.md",
                            "file_path": str(template_path),
                            "size_bytes": template_path.stat().st_size,
                            "status": "ready",
                        }
                    ]
                },
                "retrieval_plan": {"query_text": "Give me an application-focused output format", "top_k": 3, "filters": {"app_id": "app-1"}},
                "turn_action_plan": {
                    "instruction_retrieval": {"enabled": False},
                    "knowledge_retrieval": {"enabled": False},
                    "template_retrieval": {"enabled": False},
                },
            }

            def fake_retrieve(_query_text, _top_k, _filters):
                return {"results": [], "debug_trace": {"route": {"model": "knowledge"}}}

            out = retrieve.run(state, retrieve_fn=fake_retrieve)
            self.assertEqual(out["raw_evidence"][0]["retrieval_domain"], "output_template")
            self.assertEqual(out["template_resource_context"][0]["filename"], "large_template.md")
            self.assertEqual(out["template_resource_context"][0]["load_strategy"], "section_filter")
            self.assertIn("Application Format", out["template_resource_context"][0]["section_titles"])
            self.assertNotIn("Appendix", out["template_resource_context"][0]["content"])
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_prepares_instruction_resources_from_turn_execution_plan_requests(self):
        tmpdir = _workspace_tempdir("retrieve_plan_instruction_requests")
        try:
            guide_path = tmpdir / "observation_guide.md"
            guide_path.write_text("# Observation\nAsk observation questions.", encoding="utf-8")
            state = {
                "user_query": "Study this passage",
                "selected_instruction_block": {"title": "Observation", "objective": "Observe the passage"},
                "selected_instruction_block_text": "Use observation guidance.",
                "turn_execution_plan": {
                    "resource_requests": [
                        {
                            "filename": "observation_guide.md",
                            "resource_role": "instruction_source",
                            "purpose": "instruction_support",
                            "load_strategy_hint": "inline_full",
                        }
                    ]
                },
                "template_registry": {
                    "builder_documents": [
                        {
                            "id": "doc-1",
                            "filename": "observation_guide.md",
                            "file_path": str(guide_path),
                            "size_bytes": guide_path.stat().st_size,
                            "status": "ready",
                        }
                    ]
                },
                "retrieval_plan": {"query_text": "Study this passage", "top_k": 3, "filters": {"app_id": "app-1"}},
                "turn_action_plan": {
                    "instruction_retrieval": {"enabled": False},
                    "knowledge_retrieval": {"enabled": False},
                    "template_retrieval": {"enabled": False},
                },
            }

            out = retrieve.run(state, retrieve_fn=lambda *_args, **_kwargs: {"results": [], "debug_trace": {"route": {"model": "knowledge"}}})
            self.assertEqual(out["instruction_resource_context"][0]["filename"], "observation_guide.md")
            self.assertEqual(out["prepared_inputs"]["instruction_resource_context"][0]["filename"], "observation_guide.md")
            self.assertEqual(out["prepared_inputs"]["resource_requests"][0]["filename"], "observation_guide.md")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_prepared_inputs_include_session_upload_evidence_from_turn_execution_plan_requests(self):
        state = {
            "user_query": "Analyze the upload",
            "session_uploads": [
                {
                    "id": "upload-1",
                    "filename": "artifact.md",
                    "mime_type": "text/markdown",
                    "size_bytes": 20,
                    "file_path": "C:/tmp/artifact.md",
                    "text_content": "# Draft\nArtifact body",
                }
            ],
            "turn_execution_plan": {
                "resource_requests": [
                    {
                        "resource_id": "upload-1",
                        "resource_role": "knowledge_source",
                        "purpose": "session_upload",
                    }
                ]
            },
            "retrieval_plan": {"query_text": "Analyze the upload", "top_k": 3, "filters": {"app_id": "app-1"}},
            "turn_action_plan": {
                "knowledge_retrieval": {"enabled": False},
            },
        }

        out = retrieve.run(state, retrieve_fn=lambda *_args, **_kwargs: {"results": [], "debug_trace": {"route": {"model": "knowledge"}}})
        self.assertEqual(out["compressed_session_upload_evidence"][0]["doc_id"], "upload-1")
        self.assertEqual(out["prepared_inputs"]["session_upload_evidence"][0]["doc_id"], "upload-1")

    def test_turn_execution_plan_session_upload_requests_override_legacy_response_style_selection(self):
        state = {
            "user_query": "Analyze the selected upload",
            "session_uploads": [
                {
                    "id": "upload-1",
                    "filename": "legacy.md",
                    "mime_type": "text/markdown",
                    "size_bytes": 20,
                    "file_path": "C:/tmp/legacy.md",
                    "text_content": "# Legacy\nLegacy body",
                },
                {
                    "id": "upload-2",
                    "filename": "planned.md",
                    "mime_type": "text/markdown",
                    "size_bytes": 24,
                    "file_path": "C:/tmp/planned.md",
                    "text_content": "# Planned\nPlanned body",
                },
            ],
            "turn_execution_plan": {
                "resource_requests": [
                    {
                        "resource_id": "upload-2",
                        "resource_role": "knowledge_source",
                        "purpose": "session_upload",
                    }
                ]
            },
            "retrieval_plan": {"query_text": "Analyze the selected upload", "top_k": 3, "filters": {"app_id": "app-1"}},
            "turn_action_plan": {
                "response_style": {
                    "session_upload_ids": ["upload-1"],
                },
                "knowledge_retrieval": {"enabled": False},
            },
        }

        out = retrieve.run(state, retrieve_fn=lambda *_args, **_kwargs: {"results": [], "debug_trace": {"route": {"model": "knowledge"}}})
        self.assertEqual(out["compressed_session_upload_evidence"][0]["doc_id"], "upload-2")
        self.assertEqual(out["prepared_inputs"]["session_upload_evidence"][0]["doc_id"], "upload-2")

    def test_uses_turn_execution_plan_knowledge_requests_without_legacy_knowledge_plan(self):
        calls = []

        def fake_retrieve(query_text, top_k, filters):
            calls.append({"query_text": query_text, "top_k": top_k, "filters": filters})
            return {
                "results": [
                    {
                        "chunk": {
                            "doc_id": "k-1",
                            "text": "Prayer focus and structure notes.",
                            "metadata": {"title": "John 17 Notes"},
                            "chunk_id": "chunk-k1",
                        },
                        "score": 0.91,
                    }
                ],
                "debug_trace": {"route": {"model": "knowledge"}},
            }

        state = {
            "user_query": "Explain John 17 prayer flow",
            "turn_execution_plan": {
                "resource_requests": [
                    {
                        "filename": "john17_notes.md",
                        "resource_role": "knowledge_source",
                        "purpose": "knowledge_support",
                        "query_text": "John 17 prayer flow",
                        "context_hints": ["prayer structure", "focus"],
                        "objective": "Explain the prayer flow clearly",
                    }
                ]
            },
            "retrieval_plan": {"query_text": "Explain John 17 prayer flow", "top_k": 3, "filters": {"app_id": "app-1"}},
            "turn_action_plan": {},
        }

        out = retrieve.run(state, retrieve_fn=fake_retrieve)
        self.assertEqual(calls[0]["query_text"], "John 17 prayer flow")
        self.assertEqual(calls[0]["filters"]["filename"], "john17_notes.md")
        self.assertEqual(out["raw_evidence"][0]["retrieval_domain"], "knowledge_source")
        self.assertEqual(
            out["retrieval_debug_trace"]["domains"]["knowledge_source"]["executed_queries"],
            ["John 17 prayer flow"],
        )

    def test_one_of_binding_selects_single_matching_instruction_resource(self):
        tmpdir = _workspace_tempdir("retrieve_one_of_binding")
        try:
            prompt_path = tmpdir / "export_prompt_guide.md"
            prompt_path.write_text("# Export Prompt\nUse the export prompt flow.", encoding="utf-8")
            rubric_path = tmpdir / "evaluation_rubric.md"
            rubric_path.write_text("# Rubric\nUse the evaluation rubric.", encoding="utf-8")
            state = {
                "user_query": "Use the export prompt guide",
                "selected_instruction_block": {"title": "Export", "objective": "Prepare export prompt"},
                "selected_instruction_block_text": "Use the active export instruction resource.",
                "session_execution_state": {
                    "active_binding_ids": ["binding-export-guide"],
                    "artifact_gate_status": {},
                },
                "turn_execution_plan": {
                    "resource_requests": [
                        {
                            "filename": "export_prompt_guide.md",
                            "resource_role": "instruction_source",
                            "resource_kind": "instruction_resource",
                            "binding_id": "binding-export-guide",
                            "query_text": "export prompt guide",
                            "load_strategy_hint": "inline_full",
                        },
                        {
                            "filename": "evaluation_rubric.md",
                            "resource_role": "instruction_source",
                            "resource_kind": "instruction_resource",
                            "binding_id": "binding-export-guide",
                            "query_text": "evaluation rubric",
                            "load_strategy_hint": "inline_full",
                        },
                    ]
                },
                "template_registry": {
                    "builder_documents": [
                        {"id": "doc-1", "filename": "export_prompt_guide.md", "file_path": str(prompt_path), "status": "ready"},
                        {"id": "doc-2", "filename": "evaluation_rubric.md", "file_path": str(rubric_path), "status": "ready"},
                    ]
                },
                "retrieval_plan": {"query_text": "Use the export prompt guide", "top_k": 3, "filters": {"app_id": "app-1"}},
            }

            out = retrieve.run(state, retrieve_fn=lambda *_args, **_kwargs: {"results": [], "debug_trace": {"route": {"model": "knowledge"}}})
            self.assertEqual([item["filename"] for item in out["instruction_resource_context"]], ["export_prompt_guide.md"])
            self.assertEqual(out["instruction_resource_context"][0]["binding_id"], "binding-export-guide")
            self.assertEqual(out["prepared_inputs"]["instruction_resource_context"][0]["binding_id"], "binding-export-guide")
            self.assertEqual(out["prepared_inputs"]["active_binding_ids"], ["binding-export-guide"])
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_multi_required_binding_loads_all_instruction_resources(self):
        tmpdir = _workspace_tempdir("retrieve_multi_required_binding")
        try:
            first_path = tmpdir / "phase_rules.md"
            first_path.write_text("# Rules\nPhase-specific rules.", encoding="utf-8")
            second_path = tmpdir / "phase_examples.md"
            second_path.write_text("# Examples\nPhase-specific examples.", encoding="utf-8")
            state = {
                "user_query": "Run the phase bundle",
                "session_execution_state": {
                    "active_binding_ids": ["binding-phase-bundle"],
                    "artifact_gate_status": {},
                },
                "turn_execution_plan": {
                    "resource_requests": [
                        {
                            "filename": "phase_rules.md",
                            "resource_role": "instruction_source",
                            "resource_kind": "instruction_resource",
                            "binding_id": "binding-phase-bundle",
                            "dependency_group_id": "group-phase-bundle",
                            "load_strategy_hint": "inline_full",
                        },
                        {
                            "filename": "phase_examples.md",
                            "resource_role": "instruction_source",
                            "resource_kind": "instruction_resource",
                            "binding_id": "binding-phase-bundle",
                            "dependency_group_id": "group-phase-bundle",
                            "load_strategy_hint": "inline_full",
                        },
                    ]
                },
                "template_registry": {
                    "builder_documents": [
                        {"id": "doc-1", "filename": "phase_rules.md", "file_path": str(first_path), "status": "ready"},
                        {"id": "doc-2", "filename": "phase_examples.md", "file_path": str(second_path), "status": "ready"},
                    ]
                },
                "retrieval_plan": {"query_text": "Run the phase bundle", "top_k": 3, "filters": {"app_id": "app-1"}},
            }

            out = retrieve.run(state, retrieve_fn=lambda *_args, **_kwargs: {"results": [], "debug_trace": {"route": {"model": "knowledge"}}})
            self.assertEqual(
                [item["filename"] for item in out["instruction_resource_context"]],
                ["phase_rules.md", "phase_examples.md"],
            )
            self.assertTrue(all(item["binding_id"] == "binding-phase-bundle" for item in out["instruction_resource_context"]))
            self.assertTrue(all(item["dependency_group_id"] == "group-phase-bundle" for item in out["instruction_resource_context"]))
            self.assertEqual(out["prepared_inputs"]["instruction_resource_context"][1]["dependency_group_id"], "group-phase-bundle")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_required_artifact_gate_blocks_retrieval_when_upload_missing(self):
        calls = {"count": 0}

        def fake_retrieve(_query_text, _top_k, _filters):
            calls["count"] += 1
            return {"results": [], "debug_trace": {"route": {"model": "knowledge"}}}

        state = {
            "user_query": "Continue with the workflow",
            "session_execution_state": {
                "active_binding_ids": ["binding-director-bundle"],
                "artifact_gate_status": {},
            },
            "turn_execution_plan": {
                "resource_requests": [
                    {
                        "resource_role": "knowledge_source",
                        "binding_id": "binding-director-bundle",
                        "artifact_role": "director_bundle",
                        "required_for_progression": True,
                        "purpose": "session_upload",
                        "filename": "Director Bundle.md",
                    }
                ]
            },
            "retrieval_plan": {"query_text": "Continue with the workflow", "top_k": 3, "filters": {"app_id": "app-1"}},
        }

        out = retrieve.run(state, retrieve_fn=fake_retrieve)
        self.assertEqual(calls["count"], 0)
        self.assertEqual(out["raw_evidence"], [])
        self.assertTrue(out["retrieval_debug_trace"]["retrieval_bypassed"])
        self.assertEqual(out["retrieval_debug_trace"]["retrieval_bypass_reason"], "missing_required_artifact")
        self.assertEqual(out["retrieval_debug_trace"]["active_binding_ids"], ["binding-director-bundle"])
        self.assertEqual(out["retrieval_debug_trace"]["artifact_gate_status"]["director_bundle"]["status"], "blocked")
        self.assertEqual(out["retrieval_debug_trace"]["artifact_gate_status"]["director_bundle"]["reason"], "missing_required_artifact")

    def test_command_trigger_binding_loads_export_template_resources(self):
        tmpdir = _workspace_tempdir("retrieve_command_trigger_template_binding")
        try:
            template_path = tmpdir / "export_template.md"
            template_path.write_text("# Export Template\nUse this export template.", encoding="utf-8")
            state = {
                "user_query": "/generate_video_prompt",
                "session_execution_state": {
                    "active_binding_ids": ["binding-export-template"],
                    "artifact_gate_status": {},
                },
                "turn_execution_plan": {
                    "resource_requests": [
                        {
                            "filename": "export_template.md",
                            "resource_role": "output_template",
                            "resource_kind": "template_resource",
                            "binding_id": "binding-export-template",
                            "query_text": "video prompt export template",
                            "load_strategy_hint": "inline_full",
                        }
                    ]
                },
                "template_registry": {
                    "builder_documents": [
                        {"id": "tpl-1", "filename": "export_template.md", "file_path": str(template_path), "status": "ready"},
                    ]
                },
                "retrieval_plan": {"query_text": "/generate_video_prompt", "top_k": 3, "filters": {"app_id": "app-1"}},
            }

            out = retrieve.run(state, retrieve_fn=lambda *_args, **_kwargs: {"results": [], "debug_trace": {"route": {"model": "knowledge"}}})
            self.assertEqual(out["template_resource_context"][0]["filename"], "export_template.md")
            self.assertEqual(out["template_resource_context"][0]["binding_id"], "binding-export-template")
            self.assertEqual(out["template_resource_context"][0]["resource_kind"], "template_resource")
            self.assertEqual(out["prepared_inputs"]["template_resource_context"][0]["binding_id"], "binding-export-template")
            self.assertEqual(out["prepared_inputs"]["active_binding_ids"], ["binding-export-template"])
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_ignores_inactive_binding_requests_when_active_binding_set_is_present(self):
        tmpdir = _workspace_tempdir("retrieve_ignores_inactive_bindings")
        try:
            active_path = tmpdir / "active_guide.md"
            active_path.write_text("# Active\nUse the active binding guide.", encoding="utf-8")
            inactive_path = tmpdir / "inactive_guide.md"
            inactive_path.write_text("# Inactive\nThis should not load.", encoding="utf-8")
            state = {
                "user_query": "Use the active guide only",
                "session_execution_state": {
                    "active_binding_ids": ["binding-active"],
                    "artifact_gate_status": {},
                },
                "turn_execution_plan": {
                    "resource_requests": [
                        {
                            "filename": "active_guide.md",
                            "resource_role": "instruction_source",
                            "resource_kind": "instruction_resource",
                            "binding_id": "binding-active",
                            "query_text": "active guide",
                            "load_strategy_hint": "inline_full",
                        },
                        {
                            "filename": "inactive_guide.md",
                            "resource_role": "instruction_source",
                            "resource_kind": "instruction_resource",
                            "binding_id": "binding-inactive",
                            "query_text": "inactive guide",
                            "load_strategy_hint": "inline_full",
                        },
                    ]
                },
                "template_registry": {
                    "builder_documents": [
                        {"id": "doc-active", "filename": "active_guide.md", "file_path": str(active_path), "status": "ready"},
                        {"id": "doc-inactive", "filename": "inactive_guide.md", "file_path": str(inactive_path), "status": "ready"},
                    ]
                },
                "retrieval_plan": {"query_text": "Use the active guide only", "top_k": 3, "filters": {"app_id": "app-1"}},
            }

            out = retrieve.run(state, retrieve_fn=lambda *_args, **_kwargs: {"results": [], "debug_trace": {"route": {"model": "knowledge"}}})
            self.assertEqual([item["filename"] for item in out["instruction_resource_context"]], ["active_guide.md"])
            self.assertEqual([item.get("binding_id") for item in out["prepared_inputs"]["instruction_resource_context"]], ["binding-active"])
            self.assertEqual(
                [item.get("binding_id") for item in out["prepared_inputs"]["resource_requests"]],
                ["binding-active"],
            )
            self.assertEqual(out["prepared_inputs"]["active_binding_ids"], ["binding-active"])
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_ignores_inactive_knowledge_binding_requests_when_active_binding_set_is_present(self):
        calls = []

        def fake_retrieve(query_text, top_k, filters):
            calls.append({"query_text": query_text, "top_k": top_k, "filters": filters})
            return {
                "results": [
                    {
                        "chunk": {
                            "doc_id": "k-active",
                            "text": "Active knowledge guidance.",
                            "metadata": {"title": "Active Knowledge"},
                            "chunk_id": "chunk-active",
                        },
                        "score": 0.9,
                    }
                ],
                "debug_trace": {"route": {"model": "knowledge"}},
            }

        state = {
            "user_query": "Use the active knowledge source",
            "session_execution_state": {
                "active_binding_ids": ["binding-knowledge-active"],
                "artifact_gate_status": {},
            },
            "turn_execution_plan": {
                "resource_requests": [
                    {
                        "filename": "active_notes.md",
                        "resource_role": "knowledge_source",
                        "binding_id": "binding-knowledge-active",
                        "query_text": "active knowledge query",
                    },
                    {
                        "filename": "inactive_notes.md",
                        "resource_role": "knowledge_source",
                        "binding_id": "binding-knowledge-inactive",
                        "query_text": "inactive knowledge query",
                    },
                ],
                "actions": [
                    {
                        "action_type": "retrieve_knowledge",
                        "params": {
                            "query_text": "Use the active knowledge source",
                        },
                    }
                ],
            },
            "retrieval_plan": {"query_text": "Use the active knowledge source", "top_k": 3, "filters": {"app_id": "app-1"}},
        }

        out = retrieve.run(state, retrieve_fn=fake_retrieve)
        self.assertEqual(calls[0]["query_text"], "Use the active knowledge source")
        self.assertEqual(calls[0]["filters"]["filename"], "active_notes.md")
        self.assertNotIn("filename_in", calls[0]["filters"])
        executed_queries = out["retrieval_debug_trace"]["domains"]["knowledge_source"]["executed_queries"]
        self.assertEqual(executed_queries, ["Use the active knowledge source"])
        self.assertNotIn("inactive knowledge query", executed_queries)

    def test_prepared_inputs_export_only_resolved_one_of_candidate(self):
        tmpdir = _workspace_tempdir("retrieve_prepared_inputs_one_of_export")
        try:
            chosen_path = tmpdir / "chosen_template.md"
            chosen_path.write_text("# Chosen\nUse this candidate.", encoding="utf-8")
            other_path = tmpdir / "other_template.md"
            other_path.write_text("# Other\nDo not export this candidate.", encoding="utf-8")
            state = {
                "user_query": "Use the chosen special template",
                "session_execution_state": {
                    "active_binding_ids": ["binding-one-of"],
                    "artifact_gate_status": {},
                },
                "turn_execution_plan": {
                    "resource_requests": [
                        {
                            "filename": "chosen_template.md",
                            "resource_role": "instruction_source",
                            "binding_id": "binding-one-of",
                            "resource_kind": "instruction_resource",
                            "query_text": "chosen special template",
                            "load_strategy_hint": "inline_full",
                        },
                        {
                            "filename": "other_template.md",
                            "resource_role": "instruction_source",
                            "binding_id": "binding-one-of",
                            "resource_kind": "instruction_resource",
                            "query_text": "other template",
                            "load_strategy_hint": "inline_full",
                        },
                    ]
                },
                "template_registry": {
                    "builder_documents": [
                        {"id": "doc-chosen", "filename": "chosen_template.md", "file_path": str(chosen_path), "status": "ready"},
                        {"id": "doc-other", "filename": "other_template.md", "file_path": str(other_path), "status": "ready"},
                    ]
                },
                "retrieval_plan": {"query_text": "Use the chosen special template", "top_k": 3, "filters": {"app_id": "app-1"}},
            }

            out = retrieve.run(state, retrieve_fn=lambda *_args, **_kwargs: {"results": [], "debug_trace": {"route": {"model": "knowledge"}}})
            self.assertEqual(
                [item.get("filename") for item in out["prepared_inputs"]["resource_requests"]],
                ["chosen_template.md"],
            )
            self.assertEqual(
                [item.get("filename") for item in out["instruction_resource_context"]],
                ["chosen_template.md"],
            )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_one_of_required_artifact_gate_evaluates_only_resolved_candidate(self):
        state = {
            "user_query": "Continue with the chosen bundle upload flow",
            "session_execution_state": {
                "active_binding_ids": ["binding-upload-one-of"],
                "artifact_gate_status": {},
            },
            "session_uploads": [
                {
                    "id": "upload-1",
                    "filename": "chosen_bundle.md",
                    "artifact_role": "chosen_bundle",
                    "text_content": "# Chosen\nBundle",
                }
            ],
            "turn_execution_plan": {
                "resource_requests": [
                    {
                        "filename": "chosen_bundle.md",
                        "resource_role": "knowledge_source",
                        "binding_id": "binding-upload-one-of",
                        "artifact_role": "chosen_bundle",
                        "required_for_progression": True,
                        "query_text": "chosen bundle upload",
                    },
                    {
                        "filename": "other_bundle.md",
                        "resource_role": "knowledge_source",
                        "binding_id": "binding-upload-one-of",
                        "artifact_role": "other_bundle",
                        "required_for_progression": True,
                        "query_text": "other bundle",
                    },
                ]
            },
            "retrieval_plan": {"query_text": "Continue with the chosen bundle upload flow", "top_k": 3, "filters": {"app_id": "app-1"}},
        }

        out = retrieve.run(state, retrieve_fn=lambda *_args, **_kwargs: {"results": [], "debug_trace": {"route": {"model": "knowledge"}}})
        self.assertFalse(out["retrieval_debug_trace"]["retrieval_bypassed"])
        self.assertEqual(
            out["prepared_inputs"]["artifact_gate_status"]["chosen_bundle"]["status"],
            "ready",
        )
        self.assertNotIn("other_bundle", out["prepared_inputs"]["artifact_gate_status"])
        self.assertEqual(
            [item.get("filename") for item in out["prepared_inputs"]["resource_requests"]],
            ["chosen_bundle.md"],
        )


if __name__ == "__main__":
    unittest.main()
