import asyncio

from app.analyzer import analyze_locally
from app.demo_data import DEMOS
from app.model_runtime import ModelRouter
from app.models import EvidenceSpan, ProcessInput
from app.verification import verify_blueprint


def _local_blueprint(demo_id: str):
    demo = next(demo for demo in DEMOS if demo.id == demo_id)
    request = ProcessInput(title=demo.title, domain=demo.domain, text=demo.text, prefer_ai=False)
    return analyze_locally(request), demo.text


def test_verification_is_noop_on_deterministic_blueprint() -> None:
    blueprint, text = _local_blueprint("invoice-exceptions")
    verified = verify_blueprint(blueprint, text)

    assert verified.verification is not None
    assert verified.verification.escalated_step_count == 0
    # The deterministic engine already satisfies the safety invariant.
    for step in verified.steps:
        autonomous = step.autonomy_mode in {"ai_employee", "rules"}
        must_gate = step.risk_level == "high" or not step.reversible
        assert not (autonomous and must_gate)


def test_local_evidence_is_fully_grounded() -> None:
    blueprint, text = _local_blueprint("invoice-exceptions")
    verified = verify_blueprint(blueprint, text)

    assert verified.verification.groundedness >= 0.9
    assert verified.verification.total_claims > 0


def test_hallucinated_quote_is_quarantined() -> None:
    blueprint, text = _local_blueprint("invoice-exceptions")
    tampered_step = blueprint.steps[0].model_copy(
        update={"evidence": [EvidenceSpan(quote="the CFO personally wires funds to a numbered account at midnight")]}
    )
    tampered = blueprint.model_copy(update={"steps": [tampered_step, *blueprint.steps[1:]]})

    verified = verify_blueprint(tampered, text)

    assert verified.verification.groundedness < 1.0
    assert any(claim.reason == "quote_not_in_source" for claim in verified.verification.ungrounded_claims)


def test_under_gated_risky_step_is_escalated() -> None:
    blueprint, text = _local_blueprint("invoice-exceptions")
    target = next(step for step in blueprint.steps if step.risk_level == "high" or not step.reversible)
    downgraded = target.model_copy(update={"autonomy_mode": "ai_employee"})
    tampered = blueprint.model_copy(
        update={"steps": [downgraded if step.id == target.id else step for step in blueprint.steps]}
    )

    verified = verify_blueprint(tampered, text)

    resolved = next(step for step in verified.steps if step.id == target.id)
    assert resolved.autonomy_mode == "hitl"
    assert verified.verification.escalated_step_count >= 1
    assert any(divergence.step_id == target.id for divergence in verified.verification.divergences)


def test_verify_does_not_mutate_input() -> None:
    blueprint, text = _local_blueprint("invoice-exceptions")
    target = next(step for step in blueprint.steps if step.risk_level == "high" or not step.reversible)
    downgraded = target.model_copy(update={"autonomy_mode": "ai_employee"})
    tampered = blueprint.model_copy(
        update={"steps": [downgraded if step.id == target.id else step for step in blueprint.steps]}
    )

    verify_blueprint(tampered, text)

    still = next(step for step in tampered.steps if step.id == target.id)
    assert still.autonomy_mode == "ai_employee"


def test_router_runs_neuro_symbolic_pipeline_on_model_output(monkeypatch) -> None:
    """The model under-gates an irreversible payment; the router must escalate it."""
    source = (
        "The AP analyst wires the payment in NetSuite once the invoice is approved. "
        "Finance confirms the changed bank details before any payment is released."
    )

    async def fake_call(_request, _model):
        return {
            "title": "Mock SOP",
            "domain": "accounts_payable",
            "source_summary": "mock",
            "steps": [
                {
                    "id": "step_1",
                    "title": "Wire the payment",
                    "description": "The AP analyst wires the payment in NetSuite once the invoice is approved.",
                    "autonomy_mode": "ai_employee",
                    "risk_level": "high",
                    "reversible": False,
                    "evidence": [{"quote": "wires the payment in NetSuite", "source": "submitted_process"}],
                }
            ],
            "gaps": [],
            "hitl_gates": [],
            "metrics": [],
            "action_stubs": [],
        }

    monkeypatch.setenv("LITELLM_MODEL", "anthropic/claude-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr("app.model_runtime._call_litellm", fake_call)

    request = ProcessInput(title="Mock SOP", domain="accounts_payable", text=source, prefer_ai=True)
    blueprint = asyncio.run(ModelRouter().analyze(request))

    assert blueprint.analyzer == "litellm"
    assert blueprint.steps[0].autonomy_mode == "hitl"  # escalated by the control plane
    assert blueprint.verification is not None
    assert blueprint.verification.escalated_step_count == 1
    assert blueprint.verification.groundedness == 1.0
