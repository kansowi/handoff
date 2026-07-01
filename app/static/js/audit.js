// Audit tab: a military-grade evidence chain + the raw signed export.

import { esc, toast, ICON } from "./util.js";

export function fillAudit(ctx) {
  const panel = document.getElementById("proofAudit");
  if (!panel) return;
  const audit = ctx.audit;
  if (!audit) {
    panel.innerHTML = "";
    return;
  }

  const { run, case: kase, contracts, events, eval_summary, learning_updates, runtime_metadata } = audit;
  const keyPreview = contracts.slice(0, 4).map((c) => c.idempotency_key);

  const node = (title, hash, desc) => `
    <div class="chain__node">
      <span class="chain__dot"></span>
      <div class="chain__h">${title}</div>
      ${hash ? `<div class="chain__hash">${esc(hash)}</div>` : ""}
      <div class="chain__desc">${desc}</div>
    </div>`;

  panel.innerHTML = `
    <div class="section">
    <div class="section__head" style="display:flex;justify-content:space-between;align-items:flex-start;gap:var(--s3);flex-wrap:wrap">
      <div><h4>Signed evidence chain</h4><p>Not a chat transcript — a reproducible record you can verify bit-for-bit.</p></div>
      <div style="display:flex;gap:8px">
        <button class="btn btn--ghost btn--sm" data-action="copy-audit">${ICON.copy} Copy JSON</button>
        <button class="btn btn--ghost btn--sm" data-action="download-audit">${ICON.download} Export</button>
      </div>
    </div>
    <div class="chain">
      ${node("Source document", `sha256 · ${kase.source_hash}`, "The exact SOP text, content-addressed. Re-run locally to reproduce this verdict bit-for-bit.")}
      ${node(
        "Control contracts",
        keyPreview.join("  ·  "),
        `${contracts.length} deterministic contracts, each keyed by an idempotency hash of its step configuration.`,
      )}
      ${node(
        "Run events",
        `run · ${run.run_id}`,
        `${events.length} ordered events — every action carries a sequence, actor, decision, and source evidence.`,
      )}
      ${node(
        "Evaluations",
        `pass ${eval_summary.pass_count} · warn ${eval_summary.warn_count} · fail ${eval_summary.fail_count}`,
        "Span and trace-level checks, including grounding and authority reconciliation.",
      )}
      ${node(
        "Runtime attestation",
        `engine · ${esc(runtime_metadata.model_name || "deterministic")}`,
        `${learning_updates.length} proposed policy-debt fixes captured for the next deployment review.`,
      )}
    </div>
    <details class="disclose" style="margin-top:var(--s4)">
      <summary>View raw export <span class="disclose__hint">the full signed JSON</span></summary>
      <div class="codeblock" id="auditJson">${esc(JSON.stringify(audit, null, 2))}</div>
    </details>
    </div>`;
}

export async function copyAudit(ctx) {
  if (!ctx.audit) return;
  try {
    await navigator.clipboard.writeText(JSON.stringify(ctx.audit, null, 2));
    toast("Audit export copied to clipboard");
  } catch {
    toast("Copy unavailable in this browser");
  }
}

export function downloadAudit(ctx) {
  if (!ctx.audit) return;
  const blob = new Blob([JSON.stringify(ctx.audit, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `handoff-audit-${ctx.audit.run.run_id}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
  toast("Audit export downloaded");
}
