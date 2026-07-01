// Compile animation over the real neuro-symbolic pipeline.
// The only genuine wait is the neural model call (perceive + extract), so the spinner walks
// the neural stages and PARKS on extraction while the backend works. The symbolic + store
// stages stay dimmed/pending (their future-tense detail reads as "queued") because that
// deterministic control-plane work hasn't run yet — we never fake per-stage progress.
// finish(trace) then cascade-settles every stage from the REAL compile_trace — real detail
// lines and complete/warning status — truthfully showing the control plane resolve at once.

import { $all, esc, ICON, setView, sleep } from "./util.js";

const STAGES = [
  {
    name: "Perceive source document",
    layer: "neural",
    pendingDetail: (ctx) =>
      ctx.charCount
        ? `Bounded ${ctx.charCount} characters; waiting for perception output.`
        : "Bounded source loaded; waiting for perception output.",
  },
  {
    name: "Extract process graph",
    layer: "neural",
    pendingDetail: (ctx) =>
      ctx.aiMode
        ? "Model is extracting ordered steps, branches, and gates."
        : "Extracting ordered steps, branches, and gates.",
  },
  {
    name: "Ground every claim to source",
    layer: "symbolic",
    pendingDetail: () => "Evidence quotes will be checked against the source text.",
  },
  {
    name: "Reconcile authority boundaries",
    layer: "symbolic",
    pendingDetail: () => "Authority policy will gate high-risk or irreversible work.",
  },
  {
    name: "Compile control contracts",
    layer: "symbolic",
    pendingDetail: () => "Verified steps will compile into deterministic control contracts.",
  },
  {
    name: "Evaluate & score readiness",
    layer: "symbolic",
    pendingDetail: () => "Readiness will be recomputed after grounding and gates.",
  },
  {
    name: "Seal signed audit trace",
    layer: "store",
    pendingDetail: () => "Trace will be sealed into a reproducible record once the compile settles.",
  },
];

const SPIN = '<div class="spinner"></div>';
const CHECK = '<div class="check">✓</div>';
const WARN = '<div class="warn-ico">!</div>';

export function renderCompile(title, sub, context = {}) {
  const pendingContext = {
    ...context,
    charCount: Number.isFinite(Number(context.charCount)) ? Number(context.charCount) : 0,
  };
  setView(`
    <section class="compile fade-up" role="status" aria-label="Compiling deployment dossier" data-compile-key="${esc(context.compileKey || "")}">
      <div style="text-align:center">
        <div class="compile__title">${esc(title)}</div>
        <div class="compile__sub">${esc(sub)}</div>
      </div>
      <div class="compile__stages" id="cstages">
        ${STAGES.map(
          (stage, index) => `
          <div class="cstage" data-i="${index}">
            <div class="cstage__ico"></div>
            <div class="cstage__body">
              <div class="cstage__name">${esc(stage.name)}</div>
              <div class="cstage__detail">${esc(stage.pendingDetail(pendingContext))}</div>
            </div>
            <div class="cstage__layer">${esc(stage.layer)}</div>
          </div>`,
        ).join("")}
      </div>
      <div class="compile__actions" id="compileActions" hidden></div>
    </section>`);
}

export function runCompile() {
  const stages = $all(".cstage");
  const actionSlot = document.getElementById("compileActions");
  let index = 0;
  let timer = null;

  const mark = (el, cls, ico) => {
    el.classList.remove("run", "done", "warn");
    el.classList.add(cls);
    el.querySelector(".cstage__ico").innerHTML = ico;
  };

  // Stamp a stage from a real compile_trace entry: real status icon + detail line.
  const settle = (el, step) => {
    const warning = step && step.status === "warning";
    mark(el, warning ? "warn" : "done", warning ? WARN : CHECK);
    if (step) {
      el.querySelector(".cstage__name").textContent = step.name;
      el.querySelector(".cstage__layer").textContent = step.layer;
      el.querySelector(".cstage__detail").textContent = step.detail;
    }
  };

  // The only genuine wait is the neural model call (perceive + extract), so the
  // spinner walks the neural prefix and PARKS on the last neural stage while the
  // backend works. Symbolic + store stages stay dimmed/pending (their future-tense
  // detail reads as "queued") because that deterministic work hasn't run yet.
  const neuralStages = Math.min(
    STAGES.filter((stage) => stage.layer === "neural").length,
    stages.length,
  );

  const advance = () => {
    if (index > 0) mark(stages[index - 1], "done", CHECK);
    if (index < neuralStages) {
      mark(stages[index], "run", SPIN);
      index += 1;
      if (index < neuralStages) timer = window.setTimeout(advance, 340 + Math.random() * 240);
    }
  };

  if (stages.length) advance();

  return {
    async finish(trace) {
      window.clearTimeout(timer);
      const real = Array.isArray(trace) && trace.length === stages.length ? trace : null;
      // No real trace = the error path; leave the honest in-progress state frozen so
      // the caller can replace the view (avoids a misleading flash of all-green checks).
      if (!real) return;
      for (let i = 0; i < stages.length; i += 1) {
        settle(stages[i], real[i]);
        await sleep(60);
      }
      await sleep(160);
    },
    waitForOpenDossier() {
      if (!actionSlot) return Promise.resolve();
      actionSlot.hidden = false;
      actionSlot.innerHTML = `
        <button class="compile__cta" type="button" data-action="open-compiled-dossier">
          Open dossier ${ICON.arrow}
        </button>
        <span class="compile__note">Final trace is stored with the dossier.</span>`;
      const button = actionSlot.querySelector("button");
      if (!button) return Promise.resolve();
      return new Promise((resolve) => {
        button.addEventListener(
          "click",
          (event) => {
            event.preventDefault();
            resolve();
          },
          { once: true },
        );
        button.focus();
      });
    },
  };
}
