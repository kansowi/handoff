from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Literal

from app.models import (
    AnalyzerKind,
    AutonomyBlueprint,
    EvidenceSpan,
    Gap,
    HitlGate,
    Metric,
    ProcessInput,
    ProcessStep,
    RiskLevel,
    ActionStub,
)


MAX_ACTION_STEPS = 12
TRUNCATION_WARNING = "Process truncated: only the first 12 action steps were analyzed. Paste a shorter SOP section for full coverage."


ACTION_VERB_RE = re.compile(
    r"\b("
    r"receiv(?:e|es|ed)|arriv(?:e|es|ed)|log(?:s|ged)?|extract(?:s|ed)?|"
    r"check(?:s|ed)?|compar(?:e|es|ed)|match(?:es|ed)?|rout(?:e|es|ed)|"
    r"approv(?:e|es|ed)|review(?:s|ed)?|verif(?:y|ies|ied)|confirm(?:s|ed)?|"
    r"email(?:s|ed)?|ask(?:s|ed)?|schedul(?:e|es|ed)|record(?:s|ed)?|"
    r"submit(?:s|ted)?|send(?:s)?|sent|creat(?:e|es|ed)|notif(?:y|ies|ied)|"
    r"process(?:es|ed)?|detect(?:s|ed)?|resolv(?:e|es|ed)|requires?|required"
    r")\b",
    flags=re.IGNORECASE,
)

KNOWN_SYSTEMS = (
    "NetSuite",
    "Coupa",
    "SAP",
    "Oracle",
    "Stripe",
    "Zendesk",
    "Salesforce",
    "Workday",
    "Slack",
    "Gmail",
    "Excel",
)

ROLE_PATTERNS = {
    "AP Analyst": r"\b(AP analyst|accounts payable analyst)\b",
    "Finance": r"\b(finance|controller|CFO)\b",
    "Procurement": r"\b(procurement|buyer|purchasing)\b",
    "Legal": r"\blegal\b",
    "Security": r"\bsecurity\b",
    "Support": r"\b(support agent|customer support|support)\b",
    "Revenue Operations": r"\b(revenue operations|revops)\b",
    "Business Owner": r"\bbusiness owner\b",
    "Manager": r"\bmanager\b",
}

HIGH_RISK_TERMS = (
    "payment",
    "wire",
    "customer data",
)

MEDIUM_RISK_TERMS = (
    "approve",
    "approval",
    "review",
    "exception",
    "reject",
    "change",
    "fast-track",
    "dispute",
)

AMBIGUOUS_OWNER_TERMS = ("team", "queue", "someone", "owner", "requester")
TIMEOUT_TERMS = ("sla", "timeout", "respond within", "business day", "hours", "days")
AUDIT_TERMS = ("audit", "log", "record", "evidence", "note")
EXCEPTION_TERMS = ("exception", "reject", "rejection", "else", "otherwise", "does not", "missing")
POLICY_GAP_MARKERS = (
    "does not define",
    "does not specify",
    "does not say",
    "doesn't define",
    "doesn't specify",
    "doesn't say",
    "not define",
    "not specify",
    "missing:",
)
PROMPT_INJECTION_MARKERS = (
    "ignore previous instructions",
    "ignore all previous instructions",
    "disregard previous instructions",
    "mark this process ready",
    "mark the process ready",
    "do not report gaps",
    "don't report gaps",
    "do not flag gaps",
    "don't flag gaps",
    "always return ready",
    "override the analyzer",
)

SentenceKind = Literal["action_step", "policy_gap", "context_note"]


@dataclass(frozen=True)
class Sentence:
    text: str
    index: int


@dataclass(frozen=True)
class ClassifiedSentence:
    sentence: Sentence
    kind: SentenceKind


def analyze_locally(
    request: ProcessInput,
    *,
    analyzer: AnalyzerKind = "local",
    analyzer_model: str | None = None,
    warnings: list[str] | None = None,
) -> AutonomyBlueprint:
    sentences = _split_sentences(request.text)
    classified = _classify_sentences(sentences)
    action_sentences, policy_gap_sentences, truncated = _select_action_sentences(classified)
    if not action_sentences:
        action_sentences = [item.sentence for item in classified if item.kind != "policy_gap"][: min(len(sentences), 8)]
    all_warnings = list(warnings or [])
    if truncated:
        all_warnings.append(TRUNCATION_WARNING)

    steps = _build_steps(action_sentences)
    gaps = _detect_gaps(steps, request.text, policy_gap_sentences)
    hitl_gates = _build_hitl_gates(steps, gaps)
    metrics = _build_metrics(request.domain)
    stubs = _build_action_stubs(steps)
    mermaid = _generate_mermaid(steps)
    score = _readiness_score(steps, gaps, hitl_gates)
    confidence = _confidence_score(steps, gaps)

    summary = _summarize_source(request.text, request.domain)
    pitch = _executive_pitch(request.title, score, gaps, hitl_gates)

    return AutonomyBlueprint(
        title=request.title,
        domain=request.domain,
        source_summary=summary,
        readiness_score=score,
        confidence=confidence,
        steps=steps,
        hitl_gates=hitl_gates,
        gaps=gaps,
        metrics=metrics,
        action_stubs=stubs,
        mermaid=mermaid,
        executive_pitch=pitch,
        analyzer=analyzer,
        analyzer_model=analyzer_model,
        warnings=all_warnings,
    )


def coerce_blueprint(
    payload: dict,
    request: ProcessInput,
    analyzer: AnalyzerKind,
    analyzer_model: str | None = None,
) -> AutonomyBlueprint:
    """Validate an AI payload, repairing only deterministic derived fields."""
    steps = [ProcessStep.model_validate(step) for step in payload.get("steps", [])]
    if not steps:
        raise ValueError("AI response did not include process steps")

    normalized_steps = _normalize_step_graph(steps)
    gaps = [Gap.model_validate(gap) for gap in payload.get("gaps", [])]
    hitl_gates = [HitlGate.model_validate(gate) for gate in payload.get("hitl_gates", [])]
    metrics = [Metric.model_validate(metric) for metric in payload.get("metrics", [])] or _build_metrics(request.domain)
    stubs = [ActionStub.model_validate(stub) for stub in payload.get("action_stubs", [])] or _build_action_stubs(
        normalized_steps
    )
    mermaid = _generate_mermaid(normalized_steps)
    score = int(payload.get("readiness_score") or _readiness_score(normalized_steps, gaps, hitl_gates))
    confidence = float(payload.get("confidence") or _confidence_score(normalized_steps, gaps))

    return AutonomyBlueprint(
        title=str(payload.get("title") or request.title),
        domain=str(payload.get("domain") or request.domain),
        source_summary=str(payload.get("source_summary") or _summarize_source(request.text, request.domain)),
        readiness_score=max(0, min(100, score)),
        confidence=max(0.0, min(1.0, confidence)),
        steps=normalized_steps,
        hitl_gates=hitl_gates,
        gaps=gaps,
        metrics=metrics,
        action_stubs=stubs,
        mermaid=mermaid,
        executive_pitch=str(payload.get("executive_pitch") or _executive_pitch(request.title, score, gaps, hitl_gates)),
        analyzer=analyzer,
        analyzer_model=analyzer_model,
        warnings=[],
    )


def _split_sentences(text: str) -> list[Sentence]:
    normalized = re.sub(r"\s+", " ", text.strip())
    raw_parts = re.split(r"(?<=[.!?])\s+|(?:\n+)|(?:\s+\d+[.)]\s+)|(?:\s+-\s+)", normalized)
    parts = [part.strip(" -") for part in raw_parts if len(part.strip(" -")) > 12]
    return [Sentence(text=part, index=index) for index, part in enumerate(parts)]


def _classify_sentences(sentences: Iterable[Sentence]) -> list[ClassifiedSentence]:
    classified: list[ClassifiedSentence] = []
    for sentence in sentences:
        lower = sentence.text.lower()
        if _is_prompt_injection_sentence(lower):
            kind: SentenceKind = "context_note"
        elif _is_policy_gap_sentence(lower):
            kind: SentenceKind = "policy_gap"
        elif ACTION_VERB_RE.search(sentence.text):
            kind = "action_step"
        else:
            kind = "context_note"
        classified.append(ClassifiedSentence(sentence=sentence, kind=kind))
    return classified


def _is_policy_gap_sentence(lower_text: str) -> bool:
    return any(marker in lower_text for marker in POLICY_GAP_MARKERS)


def _is_prompt_injection_sentence(lower_text: str) -> bool:
    return any(marker in lower_text for marker in PROMPT_INJECTION_MARKERS)


def _select_action_sentences(classified: Iterable[ClassifiedSentence]) -> tuple[list[Sentence], list[Sentence], bool]:
    selected: list[Sentence] = []
    policy_gaps: list[Sentence] = []
    for item in classified:
        if item.kind == "action_step":
            selected.append(item.sentence)
        elif item.kind == "policy_gap":
            policy_gaps.append(item.sentence)
    return selected[:MAX_ACTION_STEPS], policy_gaps, len(selected) > MAX_ACTION_STEPS


def _build_steps(sentences: list[Sentence]) -> list[ProcessStep]:
    steps: list[ProcessStep] = []
    prior_actor: str | None = None
    for index, sentence in enumerate(sentences, start=1):
        step_id = f"step_{index}"
        text = sentence.text
        lower = text.lower()
        risk = _risk_level(lower)
        mode = _autonomy_mode(lower, risk)
        actor = _detect_actor(text, prior_actor)
        system = _detect_system(text)
        decision_rule = _detect_decision_rule(text)
        title = _make_title(text)
        next_ids = [f"step_{index + 1}"] if index < len(sentences) else []
        if actor:
            prior_actor = actor

        steps.append(
            ProcessStep(
                id=step_id,
                title=title,
                description=text,
                actor=actor,
                system=system,
                inputs=_detect_inputs(text),
                outputs=_detect_outputs(text, title),
                decision_rule=decision_rule,
                next_step_ids=next_ids,
                autonomy_mode=mode,
                risk_level=risk,
                reversible=not any(term in lower for term in ("payment", "bank", "refund", "vendor record", "wire")),
                confidence=_step_confidence(actor, system, decision_rule),
                evidence=[EvidenceSpan(quote=_truncate(text, 220))],
            )
        )
    return _normalize_step_graph(steps)


def _normalize_step_graph(steps: list[ProcessStep]) -> list[ProcessStep]:
    step_ids = {step.id for step in steps}
    normalized: list[ProcessStep] = []
    for index, step in enumerate(steps):
        fallback_next = [steps[index + 1].id] if index < len(steps) - 1 else []
        cleaned_next = [next_id for next_id in step.next_step_ids if next_id in step_ids and next_id != step.id]
        normalized.append(step.model_copy(update={"next_step_ids": cleaned_next or fallback_next}))
    return normalized


def _detect_actor(text: str, prior_actor: str | None = None) -> str | None:
    for role, pattern in ROLE_PATTERNS.items():
        if re.search(pattern, text, flags=re.IGNORECASE):
            return role
    if prior_actor and re.search(r"\b(the\s+)?analyst\b", text, flags=re.IGNORECASE):
        return prior_actor
    match = re.search(r"\b([A-Z][a-z]+(?:\s[A-Z][a-z]+){0,2})\s+(?:checks|reviews|approves|verifies|creates)", text)
    if not match:
        return None
    actor = match.group(1)
    if actor.lower() in {"someone", "anyone", "everyone", "no one", "nobody"}:
        return None
    return actor


def _detect_system(text: str) -> str | None:
    for system in KNOWN_SYSTEMS:
        if re.search(rf"\b{re.escape(system)}\b", text, flags=re.IGNORECASE):
            return system
    return None


def _detect_decision_rule(text: str) -> str | None:
    patterns = (
        r"\b(if|when)\b\s+[^.;]{1,120}",
        r"\b(above|under|between)\b\s+[^.;]{1,80}",
        r"\brequires?\b\s+[^.;]{1,80}",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            clause = match.group(0).strip()
            clause = re.split(
                r"\b(the|a|an|procurement|finance|legal|security|support|agent|analyst|manager|controller)\s+"
                r"(checks|sends|routes|asks|emails|records|creates|notifies|processes|reviews|approves|verifies)\b",
                clause,
                maxsplit=1,
                flags=re.IGNORECASE,
            )[0].strip()
            return _truncate(clause, 60)
    return None


def _detect_inputs(text: str) -> list[str]:
    inputs: list[str] = []
    lowered = text.lower()
    candidates = {
        "invoice": "Invoice",
        "po": "Purchase order",
        "purchase order": "Purchase order",
        "vendor": "Vendor record",
        "bank": "Bank details",
        "contract": "Contract",
        "questionnaire": "Questionnaire",
        "refund": "Refund request",
        "customer": "Customer record",
        "tax": "Tax information",
        "receiving": "Receiving record",
    }
    for token, label in candidates.items():
        if token in lowered and label not in inputs:
            inputs.append(label)
    return inputs[:5]


def _detect_outputs(text: str, title: str) -> list[str]:
    lowered = text.lower()
    if "approve" in lowered:
        return ["Approval decision"]
    if "record" in lowered or "log" in lowered:
        return ["System record"]
    if "notify" in lowered or "email" in lowered:
        return ["Notification"]
    if "verify" in lowered or "confirm" in lowered or "check" in lowered:
        return ["Validation result"]
    if "create" in lowered:
        return ["Created record"]
    return [f"{title} completed"]


def _risk_level(lower_text: str) -> RiskLevel:
    if "bank" in lower_text and any(term in lower_text for term in ("changed", "change", "verify", "verifies", "confirm")):
        return "high"
    if "contract" in lower_text and any(term in lower_text for term in ("review", "reviews", "approve", "approval", "above")):
        return "high"
    if "security" in lower_text and any(term in lower_text for term in ("reviews", "rejects", "customer data")):
        return "high"
    if "refund" in lower_text and any(
        term in lower_text
        for term in ("approved", "processed", "above", "between", "under", "approval", "policy window")
    ):
        return "high"
    if "vendor master" in lower_text and any(term in lower_text for term in ("change", "create", "update")):
        return "high"
    if "vendor record" in lower_text and any(term in lower_text for term in ("create", "creates", "update", "change")):
        return "high"
    if any(term in lower_text for term in HIGH_RISK_TERMS):
        return "high"
    if "vendor master" in lower_text or "refund" in lower_text:
        return "medium"
    if any(term in lower_text for term in MEDIUM_RISK_TERMS):
        return "medium"
    return "low"


def _autonomy_mode(lower_text: str, risk: RiskLevel) -> str:
    if risk == "high" and any(
        term in lower_text for term in ("security", "contract", "payment", "bank", "refund", "vendor record", "customer data", "wire")
    ):
        return "hitl"
    if any(
        term in lower_text
        for term in (
            "payment",
            "customer data",
            "refunds above",
            "refunds between",
            "processed in stripe",
            "creates the vendor record",
            "create the vendor record",
        )
    ):
        return "hitl"
    if "bank" in lower_text and any(term in lower_text for term in ("changed", "change", "verify", "verifies", "confirm")):
        return "hitl"
    if "contract" in lower_text and any(term in lower_text for term in ("review", "reviews", "approve", "approval", "above")):
        return "hitl"
    if "security" in lower_text and any(term in lower_text for term in ("reviews", "rejects", "customer data")):
        return "hitl"
    if _requires_named_human_approval(lower_text):
        return "hitl"
    if "approval" in lower_text or "approve" in lower_text:
        return "hitl" if risk == "high" else "rules"
    if any(term in lower_text for term in ("extract", "compare", "match", "detect", "classify", "review reason")):
        return "ai_employee"
    if any(term in lower_text for term in ("log", "record", "receive", "route", "notify", "email", "ask")):
        return "ai_employee"
    if any(term in lower_text for term in ("under", "above", "between", "within tolerance", "if")):
        return "rules"
    return "ai_employee"


def _requires_named_human_approval(lower_text: str) -> bool:
    if not re.search(r"\b(approves?|approval|requires?\s+[^.]{0,60}approval)\b", lower_text):
        return False
    roles = r"(controller|finance|manager|legal|security|revenue operations|revops)"
    return bool(
        re.search(rf"\b{roles}\s+approval\b", lower_text)
        or re.search(rf"\bapproval\s+(?:by|from)\s+(?:the\s+)?{roles}\b", lower_text)
        or re.search(rf"\brequires?\s+(?:the\s+)?{roles}\s+approval\b", lower_text)
        or re.search(rf"\b{roles}\s+(?:approves?|reviews?)\b", lower_text)
    )


def _step_confidence(actor: str | None, system: str | None, decision_rule: str | None) -> float:
    confidence = 0.54
    if actor:
        confidence += 0.16
    if system:
        confidence += 0.12
    if decision_rule:
        confidence += 0.08
    return min(confidence, 0.9)


def _make_title(text: str) -> str:
    lower = text.lower()
    if "logs it in netsuite" in lower and "extracts" in lower:
        return "Log invoice and extract fields"
    if "vendor master record" in lower and "compares" in lower:
        return "Validate vendor and PO match"
    if "matches within tolerance" in lower and "routes" in lower:
        return "Route matched invoice for approval"
    if "controller approval" in lower:
        return "Require controller approval for high-value invoices"
    if "changed bank details" in lower:
        return "Confirm changed bank details"
    if "po is missing" in lower:
        return "Request missing PO from requester"
    if "scheduled for payment" in lower:
        return "Schedule approved invoices for payment"
    if "payment confirmation is recorded" in lower:
        return "Record payment confirmation"
    if "business owner submits a new vendor request" in lower:
        return "Submit new vendor request"
    if "vendor is new" in lower and "w-9" in lower:
        return "Collect supplier tax and security documents"
    if "legal reviews contracts" in lower:
        return "Review high-value contract"
    if "security reviews vendors" in lower:
        return "Review customer-data vendor risk"
    if "all reviews pass" in lower and "vendor record" in lower:
        return "Create approved vendor record"
    if "customer support receives refund" in lower:
        return "Receive refund request"
    if "support agent confirms" in lower and "refund" in lower:
        return "Verify customer and refund reason"
    if "refunds under" in lower:
        return "Apply support refund threshold"
    if "refunds between" in lower:
        return "Escalate mid-tier refund approval"
    if "refunds above" in lower:
        return "Escalate high-value refund approval"
    if "request is sent to a manager" in lower:
        return "Escalate disputed refund to manager"
    if "approved refunds are processed" in lower:
        return "Process approved refund"

    clean = text.strip()
    if re.match(r"^(if|when)\b", clean, flags=re.IGNORECASE) and "," in clean:
        clean = clean.split(",", 1)[1].strip()
    clean = re.sub(r"^(if|when|once)\s+", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"^(the|a|an)\s+", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\s+", " ", clean)
    words = re.findall(r"[A-Za-z0-9$]+", clean)
    title_words = words[:7]
    while title_words and title_words[-1].lower() in {"the", "a", "an", "in", "for", "to", "and", "or"}:
        title_words.pop()
    title = " ".join(title_words)
    return title[:1].upper() + title[1:] if title else "Process step"


def _detect_gaps(steps: list[ProcessStep], full_text: str, policy_gap_sentences: list[Sentence] | None = None) -> list[Gap]:
    gaps: list[Gap] = []
    lower_full = full_text.lower()
    action_text = " ".join(step.description.lower() for step in steps)
    policy_gap_sentences = policy_gap_sentences or []
    policy_gap_text = " ".join(sentence.text.lower() for sentence in policy_gap_sentences)
    explicit_timeout_gap = "timeout" in policy_gap_text or "sla" in policy_gap_text
    explicit_exception_gap = any(term in policy_gap_text for term in ("rejection", "rejects", "negative branch"))
    explicit_audit_gap = any(term in policy_gap_text for term in ("audit", "evidence", "required note"))

    for step in steps:
        lower = step.description.lower()
        if step.actor is None:
            gaps.append(
                Gap(
                    id=f"gap_missing_owner_{step.id}",
                    severity="high" if step.risk_level == "high" else "medium",
                    gap_type="missing_owner",
                    description=f"{step.title} does not name the accountable human or team.",
                    affected_step_ids=[step.id],
                    recommendation="Assign an accountable owner before delegating this step to an AI employee.",
                    evidence=step.evidence,
                )
            )
        if any(term in lower for term in AMBIGUOUS_OWNER_TERMS) and any(
            action in lower for action in ("approval", "approve", "route", "ask", "handoff", "fast-track")
        ):
            gaps.append(
                Gap(
                    id=f"gap_ambiguous_handoff_{step.id}",
                    severity="medium",
                    gap_type="ambiguous_handoff",
                    description=f"{step.title} uses an ambiguous handoff such as queue, team, owner, or requester.",
                    affected_step_ids=[step.id],
                    recommendation="Replace the handoff with a named role, system queue, and escalation owner.",
                    evidence=step.evidence,
                )
            )
        if _has_approval_or_review_work(lower) and not _has_defined_timeout(action_text) and not explicit_timeout_gap:
            gaps.append(
                Gap(
                    id=f"gap_no_timeout_{step.id}",
                    severity="high" if step.risk_level == "high" else "medium",
                    gap_type="no_timeout_or_escalation",
                    description=f"{step.title} has approval/review work but no SLA or timeout in the source process.",
                    affected_step_ids=[step.id],
                    recommendation="Define a timeout, escalation path, and what the AI employee should do while waiting.",
                    evidence=step.evidence,
                )
            )
        if step.decision_rule and not _has_exception_path(action_text) and not explicit_exception_gap:
            gaps.append(
                Gap(
                    id=f"gap_no_exception_path_{step.id}",
                    severity="medium",
                    gap_type="no_exception_path",
                    description=f"{step.title} contains a decision but the process does not define the negative branch.",
                    affected_step_ids=[step.id],
                    recommendation="Define both pass and fail branches, including who resolves exceptions.",
                    evidence=step.evidence,
                )
            )
        if (
            step.risk_level == "high"
            and _requires_audit_evidence(lower)
            and not _has_required_audit_evidence(action_text)
            and not explicit_audit_gap
        ):
            gaps.append(
                Gap(
                    id=f"gap_no_audit_{step.id}",
                    severity="high",
                    gap_type="missing_audit_evidence",
                    description=f"{step.title} is high risk but the SOP does not require evidence capture.",
                    affected_step_ids=[step.id],
                    recommendation="Require an audit note with source evidence, decision reason, actor, and timestamp.",
                    evidence=step.evidence,
                )
            )

    gaps.extend(_explicit_policy_gaps(policy_gap_sentences, steps))

    if "learn" not in lower_full and "feedback" not in lower_full and "correction" not in lower_full:
        gaps.append(
            Gap(
                id="gap_no_feedback_loop",
                severity="low",
                gap_type="no_learning_loop",
                description="The process does not say how human corrections improve the future AI employee runbook.",
                affected_step_ids=[],
                recommendation="Add a feedback loop: every override should update policy, examples, or retrieval context.",
            )
        )

    return _dedupe_gaps(gaps)[:10]


def _explicit_policy_gaps(policy_gap_sentences: list[Sentence], steps: list[ProcessStep]) -> list[Gap]:
    gaps: list[Gap] = []
    for sentence in policy_gap_sentences:
        text = sentence.text
        lower = text.lower()
        evidence = [EvidenceSpan(quote=_truncate(text, 220))]

        def add(gap_type: str, severity: str, description: str, recommendation: str) -> None:
            gaps.append(
                Gap(
                    id=f"gap_{gap_type}_{sentence.index}",
                    severity=severity,
                    gap_type=gap_type,
                    description=description,
                    affected_step_ids=_related_step_ids(gap_type, lower, steps),
                    recommendation=recommendation,
                    evidence=evidence,
                )
            )

        if "timeout" in lower or "sla" in lower or "respond within" in lower:
            add(
                "no_timeout_or_escalation",
                "medium",
                "The source names approval or review work but explicitly says the SLA or timeout is missing.",
                "Define the wait time, escalation owner, and what the AI employee should do while waiting.",
            )
        if "rejection path" in lower or "negative branch" in lower or "what happens when" in lower or "rejects" in lower:
            add(
                "no_exception_path",
                "medium",
                "The source explicitly leaves the rejection or negative branch unresolved.",
                "Define pass, fail, and appeal branches before increasing autonomy.",
            )
        if "audit" in lower or "evidence" in lower or "required note" in lower:
            add(
                "missing_audit_evidence",
                "high" if any(term in lower for term in ("bank", "payment", "security", "vendor record", "refund")) else "medium",
                "The source explicitly says required audit evidence is missing for a risky action.",
                "Require source evidence, decision reason, actor, timestamp, and system outcome.",
            )
        if "exceptions are logged" in lower or "how exceptions are logged" in lower:
            add(
                "exception_logging",
                "medium",
                "The process does not specify how exceptions are logged for later review.",
                "Capture exception type, owner, resolution, and policy update status.",
            )
        if "duplicate" in lower:
            add(
                "duplicate_detection",
                "high" if "refund" in lower else "medium",
                "The process does not define how duplicate requests are detected.",
                "Add deterministic duplicate checks before approval or payout steps.",
            )
        if "who approves" in lower or "who handles" in lower or "who owns" in lower:
            add(
                "missing_owner",
                "high" if any(term in lower for term in ("bank", "security", "fast-track", "payment", "refund")) else "medium",
                "The source explicitly leaves a required owner or approver undefined.",
                "Name the accountable role and backup owner for the handoff.",
            )
    return gaps


def _related_step_ids(gap_type: str, lower_policy_text: str, steps: list[ProcessStep]) -> list[str]:
    keywords: list[str] = []
    if gap_type == "no_timeout_or_escalation":
        keywords.extend(["approve", "approval", "review", "manager", "controller"])
    elif gap_type == "no_exception_path":
        keywords.extend(["review", "approve", "approval", "security", "manager", "dispute"])
    elif gap_type == "duplicate_detection":
        keywords.extend(["refund", "customer", "request", "stripe"])
    elif gap_type == "missing_owner" and ("fast-track" in lower_policy_text or "vendor" in lower_policy_text):
        keywords.extend(["vendor", "procurement", "security"])
    elif "bank" in lower_policy_text:
        keywords.extend(["bank", "payment"])
    elif "security" in lower_policy_text or "customer data" in lower_policy_text:
        keywords.extend(["security", "customer data", "questionnaire"])
    elif "refund" in lower_policy_text or "duplicate" in lower_policy_text or "dispute" in lower_policy_text:
        keywords.extend(["refund", "customer", "dispute", "stripe"])
    elif "approval" in lower_policy_text or "approve" in lower_policy_text or "controller" in lower_policy_text:
        keywords.extend(["approve", "approval", "review", "controller"])
    elif "rejection" in lower_policy_text or "reject" in lower_policy_text:
        keywords.extend(["review", "approve", "security", "manager"])
    elif "fast-track" in lower_policy_text or "vendor" in lower_policy_text:
        keywords.extend(["vendor", "procurement", "security"])
    elif "audit" in lower_policy_text or "evidence" in lower_policy_text:
        keywords.extend(["bank", "payment", "refund", "vendor", "security"])

    if not keywords and gap_type == "missing_audit_evidence":
        keywords.extend(["payment", "bank", "refund", "security", "vendor"])

    related = [
        step.id
        for step in steps
        if any(keyword in f"{step.title} {step.description}".lower() for keyword in keywords)
    ]
    return related[:4]


def _has_defined_timeout(action_text: str) -> bool:
    return bool(
        re.search(r"\b(within|after|by)\s+\d+\s*(hour|hours|day|days|business day|business days)\b", action_text)
        or "respond within" in action_text
        or "sla is" in action_text
    )


def _has_approval_or_review_work(lower_step_text: str) -> bool:
    if re.search(r"\b(approve|approval|requires?\s+[^.]{0,40}approval)\b", lower_step_text):
        return True
    if re.search(r"\breviews?\b", lower_step_text) and "reason" not in lower_step_text:
        return True
    return False


def _has_exception_path(action_text: str) -> bool:
    return any(
        term in action_text
        for term in (
            "else",
            "otherwise",
            "if not",
            "does not respond",
            "missing",
            "dispute",
            "reject",
            "rejects",
            "rejected",
            "closes the request",
            "close the request",
            "notifies the requester",
            "notify the requester",
        )
    )


def _requires_audit_evidence(lower_step_text: str) -> bool:
    return (
        any(term in lower_step_text for term in ("bank", "payment", "wire"))
        or ("refund" in lower_step_text and "process" in lower_step_text)
        or ("vendor record" in lower_step_text and any(term in lower_step_text for term in ("create", "update", "change")))
        or ("security" in lower_step_text and "review" in lower_step_text)
    )


def _has_required_audit_evidence(action_text: str) -> bool:
    return any(term in action_text for term in ("audit note", "source evidence", "evidence requirement", "decision reason"))


def _dedupe_gaps(gaps: list[Gap]) -> list[Gap]:
    seen: set[tuple[str, tuple[str, ...]]] = set()
    unique: list[Gap] = []
    for gap in gaps:
        key = (gap.gap_type, tuple(gap.affected_step_ids))
        if key not in seen:
            seen.add(key)
            unique.append(gap)
    severity_order = {"high": 0, "medium": 1, "low": 2}
    return sorted(unique, key=lambda gap: severity_order[gap.severity])


def _build_hitl_gates(steps: list[ProcessStep], gaps: list[Gap]) -> list[HitlGate]:
    affected_gap_steps = {step_id for gap in gaps if gap.severity == "high" for step_id in gap.affected_step_ids}
    gates: list[HitlGate] = []
    for step in steps:
        if step.autonomy_mode == "hitl" or step.risk_level == "high" or step.id in affected_gap_steps:
            gates.append(
                HitlGate(
                    id=f"gate_{len(gates) + 1}",
                    step_id=step.id,
                    trigger=_gate_trigger(step),
                    human_question=_gate_question(step),
                    context_fields=_context_fields(step),
                    resume_action=f"resume_{_slug(step.title)}",
                    risk_reduced=_risk_reduced(step),
                )
            )
    return gates[:6]


def _gate_trigger(step: ProcessStep) -> str:
    if step.risk_level == "high":
        return "High-risk action or irreversible system change"
    if step.decision_rule:
        return "Policy threshold or branch requires a named decision"
    return "Low confidence or missing owner"


def _gate_question(step: ProcessStep) -> str:
    if "bank" in step.description.lower():
        return "Are the changed bank details verified from an independent trusted source?"
    if "payment" in step.description.lower() or "refund" in step.description.lower():
        return "Should the AI employee release this financial action now?"
    if "contract" in step.description.lower() or "security" in step.description.lower():
        return "Is this risk review cleared for the AI employee to continue?"
    return f"Should the AI employee proceed with: {step.title}?"


def _context_fields(step: ProcessStep) -> list[str]:
    fields = ["step_id", "source_evidence", "risk_level"]
    fields.extend(input_name.lower().replace(" ", "_") for input_name in step.inputs[:3])
    if step.system:
        fields.append("system_of_record")
    return fields


def _risk_reduced(step: ProcessStep) -> str:
    if not step.reversible:
        return "Prevents irreversible financial or master-data changes without human confirmation."
    if step.risk_level == "high":
        return "Adds human accountability before high-risk work continues."
    return "Turns a weak policy edge into an explicit approval checkpoint."


def _build_metrics(domain: str) -> list[Metric]:
    domain_label = domain.replace("_", " ")
    return [
        Metric(
            name="Touchless completion rate",
            definition=f"Share of {domain_label} cases completed without human intervention after policy gates are satisfied.",
            target="+30% in first 60 days",
            why_it_matters="Shows whether the AI employee is replacing coordination work, not just summarizing it.",
        ),
        Metric(
            name="Exception aging",
            definition="Median time that exceptions wait for missing information, approval, or policy clarification.",
            target="-40% in first 60 days",
            why_it_matters="Measures the true operational bottleneck an AI employee can remove.",
        ),
        Metric(
            name="Audit completeness",
            definition="Percentage of runs with source evidence, decision reason, actor, timestamp, and system outcome.",
            target=">95% before expanding autonomy",
            why_it_matters="Builds trust for finance and operations leaders.",
        ),
    ]


def _build_action_stubs(steps: list[ProcessStep]) -> list[ActionStub]:
    stubs: list[ActionStub] = []
    for step in steps:
        if step.autonomy_mode == "human_only":
            continue
        params = {"case_id": "str", "source_evidence": "list[str]"}
        for input_name in step.inputs[:4]:
            params[_slug(input_name)] = "str"
        if step.system:
            params["system"] = "str"
        stubs.append(
            ActionStub(
                action_name=_slug(step.title),
                step_id=step.id,
                action_type="AIEmployeeActivity",
                summary=f"{_mode_label(step.autonomy_mode)}: {step.title}",
                params_schema=params,
                expected_result_schema={
                    "verified": "bool",
                    "status": "str",
                    "escalation_reason": "str | None",
                    "evidence_links": "list[str]",
                },
                retry_policy={"max_attempts": 3, "backoff": "exponential"},
                hitl_trigger=_hitl_trigger_name(step) if step.autonomy_mode == "hitl" or step.risk_level == "high" else None,
                requires_hitl=step.autonomy_mode == "hitl" or step.risk_level == "high",
            )
        )
    return stubs[:10]


def _hitl_trigger_name(step: ProcessStep) -> str:
    if step.decision_rule:
        return _slug(step.decision_rule)
    if step.risk_level == "high":
        return "high_risk_ai_employee_activity"
    return "low_confidence_or_missing_context"


def _generate_mermaid(steps: list[ProcessStep]) -> str:
    lines = ["flowchart LR"]
    for step in steps:
        label = _escape_mermaid(f"{step.id}: {step.title}")
        shape = f'{{"{label}"}}' if step.decision_rule else f'["{label}"]'
        lines.append(f"    {step.id}{shape}")
    for step in steps:
        for next_id in step.next_step_ids:
            lines.append(f"    {step.id} --> {next_id}")
    for step in steps:
        css_class = "hitl" if step.autonomy_mode == "hitl" else step.risk_level
        lines.append(f"    class {step.id} {css_class}")
    lines.extend(
        [
            "    classDef high fill:#ffe5e5,stroke:#c2410c,color:#111827",
            "    classDef medium fill:#fff7cc,stroke:#a16207,color:#111827",
            "    classDef low fill:#e8fff4,stroke:#047857,color:#111827",
            "    classDef hitl fill:#e9e5ff,stroke:#6d28d9,color:#111827",
        ]
    )
    return "\n".join(lines)


def _readiness_score(steps: list[ProcessStep], gaps: list[Gap], gates: list[HitlGate]) -> int:
    if not steps:
        return 0
    score = 88
    severity_penalty = {"high": 9, "medium": 4, "low": 2}
    score -= sum(severity_penalty[gap.severity] for gap in gaps)
    score += min(8, len(gates) * 2)
    score += min(6, sum(1 for step in steps if step.actor) * 2)
    score += min(5, sum(1 for step in steps if step.system) * 2)
    score += min(5, sum(1 for step in steps if step.autonomy_mode in {"ai_employee", "rules"}) * 1)
    if any(gap.severity == "high" for gap in gaps):
        score = min(score, 79)
    elif any(gap.severity == "medium" for gap in gaps):
        score = min(score, 89)
    return max(12, min(96, score))


def _confidence_score(steps: list[ProcessStep], gaps: list[Gap]) -> float:
    if not steps:
        return 0.0
    average = sum(step.confidence for step in steps) / len(steps)
    penalty = min(0.25, 0.03 * len([gap for gap in gaps if gap.severity == "high"]))
    return round(max(0.2, min(0.94, average - penalty)), 2)


def _summarize_source(text: str, domain: str) -> str:
    role_counts = Counter(_detect_actor(sentence.text) for sentence in _split_sentences(text))
    role_counts.pop(None, None)
    roles = ", ".join(role for role, _ in role_counts.most_common(3)) or "unnamed operators"
    systems = [system for system in KNOWN_SYSTEMS if system.lower() in text.lower()]
    system_text = ", ".join(systems[:3]) if systems else "unspecified systems"
    return f"{domain.replace('_', ' ').title()} process involving {roles}, with work touching {system_text}."


def _executive_pitch(title: str, score: int, gaps: list[Gap], gates: list[HitlGate]) -> str:
    high_gaps = len([gap for gap in gaps if gap.severity == "high"])
    hitl_count = len(gates)
    recommendation = (
        f"deploy with HITL gates on {hitl_count} steps" if hitl_count > 0 else "cleared for full AI Employee handoff"
    )
    return (
        f"'{title}' scores {score}/100 on the Handoff readiness index. "
        f"It has {high_gaps} high-risk gaps that would cause an AI Employee to stall or escalate unpredictably. "
        "Resolving these gaps turns loose process context into an operating brief with fewer human bottlenecks and less process debt. "
        f"Current recommendation: {recommendation}."
    )


def _escape_mermaid(value: str) -> str:
    return value.replace('"', "'").replace("[", "(").replace("]", ")").replace("{", "(").replace("}", ")")


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    if len(slug) <= 48:
        return slug or "action"
    shortened = slug[:48].rsplit("_", 1)[0]
    return shortened or slug[:48] or "action"


def _mode_label(mode: str) -> str:
    return {
        "ai_employee": "AI employee",
        "rules": "Rules",
        "hitl": "Human gate",
        "human_only": "Human owned",
    }.get(mode, mode.replace("_", " ").title())


def _truncate(value: str, max_length: int) -> str:
    return value if len(value) <= max_length else value[: max_length - 3].rstrip() + "..."


def blueprint_to_json(blueprint: AutonomyBlueprint) -> str:
    return json.dumps(blueprint.model_dump(), indent=2)
