from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


AutonomyMode = Literal["human_only", "rules", "ai_employee", "hitl"]
RiskLevel = Literal["low", "medium", "high"]
Severity = Literal["low", "medium", "high"]
AnalyzerKind = Literal["local", "litellm", "litellm_fallback"]
RunStatus = Literal["completed", "blocked", "gated"]
RunEventType = Literal["planned", "executed", "validated", "gate_requested", "blocked", "learned"]
EvalStatus = Literal["pass", "warn", "fail"]
RuntimeMode = Literal["local", "model", "auto"]
DeploymentDecision = Literal["ready_to_delegate", "delegate_with_gates", "blocked_until_policy_fixed"]

TEXT_MIN_LENGTH = 40
TEXT_MAX_LENGTH = 25000


class EvidenceSpan(BaseModel):
    quote: str = Field(..., description="Short source excerpt supporting the extraction.")
    source: str = Field(default="submitted_process", description="Source identifier.")


class ProcessInput(BaseModel):
    title: str = Field(default="Untitled process", min_length=1, max_length=120)
    domain: str = Field(default="finance_ops", max_length=80)
    text: str = Field(..., min_length=TEXT_MIN_LENGTH, max_length=TEXT_MAX_LENGTH)
    prefer_ai: bool = Field(
        default=True,
        description="Attempt LiteLLM extraction when provider credentials are configured.",
    )
    runtime_mode: RuntimeMode | None = Field(
        default=None,
        description="Optional explicit runtime mode. Existing prefer_ai behavior is preserved when omitted.",
    )

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return "\n".join(line.strip() for line in value.strip().splitlines() if line.strip())


class ProcessStep(BaseModel):
    id: str
    title: str
    description: str
    actor: str | None = None
    system: str | None = None
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    decision_rule: str | None = None
    next_step_ids: list[str] = Field(default_factory=list)
    autonomy_mode: AutonomyMode
    risk_level: RiskLevel
    reversible: bool = True
    confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    evidence: list[EvidenceSpan] = Field(default_factory=list)


class HitlGate(BaseModel):
    id: str
    step_id: str
    trigger: str
    human_question: str
    context_fields: list[str] = Field(default_factory=list)
    resume_action: str
    risk_reduced: str


class Gap(BaseModel):
    id: str
    severity: Severity
    gap_type: str
    description: str
    affected_step_ids: list[str] = Field(default_factory=list)
    recommendation: str
    evidence: list[EvidenceSpan] = Field(default_factory=list)


class Metric(BaseModel):
    name: str
    definition: str
    target: str
    why_it_matters: str


class ActionStub(BaseModel):
    action_name: str
    step_id: str
    action_type: Literal["AIEmployeeActivity"] = "AIEmployeeActivity"
    summary: str
    params_schema: dict[str, str]
    expected_result_schema: dict[str, str]
    retry_policy: dict[str, str | int] = Field(default_factory=lambda: {"max_attempts": 3, "backoff": "exponential"})
    hitl_trigger: str | None = None
    requires_hitl: bool = False


class CompileTraceStep(BaseModel):
    name: str
    status: Literal["complete", "warning"] = "complete"
    detail: str


class ControlSummary(BaseModel):
    contract_count: int
    hitl_contract_count: int
    audit_required_count: int
    blocked_step_count: int


class ControlContract(BaseModel):
    step_id: str
    action_name: str
    required_inputs: list[str] = Field(default_factory=list)
    allowed_outputs: list[str] = Field(default_factory=list)
    validation_checks: list[str] = Field(default_factory=list)
    retry_policy: dict[str, str | int] = Field(default_factory=lambda: {"max_attempts": 3, "backoff": "exponential"})
    idempotency_key: str
    requires_hitl: bool = False
    audit_requirements: list[str] = Field(default_factory=list)


class AgentLoopPlan(BaseModel):
    perceive: list[str] = Field(default_factory=list)
    reason: list[str] = Field(default_factory=list)
    act: list[str] = Field(default_factory=list)
    verify: list[str] = Field(default_factory=list)
    escalate: list[str] = Field(default_factory=list)


class EscalationRule(BaseModel):
    trigger: str
    step_ids: list[str] = Field(default_factory=list)
    owner: str
    decision: str
    blocks_autonomy: bool = False


class AuditControl(BaseModel):
    name: str
    status: EvalStatus
    detail: str


class HandoffPacket(BaseModel):
    decision: DeploymentDecision
    decision_label: str
    persona: str
    job_to_be_done: str
    one_sentence_pitch: str
    agent_loop: AgentLoopPlan
    escalation_rules: list[EscalationRule]
    audit_controls: list[AuditControl]
    scope_kill_list: list[str]
    success_criteria: list[str]


class UngroundedClaim(BaseModel):
    """An extracted claim whose evidence could not be located in the source."""

    claim_type: Literal["step", "gap"]
    ref_id: str
    title: str
    reason: Literal["quote_not_in_source", "no_evidence"]
    quote: str | None = None


class ReconciliationDivergence(BaseModel):
    """A place where the symbolic policy engine overruled the model's authority call."""

    step_id: str
    step_title: str
    field: Literal["autonomy_mode", "risk_level"]
    model_value: str
    policy_value: str
    resolved_value: str
    reason: str


class VerificationReport(BaseModel):
    """Output of the symbolic verification layer that audits the neural extraction.

    Grounding measures how much of the model's output is traceable to the source
    text. Reconciliation records every step where the deterministic control plane
    had to escalate the model's authority call to a safer one.
    """

    groundedness: float = Field(default=1.0, ge=0.0, le=1.0)
    grounded_claims: int = 0
    total_claims: int = 0
    ungrounded_claims: list[UngroundedClaim] = Field(default_factory=list)
    divergences: list[ReconciliationDivergence] = Field(default_factory=list)
    escalated_step_count: int = 0
    policy_agreement: float = Field(default=1.0, ge=0.0, le=1.0)
    method: str = "lexical_grounding + deterministic_reconciliation"


class AutonomyBlueprint(BaseModel):
    title: str
    domain: str
    source_summary: str
    readiness_score: int = Field(..., ge=0, le=100)
    confidence: float = Field(..., ge=0.0, le=1.0)
    steps: list[ProcessStep]
    hitl_gates: list[HitlGate]
    gaps: list[Gap]
    metrics: list[Metric]
    action_stubs: list[ActionStub]
    mermaid: str
    executive_pitch: str
    analyzer: AnalyzerKind
    analyzer_model: str | None = None
    warnings: list[str] = Field(default_factory=list)
    verification: VerificationReport | None = None


class BlueprintRecord(BaseModel):
    blueprint_id: str
    source_hash: str
    blueprint: AutonomyBlueprint
    contracts: list[ControlContract]
    compile_trace: list[CompileTraceStep]
    control_summary: ControlSummary
    handoff_packet: HandoffPacket
    created_at: str
    latest_run_id: str | None = None
    latest_run_status: RunStatus | None = None


class SimulationCase(BaseModel):
    case_id: str
    title: str
    domain: str
    description: str
    source_hash: str


class RunEvent(BaseModel):
    event_id: str
    sequence: int
    timestamp: str
    event_type: RunEventType
    step_id: str | None = None
    actor: str
    status: EvalStatus | RunStatus | Literal["ok"]
    message: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    evidence: list[EvidenceSpan] = Field(default_factory=list)
    decision: str | None = None


class SimulationRun(BaseModel):
    run_id: str
    blueprint_id: str
    case_id: str
    status: RunStatus
    started_at: str
    completed_at: str


class EvalCheck(BaseModel):
    check_id: str
    name: str
    status: EvalStatus
    severity: Severity
    step_id: str | None = None
    message: str
    evidence: list[EvidenceSpan] = Field(default_factory=list)


class EvalSummary(BaseModel):
    checks: list[EvalCheck]
    pass_count: int
    warn_count: int
    fail_count: int


class LearningUpdate(BaseModel):
    update_id: str
    source_event_id: str
    update_type: Literal["policy_gap", "gate_pattern", "audit_requirement", "runbook_note"]
    target: str
    recommendation: str
    status: Literal["proposed", "accepted", "rejected"] = "proposed"


class SimulationResponse(BaseModel):
    run_id: str
    blueprint_id: str
    status: RunStatus
    case: SimulationCase
    contracts: list[ControlContract]
    events: list[RunEvent]
    eval_summary: EvalSummary
    learning_updates: list[LearningUpdate]


class RunRecord(BaseModel):
    run: SimulationRun
    case: SimulationCase
    events: list[RunEvent]
    eval_summary: EvalSummary
    learning_updates: list[LearningUpdate]
    contracts: list[ControlContract]


class AuditExport(BaseModel):
    run: SimulationRun
    case: SimulationCase
    blueprint: AutonomyBlueprint
    contracts: list[ControlContract]
    events: list[RunEvent]
    eval_summary: EvalSummary
    learning_updates: list[LearningUpdate]
    runtime_metadata: dict[str, Any]


class RuntimeCapabilities(BaseModel):
    local_analyzer_available: bool
    litellm_configured: bool
    storage_enabled: bool
    model_name: str
    runtime_mode: RuntimeMode
    database_path: str


class DemoProcess(BaseModel):
    id: str
    title: str
    domain: str
    text: str


class AnalyzeResponse(BaseModel):
    blueprint: AutonomyBlueprint
    character_count: int
    character_limit: int = TEXT_MAX_LENGTH
    minimum_characters: int = TEXT_MIN_LENGTH
    blueprint_id: str | None = None
    control_summary: ControlSummary | None = None
    compile_trace: list[CompileTraceStep] = Field(default_factory=list)
    handoff_packet: HandoffPacket | None = None
