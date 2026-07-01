// Roster / portfolio view — finance processes under review, each kept separate.

import { esc, setView, domainIcon, titleize, pct, ICON, authoritySplit, decisionMeta } from "./util.js";

export function renderRoster(cards) {
  const stats = portfolio(cards);
  const items = cards.map((card) => {
    if (card.pending) return pendingCard(card);
    if (card.error) return errorCard(card);
    return procCard(card);
  }).join("");

  setView(`
    <div class="roster">
      <div class="roster-head fade-up">
        <div class="roster-head__lede">
          <div class="eyebrow">AI Employee Platform</div>
          <h1 class="roster-head__title">Know what an AI employee can <em>safely run</em> — before you delegate.</h1>
          <p class="roster-head__sub">Handoff reads a finance process and returns a grounded verdict - what an AI employee can own end-to-end, where it must stop for a human, and what's blocking full autonomy.</p>
        </div>
      </div>

      <div class="portfolio fade-up">
        ${pstat(stats.count, "processes under review")}
        ${pstat(stats.ready, "ready to delegate now")}
        ${pstat(stats.avgReadiness, "avg readiness / 100")}
        ${pstat(stats.blockedSteps, "steps a human still owns")}
        ${pstat(pct(stats.avgGrounded), "evidence grounded to source")}
      </div>

      <div class="roster-grid">
        <button class="proc-card proc-card--new" data-action="onboard">
          <div class="onboard-inner">
            <div class="onboard-plus">${ICON.plus}</div>
            <div class="onboard-title">Onboard a process</div>
            <div class="onboard-sub">Paste a messy SOP — get a deployment verdict in seconds.</div>
          </div>
        </button>
        ${items}
      </div>
    </div>`);
}

function pendingCard(card) {
  const { pending } = card;
  return `
    <button class="proc-card proc-card--pending" data-action="open-pending" data-pending-key="${esc(pending.key)}" aria-busy="true" aria-label="Open running compile for ${esc(pending.title)}">
      <div class="proc-card__top">
        <div class="proc-card__tile proc-card__tile--pending"><div class="spinner"></div></div>
        <span class="pill pill--brand"><span class="dot"></span>Compiling</span>
      </div>
      <div class="proc-card__head">
        <div class="proc-card__domain">${esc(titleize(pending.domain))}</div>
        <h3 class="proc-card__title">${esc(pending.title)}</h3>
        <div class="proc-card__desc">${esc(pending.model)} extraction → deterministic control plane</div>
      </div>
      <div class="proc-card__pending">
        <div class="proc-card__pending-bar"><span></span></div>
      </div>
      <div class="proc-card__foot">
        <span class="proc-card__runtime">${esc(pending.model)}</span>
        <span class="proc-card__open">Open compile ${ICON.arrow}</span>
      </div>
    </button>`;
}

function procCard(card) {
  const { demo, blueprint, decision, saved } = card;
  const split = authoritySplit(blueprint);
  const meta = decisionMeta(decision);
  const grounded = blueprint.verification ? blueprint.verification.groundedness : 1;
  const action = saved ? "open-saved" : "open-demo";
  const dataAttr = saved ? `data-blueprint="${esc(saved.blueprint_id)}"` : `data-demo="${esc(demo.id)}"`;
  const title = saved ? saved.title : demo.title;
  const domain = saved ? saved.domain : demo.domain;
  const label = saved ? "Saved process" : titleize(domain);
  const exampleTag = saved ? "" : `<span class="tag-example">Example</span>`;
  return `
    <button class="proc-card proc-card--${meta.kind}" data-action="${action}" ${dataAttr}>
      <div class="proc-card__top">
        <div class="proc-card__tile proc-card__tile--${meta.kind}">${domainIcon(domain)}</div>
        <span class="pill pill--${meta.kind}"><span class="dot"></span>${esc(meta.word)}</span>
      </div>
      <div class="proc-card__head">
        <div class="proc-card__domain">${exampleTag}${esc(label)}</div>
        <h3 class="proc-card__title">${esc(title)}</h3>
        <div class="proc-card__desc">${blueprint.steps.length} steps · ${pct(grounded)} evidence-grounded</div>
      </div>
      <div class="proc-card__auth">
        <div class="seg">
          <span class="seg__part seg__part--ai" style="flex:${split.ai || 0.0001}"></span>
          <span class="seg__part seg__part--gate" style="flex:${split.gate || 0.0001}"></span>
          <span class="seg__part seg__part--block" style="flex:${split.block || 0.0001}"></span>
        </div>
        <div class="seg-legend">
          <span><i class="d d--ai"></i>${split.ai} owned</span>
          <span><i class="d d--gate"></i>${split.gate} gated</span>
          <span><i class="d d--block"></i>${split.block} blocked</span>
        </div>
      </div>
      <div class="proc-card__foot">
        <div class="proc-card__score"><b>${blueprint.readiness_score}</b><span>/ 100 ready</span></div>
        <span class="proc-card__open">Open dossier ${ICON.arrow}</span>
      </div>
    </button>`;
}

function errorCard(card) {
  return `
    <div class="proc-card" style="cursor:default">
      <div class="proc-card__top">
        <div class="proc-card__tile">${domainIcon(card.demo.domain)}</div>
        <span class="pill pill--muted">unavailable</span>
      </div>
      <div class="proc-card__head"><h3 class="proc-card__title">${esc(card.demo.title)}</h3>
        <p class="proc-card__desc">${esc(card.error)}</p></div>
    </div>`;
}

function pstat(value, label) {
  return `<div class="pstat"><b class="num">${esc(String(value))}</b><span>${esc(label)}</span></div>`;
}

function portfolio(cards) {
  const ok = cards.filter((c) => !c.error && !c.pending);
  const count = cards.length;
  if (!ok.length) {
    return { count, ready: 0, avgReadiness: 0, blockedSteps: 0, avgGrounded: 1 };
  }
  let ready = 0;
  let blockedSteps = 0;
  let readinessSum = 0;
  let groundedSum = 0;
  for (const c of ok) {
    if (c.decision === "ready_to_delegate") ready += 1;
    blockedSteps += authoritySplit(c.blueprint).block;
    readinessSum += c.blueprint.readiness_score;
    groundedSum += c.blueprint.verification ? c.blueprint.verification.groundedness : 1;
  }
  return {
    count,
    ready,
    avgReadiness: Math.round(readinessSum / ok.length),
    blockedSteps,
    avgGrounded: groundedSum / ok.length,
  };
}

export function openOnboardSheet() {
  const existing = document.getElementById("sheetOverlay");
  if (existing) existing.remove();
  const overlay = document.createElement("div");
  overlay.className = "sheet-overlay";
  overlay.id = "sheetOverlay";
  overlay.innerHTML = `
    <div class="sheet" role="dialog" aria-modal="true" aria-label="Onboard a process">
      <div class="sheet__head">
        <div><div class="eyebrow">Day 2 onboarding</div><h3>Teach the AI employee a process</h3></div>
        <button class="icon-btn" data-action="close-sheet" aria-label="Close">${ICON.close}</button>
      </div>
      <div class="sheet__body">
        <div class="sheet__row">
          <div class="field"><label>Process name</label><input id="onbTitle" value="Invoice exception resolution" maxlength="120" /></div>
          <div class="field"><label>Domain</label>
            <select id="onbDomain">
              <option value="accounts_payable">accounts_payable</option>
              <option value="procurement">procurement</option>
              <option value="revenue_operations">revenue_operations</option>
              <option value="finance_ops">finance_ops</option>
            </select>
          </div>
        </div>
        <div class="field"><label>Operating context — paste the SOP / policy</label>
          <textarea id="onbText" placeholder="The AP analyst receives the invoice and logs it in NetSuite. If the amount is above $10,000 the controller must approve. If the vendor's bank details changed, finance verifies the change before payment…"></textarea>
        </div>
      </div>
      <div class="sheet__foot">
        <span class="hint">AI perception extracts the graph, then the deterministic control plane verifies it.</span>
        <button class="btn btn--primary" data-action="submit-onboard">${ICON.bolt} Compile verdict</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) overlay.remove();
  });
  setTimeout(() => document.getElementById("onbText")?.focus(), 50);
}
