// Handoff — application entry. Routing, state, and event orchestration.

import { api } from "./api.js";
import * as store from "./store.js";
import { applyModel, getModelConfig, hasModel, modelLabel, openModelSheet } from "./model.js";
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
  savedRecords: [],
  savedById: {},
  cards: [],
  pendingCompiles: [],
  compileJobs: {},
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

  updateRuntimeChip();

  try {
    state.demos = await api.demos();
    state.demoById = Object.fromEntries(state.demos.map((d) => [d.id, d]));
  } catch (err) {
    setView(`<div class="empty-row" style="padding:var(--s10)">Could not load processes: ${esc(err.message)}</div>`);
    return;
  }

  loadSavedRecords();
  loadRuns();
  await buildCards();
  route();
  window.addEventListener("hashchange", route);
}

// Saved blueprints + run ledger live in the browser (store.js) — per session, no server DB.
function loadSavedRecords() {
  state.savedRecords = store.loadBlueprints();
  state.savedById = Object.fromEntries(state.savedRecords.map((r) => [r.blueprint_id, r]));
}

function loadRuns() {
  state.runs = store.loadRunRows();
}

async function buildCards() {
  const demoCards = await Promise.all(
    state.demos.map(async (demo) => {
      try {
        const res = await api.analyze({
          title: demo.title,
          domain: demo.domain,
          text: demo.text,
          prefer_ai: false,
          runtime_mode: "local",
          persist: false,
        });
        return { demo, blueprint: res.blueprint, decision: res.handoff_packet.decision };
      } catch (err) {
        return { demo, error: err.message };
      }
    }),
  );
  state.cards = [...demoCards, ...savedCards()];
}

function savedCards() {
  return state.savedRecords.map((record) => ({
    saved: {
      blueprint_id: record.blueprint_id,
      title: record.blueprint.title,
      domain: record.blueprint.domain,
      created_at: record.created_at,
    },
    blueprint: record.blueprint,
    decision: record.handoff_packet.decision,
  }));
}

/* ---------------- routing ---------------- */

function route() {
  const hash = location.hash || "#/";
  if (hash.startsWith("#/p/")) {
    setActiveNav("processes");
    openDemo(decodeURIComponent(hash.slice(4)));
  } else if (hash.startsWith("#/b/")) {
    setActiveNav("processes");
    openSaved(decodeURIComponent(hash.slice(4)));
  } else if (hash === "#/ledger") {
    setActiveNav("ledger");
    renderRunLedger(state.runs);
  } else if (hash === "#/trust") {
    setActiveNav("trust");
    renderTrust(state.cards);
  } else {
    setActiveNav("processes");
    renderRoster(processCards());
  }
}

function processCards() {
  return [...state.pendingCompiles, ...state.cards];
}

function isProcessRoute() {
  const hash = location.hash || "#/";
  return hash === "#/";
}

function renderProcessesIfVisible() {
  if (!isProcessRoute()) return;
  if (document.querySelector(".compile")) return;
  setActiveNav("processes");
  renderRoster(processCards());
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
  // Examples always run on the deterministic engine — instant and free, no key needed.
  await compileAndOpen({ title: demo.title, domain: demo.domain, text: demo.text }, "local", `demo:${id}`);
}

async function openSaved(id) {
  const record = state.savedById[id] || store.getBlueprint(id);
  if (!record) {
    location.hash = "#/";
    return;
  }
  state.savedById[id] = record;
  const input = { title: record.blueprint.title, domain: record.blueprint.domain, text: record.source_text };
  state.ctx = makeCtx(input, "auto", `saved:${id}`, record);
  renderDossier(state.ctx);
  await rehydrateRun(state.ctx);
}

// Reopen a saved process with its last dry-run already filled in (proof + audit), pulled
// from the browser store so it survives reloads — instead of a blank "No dry-run yet" tab.
async function rehydrateRun(ctx) {
  const entry = store.latestRunForBlueprint(ctx.record.blueprint_id);
  if (!entry) return; // never dry-run → keep the empty state
  ctx.simulation = entry.simulation;
  await fillSimulation(ctx);
  const btn = document.getElementById("simBtn");
  if (btn) btn.innerHTML = `${ICON.play} Re-run dry-run`;
  await loadAudit(ctx);
}

async function loadAudit(ctx) {
  try {
    ctx.audit = await api.audit({
      simulation: ctx.simulation,
      blueprint: ctx.record.blueprint,
      runtime_metadata: runtimeMetadata(),
    });
    fillAudit(ctx);
  } catch {
    /* audit export is optional — the proof tab still renders */
  }
}

function runtimeMetadata() {
  const cfg = getModelConfig();
  return { model_name: cfg ? cfg.model : "deterministic", analyzer: cfg ? "litellm" : "local" };
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
  const model = aiMode ? modelLabel() : "Deterministic";
  const job = addPendingCompile(input, engine, key, cacheKey, model);
  showCompileJob(job);
  const minBeat = sleep(aiMode ? 900 : 1150);
  const viewActive = () => isCompileViewActive(cacheKey);

  let record;
  try {
    record = await doCompile(input, engine);
    await minBeat;
  } catch (err) {
    removePendingCompile(cacheKey);
    if (viewActive()) {
      await job.ctrl?.finish();
      setView(
        `<div class="empty-row" style="padding:var(--s9)">Compile failed: ${esc(err.message)} · <a data-action="home" href="#/" style="color:var(--brand-ink)">back to processes</a></div>`,
      );
    } else {
      toast(`Compile failed: ${err.message}`);
      renderProcessesIfVisible();
    }
    return;
  }

  if (viewActive()) await job.ctrl?.finish(record.compile_trace);
  state.cache[cacheKey] = record;
  state.ctx = makeCtx(input, engine, key, record);
  addSavedRecord(input, record);
  removePendingCompile(cacheKey);
  if (viewActive()) await job.ctrl?.waitForOpenDossier();
  if (viewActive()) {
    renderDossier(state.ctx);
  } else {
    toast(`${input.title} compiled.`);
    renderProcessesIfVisible();
  }
}

async function doCompile(input, engine) {
  // The analyze response carries everything the dossier and a later dry-run need
  // (blueprint, contracts, control summary, trace, source hash) in one stateless call.
  const res = await api.analyze(applyModel({ ...input, prefer_ai: engine === "auto", runtime_mode: engine }));
  return {
    blueprint: res.blueprint,
    blueprint_id: newBlueprintId(),
    handoff_packet: res.handoff_packet,
    control_summary: res.control_summary,
    compile_trace: res.compile_trace,
    contracts: res.contracts,
    source_hash: res.source_hash,
    source_text: input.text,
  };
}

function newBlueprintId() {
  const rand = crypto.randomUUID ? crypto.randomUUID().replace(/-/g, "") : Math.random().toString(16).slice(2);
  return `bp_${rand.slice(0, 12)}`;
}

// Persist a freshly compiled custom process to the browser store (examples aren't saved).
function addSavedRecord(input, record) {
  if (!state.ctx?.key?.startsWith("custom:")) return;
  const rec = { ...record, created_at: new Date().toISOString() };
  state.savedRecords = store.saveBlueprint(rec);
  state.savedById = Object.fromEntries(state.savedRecords.map((r) => [r.blueprint_id, r]));
  state.cards = [...state.cards.filter((card) => !card.saved), ...savedCards()];
  toast(`${input.title} saved.`);
}

function addPendingCompile(input, engine, sourceKey, cacheKey, model) {
  const pending = state.compileJobs[cacheKey] || {
    input,
    engine,
    sourceKey,
    cacheKey,
    model,
    pending: {
      key: cacheKey,
      title: input.title,
      domain: input.domain,
      engine,
      model: engine === "auto" ? model : "Deterministic",
      started_at: new Date().toISOString(),
    },
  };
  state.compileJobs[cacheKey] = pending;
  state.pendingCompiles = [pending, ...state.pendingCompiles.filter((item) => item.pending.key !== cacheKey)];
  renderProcessesIfVisible();
  return pending;
}

function removePendingCompile(key) {
  const before = state.pendingCompiles.length;
  state.pendingCompiles = state.pendingCompiles.filter((item) => item.pending.key !== key);
  delete state.compileJobs[key];
  if (state.pendingCompiles.length !== before) renderProcessesIfVisible();
}

function isCompileViewActive(key) {
  return document.querySelector(".compile")?.dataset.compileKey === key;
}

function showCompileJob(job) {
  const aiMode = job.engine === "auto";
  renderCompile(
    aiMode ? "Compiling deployment dossier" : "Running deterministic compile",
    aiMode
      ? `${job.input.title} · ${job.model} perception`
      : `${job.input.title} · Deterministic control plane`,
    { aiMode, charCount: job.input.text.length, persist: true, compileKey: job.cacheKey },
  );
  job.ctrl = runCompile();
}

function openPendingCompile(key) {
  const job = state.compileJobs[key];
  if (!job) {
    renderProcessesIfVisible();
    return;
  }
  state.engine = job.engine;
  showCompileJob(job);
}

function makeCtx(input, engine, key, record) {
  return {
    input,
    engine,
    key,
    record,
    simulation: null,
    audit: null,
    selectedStepId: null,
  };
}

/* ---------------- simulate / audit ---------------- */

async function runSimulation(ctx) {
  const btn = document.getElementById("simBtn");
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<div class="spinner"></div> Dry-run executing…`;
  }
  try {
    ctx.simulation = await api.simulate({
      blueprint_id: ctx.record.blueprint_id,
      blueprint: ctx.record.blueprint,
      contracts: ctx.record.contracts,
      source_hash: ctx.record.source_hash,
    });
    ctx.audit = null;
    recordRun(ctx);
    setTab("proof");
    await fillSimulation(ctx);
    await loadAudit(ctx);
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
  // Ledger rows link back only to saved processes; an example run stays unlinked.
  const linked = store.getBlueprint(ctx.record.blueprint_id) ? ctx.record.blueprint_id : null;
  const row = {
    runId: sim.run_id,
    title: ctx.input.title,
    status: sim.status,
    events: sim.events.length,
    pass: sim.eval_summary.pass_count,
    fail: sim.eval_summary.fail_count,
    time: new Date().toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }),
    blueprint_id: linked,
  };
  state.runs = [row, ...state.runs.filter((r) => r.runId !== row.runId)];
  store.saveRun({ row, simulation: sim });
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
  // Use neural extraction only when the visitor has configured a model; otherwise the
  // deterministic engine compiles instantly with no key and no failed AI round-trip.
  const engine = hasModel() ? "auto" : "local";
  compileAndOpen({ title, domain, text }, engine, `custom:${Date.now()}`);
}

/* ---------------- events ---------------- */

function bindEvents() {
  document.addEventListener("click", onClick);
  document.getElementById("brandHome")?.addEventListener("click", () => navigateHash("#/"));
  document.getElementById("suitenav")?.addEventListener("click", onNavClick);
  document.getElementById("themeToggle")?.addEventListener("click", toggleTheme);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") document.getElementById("sheetOverlay")?.remove();
  });
}

function navigateHash(hash) {
  if ((location.hash || "#/") === hash) route();
  else location.hash = hash;
}

function onNavClick(e) {
  const link = e.target.closest("a[data-nav]");
  if (!link) return;
  const hash = link.getAttribute("href") || "#/";
  if ((location.hash || "#/") !== hash) return;
  e.preventDefault();
  route();
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
    case "open-saved":
      location.hash = `#/b/${encodeURIComponent(el.dataset.blueprint)}`;
      break;
    case "open-pending":
      openPendingCompile(el.dataset.pendingKey);
      break;
    case "onboard":
      openOnboardSheet();
      break;
    case "model-settings":
      openModelSheet(() => updateRuntimeChip());
      break;
    case "close-sheet":
      document.getElementById("sheetOverlay")?.remove();
      break;
    case "submit-onboard":
      submitOnboard();
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

function updateRuntimeChip() {
  const chip = document.getElementById("runtimeChip");
  if (!chip) return;
  const dot = chip.querySelector(".dot");
  const engine = chip.querySelector(".rt-engine");
  const db = chip.querySelector(".rt-db");
  const cfg = getModelConfig();
  if (cfg) {
    dot.classList.remove("warn");
    engine.textContent = `${prettyModel(cfg.model)} ready`;
  } else {
    dot.classList.add("warn");
    engine.textContent = "Deterministic engine";
  }
  if (db) db.textContent = "· bring your own model";
}

bootstrap();
