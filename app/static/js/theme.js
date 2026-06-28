// Light/dark theming: follow the system preference until the user chooses,
// then remember their choice. Drives <html data-theme> and the meta theme-color.

const KEY = "handoff.theme";
const mq = window.matchMedia("(prefers-color-scheme: dark)");

const SUN =
  '<svg viewBox="0 0 20 20" fill="none" width="17" height="17"><circle cx="10" cy="10" r="3.4" stroke="currentColor" stroke-width="1.6"/><path d="M10 2.6v2M10 15.4v2M2.6 10h2M15.4 10h2M4.7 4.7l1.4 1.4M13.9 13.9l1.4 1.4M15.3 4.7l-1.4 1.4M6.1 13.9l-1.4 1.4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>';
const MOON =
  '<svg viewBox="0 0 20 20" fill="none" width="17" height="17"><path d="M16 11.5A6 6 0 018.6 4a.6.6 0 00-.8-.8A7 7 0 1016.8 12.3a.6.6 0 00-.8-.8z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/></svg>';

function resolve() {
  const saved = localStorage.getItem(KEY);
  if (saved === "light" || saved === "dark") return saved;
  return mq.matches ? "dark" : "light";
}

function apply(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", theme === "dark" ? "#131419" : "#FBFAF8");
  const btn = document.getElementById("themeToggle");
  if (btn) {
    // Show the icon for the mode you'll switch TO.
    btn.innerHTML = theme === "dark" ? SUN : MOON;
    btn.setAttribute("aria-label", theme === "dark" ? "Switch to light theme" : "Switch to dark theme");
  }
}

export function initTheme() {
  apply(resolve());
  mq.addEventListener?.("change", () => {
    if (!localStorage.getItem(KEY)) apply(mq.matches ? "dark" : "light");
  });
}

export function toggleTheme() {
  const next = (document.documentElement.getAttribute("data-theme") || "dark") === "dark" ? "light" : "dark";
  localStorage.setItem(KEY, next);
  apply(next);
}
