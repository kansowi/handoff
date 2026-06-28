"""Symbolic verification layer for the neuro-symbolic analysis pipeline.

The LLM (neural layer) proposes a structured ``AutonomyBlueprint`` from a messy
SOP. This module is the symbolic control plane that audits that proposal before
it is trusted:

1. **Grounding** — every extracted step and gap must cite evidence that actually
   occurs in the source text. Claims that cannot be located are quarantined and
   the overall groundedness (faithfulness) score is reported.
2. **Reconciliation** — the deterministic engine independently enforces the
   invariant that *no irreversible or high-risk action may run unattended*. Where
   the model marked such a step as autonomous, the control plane escalates it to a
   human gate and logs the divergence.

Both checks are pure and deterministic (no network), so the result is identical
on every run and fully explainable. Run against a deterministic-engine blueprint
the reconciliation is a guaranteed no-op, because that engine already satisfies
the invariant.
"""

from __future__ import annotations

import re

from app.models import (
    AutonomyBlueprint,
    Gap,
    ProcessStep,
    ReconciliationDivergence,
    UngroundedClaim,
    VerificationReport,
)

# Minimum fraction of a quote's tokens that must appear in the source for the
# claim to count as grounded when an exact substring is not present.
_FUZZY_OVERLAP_THRESHOLD = 0.8

# Autonomy modes the control plane treats as "running unattended".
_AUTONOMOUS_MODES = {"ai_employee", "rules"}


def verify_blueprint(blueprint: AutonomyBlueprint, source_text: str) -> AutonomyBlueprint:
    """Return a new blueprint with reconciled authority and a verification report.

    The input blueprint is never mutated; a copy is returned.
    """
    normalized_source = _normalize(source_text)
    grounded, total, ungrounded = _check_grounding(blueprint, normalized_source)
    reconciled_steps, divergences = _reconcile_steps(blueprint.steps)

    escalated = len({divergence.step_id for divergence in divergences})
    step_count = len(blueprint.steps)
    policy_agreement = 1.0 if step_count == 0 else round((step_count - escalated) / step_count, 4)

    report = VerificationReport(
        groundedness=round(grounded / total, 4) if total else 1.0,
        grounded_claims=grounded,
        total_claims=total,
        ungrounded_claims=ungrounded,
        divergences=divergences,
        escalated_step_count=escalated,
        policy_agreement=policy_agreement,
    )
    return blueprint.model_copy(update={"steps": reconciled_steps, "verification": report})


def _reconcile_steps(
    steps: list[ProcessStep],
) -> tuple[list[ProcessStep], list[ReconciliationDivergence]]:
    reconciled: list[ProcessStep] = []
    divergences: list[ReconciliationDivergence] = []
    for step in steps:
        irreversible = not step.reversible
        high_risk = step.risk_level == "high"
        must_gate = irreversible or high_risk
        if must_gate and step.autonomy_mode in _AUTONOMOUS_MODES:
            cause = "is irreversible" if irreversible else "is high-risk"
            divergences.append(
                ReconciliationDivergence(
                    step_id=step.id,
                    step_title=step.title,
                    field="autonomy_mode",
                    model_value=step.autonomy_mode,
                    policy_value="hitl",
                    resolved_value="hitl",
                    reason=f"Step {cause} and cannot run unattended; control plane escalated it to a human gate.",
                )
            )
            reconciled.append(step.model_copy(update={"autonomy_mode": "hitl"}))
        else:
            reconciled.append(step)
    return reconciled, divergences


def _check_grounding(
    blueprint: AutonomyBlueprint, normalized_source: str
) -> tuple[int, int, list[UngroundedClaim]]:
    grounded = 0
    total = 0
    ungrounded: list[UngroundedClaim] = []

    def inspect(items, claim_type: str) -> None:
        nonlocal grounded, total
        for item in items:
            label = _claim_label(item)
            if not item.evidence:
                total += 1
                ungrounded.append(
                    UngroundedClaim(claim_type=claim_type, ref_id=item.id, title=label, reason="no_evidence")
                )
                continue
            for span in item.evidence:
                total += 1
                if _is_grounded(span.quote, normalized_source):
                    grounded += 1
                else:
                    ungrounded.append(
                        UngroundedClaim(
                            claim_type=claim_type,
                            ref_id=item.id,
                            title=label,
                            reason="quote_not_in_source",
                            quote=span.quote,
                        )
                    )

    inspect(blueprint.steps, "step")
    inspect(blueprint.gaps, "gap")
    return grounded, total, ungrounded


def _claim_label(item: ProcessStep | Gap) -> str:
    title = getattr(item, "title", None)
    if title:
        return title
    return (getattr(item, "description", "") or "")[:60]


def _is_grounded(quote: str, normalized_source: str) -> bool:
    needle = _normalize(quote)
    if not needle:
        return False
    if needle in normalized_source:
        return True
    tokens = needle.split()
    if not tokens:
        return False
    source_tokens = set(normalized_source.split())
    overlap = sum(1 for token in tokens if token in source_tokens) / len(tokens)
    return overlap >= _FUZZY_OVERLAP_THRESHOLD


def _normalize(text: str) -> str:
    lowered = re.sub(r"\s+", " ", (text or "").lower())
    return re.sub(r"[^a-z0-9 ]+", " ", lowered).strip()
