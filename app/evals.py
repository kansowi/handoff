from __future__ import annotations

from app.models import AutonomyBlueprint, ControlContract, EvalCheck, EvalSummary, EvidenceSpan


def run_evals(blueprint: AutonomyBlueprint, contracts: list[ControlContract]) -> EvalSummary:
    checks: list[EvalCheck] = []
    contract_by_step = {contract.step_id: contract for contract in contracts}

    for step in blueprint.steps:
        contract = contract_by_step.get(step.id)
        checks.append(
            EvalCheck(
                check_id=f"eval_owner_{step.id}",
                name="Owner present",
                status="pass" if step.actor else "fail" if step.risk_level == "high" else "warn",
                severity="high" if step.risk_level == "high" else "medium",
                step_id=step.id,
                message="Step names an accountable owner." if step.actor else "Step is missing an accountable owner.",
                evidence=step.evidence,
            )
        )
        checks.append(
            EvalCheck(
                check_id=f"eval_evidence_{step.id}",
                name="Source evidence present",
                status="pass" if step.evidence else "fail",
                severity="high" if step.risk_level == "high" else "medium",
                step_id=step.id,
                message="Source evidence is attached." if step.evidence else "No source evidence supports this step.",
                evidence=step.evidence,
            )
        )
        if contract is not None:
            checks.append(
                EvalCheck(
                    check_id=f"eval_idempotency_{step.id}",
                    name="Idempotency defined",
                    status="pass" if contract.idempotency_key else "fail",
                    severity="medium",
                    step_id=step.id,
                    message="Contract includes a deterministic idempotency key.",
                    evidence=step.evidence,
                )
            )
            if step.risk_level == "high" or step.autonomy_mode == "hitl":
                checks.append(
                    EvalCheck(
                        check_id=f"eval_hitl_{step.id}",
                        name="HITL control present",
                        status="pass" if contract.requires_hitl else "fail",
                        severity="high",
                        step_id=step.id,
                        message=(
                            "High-risk work is protected by a human gate."
                            if contract.requires_hitl
                            else "High-risk work lacks a human gate."
                        ),
                        evidence=step.evidence,
                    )
                )
                checks.append(
                    EvalCheck(
                        check_id=f"eval_audit_{step.id}",
                        name="Audit requirements present",
                        status="pass" if len(contract.audit_requirements) >= 3 else "fail",
                        severity="high",
                        step_id=step.id,
                        message="Contract requires audit evidence before completion.",
                        evidence=step.evidence,
                    )
                )

    high_gaps = [gap for gap in blueprint.gaps if gap.severity == "high"]
    checks.append(
        EvalCheck(
            check_id="eval_unresolved_high_gaps",
            name="Unresolved high-risk blockers",
            status="fail" if high_gaps else "pass",
            severity="high",
            message=(
                f"{len(high_gaps)} high-risk blockers remain before safe delegation."
                if high_gaps
                else "No high-risk blockers remain in the compiled brief."
            ),
            evidence=_gap_evidence(high_gaps),
        )
    )

    checks.extend(_verification_checks(blueprint))

    return EvalSummary(
        checks=checks,
        pass_count=sum(1 for check in checks if check.status == "pass"),
        warn_count=sum(1 for check in checks if check.status == "warn"),
        fail_count=sum(1 for check in checks if check.status == "fail"),
    )


def _verification_checks(blueprint: AutonomyBlueprint) -> list[EvalCheck]:
    """Trace-level checks over the neuro-symbolic verification layer."""
    report = blueprint.verification
    if report is None:
        return []

    grounded_pct = round(report.groundedness * 100)
    if report.groundedness >= 0.9:
        grounding_status: str = "pass"
    elif report.groundedness >= 0.75:
        grounding_status = "warn"
    else:
        grounding_status = "fail"

    checks = [
        EvalCheck(
            check_id="eval_groundedness",
            name="Evidence grounded to source",
            status=grounding_status,
            severity="high",
            message=(
                f"{grounded_pct}% of extracted claims are grounded in the source "
                f"({report.grounded_claims}/{report.total_claims}); "
                f"{len(report.ungrounded_claims)} quarantined."
            ),
        )
    ]

    if report.escalated_step_count:
        reconciliation_message = (
            f"Control plane independently re-checked authority and escalated "
            f"{report.escalated_step_count} step(s) the model left unattended."
        )
    else:
        reconciliation_message = (
            "Control plane independently re-checked authority on every step; "
            "the model's calls matched policy (no escalation needed)."
        )
    checks.append(
        EvalCheck(
            check_id="eval_policy_reconciliation",
            name="Authority independently verified",
            status="pass",
            severity="medium",
            message=reconciliation_message,
        )
    )
    return checks


def _gap_evidence(gaps) -> list[EvidenceSpan]:
    evidence: list[EvidenceSpan] = []
    for gap in gaps[:4]:
        evidence.extend(gap.evidence[:1])
    return evidence
