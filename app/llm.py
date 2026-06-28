from __future__ import annotations

import asyncio
import json
import os
import re

import litellm
from litellm import completion

from app.analyzer import analyze_locally, coerce_blueprint
from app.models import AutonomyBlueprint, ProcessInput


SYSTEM_PROMPT = """\
You are the perception layer of a neuro-symbolic deployment compiler for enterprise
finance AI employees. You read one messy SOP and emit a structured AutonomyBlueprint.

A deterministic control plane independently verifies everything you produce: it checks
every evidence quote against the source text, recomputes the readiness score, and
escalates any irreversible or high-risk step you leave autonomous. The system rewards
grounded honesty, not optimistic automation. If you cannot quote it from the source,
do not assert it.

OUTPUT
- Reason internally, then return EXACTLY ONE JSON object and nothing else.
- No prose, no explanation, no markdown code fences.

WHAT TO EXTRACT
- steps: every distinct action, in order. Preserve decision branches and rejection
  paths via next_step_ids (ids look like "step_1", "step_2").
- gaps: missing policy that blocks safe delegation. Use ONLY these gap_type values:
  missing_owner, no_timeout_or_escalation, no_exception_path, missing_audit_evidence,
  ambiguous_handoff, duplicate_detection, no_learning_loop.
- hitl_gates: one per step that needs a human decision (reference its step_id).
- metrics: 2-4 operational metrics worth tracking (optional).

EVIDENCE (verified — be exact)
- Every step and every gap MUST include at least one evidence span.
- Each quote MUST be a VERBATIM substring of the SOP: copy the exact characters,
  at most ~15 words, the most specific clause. Never paraphrase or summarize.

AUTHORITY CALIBRATION (the control plane enforces this — match it so it never has to override you)
- autonomy_mode:
  - ai_employee: interpretation, extraction, matching, classification, routing, communication.
  - rules: deterministic execution against a stated threshold or branch.
  - hitl: explicit human approval is required, OR the action is irreversible or high-risk
    (payments, wires, bank-detail changes, vendor/master-data writes, refunds, contract
    or security decisions).
  - human_only: cannot reasonably be automated at all.
- risk_level: low = routine reversible work; medium = approvals / reviews / exceptions;
  high = money movement, bank/vendor-master changes, security, or contract decisions.
- reversible: false for anything that moves money or mutates master data.
- Invariant: a high-risk OR irreversible step must be hitl.

LEAVE TO THE ENGINE (omit these — the control plane computes them deterministically)
- readiness_score, confidence (top-level), source_summary, mermaid, action_stubs.
Per-step "confidence" (0-1) reflects YOUR extraction certainty, not model confidence.
Prefer precision over completeness.

EXAMPLE
SOP: "The AP analyst logs the invoice in NetSuite and matches it to the PO. If the
vendor's bank details changed, finance must verify the change before payment. The SOP
does not define a timeout for that verification."
JSON:
{"title":"Invoice exception","domain":"accounts_payable","steps":[\
{"id":"step_1","title":"Log and match invoice","description":"AP analyst logs the invoice in NetSuite and matches it to the PO.","actor":"AP Analyst","system":"NetSuite","inputs":["invoice","PO"],"outputs":["matched invoice"],"decision_rule":null,"next_step_ids":["step_2"],"autonomy_mode":"ai_employee","risk_level":"low","reversible":true,"confidence":0.82,"evidence":[{"quote":"logs the invoice in NetSuite and matches it to the PO","source":"submitted_process"}]},\
{"id":"step_2","title":"Verify changed bank details","description":"Finance verifies a changed bank detail before payment.","actor":"Finance","system":null,"inputs":["bank details"],"outputs":["verified payment"],"decision_rule":"if bank details changed","next_step_ids":[],"autonomy_mode":"hitl","risk_level":"high","reversible":false,"confidence":0.8,"evidence":[{"quote":"finance must verify the change before payment","source":"submitted_process"}]}],\
"hitl_gates":[{"id":"gate_1","step_id":"step_2","trigger":"Irreversible bank-detail change before payment","human_question":"Are the changed bank details verified from an independent trusted source?","context_fields":["case_id","bank details"],"resume_action":"resume_verify_bank","risk_reduced":"Prevents payment to a fraudulently altered account."}],\
"gaps":[{"id":"gap_1","severity":"high","gap_type":"no_timeout_or_escalation","description":"No timeout is defined for bank-detail verification.","affected_step_ids":["step_2"],"recommendation":"Define an SLA and escalation owner for the verification.","evidence":[{"quote":"does not define a timeout for that verification","source":"submitted_process"}]}],\
"metrics":[]}
"""


JSON_SCHEMA_HINT = {
    "title": "string (echo or refine the process title)",
    "domain": "string",
    "steps": [
        {
            "id": "step_1",
            "title": "short imperative action title",
            "description": "one source-grounded sentence",
            "actor": "role name or null",
            "system": "system of record or null",
            "inputs": ["input names"],
            "outputs": ["output names"],
            "decision_rule": "threshold/branch text or null",
            "next_step_ids": ["step_2"],
            "autonomy_mode": "ai_employee | rules | hitl | human_only",
            "risk_level": "low | medium | high",
            "reversible": True,
            "confidence": 0.7,
            "evidence": [{"quote": "VERBATIM substring of the SOP", "source": "submitted_process"}],
        }
    ],
    "hitl_gates": [
        {
            "id": "gate_1",
            "step_id": "step_1",
            "trigger": "why a human is needed",
            "human_question": "the decision question for the human",
            "context_fields": ["case_id", "amount"],
            "resume_action": "resume_action_name",
            "risk_reduced": "risk this gate mitigates",
        }
    ],
    "gaps": [
        {
            "id": "gap_1",
            "severity": "low | medium | high",
            "gap_type": (
                "missing_owner | no_timeout_or_escalation | no_exception_path | "
                "missing_audit_evidence | ambiguous_handoff | duplicate_detection | no_learning_loop"
            ),
            "description": "source-grounded gap",
            "affected_step_ids": ["step_1"],
            "recommendation": "specific fix",
            "evidence": [{"quote": "VERBATIM substring of the SOP", "source": "submitted_process"}],
        }
    ],
    "metrics": [{"name": "string", "definition": "string", "target": "string", "why_it_matters": "string"}],
    "_omit": "Do NOT emit readiness_score, confidence, source_summary, mermaid, or action_stubs — the control plane computes them.",
}


async def analyze_with_optional_ai(request: ProcessInput) -> AutonomyBlueprint:
    model = os.getenv("LITELLM_MODEL", "gpt-4o-mini")
    if not request.prefer_ai:
        return analyze_locally(request)

    if not _has_litellm_provider_key(model):
        warnings = [f"LiteLLM provider key not configured for {model}; used deterministic local analyzer."]
        return analyze_locally(request, warnings=warnings)

    try:
        payload = await _call_litellm(request, model)
        return coerce_blueprint(payload, request, analyzer="litellm", analyzer_model=model)
    except Exception as exc:  # noqa: BLE001 - fallback is intentional for offline reliability
        return analyze_locally(
            request,
            analyzer="litellm_fallback",
            analyzer_model=model,
            warnings=[f"AI extraction failed: {str(exc)} — falling back to local analyzer."],
        )


async def _call_litellm(request: ProcessInput, model: str) -> dict:
    timeout_seconds = float(os.getenv("LITELLM_TIMEOUT_SECONDS", "120"))
    return await asyncio.wait_for(
        asyncio.to_thread(_call_litellm_sync, request, model, timeout_seconds),
        timeout=timeout_seconds + 5,
    )


def _call_litellm_sync(request: ProcessInput, model: str, timeout_seconds: float) -> dict:
    system_content = f"{SYSTEM_PROMPT}\n\nSCHEMA (field shape; obey the types and rules above):\n{json.dumps(JSON_SCHEMA_HINT, indent=2)}"
    user_content = (
        f"Process title: {request.title}\n"
        f"Domain: {request.domain}\n\n"
        "Compile the AutonomyBlueprint for the SOP below. Return only the JSON object.\n\n"
        f"<sop>\n{request.text}\n</sop>"
    )
    kwargs = _litellm_gateway_kwargs()

    response = completion(
        model=_effective_model(model),
        messages=[
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
        temperature=0,
        timeout=timeout_seconds,
        num_retries=0,  # fail fast: the deterministic analyzer is the safety net
        **kwargs,
    )
    content = response["choices"][0]["message"]["content"]
    return _extract_json(content)


def _extract_json(content: str) -> dict:
    """Parse a JSON object from a model response, tolerating code fences or stray prose."""
    text = (content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _has_litellm_provider_key(model: str) -> bool:
    if os.getenv("LITELLM_API_KEY") or os.getenv("LITELLM_PROXY_API_KEY"):
        return True
    prefix = model.split("/", 1)[0].lower() if "/" in model else "openai"
    provider_keys = {
        "anthropic": "ANTHROPIC_API_KEY",
        "claude": "ANTHROPIC_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "vertex_ai": "GOOGLE_APPLICATION_CREDENTIALS",
        "mistral": "MISTRAL_API_KEY",
        "cohere": "COHERE_API_KEY",
        "groq": "GROQ_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "azure": "AZURE_API_KEY",
        "ollama": None,
        "openai": "OPENAI_API_KEY",
    }
    env_key = provider_keys.get(prefix, "OPENAI_API_KEY")
    return env_key is None or bool(os.getenv(env_key))


def _effective_model(model: str) -> str:
    if "/" in model or not os.getenv("LITELLM_API_BASE"):
        return model
    provider = os.getenv("LITELLM_PROVIDER", "litellm_proxy").strip("/")
    return f"{provider}/{model}"


def _litellm_gateway_kwargs() -> dict[str, str]:
    kwargs: dict[str, str] = {}
    api_base = os.getenv("LITELLM_API_BASE") or os.getenv("LITELLM_PROXY_API_BASE")
    api_key = os.getenv("LITELLM_API_KEY") or os.getenv("LITELLM_PROXY_API_KEY")
    provider = os.getenv("LITELLM_PROVIDER", "litellm_proxy").strip("/")

    if api_base:
        if provider == "litellm_proxy":
            litellm.api_base = api_base
            os.environ.setdefault("LITELLM_PROXY_API_BASE", api_base)
        else:
            kwargs["api_base"] = api_base
    if api_key:
        if provider == "litellm_proxy":
            os.environ.setdefault("LITELLM_PROXY_API_KEY", api_key)
        else:
            kwargs["api_key"] = api_key
    return kwargs
