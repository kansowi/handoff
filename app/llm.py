from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import re
import socket
import threading
import time
from urllib.parse import urlparse

import httpx
import litellm
from litellm import completion

from app.analyzer import analyze_locally, coerce_blueprint
from app.models import AutonomyBlueprint, ProcessInput

# Keep caller-supplied API keys out of LiteLLM's logs/telemetry. Keys arrive per request
# and are never persisted; this prevents them (and prompts) from leaking into stdout.
litellm.turn_off_message_logging = True
litellm.suppress_debug_info = True
# Drop params a given provider doesn't support (e.g. response_format on some models) instead
# of raising — this is what makes the BYO path genuinely model-agnostic across providers.
litellm.drop_params = True


DEFAULT_LITELLM_MODEL = "ollama_chat/gemma4:26b-mlx"
OLLAMA_PROVIDERS = {"ollama", "ollama_chat"}
_OLLAMA_PROBE_TTL_SECONDS = 30.0


class ApiBaseNotAllowed(ValueError):
    """A caller-supplied api_base points at a disallowed (internal) host."""
OLLAMA_DEFAULT_OPTIONS = {
    "temperature": 0,
    "top_p": 0.95,
    "top_k": 64,
    "num_ctx": 32768,
}


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


_ollama_probe_cache: dict = {"ts": -1e9, "models": None}


def _probe_ollama() -> list[str] | None:
    """Cached probe of a local Ollama: returns its model names, or None if unreachable.

    Short timeout so a deployed box (nothing on the port) fails instantly to None.
    """
    if os.getenv("HANDOFF_DISABLE_OLLAMA_AUTODETECT"):
        return None
    now = time.monotonic()
    if now - _ollama_probe_cache["ts"] < _OLLAMA_PROBE_TTL_SECONDS:
        return _ollama_probe_cache["models"]
    models: list[str] | None
    try:
        resp = httpx.get(f"{_ollama_api_base()}/api/tags", timeout=0.4)
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", []) if m.get("name")]
    except Exception:  # noqa: BLE001 - any failure just means "no local Ollama"
        models = None
    _ollama_probe_cache.update(ts=now, models=models)
    return models


def ollama_reachable() -> bool:
    """True when a local Ollama is up — enables zero-config local AI."""
    return _probe_ollama() is not None


def ollama_models() -> list[str]:
    """Installed local Ollama model names (empty when none/unreachable). Powers the catalog."""
    return list(_probe_ollama() or [])


def _auto_ollama_model() -> str | None:
    models = _probe_ollama()
    return f"ollama_chat/{models[0]}" if models else None


def default_server_model() -> str:
    """The model the server would use with no per-request override (env → Ollama → default)."""
    return os.getenv("LITELLM_MODEL") or _auto_ollama_model() or DEFAULT_LITELLM_MODEL


def resolve_model(request: ProcessInput) -> str:
    """Model for this request: caller-supplied → server env → auto local Ollama → default."""
    return request.model or default_server_model()


def ai_extraction_available(model: str, request_api_key: str | None, request_api_base: str | None = None) -> bool:
    """Whether an AI extraction can actually run, without dialing a dead endpoint.

    Enabled by a caller-supplied key, a concrete server-side provider key, or a reachable
    Ollama (request base, server env, or auto-detected) — never the keyless Ollama default
    on a deployed box, so a keyless server goes straight to the deterministic analyzer.
    """
    if request_api_key:
        return True
    if _has_explicit_provider_key(model):
        return True
    if _is_ollama_model(model) and (request_api_base or os.getenv("OLLAMA_API_BASE") or ollama_reachable()):
        return True
    return False


def _validate_api_base(api_base: str) -> None:
    """Block SSRF via a caller-supplied base URL: only http(s) to a public host.

    Resolves the host and rejects loopback/link-local/private/reserved addresses (e.g. cloud
    metadata at 169.254.169.254). Bypass for local gateways with HANDOFF_ALLOW_PRIVATE_API_BASE=1.
    """
    if os.getenv("HANDOFF_ALLOW_PRIVATE_API_BASE"):
        return
    parsed = urlparse(api_base)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ApiBaseNotAllowed("Base URL must be a full http(s) URL.")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except OSError as exc:
        raise ApiBaseNotAllowed("Base URL host could not be resolved.") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise ApiBaseNotAllowed("Base URL points at a disallowed internal address.")


def safe_failure_warning(exc: Exception) -> str:
    """A user-facing, key-free reason for an AI failure (classified by exception type)."""
    if isinstance(exc, ApiBaseNotAllowed):
        return f"{exc} Showing the deterministic analysis instead."
    if isinstance(exc, litellm.AuthenticationError):
        return "The model rejected the API key — check the key. Showing the deterministic analysis instead."
    if isinstance(exc, (litellm.NotFoundError, litellm.BadRequestError)):
        return "The model id or request was rejected — check the model id. Showing the deterministic analysis instead."
    if isinstance(exc, litellm.RateLimitError):
        return "The model is rate-limited right now. Showing the deterministic analysis instead."
    if isinstance(exc, (litellm.Timeout, asyncio.TimeoutError)):
        return "The model timed out. Showing the deterministic analysis instead."
    return "AI extraction failed — used the deterministic analyzer instead."


async def analyze_with_optional_ai(request: ProcessInput) -> AutonomyBlueprint:
    model = resolve_model(request)
    if not request.prefer_ai:
        return analyze_locally(request)

    if not ai_extraction_available(model, request.api_key, request.api_base):
        return analyze_locally(request)

    try:
        payload = await _call_litellm(request, model)
        return coerce_blueprint(payload, request, analyzer="litellm", analyzer_model=model)
    except Exception as exc:  # noqa: BLE001 - fallback is intentional for offline reliability
        return analyze_locally(
            request,
            analyzer="litellm_fallback",
            analyzer_model=model,
            warnings=[safe_failure_warning(exc)],
        )


async def _call_litellm(request: ProcessInput, model: str) -> dict:
    if request.api_base:
        _validate_api_base(request.api_base)  # SSRF guard before any outbound call
    timeout_seconds = float(os.getenv("LITELLM_TIMEOUT_SECONDS", "120"))
    sync_call = _call_ollama_chat_sync if _is_ollama_model(model) else _call_litellm_sync
    return await asyncio.wait_for(
        asyncio.to_thread(sync_call, request, model, timeout_seconds),
        timeout=timeout_seconds + 5,
    )


def _call_litellm_sync(request: ProcessInput, model: str, timeout_seconds: float) -> dict:
    messages = _messages_for_request(request)
    if request.api_key:
        return _call_litellm_byo_sync(request, model, messages, timeout_seconds)

    # Server default-key path: may run through the configured LiteLLM gateway/proxy.
    kwargs = _litellm_gateway_kwargs()
    if request.custom_llm_provider:
        kwargs["custom_llm_provider"] = request.custom_llm_provider
    response = completion(
        model=_effective_model(model),
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0,
        timeout=timeout_seconds,
        num_retries=0,  # fail fast: the deterministic analyzer is the safety net
        **kwargs,
    )
    return _extract_json(response["choices"][0]["message"]["content"])


# Provider base URLs LiteLLM reads from the environment. A bring-your-own-key call must not
# inherit any of these (or the server gateway) — the caller's key goes to the real provider.
_PROVIDER_BASE_ENV = (
    "OPENAI_API_BASE", "OPENAI_BASE_URL", "ANTHROPIC_API_BASE", "GEMINI_API_BASE",
    "GROQ_API_BASE", "MISTRAL_API_BASE", "DEEPSEEK_API_BASE", "OPENROUTER_API_BASE",
    "LITELLM_API_BASE", "LITELLM_PROXY_API_BASE",
)
_BYO_ENV_LOCK = threading.Lock()


def _call_litellm_byo_sync(request: ProcessInput, model: str, messages: list, timeout_seconds: float) -> dict:
    """A caller-supplied key call, fully isolated from server gateway/proxy + ambient base env.

    The key is sent to the provider's real endpoint (or a base URL the caller supplied) — never
    the server's configured gateway. Explicit `custom_llm_provider` routes deterministically;
    the no-slash+base heuristic is only a fallback for OpenAI-compatible gateways.
    """
    kwargs: dict[str, str] = {"api_key": request.api_key}
    if request.api_base:
        kwargs["api_base"] = request.api_base
    provider = request.custom_llm_provider or (
        "openai" if (request.api_base and "/" not in model) else None
    )
    if provider:
        kwargs["custom_llm_provider"] = provider

    # Suppress ambient provider-base env + the module-level gateway base for the duration of the
    # call so a pasted key resolves to the provider's canonical endpoint. Serialized across BYO
    # calls (acceptable at showcase concurrency).
    with _BYO_ENV_LOCK:
        saved_env = {name: os.environ.pop(name) for name in _PROVIDER_BASE_ENV if name in os.environ}
        saved_api_base = getattr(litellm, "api_base", None)
        litellm.api_base = None
        try:
            response = completion(
                model=model,  # BYO: never gateway-prefix the caller's model
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0,
                timeout=timeout_seconds,
                num_retries=0,
                **kwargs,
            )
        finally:
            os.environ.update(saved_env)
            litellm.api_base = saved_api_base
    return _extract_json(response["choices"][0]["message"]["content"])


def _call_ollama_chat_sync(request: ProcessInput, model: str, timeout_seconds: float) -> dict:
    api_base = (request.api_base or "").rstrip("/").removesuffix("/api") or _ollama_api_base()
    headers = {"Content-Type": "application/json"}
    api_key = os.getenv("OLLAMA_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    response = httpx.post(
        f"{api_base}/api/chat",
        json=_ollama_chat_payload(request, model),
        headers=headers,
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    content = response.json()["message"]["content"]
    return _extract_json(content)


def _messages_for_request(request: ProcessInput) -> list[dict[str, str]]:
    system_content = f"{SYSTEM_PROMPT}\n\nSCHEMA (field shape; obey the types and rules above):\n{json.dumps(JSON_SCHEMA_HINT, indent=2)}"
    user_content = (
        f"Process title: {request.title}\n"
        f"Domain: {request.domain}\n\n"
        "Compile the AutonomyBlueprint for the SOP below. Return only the JSON object.\n\n"
        f"<sop>\n{request.text}\n</sop>"
    )
    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]


def _ollama_chat_payload(request: ProcessInput, model: str) -> dict:
    return {
        "model": _ollama_model_name(model),
        "messages": _messages_for_request(request),
        "format": "json",
        "options": _ollama_options(),
        "stream": False,
        "think": _env_bool("OLLAMA_THINK", default=False),
    }


def _ollama_options() -> dict[str, int | float]:
    return {
        "temperature": _env_float("OLLAMA_TEMPERATURE", OLLAMA_DEFAULT_OPTIONS["temperature"]),
        "top_p": _env_float("OLLAMA_TOP_P", OLLAMA_DEFAULT_OPTIONS["top_p"]),
        "top_k": _env_int("OLLAMA_TOP_K", OLLAMA_DEFAULT_OPTIONS["top_k"]),
        "num_ctx": _env_int("OLLAMA_NUM_CTX", OLLAMA_DEFAULT_OPTIONS["num_ctx"]),
    }


def _extract_json(content: str) -> dict:
    """Parse a JSON object from a model response, tolerating code fences or stray prose."""
    text = (content or "")
    # Reasoning models emit <think>…</think> first; strip it so its braces don't poison
    # the brace-substring fallback below.
    text = re.sub(r"<(think|reasoning)>.*?</\1>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()
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


PROVIDER_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "vertex_ai": "GOOGLE_APPLICATION_CREDENTIALS",
    "mistral": "MISTRAL_API_KEY",
    "cohere": "COHERE_API_KEY",
    "groq": "GROQ_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "azure": "AZURE_API_KEY",
    "ollama": None,
    "ollama_chat": None,
    "openai": "OPENAI_API_KEY",
}


def _has_litellm_provider_key(model: str) -> bool:
    if os.getenv("LITELLM_API_KEY") or os.getenv("LITELLM_PROXY_API_KEY"):
        return True
    env_key = PROVIDER_KEY_ENV.get(_provider_prefix(model), "OPENAI_API_KEY")
    return env_key is None or bool(os.getenv(env_key))


def _has_explicit_provider_key(model: str) -> bool:
    """A concrete server-side key is configured (keyless Ollama returns False)."""
    if os.getenv("LITELLM_API_KEY") or os.getenv("LITELLM_PROXY_API_KEY"):
        return True
    env_key = PROVIDER_KEY_ENV.get(_provider_prefix(model), "OPENAI_API_KEY")
    return bool(env_key) and bool(os.getenv(env_key))


def _effective_model(model: str) -> str:
    if "/" in model or not os.getenv("LITELLM_API_BASE"):
        return model
    provider = os.getenv("LITELLM_PROVIDER", "litellm_proxy").strip("/")
    return f"{provider}/{model}"


def _is_ollama_model(model: str) -> bool:
    return _provider_prefix(model) in OLLAMA_PROVIDERS


def _provider_prefix(model: str) -> str:
    if "/" in model:
        return model.split("/", 1)[0].lower()
    provider = os.getenv("LITELLM_PROVIDER", "").strip("/").lower()
    return provider if provider in OLLAMA_PROVIDERS else "openai"


def _ollama_model_name(model: str) -> str:
    return model.split("/", 1)[1] if "/" in model and _is_ollama_model(model) else model


def _ollama_api_base() -> str:
    api_base = os.getenv("OLLAMA_API_BASE") or "http://127.0.0.1:11434"
    return api_base.rstrip("/").removesuffix("/api")


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: int | float) -> float:
    value = os.getenv(name)
    return float(value) if value is not None else float(default)


def _env_int(name: str, default: int | float) -> int:
    value = os.getenv(name)
    return int(value) if value is not None else int(default)


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
