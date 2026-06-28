// Trust Center — portfolio-level trust posture, computed from roster blueprints.

import { esc, setView, titleize, pct, authoritySplit, decisionMeta } from "./util.js";

export function renderTrust(cards) {
  const ok = cards.filter((c) => !c.error);
  let steps = 0, ai = 0, gate = 0, block = 0, groundedSum = 0, readinessSum = 0;
  for (const c of ok) {
    const s = authoritySplit(c.blueprint);
    steps += c.blueprint.steps.length;
    ai += s.ai; gate += s.gate; block += s.block;
    groundedSum += c.blueprint.verification ? c.blueprint.verification.groundedness : 1;
    readinessSum += c.blueprint.readiness_score;
  }
  const n = ok.length || 1;
  const avgReady = Math.round(readinessSum / n);
  const avgGround = groundedSum / n;

  const rows = ok
    .map((c) => {
      const s = authoritySplit(c.blueprint);
      const meta = decisionMeta(c.decision);
      const g = c.blueprint.verification ? c.blueprint.verification.groundedness : 1;
      return `
        <tr class="click" data-action="open-demo" data-demo="${esc(c.demo.id)}">
          <td class="strong">${esc(c.demo.title)}</td>
          <td class="mono">${esc(titleize(c.demo.domain))}</td>
          <td><span class="pill pill--${meta.kind}"><span class="dot"></span>${esc(meta.word)}</span></td>
          <td class="mono strong">${c.blueprint.readiness_score}</td>
          <td class="mono"><span class="st--pass">${s.ai}</span> · <span class="st--gated">${s.gate}</span> · <span class="st--blocked">${s.block}</span></td>
          <td class="mono">${pct(g)}</td>
        </tr>`;
    })
    .join("");

  setView(`
    <div class="view-head fade-up">
      <div class="eyebrow">Trust Center</div>
      <h1>Portfolio trust posture</h1>
      <p>Aggregate authority, evidence grounding, and policy debt across every process under review — the board-level view a CFO uses to decide where AI employees can safely take ownership.</p>
    </div>
    <div class="statgrid fade-up">
      ${bigstat(avgReady, "Average readiness", `across ${ok.length} processes · / 100`)}
      ${bigstat(pct(avgGround), "Evidence grounded", "faithfulness of extraction to source")}
      ${bigstat(ai, "AI-owned steps", `of ${steps} total — safe to delegate today`)}
      ${bigstat(gate + block, "Steps needing humans", `${gate} gated · ${block} blocked by policy`)}
    </div>
    <div class="table-wrap fade-up">
      <table class="table">
        <thead><tr><th>Process</th><th>Domain</th><th>Verdict</th><th>Ready</th><th>Authority (own·gate·block)</th><th>Grounded</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`);
}

function bigstat(value, label, sub) {
  return `
    <div class="bigstat">
      <div class="bigstat__n">${esc(String(value))}</div>
      <div class="bigstat__l">${esc(label)}</div>
      ${sub ? `<div class="bigstat__sub">${esc(sub)}</div>` : ""}
    </div>`;
}
