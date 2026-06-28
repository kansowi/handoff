// Small shared helpers: escaping, DOM, formatting, icons, toast.

export function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export const $ = (sel, root = document) => root.querySelector(sel);
export const $all = (sel, root = document) => [...root.querySelectorAll(sel)];
export const sleep = (ms) => new Promise((resolve) => window.setTimeout(resolve, ms));

export function setView(html) {
  const view = document.getElementById("view");
  view.innerHTML = html;
  return view;
}

let toastTimer = null;
export function toast(message) {
  const node = document.getElementById("toast");
  if (!node) return;
  node.textContent = message;
  node.classList.add("show");
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => node.classList.remove("show"), 2600);
}

export const titleize = (value) =>
  String(value || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());

export const pct = (value) => `${Math.round((Number(value) || 0) * 100)}%`;

// Map an autonomy mode to a signal class.
export function autonomyClass(mode) {
  if (mode === "hitl") return "gate";
  if (mode === "human_only") return "human_only";
  return "ai"; // ai_employee + rules are autonomous
}

export function autonomyLabel(mode) {
  if (mode === "hitl") return "Human gate";
  if (mode === "human_only") return "Human only";
  if (mode === "rules") return "Rules";
  return "AI-owned";
}

export const ICON = {
  back: '<svg class="ico" viewBox="0 0 16 16" fill="none"><path d="M10 12L6 8l4-4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  bot: '<svg class="ico" viewBox="0 0 16 16" fill="none"><rect x="3" y="5" width="10" height="8" rx="2" stroke="currentColor" stroke-width="1.4"/><path d="M8 2v3M6 9h.01M10 9h.01" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
  gate: '<svg class="ico" viewBox="0 0 16 16" fill="none"><rect x="3.5" y="7" width="9" height="6.5" rx="1.5" stroke="currentColor" stroke-width="1.4"/><path d="M5.5 7V5a2.5 2.5 0 015 0v2" stroke="currentColor" stroke-width="1.4"/></svg>',
  block: '<svg class="ico" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="5.5" stroke="currentColor" stroke-width="1.4"/><path d="M4.5 4.5l7 7" stroke="currentColor" stroke-width="1.4"/></svg>',
  shield: '<svg class="ico" viewBox="0 0 16 16" fill="none"><path d="M8 2l5 2v4c0 3-2.2 5-5 6-2.8-1-5-3-5-6V4l5-2z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg>',
  bolt: '<svg class="ico" viewBox="0 0 16 16" fill="none"><path d="M9 2L4 9h3l-1 5 5-7H8l1-5z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>',
  check: '<svg class="ico" viewBox="0 0 16 16" fill="none"><path d="M3.5 8.5l3 3 6-7" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  play: '<svg class="ico" viewBox="0 0 16 16" fill="none"><path d="M5 3.5l7 4.5-7 4.5v-9z" fill="currentColor"/></svg>',
  copy: '<svg class="ico" viewBox="0 0 16 16" fill="none"><rect x="5" y="5" width="8" height="8" rx="1.5" stroke="currentColor" stroke-width="1.4"/><path d="M3 11V4a1 1 0 011-1h6" stroke="currentColor" stroke-width="1.4"/></svg>',
  download: '<svg class="ico" viewBox="0 0 16 16" fill="none"><path d="M8 3v7m0 0l-3-3m3 3l3-3M3.5 13h9" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  plus: '<svg class="ico" viewBox="0 0 16 16" fill="none"><path d="M8 3.5v9M3.5 8h9" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
  doc: '<svg class="ico" viewBox="0 0 16 16" fill="none"><path d="M4 2.5h5l3 3V13a.5.5 0 01-.5.5h-7A.5.5 0 014 13V2.5z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>',
  arrow: '<svg class="ico" viewBox="0 0 16 16" fill="none"><path d="M3.5 8h9m0 0l-3.5-3.5M12.5 8L9 11.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  close: '<svg class="ico" viewBox="0 0 16 16" fill="none"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
};

const DOMAIN_GLYPH = {
  accounts_payable:
    '<svg viewBox="0 0 22 22" fill="none" width="20" height="20"><path d="M6 3.5h10v15l-2-1.3-2 1.3-2-1.3-2 1.3V3.5z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M9 7.5h4M9 10.5h4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
  procurement:
    '<svg viewBox="0 0 22 22" fill="none" width="20" height="20"><path d="M11 3.2l6.5 3.4v8.8L11 18.8l-6.5-3.4V6.6L11 3.2z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M4.7 6.7L11 10l6.3-3.3M11 10v8.6" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/></svg>',
  revenue_operations:
    '<svg viewBox="0 0 22 22" fill="none" width="20" height="20"><rect x="3.5" y="5.5" width="15" height="11" rx="2.2" stroke="currentColor" stroke-width="1.5"/><path d="M3.5 9h15M6.5 13.5h3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
  finance_ops:
    '<svg viewBox="0 0 22 22" fill="none" width="20" height="20"><path d="M4 18h14M7 18v-6M11 18V6M15 18v-9" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
};
const DEFAULT_GLYPH =
  '<svg viewBox="0 0 22 22" fill="none" width="20" height="20"><rect x="4" y="5" width="14" height="12" rx="2" stroke="currentColor" stroke-width="1.5"/><path d="M4 9h14" stroke="currentColor" stroke-width="1.5"/></svg>';
export const domainIcon = (domain) => DOMAIN_GLYPH[domain] || DEFAULT_GLYPH;

// Decision → display metadata.
export function decisionMeta(decision) {
  switch (decision) {
    case "ready_to_delegate":
      return { word: "Ready to delegate", kind: "ai", kicker: "Deployment verdict" };
    case "delegate_with_gates":
      return { word: "Delegate with gates", kind: "gate", kicker: "Deployment verdict" };
    default:
      return { word: "Do not delegate ungated", kind: "block", kicker: "Deployment verdict" };
  }
}

// Authority counts derived from blueprint steps + gaps.
export function authoritySplit(blueprint) {
  const highGapSteps = new Set(
    blueprint.gaps.filter((g) => g.severity === "high").flatMap((g) => g.affected_step_ids || []),
  );
  let ai = 0;
  let gate = 0;
  let block = 0;
  for (const step of blueprint.steps) {
    if (highGapSteps.has(step.id)) block += 1;
    else if (step.autonomy_mode === "hitl" || step.autonomy_mode === "human_only") gate += 1;
    else ai += 1;
  }
  return { ai, gate, block, blocked: highGapSteps, total: blueprint.steps.length };
}

export function engineLabel(blueprint) {
  const model = blueprint.analyzer_model;
  if (blueprint.analyzer === "litellm") return `${prettyModel(model)} · live`;
  if (blueprint.analyzer === "litellm_fallback") return `Deterministic · ${prettyModel(model)} unavailable`;
  return "Deterministic engine";
}

export function prettyModel(model) {
  if (!model) return "Opus";
  return model.replace(/^.*\//, "").replace(/claude-/i, "Claude ").replace(/-/g, " ");
}
