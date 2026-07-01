from __future__ import annotations

from typing import Protocol

from app.analyzer import analyze_locally, coerce_blueprint
from app.llm import (
    _call_litellm,
    _has_explicit_provider_key,
    ai_extraction_available,
    default_server_model,
    ollama_reachable,
    resolve_model,
    safe_failure_warning,
)
from app.models import AutonomyBlueprint, ProcessInput, RuntimeCapabilities, RuntimeMode
from app.verification import verify_blueprint


class ModelClient(Protocol):
    async def analyze(self, request: ProcessInput) -> AutonomyBlueprint:
        ...


class LocalModelClient:
    async def analyze(self, request: ProcessInput) -> AutonomyBlueprint:
        return analyze_locally(request)


class ModelRouter:
    def __init__(self) -> None:
        self.local = LocalModelClient()

    async def analyze(self, request: ProcessInput) -> AutonomyBlueprint:
        """Run the neuro-symbolic pipeline: neural extraction then symbolic verification."""
        blueprint = await self._extract(request)
        return verify_blueprint(blueprint, request.text)

    async def _extract(self, request: ProcessInput) -> AutonomyBlueprint:
        if self._mode(request) == "local":
            return await self.local.analyze(request)

        model = resolve_model(request)
        if not ai_extraction_available(model, request.api_key, request.api_base):
            # No usable key/endpoint — go straight to the deterministic analyzer (no network call).
            return await self.local.analyze(request)

        try:
            payload = await _call_litellm(request, model)
            return coerce_blueprint(payload, request, analyzer="litellm", analyzer_model=model)
        except Exception as exc:  # noqa: BLE001 - fallback is the production-shaped safety behavior
            return analyze_locally(
                request,
                analyzer="litellm_fallback",
                analyzer_model=model,
                warnings=[safe_failure_warning(exc)],
            )

    def capabilities(self) -> RuntimeCapabilities:
        model = default_server_model()
        return RuntimeCapabilities(
            local_analyzer_available=True,
            litellm_configured=_has_explicit_provider_key(model) or ollama_reachable(),
            model_name=model,
            runtime_mode="auto",
        )

    @staticmethod
    def _mode(request: ProcessInput) -> RuntimeMode:
        if request.runtime_mode:
            return request.runtime_mode
        return "auto" if request.prefer_ai else "local"
