// Safety-proof fills: dry-run ledger (streamed), evals, learning — into #panel-proof.

import { esc, titleize, sleep } from "./util.js";

const HEADLINE_EVALS = new Set(["eval_groundedness", "eval_policy_reconciliation", "eval_unresolved_high_gaps"]);

function setProofCount(count) {
  const tab = document.querySelector('#tabs .tab[data-tab="proof"]');
  if (!tab) return;
  let span = tab.querySelector(".count");
  if (!span) {
    span = document.createElement("span");
    span.className = "count";
    tab.appendChild(span);
  }
  span.textContent = String(count);
}

export async function fillSimulation(ctx) {
  const sim = ctx.simulation;
  const empty = document.getElementById("proofEmpty");
  const results = document.getElementById("proofResults");
  if (empty) empty.hidden = true;
  if (results) results.hidden = false;

  renderEvals(sim.eval_summary);
  renderLearning(sim.learning_updates);
  setProofCount(sim.events.length);
  await streamLedger(sim.events);
}

async function streamLedger(events) {
  const panel = document.getElementById("proofLedger");
  if (!panel) return;
  panel.innerHTML = `
    <div class="section">
      <div class="section__head"><h4>Execution ledger</h4><p>Every event signed with a sequence, actor, decision, and source evidence — streamed live, no external system touched.</p></div>
      <div class="panel" style="box-shadow:none;background:var(--void-2)">
        <div class="ledger">
          <div class="ledger__head"><span>seq</span><span>event</span><span>action</span><span>status</span></div>
          <div id="ledgerBody"></div>
        </div>
      </div>
    </div>`;
  const body = document.getElementById("ledgerBody");
  for (const ev of events) {
    const row = document.createElement("div");
    row.className = "ledger__row stream-in";
    if (ev.step_id) {
      row.dataset.action = "open-step";
      row.dataset.step = ev.step_id;
      row.style.cursor = "pointer";
    }
    row.innerHTML = `
      <span class="ledger__seq">${String(ev.sequence).padStart(3, "0")}</span>
      <span class="ledger__type"><span class="dotc dotc--${esc(ev.event_type)}"></span>${esc(ev.event_type)}</span>
      <span class="ledger__msg" title="${esc(ev.message)}">${esc(ev.message)}</span>
      <span class="ledger__status st--${esc(ev.status)}">${esc(ev.status)}</span>`;
    body.appendChild(row);
    await sleep(80);
  }
}

function evalRow(c) {
  return `
    <div class="eval-row">
      <span class="dotc dotc--${esc(c.status)}" title="${esc(c.status)}"></span>
      <div>
        <div class="eval-row__name">${esc(c.name)} <span class="st--${esc(c.status)}" style="font-family:var(--font-mono);font-size:11px">${esc(c.status)}</span></div>
        <div class="eval-row__msg">${esc(c.message)}</div>
      </div>
      <span class="sev sev--${esc(c.severity)}">${esc(c.severity)}</span>
    </div>`;
}

function renderEvals(summary) {
  const panel = document.getElementById("proofEvals");
  if (!panel) return;
  const headline = summary.checks.filter((c) => HEADLINE_EVALS.has(c.check_id) || c.status !== "pass");
  const headlineHtml = headline.length
    ? headline.map(evalRow).join("")
    : `<div class="empty-row">Every check passed.</div>`;

  panel.innerHTML = `
    <div class="section">
      <div class="section__head"><h4>Evaluations</h4><p>Span and trace-level checks — including evidence grounding and authority reconciliation.</p></div>
      <div class="eval-summary">
        <div class="eval-stat eval-stat--pass"><b>${summary.pass_count}</b><span>pass</span></div>
        <div class="eval-stat eval-stat--warn"><b>${summary.warn_count}</b><span>warn</span></div>
        <div class="eval-stat eval-stat--fail"><b>${summary.fail_count}</b><span>fail</span></div>
      </div>
      <div class="rows">${headlineHtml}</div>
      <details class="disclose" style="margin-top:var(--s3)">
        <summary>Show all ${summary.checks.length} checks</summary>
        <div class="rows" style="margin-top:var(--s3)">${summary.checks.map(evalRow).join("")}</div>
      </details>
    </div>`;
}

function renderLearning(updates) {
  const panel = document.getElementById("proofLearning");
  if (!panel) return;
  if (!updates.length) {
    panel.innerHTML = "";
    return;
  }
  panel.innerHTML = `
    <div class="section">
      <div class="section__head"><h4>Proposed fixes <span class="count-pill">${updates.length}</span></h4><p>The control plane captures every policy gap as a concrete fix for the next deployment review.</p></div>
      <div class="rows">${updates
        .map(
          (u) => `
        <div class="row">
          <div class="row__main">
            <div class="row__title">${esc(titleize(u.update_type))}<span class="pill pill--brand"><span class="dot"></span>${esc(u.status)}</span></div>
            <div class="row__desc">${esc(u.recommendation)}</div>
            <div class="row__meta"><span class="tagx">target · ${esc(u.target)}</span></div>
          </div>
        </div>`,
        )
        .join("")}</div>
    </div>`;
}
