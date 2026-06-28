# Handoff

Handoff is the **deployment & trust layer of the Zamp AI-employee platform**. It
compiles a messy finance SOP into a grounded, gated verdict on whether — and how
far — the work can be safely delegated to an AI employee: per-step authority
(AI-owned vs. human-gated vs. blocked), control contracts with idempotency keys,
a dry-run execution ledger, evals, and a signed audit chain.

The engine is **neuro-symbolic**: a language model perceives the process, and a
deterministic control plane (`app/analyzer.py` + `app/verification.py`) verifies
it — grounding every claim against the source, escalating any irreversible step to
a human gate, and compiling typed contracts. The LLM proposes; the control plane
disposes, so the verdict is reproducible and never depends on model luck.

The app is fully useful without credentials: the deterministic engine and three
bundled finance processes run instantly offline. When `prefer_ai` is enabled (or
the dossier's model-extraction toggle is used), the backend attempts a LiteLLM
analysis via `LITELLM_MODEL` and safely falls back to the deterministic engine if
the call is slow or fails.

## LiteLLM Setup

LiteLLM lets the same code call OpenAI, Anthropic, Gemini, Mistral, Groq,
OpenRouter, local Ollama, and other providers. Set `LITELLM_MODEL` to choose the
provider/model. LiteLLM reads the provider key implied by that model prefix.

```bash
cp .env.example .env
export LITELLM_MODEL="gpt-4o-mini"
export OPENAI_API_KEY="..."
```

Example model values:

```bash
LITELLM_MODEL="gpt-4o-mini"                    # OpenAI, uses OPENAI_API_KEY
LITELLM_MODEL="anthropic/claude-3-5-sonnet"    # Anthropic, uses ANTHROPIC_API_KEY
LITELLM_MODEL="gemini/gemini-1.5-flash"        # Gemini, uses GEMINI_API_KEY
LITELLM_MODEL="mistral/mistral-large-latest"   # Mistral, uses MISTRAL_API_KEY
LITELLM_MODEL="groq/llama-3.1-70b-versatile"   # Groq, uses GROQ_API_KEY
LITELLM_MODEL="ollama/llama3.1"                # Local Ollama
```

If no matching provider key is configured, Handoff uses the deterministic
local analyzer and shows a visible warning in the UI.

For a LiteLLM Proxy/Gateway, set the generic gateway variables:

```bash
export LITELLM_API_BASE="https://your-gateway.example.com"
export LITELLM_API_KEY="..."
export LITELLM_MODEL="claude-opus-4-6"
export LITELLM_TIMEOUT_SECONDS="120"
```

When `LITELLM_API_BASE` is set and the model has no provider prefix,
Handoff defaults to LiteLLM's gateway route: `litellm_proxy/<model>`. To call a
plain OpenAI-compatible endpoint instead, set:

```bash
export LITELLM_PROVIDER="openai"
```

## Run

```bash
python3 -m pip install -r requirements.txt
python3 -m uvicorn app.main:app --reload --port 8010
```

Then open http://127.0.0.1:8010 and pick a process from the roster.

## Scope

In scope:

- Paste SOPs, policies, or example cases.
- Generate a validated `AutonomyBlueprint`.
- Identify gaps that block safe AI-employee ownership.
- Produce human checkpoints and action stubs.
- Run reliably without external APIs.

Out of scope:

- Real ERP, email, or Slack integrations.
- User accounts, persistence, permissions, or multi-tenant auth.
- Running live actions.
- Long-running background workflows.
- Multi-document reconciliation.
