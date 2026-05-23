"""Generic runtime models for GPTs-style application execution.

These models are application-agnostic. They normalize builder instructions into
runtime structures that can drive turn-level planning and dual-domain retrieval.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


ResourceDomain = Literal["instruction_source", "knowledge_source", "output_template", "output_artifact"]
ResourceUse = Literal["primary", "support", "auxiliary"]
ResourceRequestSourceLayer = Literal["procedure_step", "support_module", "direct_query"]
ExecutionStatus = Literal["idle", "guiding", "waiting_user", "answering", "completed", "ended"]
ActionType = Literal["guide", "answer", "clarify", "advance_step", "summarize", "end_session", "wait"]
InstructionBlockType = Literal["mode", "workflow", "step", "support_module", "rule", "generic"]
InstructionScopeType = Literal[
    "global",
    "mode",
    "workflow",
    "module",
    "step",
    "support_module",
    "response_logic",
    "composition_rule",
    "generic",
]
TurnIntent = Literal[
    "start",
    "answer",
    "answer_prior_questions",
    "clarify",
    "advance",
    "switch_mode",
    "use_support_module",
    "analyze_upload",
    "structured_generation_brief",
    "freeform_generation_request",
    "app_scoped_question",
    "general_out_of_scope_question",
    "artifact_analysis",
    "session_followup",
    "assemble_output",
    "finalize",
    "unknown",
]
ActionTypeV2 = Literal[
    "respond_to_user",
    "generate_intermediate_output",
    "load_resource",
    "retrieve_knowledge",
    "invoke_tool",
    "invoke_skill",
    "assemble_output",
    "validate_output",
    "update_session_state",
]
BindingTriggerType = Literal[
    "phase",
    "module",
    "workflow_step",
    "command_trigger",
    "artifact_gate",
    "starter",
]
BindingMode = Literal[
    "none",
    "single_required",
    "one_of",
    "multi_required",
    "ordered_multi",
]
ResourceKind = Literal[
    "instruction_resource",
    "template_resource",
    "rubric_resource",
    "schema_anchor",
    "output_format_guide",
    "resource_index",
    "artifact_template",
]
ArtifactContractMode = Literal[
    "none",
    "produces_artifact",
    "requires_artifact",
    "updates_artifact",
]
InstructionServiceBlockType = Literal[
    "primary_workflow",
    "entry_mode",
    "support_module",
    "followup_module",
    "supplementary_workflow",
    "global_policy",
    "resource_catalog",
    "output_contract",
]
CompiledInstructionUnderstandingStatus = Literal["ready", "stale", "failed_compile", "building", "superseded"]
InstructionUnderstandingReviewStatus = Literal[
    "not_reviewed",
    "reviewed_ok",
    "reviewed_with_warnings",
    "review_failed",
    "review_stale",
]
InstructionUnderstandingCacheStatus = Literal[
    "hot",
    "stale_instructions",
    "stale_parser_contract",
    "stale_binding_logic",
    "stale_resource_catalog",
    "missing",
    "invalid",
]
InteractionLogicScope = Literal["global", "workflow", "step"]
InteractionLogicRuleType = Literal[
    "ask_wait_progress",
    "clarification_behavior",
    "response_handling",
    "stop_continue",
    "pacing",
    "safety_escalation",
]
RoutingConditionType = Literal["keyword", "semantic_intent", "threshold", "explicit_rule", "session_state"]
RoutingOutcomeType = Literal[
    "select_role",
    "select_workflow",
    "select_module",
    "select_supplementary_workflow",
    "select_style_profile",
    "go_to_step",
    "ask_clarification",
    "stop",
]
RoutingRuleKind = Literal[
    "intent_routing",
    "role_selection",
    "workflow_selection",
    "module_selection",
    "supplementary_selection",
    "style_selection",
    "mode_switch",
    "escalation",
]
SemanticPrimaryServiceMode = Literal["single_default_workflow", "intent_routed_multi_workflow", "mixed"]
ModuleOrchestrationSelectionMode = Literal["semantic", "trigger_based", "mixed"]
ModuleStopCondition = Literal["wait_for_user", "output_complete", "continue"]
InstructionApprovalDecision = Literal["approve", "reject", "modify", "manual_only"]


class InstructionResourceBinding(BaseModel):
    resource_id: str
    title: str
    filename: str
    domain: ResourceDomain
    document_id: Optional[str] = None
    file_status: Optional[str] = None
    use_type: ResourceUse = "primary"
    confidence: float = 1.0
    linked_mode_id: Optional[str] = None
    linked_workflow: Optional[str] = None
    linked_step_order: Optional[int] = None
    linked_step_title: Optional[str] = None
    description: Optional[str] = None
    source_section_role: Optional[str] = None
    activation_signals: List[str] = Field(default_factory=list)
    triggers: List[str] = Field(default_factory=list)


class InstructionBlock(BaseModel):
    block_id: str
    block_type: InstructionBlockType
    title: str
    body_text: str
    objective: Optional[str] = None
    operation_text: Optional[str] = None
    response_hint: Optional[str] = None
    activation_triggers: List[str] = Field(default_factory=list)
    referenced_resources: List[str] = Field(default_factory=list)
    document_ids: List[str] = Field(default_factory=list)
    linked_mode_id: Optional[str] = None
    linked_workflow: Optional[str] = None
    linked_step_order: Optional[int] = None
    linked_step_title: Optional[str] = None
    declared_binding_id: Optional[str] = None
    command_triggers: List[str] = Field(default_factory=list)
    artifact_role: Optional[str] = None


class DependencyGroup(BaseModel):
    group_id: str
    title: str
    resource_ids: List[str] = Field(default_factory=list)
    filenames: List[str] = Field(default_factory=list)
    ordered: bool = False
    notes: Optional[str] = None


class ArtifactContract(BaseModel):
    mode: ArtifactContractMode = "none"
    artifact_role: Optional[str] = None
    filename_patterns: List[str] = Field(default_factory=list)
    schema_anchor_filename: Optional[str] = None
    required_for_progression: bool = False
    missing_artifact_prompt: Optional[str] = None


class PhaseResourceBinding(BaseModel):
    binding_id: str
    title: str
    trigger_type: BindingTriggerType
    binding_mode: BindingMode = "none"
    trigger_signals: List[str] = Field(default_factory=list)
    scope_id: Optional[str] = None
    step_order: Optional[int] = None
    resource_ids: List[str] = Field(default_factory=list)
    filenames: List[str] = Field(default_factory=list)
    resource_kinds: List[ResourceKind] = Field(default_factory=list)
    dependency_groups: List[str] = Field(default_factory=list)
    artifact_contract: ArtifactContract = Field(default_factory=ArtifactContract)
    objective: Optional[str] = None
    activation_reason: Optional[str] = None
    priority: int = 100


class InstructionResourceLoadPlan(BaseModel):
    resource_id: Optional[str] = None
    filename: str
    resource_role: ResourceDomain
    load_strategy: Literal["inline_full", "section_filter", "vector_retrieve"]
    reason: Optional[str] = None
    size_hint: Optional[str] = None
    document_id: Optional[str] = None


class InstructionScopeSelection(BaseModel):
    scope_id: str
    scope_type: InstructionScopeType
    title: Optional[str] = None
    reason: Optional[str] = None


class InstructionHeadingNode(BaseModel):
    node_id: str
    level: int
    title: str
    normalized_title: str
    body_text: str = ""
    children: List["InstructionHeadingNode"] = Field(default_factory=list)
    source_span: Optional[Dict[str, Any]] = None


class GlobalAppDefaults(BaseModel):
    default_role_id: Optional[str] = None
    default_tone_style: Optional[str] = None


class GlobalAppContract(BaseModel):
    mission: Optional[str] = None
    objective: Optional[str] = None
    constraints: List[str] = Field(default_factory=list)
    security_rules: List[str] = Field(default_factory=list)
    boundaries: List[str] = Field(default_factory=list)
    global_defaults: GlobalAppDefaults = Field(default_factory=GlobalAppDefaults)
    confidence: Optional[float] = None


class InteractionLogicRule(BaseModel):
    rule_type: InteractionLogicRuleType
    expression: str


class InteractionLogicBlock(BaseModel):
    logic_id: str
    scope: InteractionLogicScope
    title: str
    source_section_id: str
    applies_to_ids: List[str] = Field(default_factory=list)
    rules: List[InteractionLogicRule] = Field(default_factory=list)
    confidence: Optional[float] = None


class RoleProfile(BaseModel):
    role_id: str
    name: str
    purpose: Optional[str] = None
    tone_style: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    allowed_workflow_ids: List[str] = Field(default_factory=list)
    allowed_module_ids: List[str] = Field(default_factory=list)
    default_for_intents: List[str] = Field(default_factory=list)
    confidence: Optional[float] = None


class RoutingCondition(BaseModel):
    condition_type: RoutingConditionType
    expression: str


class RoutingOutcome(BaseModel):
    outcome_type: RoutingOutcomeType
    target_id: Optional[str] = None


class RoutingRule(BaseModel):
    rule_id: str
    title: str
    source_section_id: str
    rule_kind: RoutingRuleKind
    conditions: List[RoutingCondition] = Field(default_factory=list)
    outcomes: List[RoutingOutcome] = Field(default_factory=list)
    confidence: Optional[float] = None


class ModuleTaskMapping(BaseModel):
    mapping_id: str
    task_pattern: str
    target_module_id: str
    priority: int = 0
    sequence_order: int = 0
    stop_condition: ModuleStopCondition = "continue"


class ModuleOrchestration(BaseModel):
    orchestration_id: str
    selection_mode: ModuleOrchestrationSelectionMode
    starter_required: bool = False
    assistant_suggestion_allowed: bool = True
    allow_multi_module: bool = True
    composition_mode: Literal["ordered_sequential"] = "ordered_sequential"
    task_module_mappings: List[ModuleTaskMapping] = Field(default_factory=list)
    confidence: Optional[float] = None


class ClarificationSlotPolicy(BaseModel):
    mode: Literal["threshold", "explicit_required_slots"]
    minimum_filled_slots: int = 0
    required_slots: List[str] = Field(default_factory=list)
    optional_slots: List[str] = Field(default_factory=list)


class ClarificationSlotDefinition(BaseModel):
    slot_name: str
    evidence_examples: List[str] = Field(default_factory=list)
    priority: int = 0


class ClarificationGateRule(BaseModel):
    gate_rule_id: str
    procedure_id: str
    clarification_step_id: str
    completion_step_id: str
    slot_policy: ClarificationSlotPolicy = Field(default_factory=lambda: ClarificationSlotPolicy(mode="threshold"))
    slot_definitions: List[ClarificationSlotDefinition] = Field(default_factory=list)
    confidence: Optional[float] = None


class TriggerCondition(BaseModel):
    trigger_type: str
    phrases: List[str] = Field(default_factory=list)
    command_markers: List[str] = Field(default_factory=list)
    artifact_roles: List[str] = Field(default_factory=list)
    starter_prompts: List[str] = Field(default_factory=list)


class InstructionServiceBlock(BaseModel):
    block_id: str
    block_type: InstructionServiceBlockType
    title: str
    body_text: str = ""
    parent_block_id: Optional[str] = None
    trigger_conditions: List[TriggerCondition] = Field(default_factory=list)
    required_inputs: List[str] = Field(default_factory=list)
    resource_refs: List[str] = Field(default_factory=list)
    policy_refs: List[str] = Field(default_factory=list)
    is_default: bool = False


class InstructionProcedure(BaseModel):
    procedure_id: str
    service_block_id: str
    title: str
    procedure_kind: Literal["primary", "supplementary", "followup"]
    is_default: bool = False
    entry_mode_ids: List[str] = Field(default_factory=list)
    trigger_conditions: List[TriggerCondition] = Field(default_factory=list)
    step_sequence: List[str] = Field(default_factory=list)
    output_targets: List[str] = Field(default_factory=list)


class ProcedureStepDefinition(BaseModel):
    step_id: str
    procedure_id: str
    order: int
    title: str
    body_text: str = ""
    step_kind: Optional[str] = None
    execution_mode: Literal["interactive", "bundled"] = "interactive"
    bundled_step_ids: List[str] = Field(default_factory=list)
    bundled_resource_refs: List[str] = Field(default_factory=list)
    stop_after_completion: bool = False
    wait_for_user: bool = False
    advance_conditions: List[str] = Field(default_factory=list)
    resource_refs: List[str] = Field(default_factory=list)
    primary_support_module_id: Optional[str] = None
    step_output_role: Optional[str] = None

    @model_validator(mode="after")
    def _validate_bundled_execution_fields(self) -> "ProcedureStepDefinition":
        if self.execution_mode != "bundled":
            if self.bundled_step_ids:
                raise ValueError("bundled_step_ids requires execution_mode='bundled'")
            if self.bundled_resource_refs:
                raise ValueError("bundled_resource_refs requires execution_mode='bundled'")
            if self.stop_after_completion:
                raise ValueError("stop_after_completion requires execution_mode='bundled'")
        return self


class ProcedureStepActivation(BaseModel):
    step_scope_id: str
    step_scope_type: Literal["step"] = "step"
    step_order: Optional[int] = None
    step_title: Optional[str] = None
    resource_ids: List[str] = Field(default_factory=list)
    primary_support_module_id: Optional[str] = None


class PrimarySupportModuleActivation(BaseModel):
    support_module_id: str
    support_module_title: Optional[str] = None
    resource_ids: List[str] = Field(default_factory=list)
    step_scope_id: Optional[str] = None


class ResourceRequest(BaseModel):
    filename: Optional[str] = None
    resource_id: Optional[str] = None
    resource_role: Optional[ResourceDomain] = None
    binding_id: Optional[str] = None
    resource_kind: Optional[ResourceKind] = None
    dependency_group_id: Optional[str] = None
    artifact_role: Optional[str] = None
    required_for_progression: bool = False
    purpose: Optional[str] = None
    query_text: Optional[str] = None
    context_hints: List[str] = Field(default_factory=list)
    objective: Optional[str] = None
    stage_label: Optional[str] = None
    request_reason: Optional[str] = None
    load_strategy_hint: Optional[Literal["inline_full", "section_filter", "vector_retrieve"]] = None
    source_layer: Optional[ResourceRequestSourceLayer] = None
    step_scope_id: Optional[str] = None
    support_module_id: Optional[str] = None
    required: bool = True


class PresentationPolicy(BaseModel):
    mode: Literal[
        "question_only",
        "summary_only",
        "partial_output",
        "full_output",
        "final_output",
        "internal_only",
    ] = "full_output"
    show_intermediate_outputs: bool = False
    summarize_hidden_outputs: bool = False
    hide_reasoning_artifacts: bool = True
    include_citations_when_available: bool = True


class TurnAction(BaseModel):
    action_id: str
    action_type: ActionTypeV2
    target: Optional[str] = None
    input_keys: List[str] = Field(default_factory=list)
    output_key: Optional[str] = None
    visibility: Literal["internal_only", "summary_visible", "user_visible", "final_visible"] = "internal_only"
    params: Dict[str, Any] = Field(default_factory=dict)


class IntermediateOutput(BaseModel):
    output_id: str
    output_type: str
    producer_scope_id: Optional[str] = None
    producer_turn_index: Optional[int] = None
    visibility: Literal["internal_only", "summary_visible", "user_visible", "final_visible"] = "internal_only"
    content: Optional[str] = None
    structured_data: Dict[str, Any] = Field(default_factory=dict)
    consumed_by: List[str] = Field(default_factory=list)
    status: Literal["draft", "complete", "consumed"] = "draft"


class ExecutionArtifact(BaseModel):
    artifact_id: str
    artifact_type: str
    source_action_id: Optional[str] = None
    content: Dict[str, Any] = Field(default_factory=dict)


class ModeRule(BaseModel):
    mode_id: str
    title: str
    triggers: List[str] = Field(default_factory=list)
    workflow_name: Optional[str] = None
    entry_response_hint: Optional[str] = None


class SupportModuleRule(BaseModel):
    module_id: str
    title: str
    block_type: Literal["support_module"] = "support_module"
    is_default: bool = False
    activation_triggers: List[str] = Field(default_factory=list)
    resource_ids: List[str] = Field(default_factory=list)
    referenced_resources: List[str] = Field(default_factory=list)
    parent_block_id: Optional[str] = None
    required_inputs: List[str] = Field(default_factory=list)
    policy_refs: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class ProgressionRules(BaseModel):
    wait_for_user_response: bool = True
    require_explicit_advance: bool = False
    min_questions_per_turn: int = 1
    max_questions_per_turn: int = 3
    continue_markers: List[str] = Field(default_factory=list)
    end_markers: List[str] = Field(default_factory=list)


class TurnConstraints(BaseModel):
    max_questions_per_turn: int = 3
    wait_after_questions: bool = True
    avoid_answer_and_question_same_turn: bool = False


class GlobalInstructionContext(BaseModel):
    role_summary: Optional[str] = None
    primary_objectives: List[str] = Field(default_factory=list)
    behavior_rules: List[str] = Field(default_factory=list)
    progression_rules: Dict[str, Any] = Field(default_factory=dict)
    turn_constraints: Dict[str, Any] = Field(default_factory=dict)
    response_policies: Dict[str, Any] = Field(default_factory=dict)
    mode_summaries: List[Dict[str, Any]] = Field(default_factory=list)
    support_module_summaries: List[Dict[str, Any]] = Field(default_factory=list)


class InstructionRuntimeModel(BaseModel):
    primary_service_mode: Optional[SemanticPrimaryServiceMode] = None
    default_workflow_id: Optional[str] = None
    global_app_contract: Optional[GlobalAppContract] = None
    interaction_logic_blocks: List[InteractionLogicBlock] = Field(default_factory=list)
    role_profiles: List[RoleProfile] = Field(default_factory=list)
    routing_rules: List[RoutingRule] = Field(default_factory=list)
    module_orchestration: Optional[ModuleOrchestration] = None
    role_summary: Optional[str] = None
    primary_objectives: List[str] = Field(default_factory=list)
    behavior_rules: List[str] = Field(default_factory=list)
    mode_rules: List[ModeRule] = Field(default_factory=list)
    instruction_blocks: List[InstructionBlock] = Field(default_factory=list)
    instruction_heading_tree: List[InstructionHeadingNode] = Field(default_factory=list)
    instruction_service_blocks: List[InstructionServiceBlock] = Field(default_factory=list)
    instruction_procedures: List[InstructionProcedure] = Field(default_factory=list)
    procedure_steps: List[ProcedureStepDefinition] = Field(default_factory=list)
    progression_rules: ProgressionRules = Field(default_factory=ProgressionRules)
    instruction_resources: List[InstructionResourceBinding] = Field(default_factory=list)
    dependency_groups: List[DependencyGroup] = Field(default_factory=list)
    phase_resource_bindings: List[PhaseResourceBinding] = Field(default_factory=list)
    support_modules: List[SupportModuleRule] = Field(default_factory=list)
    followup_modules: List[InstructionServiceBlock] = Field(default_factory=list)
    global_policies: List[InstructionServiceBlock] = Field(default_factory=list)
    clarification_gate_rules: List[ClarificationGateRule] = Field(default_factory=list)
    turn_constraints: TurnConstraints = Field(default_factory=TurnConstraints)
    response_policies: Dict[str, Any] = Field(default_factory=dict)
    global_instruction_context: GlobalInstructionContext = Field(default_factory=GlobalInstructionContext)


class SessionExecutionState(BaseModel):
    active_role_id: Optional[str] = None
    active_mode: Optional[str] = None
    active_workflow: Optional[str] = None
    active_step_order: Optional[int] = None
    active_step_title: Optional[str] = None
    active_execution_mode: Optional[Literal["interactive", "bundled"]] = None
    active_bundled_step_ids: List[str] = Field(default_factory=list)
    bundled_execution_completed: bool = False
    bundled_entry_step_id: Optional[str] = None
    active_service_block_type: Optional[InstructionServiceBlockType] = None
    active_service_block_id: Optional[str] = None
    active_service_block_title: Optional[str] = None
    primary_scope_id: Optional[str] = None
    primary_scope_type: Optional[InstructionScopeType] = None
    primary_scope_title: Optional[str] = None
    active_step_scope_id: Optional[str] = None
    primary_support_module_id: Optional[str] = None
    primary_support_module_title: Optional[str] = None
    selected_routing_rule_id: Optional[str] = None
    active_module_queue: List[str] = Field(default_factory=list)
    current_module_index: int = 0
    clarification_gate_status: Dict[str, Any] = Field(default_factory=dict)
    procedure_step_activation: Optional[ProcedureStepActivation] = None
    primary_support_module_activation: Optional[PrimarySupportModuleActivation] = None
    execution_status: ExecutionStatus = "idle"
    last_input_type: Optional[str] = None
    active_instruction_resources: List[str] = Field(default_factory=list)
    active_support_resources: List[str] = Field(default_factory=list)
    active_template_resources: List[str] = Field(default_factory=list)
    active_session_upload_ids: List[str] = Field(default_factory=list)
    output_artifact_targets: List[str] = Field(default_factory=list)
    pending_prompt_type: Optional[str] = None
    last_turn_action: Optional[ActionType] = None
    active_scope_ids: List[str] = Field(default_factory=list)
    active_binding_ids: List[str] = Field(default_factory=list)
    active_dependency_group_ids: List[str] = Field(default_factory=list)
    active_artifact_roles: List[str] = Field(default_factory=list)
    artifact_gate_status: Dict[str, Any] = Field(default_factory=dict)
    intermediate_output_ids: List[str] = Field(default_factory=list)
    pending_question_ids: List[str] = Field(default_factory=list)
    assembly_state: Dict[str, Any] = Field(default_factory=dict)
    workflow_progress: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_layered_scope_consistency(self) -> "SessionExecutionState":
        if self.active_execution_mode != "bundled":
            if self.active_bundled_step_ids:
                raise ValueError("active_bundled_step_ids requires active_execution_mode='bundled'")
            if self.bundled_entry_step_id is not None:
                raise ValueError("bundled_entry_step_id requires active_execution_mode='bundled'")
            if self.bundled_execution_completed:
                raise ValueError("bundled_execution_completed=True requires active_execution_mode='bundled'")

        if self.procedure_step_activation is not None:
            if self.active_step_order is None:
                self.active_step_order = self.procedure_step_activation.step_order
            elif (
                self.procedure_step_activation.step_order is not None
                and self.active_step_order != self.procedure_step_activation.step_order
            ):
                raise ValueError(
                    "active_step_order must match procedure_step_activation.step_order"
                )
            if self.active_step_title is None:
                self.active_step_title = self.procedure_step_activation.step_title
            elif (
                self.procedure_step_activation.step_title is not None
                and self.active_step_title != self.procedure_step_activation.step_title
            ):
                raise ValueError(
                    "active_step_title must match procedure_step_activation.step_title"
                )
            step_scope_id = self.procedure_step_activation.step_scope_id
            if self.active_step_scope_id is None:
                self.active_step_scope_id = step_scope_id
            elif self.active_step_scope_id != step_scope_id:
                raise ValueError(
                    "active_step_scope_id must match procedure_step_activation.step_scope_id"
                )
            support_module_id = self.procedure_step_activation.primary_support_module_id
            if support_module_id:
                if self.primary_support_module_id is None:
                    self.primary_support_module_id = support_module_id
                elif self.primary_support_module_id != support_module_id:
                    raise ValueError(
                        "primary_support_module_id must match procedure_step_activation.primary_support_module_id"
                    )

        if self.primary_support_module_activation is not None:
            support_module_id = self.primary_support_module_activation.support_module_id
            if self.primary_support_module_title is None:
                self.primary_support_module_title = self.primary_support_module_activation.support_module_title
            elif (
                self.primary_support_module_activation.support_module_title is not None
                and self.primary_support_module_title
                != self.primary_support_module_activation.support_module_title
            ):
                raise ValueError(
                    "primary_support_module_title must match primary_support_module_activation.support_module_title"
                )
            if self.primary_support_module_id is None:
                self.primary_support_module_id = support_module_id
            elif self.primary_support_module_id != support_module_id:
                raise ValueError(
                    "primary_support_module_id must match primary_support_module_activation.support_module_id"
                )
            step_scope_id = self.primary_support_module_activation.step_scope_id
            if step_scope_id:
                if self.active_step_scope_id is None:
                    self.active_step_scope_id = step_scope_id
                elif self.active_step_scope_id != step_scope_id:
                    raise ValueError(
                        "active_step_scope_id must match primary_support_module_activation.step_scope_id"
                    )

        return self


class RetrievalDomainPlan(BaseModel):
    enabled: bool = False
    resource_ids: List[str] = Field(default_factory=list)
    filename_filters: List[str] = Field(default_factory=list)
    query_text: Optional[str] = None
    context_hints: List[str] = Field(default_factory=list)
    objective: Optional[str] = None
    stage_label: Optional[str] = None
    query_variants: List[str] = Field(default_factory=list)
    fallback_queries: List[str] = Field(default_factory=list)
    retry_on_weak_results: bool = False


class TurnActionPlan(BaseModel):
    action_type: ActionType
    instruction_retrieval: RetrievalDomainPlan = Field(default_factory=RetrievalDomainPlan)
    knowledge_retrieval: RetrievalDomainPlan = Field(default_factory=RetrievalDomainPlan)
    template_retrieval: RetrievalDomainPlan = Field(default_factory=RetrievalDomainPlan)
    instruction_resource_load_plan: List[InstructionResourceLoadPlan] = Field(default_factory=list)
    template_resource_load_plan: List[InstructionResourceLoadPlan] = Field(default_factory=list)
    response_style: Dict[str, Any] = Field(default_factory=dict)
    state_updates: Dict[str, Any] = Field(default_factory=dict)


class TurnExecutionPlan(BaseModel):
    turn_intent: TurnIntent = "unknown"
    selected_role_id: Optional[str] = None
    selected_routing_rule_id: Optional[str] = None
    active_service_block_type: Optional[InstructionServiceBlockType] = None
    active_service_block_id: Optional[str] = None
    active_service_block_title: Optional[str] = None
    active_execution_mode: Optional[Literal["interactive", "bundled"]] = None
    active_bundled_step_ids: List[str] = Field(default_factory=list)
    bundled_execution_completed: bool = False
    bundled_entry_step_id: Optional[str] = None
    primary_scope: Optional[InstructionScopeSelection] = None
    active_step_scope: Optional[InstructionScopeSelection] = None
    primary_support_module_scope: Optional[InstructionScopeSelection] = None
    secondary_scopes: List[InstructionScopeSelection] = Field(default_factory=list)
    active_module_queue: List[str] = Field(default_factory=list)
    current_module_index: int = 0
    clarification_gate_status: Dict[str, Any] = Field(default_factory=dict)
    resource_requests: List[ResourceRequest] = Field(default_factory=list)
    actions: List[TurnAction] = Field(default_factory=list)
    presentation_policy: PresentationPolicy = Field(default_factory=PresentationPolicy)
    state_updates: Dict[str, Any] = Field(default_factory=dict)
    llm_reason_summary: Optional[str] = None

    @model_validator(mode="after")
    def _validate_bundled_execution_fields(self) -> "TurnExecutionPlan":
        if self.active_execution_mode != "bundled":
            if self.active_bundled_step_ids:
                raise ValueError("active_bundled_step_ids requires active_execution_mode='bundled'")
            if self.bundled_entry_step_id is not None:
                raise ValueError("bundled_entry_step_id requires active_execution_mode='bundled'")
            if self.bundled_execution_completed:
                raise ValueError("bundled_execution_completed=True requires active_execution_mode='bundled'")
        return self


class CompiledInstructionUnderstandingRecord(BaseModel):
    id: str
    app_id: str
    instruction_source_hash: str
    instruction_source_version: Optional[int] = None
    instruction_uri: Optional[str] = None
    parser_contract_version: str
    binding_logic_version: str
    resource_catalog_hash: str
    compiled_status: CompiledInstructionUnderstandingStatus = "ready"
    compiled_at: str
    compile_duration_ms: int = 0
    compile_errors: List[str] = Field(default_factory=list)
    compiled_contract: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class InstructionUnderstandingReviewRecord(BaseModel):
    id: str
    app_id: str
    instruction_source_hash: str
    parser_contract_version: str
    review_model: Optional[str] = None
    review_prompt_version: str
    review_status: InstructionUnderstandingReviewStatus = "not_reviewed"
    reviewed_at: str
    review_confidence: Optional[float] = None
    review_findings: Dict[str, Any] = Field(default_factory=dict)
    review_summary_md: str = ""
    review_recommendations: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class InstructionUnderstandingApprovalFinding(BaseModel):
    finding_id: str
    decision: InstructionApprovalDecision
    approved_revision_note: Optional[str] = None


class InstructionUnderstandingApprovalRecord(BaseModel):
    id: str
    app_id: str
    compiled_record_id: str
    review_record_id: str
    approved_findings: List[InstructionUnderstandingApprovalFinding] = Field(default_factory=list)
    approver: Optional[str] = None
    approved_at: str
    is_active: bool = True


class InstructionUnderstandingRevisionRecord(BaseModel):
    id: str
    app_id: str
    compiled_record_id: str
    review_record_id: Optional[str] = None
    approval_record_id: Optional[str] = None
    instruction_source_hash: str
    parser_contract_version: str
    revision_prompt_version: str
    revision_status: Literal["draft", "validated", "published", "failed"]
    revised_contract: Dict[str, Any] = Field(default_factory=dict)
    revision_notes: List[str] = Field(default_factory=list)
    preserved_ids: List[str] = Field(default_factory=list)
    changed_ids: List[str] = Field(default_factory=list)
    revision_confidence: Optional[float] = None
    revised_at: str
    is_active: bool = True


def to_plain_dict(model: BaseModel | Dict[str, Any] | None) -> Dict[str, Any]:
    if model is None:
        return {}
    if isinstance(model, BaseModel):
        return model.model_dump()
    if isinstance(model, dict):
        return dict(model)
    raise TypeError(f"Unsupported runtime model payload: {type(model)!r}")
