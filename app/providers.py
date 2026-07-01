from __future__ import annotations

from app.llm import ollama_models
from app.models import ModelCatalog, Provider, ProviderModel


def _m(model_id: str, label: str | None = None) -> ProviderModel:
    return ProviderModel(id=model_id, label=label or model_id)


# Static, curated provider registry. The final LiteLLM model id is
# f"{prefix}/{model_id}" (or the bare id when prefix is empty). Every provider allows a
# "Custom…" id so a new/rare model stays reachable without a code change.
PROVIDERS: list[Provider] = [
    Provider(
        id="openai",
        label="OpenAI",
        prefix="openai",
        key_label="OpenAI API key",
        key_placeholder="sk-…",
        models=[_m("gpt-4o-mini"), _m("gpt-4o"), _m("gpt-4.1-mini"), _m("gpt-4.1"), _m("o3-mini")],
    ),
    Provider(
        id="anthropic",
        label="Anthropic",
        prefix="anthropic",
        key_label="Anthropic API key",
        key_placeholder="sk-ant-…",
        models=[_m("claude-opus-4-8"), _m("claude-sonnet-4-6"), _m("claude-haiku-4-5")],
    ),
    Provider(
        id="gemini",
        label="Google Gemini",
        prefix="gemini",
        key_label="Google AI Studio key",
        key_placeholder="AIza…",
        models=[_m("gemini-2.5-flash"), _m("gemini-2.5-pro"), _m("gemini-2.0-flash")],
    ),
    Provider(
        id="groq",
        label="Groq",
        prefix="groq",
        key_label="Groq API key",
        key_placeholder="gsk_…",
        models=[_m("llama-3.3-70b-versatile"), _m("llama-3.1-8b-instant")],
    ),
    Provider(
        id="deepseek",
        label="DeepSeek",
        prefix="deepseek",
        key_label="DeepSeek API key",
        key_placeholder="sk-…",
        models=[_m("deepseek-chat"), _m("deepseek-reasoner")],
    ),
    Provider(
        id="mistral",
        label="Mistral",
        prefix="mistral",
        key_label="Mistral API key",
        key_placeholder="…",
        models=[_m("mistral-large-latest"), _m("mistral-small-latest")],
    ),
    Provider(
        id="openrouter",
        label="OpenRouter",
        prefix="openrouter",
        key_label="OpenRouter API key",
        key_placeholder="sk-or-…",
        models=[
            _m("openai/gpt-4o-mini"),
            _m("anthropic/claude-3.5-sonnet"),
            _m("google/gemini-2.0-flash"),
        ],
    ),
    Provider(
        id="openai_compatible",
        label="OpenAI-compatible",
        prefix="",
        needs_base=True,
        key_label="API key",
        key_placeholder="sk-…",
        models=[],  # custom id + base URL only
    ),
    Provider(
        id="ollama",
        label="Ollama (local)",
        prefix="ollama_chat",
        keyless=True,
        needs_base=True,
        key_placeholder="(no key)",
        models=[],  # filled live from the local Ollama probe
    ),
]


def build_catalog() -> ModelCatalog:
    """Static providers, with the Ollama entry filled from a live local probe."""
    providers: list[Provider] = []
    for provider in PROVIDERS:
        if provider.id == "ollama":
            names = ollama_models()
            provider = provider.model_copy(update={"models": [_m(name) for name in names]})
        providers.append(provider)
    return ModelCatalog(providers=providers)
