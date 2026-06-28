from __future__ import annotations

import hashlib
import re

from app.models import AutonomyBlueprint, ControlContract, ControlSummary, ProcessStep


def build_contracts(blueprint: AutonomyBlueprint) -> list[ControlContract]:
    return [_contract_for_step(step) for step in blueprint.steps if step.autonomy_mode != "human_only"]


def summarize_contracts(blueprint: AutonomyBlueprint, contracts: list[ControlContract]) -> ControlSummary:
    blocked_step_ids = {
        step_id
        for gap in blueprint.gaps
        if gap.severity == "high"
        for step_id in gap.affected_step_ids
    }
    return ControlSummary(
        contract_count=len(contracts),
        hitl_contract_count=sum(1 for contract in contracts if contract.requires_hitl),
        audit_required_count=sum(1 for contract in contracts if contract.audit_requirements),
        blocked_step_count=len(blocked_step_ids),
    )


def _contract_for_step(step: ProcessStep) -> ControlContract:
    requires_hitl = step.autonomy_mode == "hitl" or step.risk_level == "high" or not step.reversible
    audit_requirements = ["source_evidence", "decision_reason", "actor", "timestamp", "system_outcome"]
    if step.risk_level == "low" and step.reversible and not requires_hitl:
        audit_requirements = ["source_evidence", "system_outcome"]

    required_inputs = ["case_id", "source_evidence", *step.inputs]
    if step.system:
        required_inputs.append("system")
    if requires_hitl:
        required_inputs.append("human_decision")

    validation_checks = [
        "source evidence is attached",
        "output matches allowed schema",
        "idempotency key is present",
    ]
    if step.actor:
        validation_checks.append("accountable owner is named")
    if requires_hitl:
        validation_checks.append("human gate is resolved before resume")
    if audit_requirements:
        validation_checks.append("audit requirements are complete")

    action_name = _slug(step.title)
    idempotency_key = _idempotency_key(step, action_name)
    return ControlContract(
        step_id=step.id,
        action_name=action_name,
        required_inputs=_dedupe(required_inputs),
        allowed_outputs=_dedupe(step.outputs or [f"{step.title} completed"]),
        validation_checks=_dedupe(validation_checks),
        retry_policy={"max_attempts": 1 if requires_hitl else 3, "backoff": "manual_gate" if requires_hitl else "exponential"},
        idempotency_key=idempotency_key,
        requires_hitl=requires_hitl,
        audit_requirements=audit_requirements,
    )


def _idempotency_key(step: ProcessStep, action_name: str) -> str:
    raw = "|".join(
        [
            step.id,
            action_name,
            step.autonomy_mode,
            step.risk_level,
            step.system or "no_system",
            ",".join(step.inputs),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug[:56].rstrip("_") or "action"


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    cleaned: list[str] = []
    for value in values:
        normalized = str(value).strip()
        key = normalized.lower()
        if normalized and key not in seen:
            seen.add(key)
            cleaned.append(normalized)
    return cleaned
