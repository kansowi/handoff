import os

# The app is stateless — there is no database to isolate. Keep the suite hermetic and
# offline instead: skip loading the developer's local .env and blank any provider keys so
# importing app.main can never trigger a real model call. Tests that exercise the AI path
# monkeypatch the LLM call explicitly. This runs before any test imports app.main.
os.environ["HANDOFF_SKIP_DOTENV"] = "1"
# Keep the suite independent of whether the dev machine happens to run a local Ollama.
os.environ["HANDOFF_DISABLE_OLLAMA_AUTODETECT"] = "1"
for _var in (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_API_BASE",
    "GEMINI_API_KEY",
    "MISTRAL_API_KEY",
    "GROQ_API_KEY",
    "OPENROUTER_API_KEY",
    "LITELLM_API_KEY",
    "LITELLM_PROXY_API_KEY",
    "LITELLM_API_BASE",
    "LITELLM_MODEL",
    "OLLAMA_API_BASE",
):
    os.environ[_var] = ""
