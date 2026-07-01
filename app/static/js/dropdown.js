import { esc, ICON, titleize } from "./util.js";

const CUSTOM_DOMAINS_KEY = "handoff.customDomains";

const CHEVRON =
  '<svg class="ico" viewBox="0 0 16 16" fill="none"><path d="M4 6l4 4 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>';

// ---- Custom-domain persistence (best-effort; never throws) ----

export function loadCustomDomains() {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(CUSTOM_DOMAINS_KEY) || "[]");
    if (!Array.isArray(parsed)) return [];
    return [...new Set(parsed.map(normalizeDomain).filter(Boolean))];
  } catch {
    return [];
  }
}

function persistCustomDomain(value) {
  try {
    const next = [...new Set([...loadCustomDomains(), value])];
    window.localStorage.setItem(CUSTOM_DOMAINS_KEY, JSON.stringify(next));
  } catch {
    // Storage unavailable / quota exceeded — the option still lives for this
    // session, we just can't remember it. Non-fatal.
  }
}

// snake_case, alphanumerics only, capped to the server's 80-char domain limit.
export function normalizeDomain(raw) {
  return String(raw || "")
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, "_")
    .replace(/[^a-z0-9_]/g, "")
    .replace(/_+/g, "_")
    .replace(/^_|_$/g, "")
    .slice(0, 80);
}

// ---- Enhancer ----

export function enhanceSelect(select, options = {}) {
  if (!select || select.dataset.enhanced === "true") return null;
  const { renderIcon, allowAdd = false, addLabel = "Add domain", persist = false } = options;
  select.dataset.enhanced = "true";

  const icon = typeof renderIcon === "function" ? renderIcon : null;
  const labelText =
    select.closest(".field")?.querySelector("label")?.textContent?.trim() || "Select";

  // Move the native select into a positioned wrapper and hide it (still focusable
  // by assistive tech is undesirable here — the trigger is the a11y proxy).
  const wrap = document.createElement("div");
  wrap.className = "select";
  select.parentNode.insertBefore(wrap, select);
  wrap.appendChild(select);
  select.classList.add("select__native");
  select.tabIndex = -1;
  select.setAttribute("aria-hidden", "true");

  const trigger = document.createElement("button");
  trigger.type = "button";
  trigger.className = "select__trigger";
  trigger.setAttribute("aria-haspopup", "listbox");
  trigger.setAttribute("aria-expanded", "false");
  trigger.setAttribute("aria-label", labelText);

  const menu = document.createElement("ul");
  menu.className = "select__menu";
  menu.setAttribute("role", "listbox");
  menu.hidden = true;

  wrap.appendChild(trigger);
  wrap.appendChild(menu);

  let open = false;

  const currentOption = () => select.options[select.selectedIndex] || select.options[0];

  function renderTrigger() {
    const opt = currentOption();
    trigger.innerHTML = `
      <span class="select__val">
        ${icon ? `<span class="select__ico">${icon(opt ? opt.value : "")}</span>` : ""}
        <span class="select__label">${esc(titleize(opt ? opt.textContent : ""))}</span>
      </span>
      <span class="select__chevron">${CHEVRON}</span>`;
  }

  function buildMenu() {
    const rows = [...select.options].map((opt, i) => {
      const selected = i === select.selectedIndex;
      return `
        <li class="select__opt${selected ? " is-selected" : ""}" role="option"
            aria-selected="${selected}" data-value="${esc(opt.value)}" tabindex="-1">
          ${icon ? `<span class="select__ico">${icon(opt.value)}</span>` : ""}
          <span class="select__opt-label">${esc(titleize(opt.textContent))}</span>
          <span class="select__check">${ICON.check}</span>
        </li>`;
    });
    const addRow = allowAdd
      ? `<li class="select__add" data-add="1" tabindex="-1">${ICON.plus}<span>${esc(addLabel)}</span></li>`
      : "";
    menu.innerHTML = rows.join("") + addRow;
  }

  function openMenu() {
    if (open) return;
    buildMenu();
    menu.hidden = false;
    open = true;
    trigger.setAttribute("aria-expanded", "true");
    wrap.classList.add("is-open");
    (menu.querySelector(".select__opt.is-selected") || menu.querySelector(".select__opt"))?.focus();
    document.addEventListener("click", onDocClick, true);
  }

  function closeMenu(focusTrigger = false) {
    if (!open) return;
    menu.hidden = true;
    open = false;
    trigger.setAttribute("aria-expanded", "false");
    wrap.classList.remove("is-open");
    document.removeEventListener("click", onDocClick, true);
    if (focusTrigger) trigger.focus();
  }

  function choose(value) {
    if (select.value !== value) {
      select.value = value;
      select.dispatchEvent(new Event("change", { bubbles: true }));
    }
    renderTrigger();
    closeMenu(true);
  }

  function startAdd() {
    const addLi = menu.querySelector(".select__add");
    if (!addLi) return;
    addLi.classList.add("is-editing");
    addLi.innerHTML = '<input class="select__add-input" type="text" placeholder="Domain name" maxlength="80" />';
    const input = addLi.querySelector("input");
    input.focus();

    const cancel = () => {
      buildMenu();
      menu.querySelector(".select__opt")?.focus();
    };
    const commit = () => {
      const value = normalizeDomain(input.value);
      if (!value) {
        cancel();
        return;
      }
      if (![...select.options].some((o) => o.value === value)) {
        select.add(new Option(titleize(value), value));
        if (persist) persistCustomDomain(value);
      }
      choose(value);
    };

    input.addEventListener("keydown", (e) => {
      e.stopPropagation(); // keep arrow/enter out of the menu navigator
      if (e.key === "Enter") {
        e.preventDefault();
        commit();
      } else if (e.key === "Escape") {
        e.preventDefault();
        cancel();
      }
    });
  }

  function onDocClick(e) {
    if (!wrap.contains(e.target)) closeMenu();
  }

  function onKeydown(e) {
    if (!open) return;
    const items = [...menu.querySelectorAll(".select__opt, .select__add")];
    const idx = items.indexOf(document.activeElement);
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      closeMenu(true);
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      e.stopPropagation();
      (items[idx + 1] || items[0])?.focus();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      e.stopPropagation();
      (items[idx - 1] || items[items.length - 1])?.focus();
    } else if (e.key === "Enter" || e.key === " ") {
      const el = document.activeElement;
      if (el.classList.contains("select__add")) {
        e.preventDefault();
        e.stopPropagation();
        startAdd();
      } else if (el.classList.contains("select__opt")) {
        e.preventDefault();
        e.stopPropagation();
        choose(el.dataset.value);
      }
    }
  }

  trigger.addEventListener("click", (e) => {
    e.preventDefault();
    open ? closeMenu() : openMenu();
  });
  trigger.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" && !open) {
      e.preventDefault();
      openMenu();
    }
  });
  menu.addEventListener("keydown", onKeydown);
  menu.addEventListener("click", (e) => {
    const opt = e.target.closest(".select__opt");
    if (opt) {
      choose(opt.dataset.value);
      return;
    }
    const add = e.target.closest(".select__add");
    if (add && !add.classList.contains("is-editing")) startAdd();
  });
  select.addEventListener("change", renderTrigger);

  renderTrigger();
  return { refresh: renderTrigger };
}
