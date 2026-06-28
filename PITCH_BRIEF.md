# Handoff — Pitch Brief & Delivery Plan

## Product concept (one sentence)

**Handoff is the deployment & trust layer of the Zamp AI-employee platform — it
compiles a messy finance SOP into a grounded, gated verdict on whether (and how
far) the work can be safely delegated to an AI employee.**

The 30-second "aha" is a verdict-first card that leads with **refusal**:
*DO NOT DELEGATE UNGATED* — then shows exactly which steps the AI employee can
own, which must stop at a human gate, and which are blocked by policy debt.

## Why this fits Zamp

Zamp builds *AI employees you delegate whole jobs to* — autonomous inside
enterprise guardrails, escalating at human gates, leaving evidence for every
decision. The unanswered question before any of that is: *can this process be
trusted to an AI employee yet?* Dashboards show the queue, RPA clicks the happy
path, chatbots summarize the SOP — none decide **authority**. Handoff does, and
it does it conservatively, which is the opposite of a "GPT wrapper saying yes."

## The technical engine — neuro-symbolic (the 10x)

The product is deliberately **neuro-symbolic**: the LLM proposes, a deterministic
control plane disposes.

1. **Perceive / Extract (neural).** An LLM (configurable via a LiteLLM gateway —
   `glm-latest` / `claude-opus-4-6`) turns an unstructured SOP into a structured
   process graph: steps, actors, systems, decision branches, risk, reversibility.
2. **Ground / verify (symbolic — `app/verification.py`).** Every extracted claim
   must cite evidence that actually occurs in the source. Ungrounded claims are
   quarantined and a **faithfulness score** is reported (hallucination guard).
3. **Reconcile (neuro-symbolic).** The control plane independently enforces the
   invariant *no irreversible or high-risk step may run unattended* — where the
   model under-gates, it escalates to a human gate and logs the divergence.
4. **Compile.** Typed control contracts with SHA-256 idempotency keys + HITL gates.
5. **Evaluate.** Span-level + trace-level evals, including grounding and
   reconciliation checks.
6. **Persist + audit.** A signed evidence chain: source hash → contract keys →
   run events → evals → runtime attestation.

**The 10x:** a controller's "is this safe to automate?" call goes from days of
subjective SOP-reading to a seconds-long, reproducible, evidence-grounded verdict
with per-step authority, dry-run proof, and an audit trail — and it scales across
the whole process portfolio. Critically, the verdict is **deterministic**: it
never depends on model luck, and degrades gracefully to the deterministic engine
if the model is slow or offline.

## Demo surfaces

UI language is **Modern Fintech (Ramp/Mercury)** — warm, soft, rounded — shipping in
**both light and dark themes** (defaults to the system preference, with a remembered
toggle). Three coherent modules: **Processes · Run Ledger · Trust Center**.

- **Roster** — finance processes kept *separate*, each a card with a line-icon tile,
  status, readiness, a segmented authority bar, and a portfolio summary strip.
- **Trust Center** — portfolio-level posture (avg readiness, evidence grounded,
  AI-owned vs. human-needed steps) + a per-process trust table.
- **Run Ledger** — replayable record of every dry-run executed in the session.
- **Deployment dossier** — verdict hero + animated readiness gauge + authority
  split; an authority map (green AI-owned / amber gated / red blocked); a step
  inspector with source evidence; engine toggle (Deterministic ⇄ model extraction)
  and faithfulness chips; tabs for Runbook, Contracts, Dry-run ledger, Evals,
  Audit, and Learning.

Functional: extraction (deterministic + optional model), grounding,
reconciliation, contracts, streamed dry-run, evals, audit export, persistence.
Mocked (by design, stated on screen): no live ERP / email / bank calls.

## Verified build

- `python3 -m pytest` → **30 passed** (22 analyzer/API, 6 verification incl. the
  full neuro-symbolic router path mocked, 2 Playwright incl. a browser smoke that
  walks roster → verdict → ledger → audit and asserts zero horizontal overflow at
  1440/1120/720/390 px).
- Live walkthrough verified via Playwright: dossier opens in ~150 ms, dry-run
  streams 26 events, audit chain renders real hashes, 390 px mobile has zero
  page-level horizontal overflow.

## Known limitations

- Dry-run only; no real ERP/email/bank integrations (by design, shown on screen).
- Grounding is lexical (quote-in-source), not semantic entailment — v1 trust signal.
- Single-document analysis; no multi-tenant auth.
- The hosted LLM gateway is latency-variable; the demo defaults to the
  deterministic engine for reliability and exposes the model as an explicit toggle.

---

## Final 3-minute pitch script (word-for-word)

> **[0:00 — Hook · roster on screen]**
> Enterprise finance doesn't run on clean workflows. It runs on exceptions —
> invoices over a threshold, a vendor's bank details that changed, a missing PO.
> Before any of this gets automated, a controller has to answer one question:
> *can I safely hand this to an AI employee?* Today that's days of reading SOPs and
> a gut call.

> **[0:25 — Stakes · hover the three cards]**
> A dashboard shows the queue. RPA clicks the happy path. A chatbot summarizes the
> SOP. None of them answer that question — because none of them decide *authority*.

> **[0:45 — Reveal + aha · open Invoice Exceptions]**
> So I built Handoff — the deployment and trust layer for Zamp's AI employees.
> Watch. *(verdict stamps in)* It doesn't say "yes, I can automate invoices." It
> says **do not delegate ungated** — readiness 65, and here's exactly why: four
> steps the AI employee can own, one that stops at a human gate, and three frozen
> by policy debt.

> **[1:15 — Authority vs gates · click the bank-detail step]**
> This is the money moment. The changed-bank-detail step is *blocked* — irreversible,
> and the SOP itself has no confirmation policy or audit note. The control plane
> refuses to let an AI employee touch it silently, and it shows the exact source
> quote it's reasoning from.

> **[1:45 — Dry-run · click Run dry-run]**
> Now a dry-run. No ERP, no email, no bank is touched. The employee plans, executes
> the safe work, stops at the human gate, and blocks on policy debt — every event
> signed with a sequence, actor, decision, and source evidence, streaming like a
> trading tape.

> **[2:15 — The engine · flash chips + audit tab]**
> Under the hood it's neuro-symbolic. A frontier model perceives the messy process;
> a deterministic control plane grounds every claim against the source — 94% here —
> re-derives the risk, escalates anything irreversible, and compiles typed contracts
> with cryptographic idempotency keys. The audit tab isn't a chat transcript; it's a
> signed evidence chain you can reproduce bit-for-bit. The LLM proposes; the control
> plane disposes — so the verdict never depends on model luck.

> **[2:45 — Close · back to roster]**
> Autonomous companies won't be built by chatting with dashboards. They'll be built
> by hiring AI employees into explicit jobs — with authority, gates, and proof.
> That's Handoff.

**Tone:** founder to a peer. Crisp, outcome-led, unbothered. Let the verdict
stamp-in and the bank-detail block breathe — those are the two beats that land.

## Recording / delivery notes

- 1920×1080, dark room, large UI scale, calm cursor.
- Pre-open the app on the roster; the deterministic engine makes every transition
  instant, so there is **no waiting** on camera.
- Optional flourish: after the verdict lands, toggle to the model extraction once
  to show the neural layer + faithfulness score, then continue. Keep it short; the
  deterministic path is the reliable spine.
- The two signature shots: the verdict **stamp-in** (~0:48) and the bank-detail
  step rendering **red/blocked** with its evidence (~1:20).
