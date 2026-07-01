// Session persistence in the browser. There is no server-side database and no user
// account — each visitor's saved blueprints and dry-run ledger live in their own
// localStorage, survive reloads, and never leave the device. All updates are immutable
// (read → new array → write); reads tolerate corrupt/absent data and never throw.

const BP_KEY = "handoff:blueprints:v1";
const RUN_KEY = "handoff:runs:v1";
const MAX_BLUEPRINTS = 50;
const MAX_RUNS = 100;

function read(key) {
  try {
    const parsed = JSON.parse(localStorage.getItem(key) || "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function write(key, list) {
  try {
    localStorage.setItem(key, JSON.stringify(list));
  } catch {
    /* quota or privacy mode — persistence is best-effort, the session still works */
  }
}

/* ---------------- saved blueprints ---------------- */

export function loadBlueprints() {
  return read(BP_KEY);
}

export function getBlueprint(id) {
  return loadBlueprints().find((record) => record.blueprint_id === id) || null;
}

// Save (or replace) a full compiled record, newest first, de-duped by id and source hash.
export function saveBlueprint(record) {
  const next = [
    record,
    ...loadBlueprints().filter(
      (item) => item.blueprint_id !== record.blueprint_id && item.source_hash !== record.source_hash,
    ),
  ].slice(0, MAX_BLUEPRINTS);
  write(BP_KEY, next);
  return next;
}

/* ---------------- dry-run ledger ---------------- */
// Each entry = { row, simulation }: `row` renders the ledger; `simulation` rehydrates the
// proof/audit tabs when a saved process is reopened.

export function loadRuns() {
  return read(RUN_KEY);
}

export function loadRunRows() {
  return loadRuns().map((entry) => entry.row);
}

export function latestRunForBlueprint(blueprintId) {
  return loadRuns().find((entry) => entry.row.blueprint_id === blueprintId) || null;
}

export function saveRun(entry) {
  const next = [
    entry,
    ...loadRuns().filter((item) => item.row.runId !== entry.row.runId),
  ].slice(0, MAX_RUNS);
  write(RUN_KEY, next);
  return next;
}
