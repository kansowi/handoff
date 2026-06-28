// Handoff — application entry. Routing, state, and event orchestration.

import { api } from "./api.js";
import { esc, setView, toast, prettyModel, sleep, ICON } from "./util.js";
import { initTheme, toggleTheme } from "./theme.js";
import { renderRoster, openOnboardSheet } from "./roster.js";
import { renderTrust } from "./trust.js";
import { renderRunLedger } from "./runledger.js";
import { renderDossier, selectStep, setTab } from "./dossier.js";
import { renderCompile, runCompile } from "./compile.js";
import { fillSimulation } from "./ledger.js";
import { fillAudit, copyAudit, downloadAudit } from "./audit.js";

const state = {
  runtime: null,
  demos: [],
  demoById: {},
  cards: [],
  runs: [],
  engine: "local",
  ctx: null,
  cache: {},
};

/* ---------------- bootstrap ---------------- */

async function bootstrap() {
  initTheme();
  bindEvents();
  setView(`<div class="empty-row" style="padding:var(--s10)">Booting deployment control plane…</div>`);

  try {
    state.runtime = await api.runtime();
    updateRuntimeChip(state.runtime);
  } catch {
    /* runtime chip is non-essential */
  }

  try {
    state.demos = await api.demos();
    state.demoById = Object.fromEntries(state.demos.map((d) => [d.id, d]));
  } catch (err) {
    setView(`<div class="empty-row" style="padding:var(--s10)">Could not load processes: ${esc(err.message)}</div>`);
    return;
  }

  await buildCards();
  route();
  window.addEventListener("hashchange", route);
}

async function buildCards() {
  state.cards = await Promise.all(
    state.demos.map(async (demo) => {
      try {
        const res = await api.analyze({
          title: demo.title,
          domain: demo.domain,
          text: demo.text,
          prefer_ai: false,
          runtime_mode: "local",
        });
        return { demo, blueprint: res.blueprint, decision: res.handoff_packet.decision };
      } catch (err) {
        return { demo, error: err.message };
      }
    }),
  );
}

/* ---------------- routing ---------------- */

function route() {
  const hash = location.hash || "#/";
  if (hash.startsWith("#/p/")) {
    setActiveNav("processes");
    openDemo(decodeURIComponent(hash.slice(4)));
  } else if (hash === "#/ledger") {
    setActiveNav("ledger");
    renderRunLedger(state.runs);
  } else if (hash === "#/trust") {
    setActiveNav("trust");
    renderTrust(state.cards);
  } else {
    setActiveNav("processes");
    renderRoster(state.cards);
  }
}

function setActiveNav(name) {
  for (const link of document.querySelectorAll(".suitenav a")) {
    link.classList.toggle("active", link.dataset.nav === name);
  }
}

async function openDemo(id) {
  const demo = state.demoById[id];
  if (!demo) {
    location.hash = "#/";
    return;
  }
  await compileAndOpen({ title: demo.title, domain: demo.domain, text: demo.text }, state.engine, `demo:${id}`);
}

/* ---------------- compile ---------------- */

async function compileAndOpen(input, engine, key) {
  state.engine = engine;
  const cacheKey = `${key}:${engine}`;

  if (state.cache[cacheKey]) {
    state.ctx = makeCtx(input, engine, key, state.cache[cacheKey]);
    renderDossier(state.ctx);
    return;
  }

  const aiMode = engine === "auto";
  const model = prettyModel(state.runtime?.model_name);
  renderCompile(
    aiMode ? "Compiling deployment dossier" : "Running deterministic compile",
    aiMode ? `${model} perception → deterministic control plane` : "Deterministic control plane",
  );
  const ctrl = runCompile();
  const minBeat = sleep(aiMode ? 900 : 1150);

  let record;
  try {
    record = await doCompile(input, engine);
    await minBeat;
  } catch (err) {
    await ctrl.finish();
    setView(
      `<div class="empty-row" style="padding:var(--s9)">Compile failed: ${esc(err.message)} · <a data-action="home" href="#/" style="color:var(--brand-ink)">back to processes</a></div>`,
    );
    return;
  }

  await ctrl.finish();
  state.cache[cacheKey] = record;
  state.ctx = makeCtx(input, engine, key, record);
  renderDossier(state.ctx);
}

async function doCompile(input, engine) {
  const res = await api.analyze({ ...input, prefer_ai: engine === "auto", runtime_mode: engine });
  const rec = await api.blueprint(res.blueprint_id);
  return {
    blueprint: res.blueprint,
    blueprint_id: res.blueprint_id,
    handoff_packet: res.handoff_packet,
    control_summary: res.control_summary,
    compile_trace: res.compile_trace,
    contracts: rec.contracts,
    source_hash: rec.source_hash,
  };
}

function makeCtx(input, engine, key, record) {
  return {
    input,
    engine,
    key,
    record,
    modelName: state.runtime?.model_name,
    simulation: null,
    audit: null,
    selectedStepId: null,
  };
}

async function reEngine(engine) {
  if (!state.ctx || state.ctx.engine === engine) return;
  await compileAndOpen(state.ctx.input, engine, state.ctx.key);
}

/* ---------------- simulate / audit ---------------- */

async function runSimulation(ctx) {
  const btn = document.getElementById("simBtn");
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<div class="spinner"></div> Dry-run executing…`;
  }
  try {
    ctx.simulation = await api.simulate(ctx.record.blueprint_id);
    ctx.audit = null;
    recordRun(ctx);
    setTab("proof");
    await fillSimulation(ctx);
    try {
      ctx.audit = await api.audit(ctx.simulation.run_id);
      fillAudit(ctx);
    } catch {
      /* audit export is optional */
    }
  } catch (err) {
    toast(`Simulation failed: ${err.message}`);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `${ICON.play} Re-run dry-run`;
    }
  }
}

function recordRun(ctx) {
  const sim = ctx.simulation;
  if (!sim) return;
  if (state.runs.some((r) => r.runId === sim.run_id)) return;
  state.runs.unshift({
    runId: sim.run_id,
    title: ctx.input.title,
    status: sim.status,
    events: sim.events.length,
    pass: sim.eval_summary.pass_count,
    fail: sim.eval_summary.fail_count,
    time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    demo: ctx.key && ctx.key.startsWith("demo:") ? ctx.key.slice(5) : null,
  });
}

function onTab(tab) {
  setTab(tab);
}

/* ---------------- onboarding ---------------- */

function submitOnboard() {
  const title = (document.getElementById("onbTitle")?.value || "").trim() || "Pasted process";
  const domain = document.getElementById("onbDomain")?.value || "finance_ops";
  const text = (document.getElementById("onbText")?.value || "").trim();
  if (text.length < 40) {
    toast("Paste at least 40 characters of SOP context.");
    return;
  }
  document.getElementById("sheetOverlay")?.remove();
  compileAndOpen({ title, domain, text }, "auto", `custom:${Date.now()}`);
}

/* ---------------- events ---------------- */

function bindEvents() {
  document.addEventListener("click", onClick);
  document.getElementById("brandHome")?.addEventListener("click", () => (location.hash = "#/"));
  document.getElementById("themeToggle")?.addEventListener("click", toggleTheme);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") document.getElementById("sheetOverlay")?.remove();
  });
}

async function onClick(e) {
  const el = e.target.closest("[data-action]");
  if (!el) return;
  const action = el.dataset.action;

  switch (action) {
    case "home":
      e.preventDefault();
      location.hash = "#/";
      break;
    case "open-demo":
      location.hash = `#/p/${encodeURIComponent(el.dataset.demo)}`;
      break;
    case "onboard":
      openOnboardSheet();
      break;
    case "close-sheet":
      document.getElementById("sheetOverlay")?.remove();
      break;
    case "submit-onboard":
      submitOnboard();
      break;
    case "run-engine":
      reEngine(el.dataset.engine);
      break;
    case "simulate":
      if (state.ctx) runSimulation(state.ctx);
      break;
    case "set-tab":
      onTab(el.dataset.tab);
      break;
    case "open-step":
      if (state.ctx) selectStep(state.ctx, el.dataset.step);
      break;
    case "copy-audit":
      copyAudit(state.ctx);
      break;
    case "download-audit":
      downloadAudit(state.ctx);
      break;
    default:
      break;
  }
}

/* ---------------- runtime chip ---------------- */

function updateRuntimeChip(rt) {
  const chip = document.getElementById("runtimeChip");
  if (!chip) return;
  const dot = chip.querySelector(".dot");
  const engine = chip.querySelector(".rt-engine");
  const db = chip.querySelector(".rt-db");
  if (rt.litellm_configured) {
    dot.classList.remove("warn");
    engine.textContent = `${prettyModel(rt.model_name)} ready`;
  } else {
    dot.classList.add("warn");
    engine.textContent = "Deterministic only";
  }
  if (db) db.textContent = rt.storage_enabled ? "· store on" : "· store off";
}

bootstrap();
