from __future__ import annotations

from collections import Counter

from app.models import (
    AgentLoopPlan,
    AuditControl,
    AutonomyBlueprint,
    ControlContract,
    ControlSummary,
    DeploymentDecision,
    EscalationRule,
    Gap,
    HandoffPacket,
    ProcessStep,
)


DOMAIN_PERSONAS = {
    "accounts_payable": "Accounts payable leader",
    "finance_ops": "Finance operations owner",
    "procurement": "Procurement operations leader",
    "revenue_operations": "Revenue operations leader",
}

SCOPE_KILL_LIST = [
    "No live ERP, bank, email, or ticketing writes in v1.",
    "No automatic payment, refund, bank-detail, or master-data release.",
    "No user accounts, tenant permissions, or production credential storage.",
    "No multi-document reconciliation beyond the submitted process source.",
    "No generic chat interface; every output must compile into contracts, gates, or audit evidence.",
]


def build_handoff_packet(
    blueprint: AutonomyBlueprint,
    contracts: list[ControlContract],
    control_summary: ControlSummary,
) -> HandoffPacket:
    high_gaps = [gap for gap in blueprint.gaps if gap.severity == "high"]
    decision = _deployment_decision(high_gaps, control_summary)
    label = _decision_label(decision)
    autonomous_steps = [
        step for step in blueprint.steps if step.autonomy_mode in {"ai_employee", "rules"} and step.risk_level != "high"
    ]

    return HandoffPacket(
        decision=decision,
        decision_label=label,
        persona=DOMAIN_PERSONAS.get(blueprint.domain, "Finance operations owner"),
        job_to_be_done=_job_to_be_done(blueprint, autonomous_steps, control_summary),
        one_sentence_pitch=_one_sentence_pitch(blueprint, label, control_summary),
        agent_loop=_agent_loop(blueprint, contracts),
        escalation_rules=_escalation_rules(blueprint.steps, blueprint.gaps, contracts),
        audit_controls=_audit_controls(blueprint, contracts, control_summary),
        scope_kill_list=SCOPE_KILL_LIST,
        success_criteria=_success_criteria(control_summary),
    )


def _deployment_decision(high_gaps: list[Gap], control_summary: ControlSummary) -> DeploymentDecision:
    if high_gaps or control_summary.blocked_step_count > 0:
        return "blocked_until_policy_fixed"
    if control_summary.hitl_contract_count > 0:
        return "delegate_with_gates"
    return "ready_to_delegate"


def _decision_label(decision: DeploymentDecision) -> str:
    return {
        "blocked_until_policy_fixed": "Do not delegate ungated",
        "delegate_with_gates": "Delegate with human gates",
        "ready_to_delegate": "Ready to delegate",
    }[decision]


def _job_to_be_done(
    blueprint: AutonomyBlueprint,
    autonomous_steps: list[ProcessStep],
    control_summary: ControlSummary,
) -> str:
    return (
        f"Turn {blueprint.title} into an AI employee operating contract: "
        f"{len(autonomous_steps)} routine steps can be handled by rules or an AI employee, "
        f"{control_summary.hitl_contract_count} steps require gates, "
        f"and {control_summary.blocked_step_count} steps are blocked by unresolved policy debt."
    )


def _one_sentence_pitch(blueprint: AutonomyBlueprint, label: str, control_summary: ControlSummary) -> str:
    return (
        f"{label}: You can see exactly what the AI employee may own, what must escalate, "
        f"and which {control_summary.blocked_step_count} control blockers must be fixed before full autonomy."
    )


def _agent_loop(blueprint: AutonomyBlueprint, contracts: list[ControlContract]) -> AgentLoopPlan:
    steps_by_id = {step.id: step for step in blueprint.steps}
    runnable_contracts = [
        contract
        for contract in contracts
        if not contract.requires_hitl and steps_by_id.get(contract.step_id, None) is not None
    ]
    gated_contracts = [contract for contract in contracts if contract.requires_hitl]

    return AgentLoopPlan(
        perceive=_dedupe(
            [
                "submitted process source and evidence spans",
                *_top_inputs(blueprint.steps),
                *_systems(blueprint.steps),
            ]
        )[:5],
        reason=_dedupe(
            [
                "classify each step as rules, AI employee, human gate, or human-owned",
                "score risk, reversibility, owner clarity, and system specificity",
                *_decision_rules(blueprint.steps),
                *_top_gap_types(blueprint.gaps),
            ]
        )[:5],
        act=[
            *(f"execute {contract.action_name}" for contract in runnable_contracts[:4]),
            *(
                ["prepare gated case packets for human owners"]
                if gated_contracts
                else []
            ),
        ]
        or ["prepare the operating brief without calling external systems"],
        verify=_dedupe(
            [
                f"require source evidence on {len([step for step in blueprint.steps if step.evidence])}/{len(blueprint.steps)} steps",
                f"enforce idempotency keys on {len(contracts)} generated contracts",
                *_audit_fields(contracts),
            ]
        )[:5],
        escalate=_dedupe(
            [
                *(gate.human_question for gate in blueprint.hitl_gates[:3]),
                *(gap.description for gap in blueprint.gaps if gap.severity == "high"),
            ]
        )[:5],
    )


def _escalation_rules(
    steps: list[ProcessStep],
    gaps: list[Gap],
    contracts: list[ControlContract],
) -> list[EscalationRule]:
    steps_by_id = {step.id: step for step in steps}
    contract_by_step = {contract.step_id: contract for contract in contracts}
    rules: list[EscalationRule] = []

    for gap in [gap for gap in gaps if gap.severity == "high"][:4]:
        rules.append(
            EscalationRule(
                trigger=gap.description,
                step_ids=gap.affected_step_ids,
                owner=_owner_for_steps(gap.affected_step_ids, steps_by_id),
                decision=gap.recommendation,
                blocks_autonomy=True,
            )
        )

    for step in steps:
        contract = contract_by_step.get(step.id)
        if not contract or not contract.requires_hitl:
            continue
        rules.append(
            EscalationRule(
                trigger=f"{step.title} requires human confirmation before the run can continue.",
                step_ids=[step.id],
                owner=step.actor or "named process owner",
                decision=f"Resolve {contract.action_name} and call resume_{contract.action_name}.",
                blocks_autonomy=False,
            )
        )

    return _dedupe_escalation_rules(rules)[:6]


def _audit_controls(
    blueprint: AutonomyBlueprint,
    contracts: list[ControlContract],
    control_summary: ControlSummary,
) -> list[AuditControl]:
    evidence_count = sum(1 for step in blueprint.steps if step.evidence)
    hitl_contracts = [contract for contract in contracts if contract.requires_hitl]
    idempotent_contracts = sum(1 for contract in contracts if contract.idempotency_key)
    audit_contracts = sum(1 for contract in contracts if contract.audit_requirements)

    return [
        AuditControl(
            name="Source evidence",
            status="pass" if evidence_count == len(blueprint.steps) else "warn",
            detail=f"{evidence_count}/{len(blueprint.steps)} process steps carry source-backed evidence.",
        ),
        AuditControl(
            name="Idempotency",
            status="pass" if idempotent_contracts == len(contracts) else "fail",
            detail=f"{idempotent_contracts}/{len(contracts)} contracts include deterministic idempotency keys.",
        ),
        AuditControl(
            name="Human gates",
            status="pass" if control_summary.hitl_contract_count == len(hitl_contracts) else "warn",
            detail=f"{control_summary.hitl_contract_count} contracts require human decisions before risky actions resume.",
        ),
        AuditControl(
            name="Audit trail",
            status="pass" if audit_contracts > 0 else "warn",
            detail=f"{audit_contracts} contracts require audit fields such as actor, timestamp, source evidence, and system outcome.",
        ),
        AuditControl(
            name="Autonomy blockers",
            status="fail" if control_summary.blocked_step_count else "pass",
            detail=f"{control_summary.blocked_step_count} steps are blocked by high-severity policy or control gaps.",
        ),
    ]


def _success_criteria(control_summary: ControlSummary) -> list[str]:
    return [
        "Routine steps produce planned, executed, and validated dry-run events without external system calls.",
        "High-risk financial or master-data actions gate or block instead of executing silently.",
        f"{control_summary.contract_count} generated contracts expose required inputs, allowed outputs, validation checks, retries, and idempotency keys.",
        "The audit export can reconstruct evidence, decisions, gates, timestamps, runtime metadata, and proposed learning updates.",
    ]


def _top_inputs(steps: list[ProcessStep]) -> list[str]:
    counts = Counter(input_name for step in steps for input_name in step.inputs)
    return [f"{name} input" for name, _ in counts.most_common(4)]


def _systems(steps: list[ProcessStep]) -> list[str]:
    return [f"{system} system context" for system in _dedupe([step.system or "" for step in steps]) if system]


def _decision_rules(steps: list[ProcessStep]) -> list[str]:
    return [f"apply rule: {step.decision_rule}" for step in steps if step.decision_rule][:3]


def _top_gap_types(gaps: list[Gap]) -> list[str]:
    counts = Counter(gap.gap_type.replace("_", " ") for gap in gaps)
    return [f"detect {name}" for name, _ in counts.most_common(3)]


def _audit_fields(contracts: list[ControlContract]) -> list[str]:
    fields = _dedupe([field for contract in contracts for field in contract.audit_requirements])
    if not fields:
        return ["record run status and generated contracts"]
    return [f"capture {field.replace('_', ' ')}" for field in fields[:3]]


def _owner_for_steps(step_ids: list[str], steps_by_id: dict[str, ProcessStep]) -> str:
    owners = [steps_by_id[step_id].actor for step_id in step_ids if step_id in steps_by_id and steps_by_id[step_id].actor]
    if owners:
        return Counter(owners).most_common(1)[0][0]
    return "named process owner"


def _dedupe(values) -> list[str]:
    seen: set[str] = set()
    cleaned: list[str] = []
    for value in values:
        normalized = str(value).strip()
        key = normalized.lower()
        if normalized and key not in seen:
            seen.add(key)
            cleaned.append(normalized)
    return cleaned


def _dedupe_escalation_rules(rules: list[EscalationRule]) -> list[EscalationRule]:
    seen: set[tuple[str, tuple[str, ...]]] = set()
    unique: list[EscalationRule] = []
    for rule in rules:
        key = (rule.trigger.lower(), tuple(rule.step_ids))
        if key not in seen:
            seen.add(key)
            unique.append(rule)
    return unique
