"""Graph state definitions aligned to RAGenius LangGraph blueprint.

No business logic lives here. This file only defines shared workflow state
contracts used by node stubs and graph assembly.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict

from pydantic import BaseModel, ConfigDict


class GraphState(TypedDict, total=False):
    """Mutable state object passed between workflow nodes."""

    # identity / routing
    session_id: str
    collection_id: str
    domain: str
    user_id: str

    # frozen versions (session-level)
    config_version: int
    adapter_version: int
    template_version: int

    # user input / context
    user_query: str
    turn_input_type: str
    session_upload_event_ids: List[str]
    pending_upload_analysis: bool
    chat_history: List[Dict[str, Any]]
    session_uploads: List[Dict[str, Any]]

    # config / adapter / template assets
    config_pdf_path: str
    config_extracted_text: str
    config_json: Dict[str, Any]
    adapter_draft: Dict[str, Any]
    adapter_draft_version: int
    adapter_json: Dict[str, Any]
    template_registry: Dict[str, Any]
    full_instruction_text: str
    instruction_scope_candidates: List[Dict[str, Any]]
    instruction_runtime_model: Dict[str, Any]
    session_execution_state: Dict[str, Any]
    session_lane_state: Dict[str, Any]
    approved_content_snapshot: Dict[str, Any]
    execution_intent_record: Dict[str, Any]
    turn_routing_decision: Dict[str, Any]
    turn_action_plan: Dict[str, Any]
    turn_execution_plan: Dict[str, Any]
    workflow_progress: Dict[str, Any]
    instruction_workflow: Dict[str, Any]
    instruction_module: Dict[str, Any]
    instruction_step: Dict[str, Any]
    global_instruction_context: Dict[str, Any]
    selected_instruction_block: Dict[str, Any]
    selected_instruction_block_text: str
    instruction_resource_load_plan: List[Dict[str, Any]]
    instruction_resource_context: List[Dict[str, Any]]
    template_resource_load_plan: List[Dict[str, Any]]
    template_resource_context: List[Dict[str, Any]]
    instruction_resource: str
    instruction_resource_filters: Dict[str, Any]
    template_resource_filters: Dict[str, Any]

    # planner / retrieval artifacts
    planner_output: Dict[str, Any]
    retrieval_plan: Dict[str, Any]
    retrieval_debug_trace: Dict[str, Any]
    raw_evidence: List[Dict[str, Any]]
    compressed_evidence: List[Dict[str, Any]]
    compressed_instruction_evidence: List[Dict[str, Any]]
    compressed_knowledge_evidence: List[Dict[str, Any]]
    compressed_template_evidence: List[Dict[str, Any]]
    compressed_session_upload_evidence: List[Dict[str, Any]]
    evidence_analysis: Dict[str, Any]
    intermediate_outputs: List[Dict[str, Any]]
    execution_artifacts: List[Dict[str, Any]]
    presentation_policy: Dict[str, Any]
    visible_outputs: List[Dict[str, Any]]
    hidden_outputs: List[Dict[str, Any]]
    tool_results: List[Dict[str, Any]]
    assembly_state: Dict[str, Any]

    # final output
    final_answer: Dict[str, Any]
    answer_generation_meta: Dict[str, Any]

    # runtime dependency injection hooks (for pipeline execution)
    _session_repo: Any
    _chat_repo: Any
    _planner_repo: Any
    _retrieval_repo: Any
    _llm_config_extractor: Any
    _llm_generate_adapter: Any
    _llm_planner: Any
    _retrieve_fn: Any
    _llm_evidence_analysis: Any
    _llm_answer: Any


class GraphStateModel(BaseModel):
    """Pydantic mirror for optional serialization and schema checks."""

    session_id: Optional[str] = None
    collection_id: Optional[str] = None
    domain: Optional[str] = None
    user_id: Optional[str] = None

    config_version: Optional[int] = None
    adapter_version: Optional[int] = None
    template_version: Optional[int] = None

    user_query: Optional[str] = None
    turn_input_type: Optional[str] = None
    session_upload_event_ids: Optional[List[str]] = None
    pending_upload_analysis: Optional[bool] = None
    chat_history: Optional[List[Dict[str, Any]]] = None
    session_uploads: Optional[List[Dict[str, Any]]] = None

    config_pdf_path: Optional[str] = None
    config_extracted_text: Optional[str] = None
    config_json: Optional[Dict[str, Any]] = None
    adapter_draft: Optional[Dict[str, Any]] = None
    adapter_draft_version: Optional[int] = None
    adapter_json: Optional[Dict[str, Any]] = None
    template_registry: Optional[Dict[str, Any]] = None
    full_instruction_text: Optional[str] = None
    instruction_scope_candidates: Optional[List[Dict[str, Any]]] = None
    instruction_runtime_model: Optional[Dict[str, Any]] = None
    session_execution_state: Optional[Dict[str, Any]] = None
    session_lane_state: Optional[Dict[str, Any]] = None
    approved_content_snapshot: Optional[Dict[str, Any]] = None
    execution_intent_record: Optional[Dict[str, Any]] = None
    turn_routing_decision: Optional[Dict[str, Any]] = None
    turn_action_plan: Optional[Dict[str, Any]] = None
    turn_execution_plan: Optional[Dict[str, Any]] = None
    workflow_progress: Optional[Dict[str, Any]] = None
    instruction_workflow: Optional[Dict[str, Any]] = None
    instruction_module: Optional[Dict[str, Any]] = None
    instruction_step: Optional[Dict[str, Any]] = None
    global_instruction_context: Optional[Dict[str, Any]] = None
    selected_instruction_block: Optional[Dict[str, Any]] = None
    selected_instruction_block_text: Optional[str] = None
    instruction_resource_load_plan: Optional[List[Dict[str, Any]]] = None
    instruction_resource_context: Optional[List[Dict[str, Any]]] = None
    template_resource_load_plan: Optional[List[Dict[str, Any]]] = None
    template_resource_context: Optional[List[Dict[str, Any]]] = None
    instruction_resource: Optional[str] = None
    instruction_resource_filters: Optional[Dict[str, Any]] = None
    template_resource_filters: Optional[Dict[str, Any]] = None

    planner_output: Optional[Dict[str, Any]] = None
    retrieval_plan: Optional[Dict[str, Any]] = None
    retrieval_debug_trace: Optional[Dict[str, Any]] = None
    raw_evidence: Optional[List[Dict[str, Any]]] = None
    compressed_evidence: Optional[List[Dict[str, Any]]] = None
    compressed_instruction_evidence: Optional[List[Dict[str, Any]]] = None
    compressed_knowledge_evidence: Optional[List[Dict[str, Any]]] = None
    compressed_template_evidence: Optional[List[Dict[str, Any]]] = None
    compressed_session_upload_evidence: Optional[List[Dict[str, Any]]] = None
    evidence_analysis: Optional[Dict[str, Any]] = None
    intermediate_outputs: Optional[List[Dict[str, Any]]] = None
    execution_artifacts: Optional[List[Dict[str, Any]]] = None
    presentation_policy: Optional[Dict[str, Any]] = None
    visible_outputs: Optional[List[Dict[str, Any]]] = None
    hidden_outputs: Optional[List[Dict[str, Any]]] = None
    tool_results: Optional[List[Dict[str, Any]]] = None
    assembly_state: Optional[Dict[str, Any]] = None

    final_answer: Optional[Dict[str, Any]] = None
    answer_generation_meta: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(extra="allow")
