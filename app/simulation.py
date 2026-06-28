from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.evals import run_evals
from app.models import (
    AutonomyBlueprint,
    ControlContract,
    EvalSummary,
    Gap,
    LearningUpdate,
    RunEvent,
    RunStatus,
    SimulationCase,
    SimulationResponse,
)


def simulate_blueprint(
    *,
    blueprint_id: str,
    blueprint: AutonomyBlueprint,
    contracts: list[ControlContract],
    source_hash: str,
) -> SimulationResponse:
    run_id = f"run_{uuid4().hex[:12]}"
    case = SimulationCase(
        case_id=f"case_{source_hash[:10]}",
        title=f"{blueprint.title} dry run",
        domain=blueprint.domain,
        description="Deterministic dry run generated from the persisted operating brief. No external systems were called.",
        source_hash=source_hash,
    )

    contract_by_step = {contract.step_id: contract for contract in contracts}
    high_gap_steps = {
        step_id
        for gap in blueprint.gaps
        if gap.severity == "high"
        for step_id in gap.affected_step_ids
    }
    gap_by_step = _gaps_by_step(blueprint.gaps)

    events: list[RunEvent] = []
    sequence = 1
    gated = False
    blocked = False

    for step in blueprint.steps:
        contract = contract_by_step.get(step.id)
        events.append(
            _event(
                run_id=run_id,
                sequence=sequence,
                event_type="planned",
                step_id=step.id,
                actor="control_plane",
                status="ok",
                message=f"Planned {step.title} using {step.autonomy_mode.replace('_', ' ')} mode.",
                inputs={"required_inputs": contract.required_inputs if contract else []},
                outputs={"allowed_outputs": contract.allowed_outputs if contract else step.outputs},
                evidence=step.evidence,
            )
        )
        sequence += 1

        if step.id in high_gap_steps:
            blocked = True
            related = gap_by_step.get(step.id, [])
            events.append(
                _event(
                    run_id=run_id,
                    sequence=sequence,
                    event_type="blocked",
                    step_id=step.id,
                    actor="control_plane",
                    status="blocked",
                    message=_block_message(step.title, related),
                    inputs={"open_gaps": [gap.gap_type for gap in related]},
                    outputs={"resume_condition": "Resolve blocker and rerun validation."},
                    evidence=step.evidence,
                    decision="blocked_before_action",
                )
            )
            sequence += 1
            continue

        if contract and contract.requires_hitl:
            gated = True
            events.append(
                _event(
                    run_id=run_id,
                    sequence=sequence,
                    event_type="gate_requested",
                    step_id=step.id,
                    actor=step.actor or "human_owner",
                    status="gated",
                    message=f"Human gate requested before {step.title}.",
                    inputs={"audit_requirements": contract.audit_requirements},
                    outputs={"resume_action": f"resume_{contract.action_name}"},
                    evidence=step.evidence,
                    decision="await_human_confirmation",
                )
            )
            sequence += 1
            continue

        events.append(
            _event(
                run_id=run_id,
                sequence=sequence,
                event_type="executed",
                step_id=step.id,
                actor="ai_employee",
                status="ok",
                message=f"Dry-run executed {step.title}; no external system was called.",
                inputs={"idempotency_key": contract.idempotency_key if contract else None},
                outputs={"status": "simulated_success"},
                evidence=step.evidence,
            )
        )
        sequence += 1
        events.append(
            _event(
                run_id=run_id,
                sequence=sequence,
                event_type="validated",
                step_id=step.id,
                actor="control_plane",
                status="pass",
                message=f"Validated contract checks for {step.title}.",
                inputs={"validation_checks": contract.validation_checks if contract else []},
                outputs={"validated": True},
                evidence=step.evidence,
            )
        )
        sequence += 1

    learning_updates = _learning_updates(blueprint.gaps, events)
    for update in learning_updates:
        events.append(
            _event(
                run_id=run_id,
                sequence=sequence,
                event_type="learned",
                step_id=None,
                actor="company_brain",
                status="warn",
                message=update.recommendation,
                inputs={"target": update.target, "update_type": update.update_type},
                outputs={"status": update.status},
                evidence=[],
                decision="propose_runbook_update",
            )
        )
        sequence += 1

    eval_summary = run_evals(blueprint, contracts)
    status: RunStatus = "blocked" if blocked else "gated" if gated else "completed"
    return SimulationResponse(
        run_id=run_id,
        blueprint_id=blueprint_id,
        status=status,
        case=case,
        contracts=contracts,
        events=events,
        eval_summary=eval_summary,
        learning_updates=learning_updates,
    )


def _event(
    *,
    run_id: str,
    sequence: int,
    event_type,
    step_id: str | None,
    actor: str,
    status,
    message: str,
    inputs: dict,
    outputs: dict,
    evidence,
    decision: str | None = None,
) -> RunEvent:
    return RunEvent(
        event_id=f"{run_id}_evt_{sequence:03d}",
        sequence=sequence,
        timestamp=datetime.now(UTC).isoformat(),
        event_type=event_type,
        step_id=step_id,
        actor=actor,
        status=status,
        message=message,
        inputs=inputs,
        outputs=outputs,
        evidence=evidence,
        decision=decision,
    )


def _gaps_by_step(gaps: list[Gap]) -> dict[str, list[Gap]]:
    by_step: dict[str, list[Gap]] = {}
    for gap in gaps:
        for step_id in gap.affected_step_ids:
            by_step.setdefault(step_id, []).append(gap)
    return by_step


def _block_message(step_title: str, gaps: list[Gap]) -> str:
    if not gaps:
        return f"Blocked {step_title} because a high-risk control is unresolved."
    gap_names = ", ".join(gap.gap_type.replace("_", " ") for gap in gaps[:3])
    return f"Blocked {step_title}; unresolved control gaps: {gap_names}."


def _learning_updates(gaps: list[Gap], events: list[RunEvent]) -> list[LearningUpdate]:
    updates: list[LearningUpdate] = []
    first_event = events[0].event_id if events else "run_start"
    for index, gap in enumerate(gaps[:6], start=1):
        update_type = "policy_gap"
        if "audit" in gap.gap_type:
            update_type = "audit_requirement"
        elif "timeout" in gap.gap_type or "handoff" in gap.gap_type:
            update_type = "gate_pattern"
        elif "learning" in gap.gap_type:
            update_type = "runbook_note"
        target = ", ".join(gap.affected_step_ids) if gap.affected_step_ids else "process"
        updates.append(
            LearningUpdate(
                update_id=f"learn_{index}",
                source_event_id=first_event,
                update_type=update_type,
                target=target,
                recommendation=gap.recommendation,
            )
        )
    return updates
