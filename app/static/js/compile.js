// Cinematic compile animation that mirrors the real neuro-symbolic pipeline.
// Stages advance on a timer and hold on the last stage until finish() is called,
// so the animation never completes before the backend responds.

import { $all, setView, sleep } from "./util.js";

const STAGES = [
  { name: "Perceive source document", layer: "neural" },
  { name: "Extract process graph", layer: "neural" },
  { name: "Ground every claim to source", layer: "symbolic" },
  { name: "Reconcile authority boundaries", layer: "symbolic" },
  { name: "Compile control contracts", layer: "symbolic" },
  { name: "Evaluate & score readiness", layer: "symbolic" },
  { name: "Persist signed audit trace", layer: "store" },
];

const SPIN = '<div class="spinner"></div>';
const CHECK = '<div class="check">✓</div>';

export function renderCompile(title, sub) {
  setView(`
    <section class="compile fade-up" role="status" aria-label="Compiling deployment dossier">
      <div style="text-align:center">
        <div class="compile__title">${title}</div>
        <div class="compile__sub">${sub}</div>
      </div>
      <div class="compile__stages" id="cstages">
        ${STAGES.map(
          (stage, index) => `
          <div class="cstage" data-i="${index}">
            <div class="cstage__ico"></div>
            <div class="cstage__name">${stage.name}</div>
            <div class="cstage__layer">${stage.layer}</div>
          </div>`,
        ).join("")}
      </div>
    </section>`);
}

export function runCompile() {
  const stages = $all(".cstage");
  let index = 0;
  let timer = null;

  const mark = (el, cls, ico) => {
    el.classList.remove("run", "done");
    el.classList.add(cls);
    el.querySelector(".cstage__ico").innerHTML = ico;
  };

  const advance = () => {
    if (index > 0) mark(stages[index - 1], "done", CHECK);
    if (index < stages.length) {
      mark(stages[index], "run", SPIN);
      index += 1;
      if (index < stages.length) timer = window.setTimeout(advance, 340 + Math.random() * 240);
    }
  };

  if (stages.length) advance();

  return {
    async finish() {
      window.clearTimeout(timer);
      for (const stage of stages) {
        mark(stage, "done", CHECK);
        await sleep(60);
      }
      await sleep(160);
    },
  };
}
