from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.models import (
    AuditExport,
    AutonomyBlueprint,
    SimulationResponse,
    SimulationRun,
)


def build_audit_export(
    simulation: SimulationResponse,
    blueprint: AutonomyBlueprint,
    runtime_metadata: dict[str, Any] | None = None,
) -> AuditExport:
    """Assemble a signed, reproducible audit export from a single dry-run.

    Pure and stateless: every field is derived from the artifacts the caller already
    holds, so the same run always produces the same export with no storage involved.
    """
    events = simulation.events
    now = datetime.now(UTC).isoformat()
    run = SimulationRun(
        run_id=simulation.run_id,
        blueprint_id=simulation.blueprint_id,
        case_id=simulation.case.case_id,
        status=simulation.status,
        started_at=events[0].timestamp if events else now,
        completed_at=events[-1].timestamp if events else now,
    )
    return AuditExport(
        run=run,
        case=simulation.case,
        blueprint=blueprint,
        contracts=simulation.contracts,
        events=events,
        eval_summary=simulation.eval_summary,
        learning_updates=simulation.learning_updates,
        runtime_metadata=runtime_metadata or {},
    )
