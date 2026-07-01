// Thin client over the Handoff FastAPI backend. All boundary calls validated.

async function request(method, url, body) {
  let response;
  try {
    response = await fetch(url, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (networkError) {
    throw new Error(`Network error reaching ${url}: ${networkError.message}`);
  }
  const text = await response.text();
  let payload = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }
  if (!response.ok) {
    const detail = payload && payload.detail ? payload.detail : `${response.status} ${response.statusText}`;
    throw new Error(detail);
  }
  return payload;
}

// The backend is stateless: it compiles, simulates, and assembles audit exports from the
// artifacts the client sends. Persistence (saved blueprints + run ledger) lives in store.js.
export const api = {
  runtime: () => request("GET", "/api/runtime"),
  models: () => request("GET", "/api/models"),
  demos: () => request("GET", "/api/demos"),
  analyze: (input) => request("POST", "/api/analyze", input),
  simulate: (body) => request("POST", "/api/simulate", body),
  audit: (body) => request("POST", "/api/audit", body),
};
