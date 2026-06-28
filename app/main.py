from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from app.contracts import build_contracts, summarize_contracts
from app.demo_data import DEMOS, get_demo
from app.handoff_packet import build_handoff_packet
from app.model_runtime import ModelRouter
from app.models import (
    AnalyzeResponse,
    BlueprintRecord,
    CompileTraceStep,
    DemoProcess,
    ProcessInput,
    RunRecord,
    RuntimeCapabilities,
    SimulationResponse,
    TEXT_MAX_LENGTH,
    TEXT_MIN_LENGTH,
)
from app.repository import HandoffRepository
from app.simulation import simulate_blueprint


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
repository = HandoffRepository()
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
    for error in exc.errors():
        field = ".".join(str(part) for part in error.get("loc", []) if part != "body") or "input"
        messages.append(f"{field}: {error.get('msg', 'invalid value')}")
    detail = "Input validation failed — " + "; ".join(messages)
    return JSONResponse(status_code=422, content={"detail": detail, "errors": exc.errors()})


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
    return model_router.capabilities(repository.db_path)


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
    blueprint = await model_router.analyze(request)
    contracts = build_contracts(blueprint)
    control_summary = summarize_contracts(blueprint, contracts)
    handoff_packet = build_handoff_packet(blueprint, contracts, control_summary)
    compile_trace = _compile_trace(blueprint, len(contracts))
    blueprint_id = repository.save_blueprint(
        source_text=request.text,
        blueprint=blueprint,
        contracts=contracts,
        compile_trace=compile_trace,
        control_summary=control_summary,
    )
    return AnalyzeResponse(
        blueprint=blueprint,
        character_count=len(request.text),
        character_limit=TEXT_MAX_LENGTH,
        minimum_characters=TEXT_MIN_LENGTH,
        blueprint_id=blueprint_id,
        control_summary=control_summary,
        compile_trace=compile_trace,
        handoff_packet=handoff_packet,
    )


@app.post("/analyze", response_model=AnalyzeResponse, include_in_schema=False)
async def analyze_alias(request: ProcessInput) -> AnalyzeResponse:
    return await analyze(request)


@app.get("/api/blueprints/{blueprint_id}", response_model=BlueprintRecord)
async def blueprint(blueprint_id: str) -> BlueprintRecord:
    found = repository.get_blueprint(blueprint_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Blueprint not found")
    return found


@app.post("/api/blueprints/{blueprint_id}/simulate", response_model=SimulationResponse)
async def simulate(blueprint_id: str) -> SimulationResponse:
    found = repository.get_blueprint(blueprint_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Blueprint not found")
    simulation = simulate_blueprint(
        blueprint_id=blueprint_id,
        blueprint=found.blueprint,
        contracts=found.contracts,
        source_hash=found.source_hash,
    )
    repository.save_run(simulation)
    return simulation


@app.get("/api/runs/{run_id}", response_model=RunRecord)
async def run(run_id: str) -> RunRecord:
    found = repository.get_run(run_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return found


@app.get("/api/runs/{run_id}/audit")
async def audit(run_id: str):
    export = repository.build_audit_export(
        run_id,
        runtime_metadata=model_router.capabilities(repository.db_path).model_dump(mode="json"),
    )
    if export is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return export


def _compile_trace(blueprint, contract_count: int) -> list[CompileTraceStep]:
    return [
        CompileTraceStep(name="Normalize", detail="Source text normalized and bounded before analysis."),
        CompileTraceStep(name="Extract", detail=f"Extracted {len(blueprint.steps)} source-backed process steps."),
        CompileTraceStep(name="Validate", detail=f"Validated blueprint with {len(blueprint.gaps)} unresolved gaps."),
        CompileTraceStep(name="Contract", detail=f"Generated {contract_count} deterministic control contracts."),
        CompileTraceStep(name="Persist", detail="Stored blueprint, contracts, and trace in the local audit store."),
    ]
