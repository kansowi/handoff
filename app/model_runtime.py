from __future__ import annotations

import os
from typing import Protocol

from app.analyzer import analyze_locally, coerce_blueprint
from app.llm import _call_litellm, _has_litellm_provider_key
from app.models import AutonomyBlueprint, ProcessInput, RuntimeCapabilities, RuntimeMode
from app.verification import verify_blueprint


class ModelClient(Protocol):
    async def analyze(self, request: ProcessInput) -> AutonomyBlueprint:
        ...


class LocalModelClient:
    async def analyze(self, request: ProcessInput) -> AutonomyBlueprint:
        return analyze_locally(request)


class LiteLLMModelClient:
    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.getenv("LITELLM_MODEL", "gpt-4o-mini")

    async def analyze(self, request: ProcessInput) -> AutonomyBlueprint:
        payload = await _call_litellm(request, self.model)
        return coerce_blueprint(payload, request, analyzer="litellm", analyzer_model=self.model)


class ModelRouter:
    def __init__(self) -> None:
        self.local = LocalModelClient()
        self.model_name = os.getenv("LITELLM_MODEL", "gpt-4o-mini")
        self.litellm = LiteLLMModelClient(self.model_name)

    async def analyze(self, request: ProcessInput) -> AutonomyBlueprint:
        """Run the neuro-symbolic pipeline: neural extraction then symbolic verification."""
        blueprint = await self._extract(request)
        return verify_blueprint(blueprint, request.text)

    async def _extract(self, request: ProcessInput) -> AutonomyBlueprint:
        mode = self._mode(request)
        if mode == "local":
            return await self.local.analyze(request)

        if not _has_litellm_provider_key(self.model_name):
            warning = f"LiteLLM provider key not configured for {self.model_name}; used deterministic local analyzer."
            return analyze_locally(request, warnings=[warning])

        try:
            return await self.litellm.analyze(request)
        except Exception as exc:  # noqa: BLE001 - fallback is the production-shaped safety behavior
            warning = f"AI extraction failed: {str(exc)} — falling back to local analyzer."
            return analyze_locally(request, analyzer="litellm_fallback", analyzer_model=self.model_name, warnings=[warning])

    def capabilities(self, db_path: str) -> RuntimeCapabilities:
        return RuntimeCapabilities(
            local_analyzer_available=True,
            litellm_configured=_has_litellm_provider_key(self.model_name),
            storage_enabled=True,
            model_name=self.model_name,
            runtime_mode="auto",
            database_path=db_path,
        )

    @staticmethod
    def _mode(request: ProcessInput) -> RuntimeMode:
        if request.runtime_mode:
            return request.runtime_mode
        return "auto" if request.prefer_ai else "local"
