// Run Ledger — every stored dry-run, hydrated from the server on boot (survives reloads).

import { esc, setView } from "./util.js";

const statusKind = (status) => (status === "completed" ? "ai" : status === "gated" ? "gate" : "block");

export function renderRunLedger(runs) {
  const rows = runs
    .map((r) => {
      const clickable = r.blueprint_id ? `class="click" data-action="open-saved" data-blueprint="${esc(r.blueprint_id)}"` : "";
      return `
        <tr ${clickable}>
          <td class="strong mono">${esc(r.runId)}</td>
          <td>${esc(r.title)}</td>
          <td><span class="pill pill--${statusKind(r.status)}"><span class="dot"></span>${esc(r.status)}</span></td>
          <td class="mono">${r.events}</td>
          <td class="mono"><span class="st--pass">${r.pass}</span> / <span class="st--fail">${r.fail}</span></td>
          <td class="mono">${esc(r.time)}</td>
        </tr>`;
    })
    .join("");

  setView(`
    <div class="view-head fade-up">
      <div class="eyebrow">Run Ledger</div>
      <h1>Dry-run ledger</h1>
      <p>Every dry-run you've run — stored, deterministic, and replayable, with no external systems touched. Each run is a signed record with its own evidence chain. Open one to replay it.</p>
    </div>
    ${
      runs.length
        ? `<div class="table-wrap fade-up">
            <table class="table">
              <thead><tr><th>Run</th><th>Process</th><th>Status</th><th>Events</th><th>Evals P / F</th><th>When</th></tr></thead>
              <tbody>${rows}</tbody>
            </table>
          </div>`
        : `<div class="panel fade-up"><div class="panel__body"><div class="empty-row">No dry-runs yet. Open a process, run the dry-run simulation, and it lands here as a replayable record.</div></div></div>`
    }`);
}
