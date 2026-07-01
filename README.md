<div align="center">

# Handoff

### The Deployment & Trust Layer for AI Employees

Compile messy SOPs into deterministic, auditable execution plans.

<p>
  <img src="https://img.shields.io/badge/Architecture-Neuro--Symbolic-blue?style=for-the-badge">
  <img src="https://img.shields.io/badge/Backend-FastAPI-green?style=for-the-badge">
  <img src="https://img.shields.io/badge/LLMs-LiteLLM-orange?style=for-the-badge">
  <img src="https://img.shields.io/badge/Frontend-Vanilla_JS-yellow?style=for-the-badge">
</p>

> **LLMs perceive. Deterministic systems decide.**

</div>

**The deployment & trust layer for AI Agents.** Handoff compiles
a messy finance SOP into a grounded, gated verdict on whether — and how far — the work
can be safely delegated to an AI employee.

The engine is **neuro-symbolic**: a language model perceives the process, and a
deterministic control plane verifies it — grounding every claim against the source,
escalating any irreversible step to a human gate, and compiling typed contracts. The
LLM proposes; the control plane disposes, so the verdict is reproducible and never
depends on model luck.

The pipeline in one line: **paste an SOP → perceive → ground & gate →
`AutonomyBlueprint` → dry-run ledger → signed audit export.**

## Highlights

- **Works with zero setup.** The default engine is the deterministic control plane — no
  API key, no model, instant and free. Three bundled finance processes are marked
  **Example** and run on it.
- **Model-agnostic, bring your own key.** Point compiles at any
  [LiteLLM](https://docs.litellm.ai/)-supported model (OpenAI, Anthropic, Gemini,
  Mistral, Groq, OpenRouter, a gateway, local Ollama). Keys entered in the UI live in the
  tab's `sessionStorage` and are **never stored or logged on the server**.
- **Stateless, no database.** Saved blueprints and the dry-run ledger persist per visitor
  in the browser (`localStorage`). No shared store, no accounts — so it deploys anywhere
  with no disk.
- **Per-step authority gating.** Every step is classified AI-owned, rules-based,
  human-gated (HITL), or human-only; high-risk or irreversible work is always escalated.
- **Typed control contracts** with idempotency keys, an **evals** pass, a deterministic
  **dry-run ledger**, and a **signed audit chain** you can export.

## Quick start

```bash
python3 -m pip install -r requirements.txt
python3 -m uvicorn app.main:app --reload --port 8010
# open http://127.0.0.1:8010
```

That runs the deterministic engine out of the box. To add the neural layer:

- **Local Ollama** — if it's running, Handoff auto-detects it and uses it. No key, no env.
- **Hosted provider** — copy the env template and set one model + its key:

  ```bash
  cp .env.example .env
  echo 'LITELLM_MODEL=openai/gpt-4o-mini' >> .env   # or anthropic/… , gemini/… , groq/…
  echo 'OPENAI_API_KEY=sk-...'            >> .env
  ```

## Configuration

All configuration is optional — Handoff falls back to the deterministic engine when no
model is set. Set one provider in `.env` (LiteLLM reads the key implied by the model
prefix):

| Variable | Purpose |
| --- | --- |
| `LITELLM_MODEL` | Model id, e.g. `openai/gpt-4o-mini`, `anthropic/claude-3-5-sonnet`, `ollama_chat/gemma3` |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` / `MISTRAL_API_KEY` / `GROQ_API_KEY` | Provider key for the chosen model |
| `OLLAMA_API_BASE` | Local Ollama endpoint (default `http://127.0.0.1:11434`); tune with `OLLAMA_TEMPERATURE`, `OLLAMA_TOP_P`, `OLLAMA_TOP_K`, `OLLAMA_NUM_CTX`, `OLLAMA_THINK` |
| `LITELLM_API_BASE` / `LITELLM_API_KEY` | Generic OpenAI-compatible gateway or LiteLLM proxy (set `LITELLM_PROVIDER=openai` for a plain endpoint) |

The UI model override always takes precedence over these, per request.

## Project structure

```
app/
  main.py           FastAPI app + API routes (/api/analyze, /simulate, /audit, /demos…)
  analyzer.py       Deterministic control plane — parses the SOP into steps & gaps
  verification.py   Symbolic layer — grounds claims to source, enforces gating policy
  llm.py            Optional LiteLLM wrapper (the neural perception layer)
  contracts.py      Typed control contracts + idempotency keys
  models.py         Pydantic data contracts (AutonomyBlueprint, responses)
  demo_data.py      Three bundled Example finance processes
  static/           Vanilla-JS single-page frontend (html, css, js)
tests/
  test_analyzer.py           Analyzer, autonomy modes, risk scoring
  test_verification.py       Grounding & reconciliation
  test_frontend_playwright.py  Browser smoke tests (skip cleanly without Playwright)
```

## Testing

```bash
python3 -m pip install -e ".[test]"      # pytest + Playwright extras
python3 -m pytest                         # backend + integration tests
python3 -m playwright install chromium    # once, for the frontend smoke test
```
## Scope

**In scope**

- Paste SOPs/policies (or open a bundled **Example**) → a validated `AutonomyBlueprint`.
- Identify gaps that block safe AI-employee ownership.
- Human checkpoints, typed control contracts, dry-run ledger, evals, signed audit export.
- Runs reliably with no external APIs (deterministic engine) or with any model you bring.

**Out of scope**

- Real ERP, email, or Slack integrations; running live actions.
- User accounts, server-side persistence, permissions, or multi-tenant auth
  (persistence is per-browser, by design).
- Long-running background workflows; multi-document reconciliation.
