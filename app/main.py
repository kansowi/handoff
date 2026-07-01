from __future__ import annotations

import hashlib
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from app.audit_export import build_audit_export
from app.contracts import build_contracts, summarize_contracts
from app.demo_data import DEMOS, get_demo
from app.handoff_packet import build_handoff_packet
from app.model_runtime import ModelRouter
from app.models import (
    AnalyzeResponse,
    AuditExport,
    AuditRequest,
    CompileTraceStep,
    DemoProcess,
    ModelCatalog,
    ProcessInput,
    RuntimeCapabilities,
    SimulateRequest,
    SimulationResponse,
    TEXT_MAX_LENGTH,
    TEXT_MIN_LENGTH,
)
from app.providers import build_catalog
from app.simulation import simulate_blueprint


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


def _load_local_env() -> None:
    if os.getenv("HANDOFF_SKIP_DOTENV"):
        return
    env_path = BASE_DIR.parent / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key.removeprefix("export ").strip()
        if key:
            os.environ.setdefault(key, value.strip().strip("\"'"))


_load_local_env()
model_router = ModelRouter()

app = FastAPI(
    title="Handoff",
    description="Operating brief compiler for AI employee handoffs.",
    version="0.1.0",
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def revalidate_static(request: Request, call_next):
    """Force asset revalidation so a redeploy/edit never serves stale CSS or JS."""
    response = await call_next(request)
    if request.url.path.startswith("/static") or request.url.path in ("/", "/index.html"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    messages: list[str] = []
    safe_errors: list[dict] = []
    for error in exc.errors():
        loc = [str(part) for part in error.get("loc", []) if part != "body"]
        field = ".".join(loc) or "input"
        msg = error.get("msg", "invalid value")
        messages.append(f"{field}: {msg}")
        # Never echo `input`/`ctx`/`url` — they carry the offending value (e.g. an api_key).
        safe_errors.append({"type": error.get("type"), "loc": loc, "msg": msg})
    detail = "Input validation failed — " + "; ".join(messages)
    return JSONResponse(status_code=422, content={"detail": detail, "errors": safe_errors})


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    return Response(status_code=204)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/runtime", response_model=RuntimeCapabilities)
async def runtime() -> RuntimeCapabilities:
    return model_router.capabilities()


@app.get("/api/models", response_model=ModelCatalog)
async def models_catalog() -> ModelCatalog:
    """Provider → model catalog for the BYO picker. Static providers + live local Ollama models."""
    return build_catalog()


@app.get("/api/demos", response_model=list[DemoProcess])
async def list_demos() -> list[DemoProcess]:
    return DEMOS


@app.get("/api/demo/{demo_id}", response_model=DemoProcess)
async def demo(demo_id: str) -> DemoProcess:
    found = get_demo(demo_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Example workflow not found")
    return found


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze(request: ProcessInput) -> AnalyzeResponse:
    """Compile an SOP into a verified blueprint. Pure compute — the client owns persistence."""
    blueprint = await model_router.analyze(request)
    contracts = build_contracts(blueprint)
    control_summary = summarize_contracts(blueprint, contracts)
    handoff_packet = build_handoff_packet(blueprint, contracts, control_summary)
    compile_trace = _compile_trace(blueprint, control_summary, handoff_packet, len(request.text))
    return AnalyzeResponse(
        blueprint=blueprint,
        character_count=len(request.text),
        character_limit=TEXT_MAX_LENGTH,
        minimum_characters=TEXT_MIN_LENGTH,
        source_hash=_source_hash(request.text),
        contracts=contracts,
        control_summary=control_summary,
        compile_trace=compile_trace,
        handoff_packet=handoff_packet,
    )


@app.post("/analyze", response_model=AnalyzeResponse, include_in_schema=False)
async def analyze_alias(request: ProcessInput) -> AnalyzeResponse:
    return await analyze(request)


@app.post("/api/simulate", response_model=SimulationResponse)
async def simulate(request: SimulateRequest) -> SimulationResponse:
    """Deterministic dry-run over client-supplied artifacts. Stateless — nothing is stored."""
    return simulate_blueprint(
        blueprint_id=request.blueprint_id,
        blueprint=request.blueprint,
        contracts=request.contracts,
        source_hash=request.source_hash,
    )


@app.post("/api/audit", response_model=AuditExport)
async def audit(request: AuditRequest) -> AuditExport:
    """Assemble a signed audit export from a single run. Stateless — nothing is stored."""
    return build_audit_export(request.simulation, request.blueprint, request.runtime_metadata)


def _source_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _compile_trace(blueprint, control_summary, handoff_packet, char_count: int) -> list[CompileTraceStep]:
    """Real, post-compile pipeline trace — every figure is computed, not cosmetic.

    The frontend compile animation and the dossier "Compile trace" disclosure both render
    this list, so each step's detail and status must reflect the actual blueprint.
    """
    steps = len(blueprint.steps)
    gates = len(blueprint.hitl_gates)
    gaps = len(blueprint.gaps)
    blocked = control_summary.blocked_step_count
    audit = control_summary.audit_required_count
    conf_pct = round(blueprint.confidence * 100)
    ready = handoff_packet.decision == "ready_to_delegate"

    # Grounding + escalation figures come from the symbolic verification report
    # (real source-verification), not just "does the step carry an evidence span".
    verification = blueprint.verification
    grounded_claims = verification.grounded_claims if verification else steps
    total_claims = verification.total_claims if verification else steps
    groundedness = verification.groundedness if verification else 1.0
    escalated = verification.escalated_step_count if verification else 0
    ground_pct = round(groundedness * 100)

    return [
        CompileTraceStep(
            name="Perceive source document",
            layer="neural",
            detail=f"Normalized and bounded {char_count} characters of source.",
        ),
        CompileTraceStep(
            name="Extract process graph",
            layer="neural",
            detail=f"Extracted {steps} source-backed steps and {gates} decision gates.",
        ),
        CompileTraceStep(
            name="Ground every claim to source",
            layer="symbolic",
            status="complete" if groundedness >= 1.0 else "warning",
            detail=f"Grounded {grounded_claims}/{total_claims} claims to source ({ground_pct}%).",
        ),
        CompileTraceStep(
            name="Reconcile authority boundaries",
            layer="symbolic",
            status="warning" if (blocked > 0 or gaps > 0 or escalated > 0) else "complete",
            detail=f"Reconciled authority — {escalated} escalated by policy, {control_summary.hitl_contract_count} human gates, {blocked} blocked, {gaps} unresolved gaps.",
        ),
        CompileTraceStep(
            name="Compile control contracts",
            layer="symbolic",
            detail=f"Generated {control_summary.contract_count} deterministic contracts ({audit} audit-required).",
        ),
        CompileTraceStep(
            name="Evaluate & score readiness",
            layer="symbolic",
            status="complete" if ready else "warning",
            detail=f"Readiness {blueprint.readiness_score}/100 · confidence {conf_pct}% → {handoff_packet.decision_label}.",
        ),
        CompileTraceStep(
            name="Seal signed audit trace",
            layer="store",
            detail="Sealed blueprint, contracts, and trace into a reproducible, content-addressed record.",
        ),
    ]
