// Bring-your-own model. Handoff is model-agnostic: the default engine is the deterministic
// control plane (no key, works for everyone). A visitor can optionally point compiles at any
// provider by picking it from the dropdowns (backed by GET /api/models). The key is held in
// sessionStorage (cleared when the tab closes), sent only with that compile request, and never
// stored or logged on the server.

import { api } from "./api.js";
import { esc, ICON, toast, prettyModel } from "./util.js";

const KEY = "handoff:model:v1";
// Where "run it locally" points. Set this to your repo once it's pushed.
const REPO_URL = "https://github.com/your-username/handoff";
const CUSTOM = "__custom__";

let catalogCache = null;

export function getModelConfig() {
  try {
    const cfg = JSON.parse(sessionStorage.getItem(KEY) || "null");
    return cfg && cfg.model && (cfg.keyless || cfg.apiKey) ? cfg : null;
  } catch {
    return null;
  }
}

export function hasModel() {
  return getModelConfig() !== null;
}

export function modelLabel() {
  const cfg = getModelConfig();
  return cfg ? prettyModel(cfg.model) : "Deterministic engine";
}

// Return a new input augmented with the per-request model overrides (immutable).
export function applyModel(input) {
  const cfg = getModelConfig();
  if (!cfg) return input;
  return {
    ...input,
    model: cfg.model,
    api_key: cfg.apiKey || null,
    api_base: cfg.apiBase || null,
    custom_llm_provider: cfg.customProvider || null,
  };
}

function persist(cfg) {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(cfg));
  } catch {
    /* private mode — config just won't persist across reloads */
  }
}

function clear() {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}

function stripPrefix(model, prefix) {
  return prefix && model.startsWith(`${prefix}/`) ? model.slice(prefix.length + 1) : model;
}

// Minimal fallback so the drawer still works if the catalog fetch fails.
const FALLBACK_CATALOG = {
  providers: [
    {
      id: "custom",
      label: "Custom",
      prefix: "",
      keyless: false,
      needs_base: false,
      allow_custom: true,
      key_label: "API key",
      key_placeholder: "sk-…",
      models: [],
    },
  ],
};

async function loadCatalog() {
  if (catalogCache) return catalogCache;
  try {
    catalogCache = await api.models();
  } catch {
    catalogCache = FALLBACK_CATALOG;
  }
  return catalogCache;
}

export async function openModelSheet(onChange) {
  document.getElementById("sheetOverlay")?.remove();
  const catalog = await loadCatalog();
  const providers = catalog.providers;
  const saved = getModelConfig();

  const overlay = document.createElement("div");
  overlay.className = "sheet-overlay";
  overlay.id = "sheetOverlay";
  overlay.innerHTML = `
    <div class="sheet" role="dialog" aria-modal="true" aria-label="Choose a model">
      <div class="sheet__head">
        <div><div class="eyebrow">Model-agnostic engine</div><h3>Use your own model</h3></div>
        <button class="icon-btn" data-action="close-sheet" aria-label="Close">${ICON.close}</button>
      </div>
      <div class="sheet__body">
        <p class="hint" style="margin:0 0 var(--s3)">
          Default is the deterministic control plane — no key needed. To run neural extraction,
          pick a provider and model below. Your key stays in this tab, is sent only with the compile
          request, and is <b>never stored or logged on the server</b>.
        </p>
        <div class="sheet__row">
          <div class="field">
            <label>Provider</label>
            <select id="mdlProvider">
              ${providers.map((p) => `<option value="${esc(p.id)}">${esc(p.label)}</option>`).join("")}
            </select>
          </div>
          <div class="field" id="mdlModelField">
            <label>Model</label>
            <select id="mdlModelSel"></select>
          </div>
        </div>
        <div class="field" id="mdlCustomField" hidden>
          <label>Model id</label>
          <input id="mdlCustom" placeholder="model-id" maxlength="200" />
        </div>
        <div class="field" id="mdlKeyField">
          <label id="mdlKeyLabel">API key</label>
          <input id="mdlKey" type="password" placeholder="sk-…" maxlength="400" autocomplete="off" />
        </div>
        <div class="field" id="mdlBaseField" hidden>
          <label>Base URL <span style="color:var(--ink-mute)">(for gateways / self-hosted)</span></label>
          <input id="mdlBase" placeholder="https://gateway.example.com" maxlength="400" />
        </div>
        <div class="model-note">
          ${ICON.shield}
          <span>Rather not paste a key into a website? Totally fair — Handoff runs locally with
          your own model (or a local Ollama, zero key). <a href="${esc(REPO_URL)}" target="_blank"
          rel="noopener">Clone &amp; run it locally →</a></span>
        </div>
      </div>
      <div class="sheet__foot">
        <button class="btn btn--ghost" id="mdlClear" type="button">Use deterministic engine</button>
        <button class="btn btn--primary" id="mdlSave" type="button">${ICON.bolt} Save model</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) overlay.remove();
  });

  const providerSel = overlay.querySelector("#mdlProvider");
  const modelSel = overlay.querySelector("#mdlModelSel");
  const customField = overlay.querySelector("#mdlCustomField");
  const customInput = overlay.querySelector("#mdlCustom");
  const keyField = overlay.querySelector("#mdlKeyField");
  const keyLabel = overlay.querySelector("#mdlKeyLabel");
  const keyInput = overlay.querySelector("#mdlKey");
  const baseField = overlay.querySelector("#mdlBaseField");
  const baseInput = overlay.querySelector("#mdlBase");

  const providerById = Object.fromEntries(providers.map((p) => [p.id, p]));

  function currentProvider() {
    return providerById[providerSel.value] || providers[0];
  }

  function refreshCustomVisibility() {
    const provider = currentProvider();
    const isCustom = modelSel.value === CUSTOM || provider.models.length === 0;
    customField.hidden = !isCustom;
  }

  function renderProvider(preselectModelId) {
    const provider = currentProvider();
    const options = provider.models.map(
      (m) => `<option value="${esc(m.id)}">${esc(m.label)}</option>`,
    );
    if (provider.allow_custom || provider.models.length === 0) {
      options.push(`<option value="${CUSTOM}">Custom…</option>`);
    }
    modelSel.innerHTML = options.join("");
    modelSel.value = preselectModelId && [...modelSel.options].some((o) => o.value === preselectModelId)
      ? preselectModelId
      : provider.models.length
        ? provider.models[0].id
        : CUSTOM;
    keyField.hidden = provider.keyless;
    keyLabel.textContent = provider.key_label || "API key";
    keyInput.placeholder = provider.key_placeholder || "sk-…";
    baseField.hidden = !provider.needs_base;
    refreshCustomVisibility();
  }

  // Restore a saved selection, else default to the first provider.
  if (saved && providerById[saved.provider]) {
    providerSel.value = saved.provider;
    const provider = providerById[saved.provider];
    const bareId = stripPrefix(saved.model, provider.prefix);
    const known = provider.models.some((m) => m.id === bareId);
    renderProvider(known ? bareId : CUSTOM);
    if (!known) customInput.value = bareId;
    if (saved.apiKey) keyInput.value = saved.apiKey;
    if (saved.apiBase) baseInput.value = saved.apiBase;
  } else {
    renderProvider();
  }

  providerSel.addEventListener("change", () => renderProvider());
  modelSel.addEventListener("change", refreshCustomVisibility);

  overlay.querySelector("#mdlSave")?.addEventListener("click", () => {
    const provider = currentProvider();
    const useCustom = modelSel.value === CUSTOM || provider.models.length === 0;
    const rawId = (useCustom ? customInput.value : modelSel.value).trim();
    const apiKey = keyInput.value.trim();
    const apiBase = baseInput.value.trim();

    if (!rawId) {
      toast("Pick or enter a model id.");
      return;
    }
    if (!provider.keyless && !apiKey) {
      toast(`Enter your ${provider.key_label || "API key"}.`);
      return;
    }
    if (provider.id === "openai_compatible" && !apiBase) {
      toast("Enter the gateway Base URL.");
      return;
    }

    const model = provider.prefix ? `${provider.prefix}/${rawId}` : rawId;
    persist({
      provider: provider.id,
      model,
      apiKey,
      apiBase,
      keyless: provider.keyless,
      // OpenAI-compatible gateways route via an explicit provider (id shape can't be inferred).
      customProvider: provider.id === "openai_compatible" ? "openai" : null,
    });
    overlay.remove();
    toast(`${prettyModel(model)} set for this session.`);
    onChange?.();
  });

  overlay.querySelector("#mdlClear")?.addEventListener("click", () => {
    clear();
    overlay.remove();
    toast("Using the deterministic engine.");
    onChange?.();
  });

  setTimeout(() => providerSel?.focus(), 50);
}
