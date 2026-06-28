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

export const api = {
  runtime: () => request("GET", "/api/runtime"),
  demos: () => request("GET", "/api/demos"),
  analyze: (input) => request("POST", "/api/analyze", input),
  blueprint: (id) => request("GET", `/api/blueprints/${encodeURIComponent(id)}`),
  simulate: (id) => request("POST", `/api/blueprints/${encodeURIComponent(id)}/simulate`),
  audit: (runId) => request("GET", `/api/runs/${encodeURIComponent(runId)}/audit`),
};
