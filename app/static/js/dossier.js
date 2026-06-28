// Deployment dossier: verdict hero, authority map, inspector, runbook, contracts.

import {
  $, $all, esc, titleize, pct, ICON, autonomyClass, autonomyLabel,
  decisionMeta, authoritySplit, engineLabel, prettyModel,
} from "./util.js";

const GAUGE_R = 74;
const GAUGE_C = 2 * Math.PI * GAUGE_R;

export function renderDossier(ctx) {
  const bp = ctx.record.blueprint;
  const packet = ctx.record.handoff_packet;
  const split = authoritySplit(bp);
  const meta = decisionMeta(packet.decision);
  const v = bp.verification || { groundedness: 1, escalated_step_count: 0, ungrounded_claims: [] };

  const warnings = (bp.warnings || []).filter(Boolean);
  const warningHtml = warnings.length
    ? `<div class="banner">${ICON.shield}<div>${warnings.map(esc).join("<br/>")}</div></div>`
    : "";

  const html = `
  <div class="dossier">
    <div class="crumb fade-up">
      <a data-action="home" href="#/">${ICON.back} All processes</a>
      <span style="color:var(--ink-faint)">/</span>
      <span class="mono" style="color:var(--ink-soft);font-size:12.5px">${esc(bp.title)}</span>
    </div>

    ${warningHtml}

    <section class="verdict fade-up" data-decision="${esc(packet.decision)}">
      <div class="verdict__grid">
        <div>
          <div class="verdict__eyebrow">
            <span class="eyebrow">${esc(meta.kicker)}</span>
            <span class="pill pill--${meta.kind}"><span class="dot"></span>${esc(packet.decision_label)}</span>
          </div>
          <h1 class="verdict__word stamp">${esc(meta.word)}</h1>
          <p class="verdict__pitch">${esc(verdictPitch(packet.decision, split))}</p>
          <div class="verdict__chips">
            <span class="pill pill--brand"><span class="dot"></span>${ICON.bot} ${esc(engineLabel(bp))}</span>
            <span class="pill ${v.groundedness >= 0.9 ? "pill--ai" : "pill--gate"}"><span class="dot"></span>Grounded ${pct(v.groundedness)}</span>
            <span class="pill pill--muted">${ICON.shield} ${v.escalated_step_count} policy escalation${v.escalated_step_count === 1 ? "" : "s"}</span>
            <span class="pill pill--muted">${ICON.bot} Confidence ${pct(bp.confidence)}</span>
          </div>
        </div>
        <div class="gauge" aria-label="Readiness ${bp.readiness_score} of 100">
          <svg viewBox="0 0 168 168">
            <circle class="gauge__track" cx="84" cy="84" r="${GAUGE_R}"></circle>
            <circle class="gauge__arc" id="gaugeArc" cx="84" cy="84" r="${GAUGE_R}"
              stroke="var(--${meta.kind})" stroke-dasharray="${GAUGE_C}" stroke-dashoffset="${GAUGE_C}"></circle>
          </svg>
          <div class="gauge__center">
            <div>
              <div class="gauge__num" id="gaugeNum" style="color:var(--${meta.kind}-ink)">0</div>
              <div class="gauge__label">Readiness</div>
            </div>
          </div>
        </div>
      </div>
      <div class="authority-split">
        ${asplit("ai", "AI-owned", split.ai, split.total, "Routine work the employee runs end-to-end")}
        ${asplit("gate", "Human-gated", split.gate, split.total, "Steps that stop for a named human")}
        ${asplit("block", "Blocked", split.block, split.total, "Steps frozen by unresolved policy debt")}
      </div>
    </section>

    <div class="control-bar fade-up" style="display:flex;flex-wrap:wrap;gap:var(--s3);align-items:center;justify-content:space-between">
      <div class="engine-toggle" role="group" aria-label="Extraction engine">
        <button data-action="run-engine" data-engine="local" class="${ctx.engine === "local" ? "active" : ""}">Deterministic</button>
        <button data-action="run-engine" data-engine="auto" class="${ctx.engine === "auto" ? "active" : ""}">${esc(prettyModel(ctx.modelName))} extraction</button>
      </div>
      <button class="btn btn--primary" data-action="simulate" id="simBtn">${ICON.play} Run dry-run simulation</button>
    </div>

    <div class="dossier-grid">
      <div class="panel fade-up">
        <div class="panel__head">
          <div><h3>Authority map</h3><div class="sub">Per-step ownership, independently verified by the control plane</div></div>
          <span class="mono" style="font-size:11px;color:var(--ink-mute)">${bp.steps.length} steps</span>
        </div>
        <div class="panel__body">
          <div class="lanes" id="lanes">${bp.steps.map((s, i) => lane(s, i, split)).join("")}</div>
        </div>
      </div>
      <div class="panel fade-up">
        <div class="panel__head"><div><h3>Step inspector</h3><div class="sub">Evidence &amp; authority basis</div></div></div>
        <div class="panel__body"><div class="inspector" id="inspector"></div></div>
      </div>
    </div>

    <div class="panel fade-up">
      <div class="panel__head" style="border-bottom:none;padding-bottom:0">
        <div class="tabs" id="tabs">
          ${tab("plan", "Operating plan", bp.hitl_gates.length)}
          ${tab("proof", "Safety proof", null)}
          ${tab("controls", "Controls", (ctx.record.contracts || []).length)}
        </div>
      </div>
      <div class="panel__body">
        <div class="tabpanel" data-panel="plan" id="panel-plan">${renderOperatingPlan(bp, packet)}</div>
        <div class="tabpanel" data-panel="proof" id="panel-proof" hidden>${renderProofShell()}</div>
        <div class="tabpanel" data-panel="controls" id="panel-controls" hidden>${renderControls(ctx.record.contracts || [], bp)}</div>
      </div>
    </div>
  </div>`;

  document.getElementById("view").innerHTML = html;
  setTab("plan");
  animateGauge(bp.readiness_score);
  animateSplit();
  selectStep(ctx, firstInterestingStep(bp, split));
}

/* ---------- pieces ---------- */

function asplit(kind, label, n, total, caption) {
  const w = total ? Math.round((n / total) * 100) : 0;
  return `
  <div class="asplit asplit--${kind}">
    <div class="asplit__top"><span class="asplit__n" data-count="${n}">0</span><span class="pill pill--${kind}"><span class="dot"></span>${esc(label)}</span></div>
    <div class="asplit__bar"><div class="asplit__fill" data-w="${w}"></div></div>
    <div class="asplit__cap">${esc(caption)}</div>
  </div>`;
}

function lane(step, index, split) {
  const blocked = split.blocked.has(step.id);
  const kind = blocked ? "block" : autonomyClass(step.autonomy_mode);
  const tagLabel = blocked ? "Blocked" : autonomyLabel(step.autonomy_mode);
  return `
  <div class="lane lane--${kind}" data-action="open-step" data-step="${esc(step.id)}" role="button" tabindex="0">
    <span class="lane__idx">${String(index + 1).padStart(2, "0")}</span>
    <div style="min-width:0">
      <div class="lane__title">${esc(step.title)}</div>
      <div class="lane__meta">
        <span>${esc(step.actor || "no owner")}</span>
        ${step.system ? `<span>· ${esc(step.system)}</span>` : ""}
        <span>· ${esc(step.risk_level)} risk</span>
      </div>
    </div>
    <span class="lane__tag lane__tag--${kind}">${esc(tagLabel)}</span>
  </div>`;
}

function tab(name, label, count) {
  return `<button class="tab" data-action="set-tab" data-tab="${name}">${esc(label)}${
    count != null ? `<span class="count">${count}</span>` : ""
  }</button>`;
}

function verdictPitch(decision, split) {
  if (decision === "ready_to_delegate") {
    return `Cleared — all ${split.total} steps are safe for an AI employee to run end-to-end, with source evidence behind every action.`;
  }
  if (decision === "delegate_with_gates") {
    return `Ready, with guardrails — ${split.ai} steps run autonomously and ${split.gate} stop for a named human before anything irreversible.`;
  }
  return `Not yet — ${split.ai} steps safe for an AI employee, ${split.gate} for a human, ${split.block} blocked until the policy gaps below are fixed.`;
}

/* ---------- operating plan ---------- */

function renderOperatingPlan(bp, packet) {
  const gates = bp.hitl_gates.length
    ? bp.hitl_gates
        .map(
          (gate) => `
        <div class="row">
          <div class="row__main">
            <div class="row__title">${ICON.gate} ${esc(gate.human_question)}</div>
            <div class="row__desc">${esc(gate.trigger)}${gate.risk_reduced ? ` — ${esc(gate.risk_reduced)}` : ""}</div>
            <div class="row__meta"><span class="tagx">resume · ${esc(gate.resume_action)}</span>${(gate.context_fields || [])
              .slice(0, 4)
              .map((f) => `<span class="tagx">${esc(f)}</span>`)
              .join("")}</div>
          </div>
        </div>`,
        )
        .join("")
    : `<div class="empty-row">No human gates — every step is safe to automate.</div>`;

  const gaps = bp.gaps.length
    ? bp.gaps
        .map(
          (gap) => `
        <div class="row">
          <div class="row__main">
            <div class="row__title">${esc(titleize(gap.gap_type))}<span class="sev sev--${esc(gap.severity)}">${esc(gap.severity)}</span></div>
            <div class="row__desc">${esc(gap.description)}</div>
            <div class="row__desc" style="color:var(--ink-mute);margin-top:4px">Fix · ${esc(gap.recommendation)}</div>
            ${gap.evidence && gap.evidence[0] ? `<div class="evidence" style="margin-top:8px">“${esc(gap.evidence[0].quote)}”</div>` : ""}
          </div>
        </div>`,
        )
        .join("")
    : `<div class="empty-row">No policy gaps — nothing is blocking full autonomy.</div>`;

  const loop = packet.agent_loop || {};
  const loopCols = ["perceive", "reason", "act", "verify", "escalate"]
    .map(
      (key) => `
      <div class="loop__col">
        <div class="loop__h">${key}</div>
        <ul>${(loop[key] || []).map((item) => `<li>${esc(item)}</li>`).join("") || "<li>—</li>"}</ul>
      </div>`,
    )
    .join("");

  const limits = (packet.scope_kill_list || []).map((k) => `<span class="tagx">${ICON.block} ${esc(k)}</span>`).join("");

  return `
    <p class="tab-summary">Who decides what. The AI employee owns the routine work; below are the moments a person must step in, and the policy gaps standing between this process and full autonomy.</p>
    <div class="section">
      <div class="section__head"><h4>Human decisions <span class="count-pill">${bp.hitl_gates.length}</span></h4><p>Where the employee stops and asks a named owner before acting.</p></div>
      <div class="rows">${gates}</div>
    </div>
    <div class="section">
      <div class="section__head"><h4>What's blocking full autonomy <span class="count-pill">${bp.gaps.length}</span></h4><p>Missing policy the control plane won't let an AI employee guess.</p></div>
      <div class="rows">${gaps}</div>
    </div>
    <details class="disclose">
      <summary>How this AI employee operates <span class="disclose__hint">perceive → reason → act → verify → escalate</span></summary>
      <div class="loop loop--compact">${loopCols}</div>
    </details>
    ${limits ? `<details class="disclose"><summary>Hard limits <span class="disclose__hint">what it will never do in v1</span></summary><div class="chips-inline" style="margin-top:var(--s3)">${limits}</div></details>` : ""}`;
}

/* ---------- safety proof (filled after dry-run) ---------- */

function renderProofShell() {
  return `
    <p class="tab-summary">Prove it before you trust it. A dry-run executes every step with no real ERP, bank, or email touched — routine work runs, gates stop, blockers freeze — then signs the evidence.</p>
    <div id="proofEmpty" class="empty-cta">
      <div>
        <div class="empty-cta__title">No dry-run yet</div>
        <div class="empty-cta__sub">Use <b>Run dry-run</b> above to stream the execution ledger, the evals, and a signed audit chain.</div>
      </div>
    </div>
    <div id="proofResults" hidden>
      <div id="proofLedger"></div>
      <div id="proofEvals"></div>
      <div id="proofAudit"></div>
      <div id="proofLearning"></div>
    </div>`;
}

/* ---------- controls (typed contracts) ---------- */

function retryLabel(retry) {
  if (!retry || typeof retry !== "object") return "—";
  const attempts = Number(retry.max_attempts ?? retry.maxAttempts ?? 1);
  const backoff = String(retry.backoff || "").replace(/_/g, " ");
  const attemptText = `${attempts} attempt${attempts === 1 ? "" : "s"}`;
  return backoff ? `${attemptText} · ${backoff}` : attemptText;
}

function renderControls(contracts, bp) {
  if (!contracts.length) return `<p class="tab-summary">No control contracts generated.</p>`;
  const titleById = Object.fromEntries(bp.steps.map((s) => [s.id, s.title]));
  const hitl = contracts.filter((c) => c.requires_hitl).length;
  const rows = contracts
    .map(
      (c) => `
      <details class="contract">
        <summary class="contract__top">
          <div class="contract__lead">
            <span class="contract__name">${esc(c.action_name)}</span>
            <span class="row__desc">${esc(titleById[c.step_id] || c.step_id)}</span>
          </div>
          <div class="contract__badges">
            ${c.requires_hitl ? `<span class="pill pill--gate"><span class="dot"></span>Human gate</span>` : `<span class="pill pill--ai"><span class="dot"></span>Autonomous</span>`}
            <span class="contract__key" title="idempotency key">${esc(c.idempotency_key)}</span>
          </div>
        </summary>
        <div class="contract__grid">
          <div class="contract__cell"><div class="lbl">Required inputs</div><div class="chips-inline">${(c.required_inputs || []).map((x) => `<span class="tagx">${esc(x)}</span>`).join("")}</div></div>
          <div class="contract__cell"><div class="lbl">Validation checks</div><div class="chips-inline">${(c.validation_checks || []).map((x) => `<span class="tagx">${esc(x)}</span>`).join("")}</div></div>
          <div class="contract__cell"><div class="lbl">Audit requirements</div><div class="chips-inline">${(c.audit_requirements || []).map((x) => `<span class="tagx">${esc(x)}</span>`).join("")}</div></div>
          <div class="contract__cell"><div class="lbl">Retry policy</div><div class="chips-inline"><span class="tagx">${esc(retryLabel(c.retry_policy))}</span></div></div>
        </div>
      </details>`,
    )
    .join("");
  return `
    <p class="tab-summary">Every action the AI employee can take is a typed contract — explicit inputs, validation, audit fields, and a cryptographic idempotency key so nothing runs twice. ${hitl} of ${contracts.length} require a human gate. Click any contract to expand.</p>
    <div class="rows">${rows}</div>`;
}

/* ---------- inspector + interactions ---------- */

export function selectStep(ctx, stepId) {
  const bp = ctx.record.blueprint;
  const step = bp.steps.find((s) => s.id === stepId) || bp.steps[0];
  if (!step) return;
  ctx.selectedStepId = step.id;
  $all(".lane").forEach((el) => el.classList.toggle("active", el.dataset.step === step.id));

  const split = authoritySplit(bp);
  const blocked = split.blocked.has(step.id);
  const kind = blocked ? "block" : autonomyClass(step.autonomy_mode);
  const div = (bp.verification && bp.verification.divergences || []).find((d) => d.step_id === step.id);

  const inspector = document.getElementById("inspector");
  if (!inspector) return;
  inspector.innerHTML = `
    <div>
      <div style="display:flex;justify-content:space-between;align-items:center;gap:8px">
        <div class="row__title" style="font-size:15px">${esc(step.title)}</div>
        <span class="lane__tag lane__tag--${kind}">${blocked ? "Blocked" : autonomyLabel(step.autonomy_mode)}</span>
      </div>
      <p class="row__desc" style="margin-top:6px">${esc(step.description)}</p>
    </div>
    <dl class="kv">
      <dt>Owner</dt><dd>${esc(step.actor || "— unassigned")}</dd>
      <dt>System</dt><dd>${esc(step.system || "—")}</dd>
      <dt>Risk</dt><dd>${esc(step.risk_level)} · ${step.reversible ? "reversible" : "irreversible"}</dd>
      <dt>Decision</dt><dd>${esc(step.decision_rule || "—")}</dd>
      <dt>Inputs</dt><dd>${(step.inputs || []).map(esc).join(", ") || "—"}</dd>
      <dt>Confidence</dt><dd>${pct(step.confidence)}</dd>
    </dl>
    ${div ? `<div class="banner">${ICON.shield}<div><b>Control-plane override.</b> ${esc(div.reason)} (model said “${esc(div.model_value)}”).</div></div>` : ""}
    <div>
      <div class="eyebrow" style="margin-bottom:8px">Source evidence</div>
      ${(step.evidence || []).length
        ? step.evidence.map((e) => `<div class="evidence" style="margin-bottom:6px">“${esc(e.quote)}”</div>`).join("")
        : `<div class="empty-row" style="padding:var(--s4)">No source evidence — quarantined by the grounding check.</div>`}
    </div>`;
}

export function setTab(name) {
  $all("#tabs .tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  $all(".tabpanel").forEach((p) => (p.hidden = p.dataset.panel !== name));
}

/* ---------- animations ---------- */

function animateGauge(score) {
  const arc = document.getElementById("gaugeArc");
  const num = document.getElementById("gaugeNum");
  if (!arc || !num) return;
  const target = Math.max(0, Math.min(100, score));
  requestAnimationFrame(() => {
    arc.style.strokeDashoffset = String(GAUGE_C * (1 - target / 100));
  });
  const start = performance.now();
  const dur = 1000;
  const tick = (now) => {
    const p = Math.min(1, (now - start) / dur);
    const eased = 1 - Math.pow(1 - p, 3);
    num.textContent = String(Math.round(target * eased));
    if (p < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

function animateSplit() {
  requestAnimationFrame(() => {
    $all(".asplit__fill").forEach((el) => (el.style.width = `${el.dataset.w}%`));
    $all(".asplit__n").forEach((el) => {
      const target = Number(el.dataset.count) || 0;
      let cur = 0;
      const step = () => {
        cur += 1;
        el.textContent = String(Math.min(cur, target));
        if (cur < target) window.setTimeout(step, 90);
      };
      if (target > 0) step();
    });
  });
}

function firstInterestingStep(bp, split) {
  const blocked = bp.steps.find((s) => split.blocked.has(s.id));
  if (blocked) return blocked.id;
  const gated = bp.steps.find((s) => s.autonomy_mode === "hitl");
  return (gated || bp.steps[0] || {}).id;
}
