let sequence = 0;
let activeController = null;

export class ApiError extends Error {
  constructor(message, status, payload) { super(message); this.status = status; this.payload = payload; }
}

export async function request(method, path, body, { latest = false } = {}) {
  const id = ++sequence;
  if (latest && activeController) activeController.abort();
  const controller = new AbortController();
  if (latest) activeController = controller;
  const options = { method, signal: controller.signal, headers: {} };
  if (body !== undefined) { options.headers["Content-Type"] = "application/json"; options.body = JSON.stringify(body); }
  const response = await fetch(path, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(payload.message || payload.error || `HTTP ${response.status}`, response.status, payload);
  return { payload, id, isLatest: () => !latest || id === sequence };
}

export async function waitForHealth(url, timeout = 1500) {
  const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), timeout);
  try { const response = await fetch(`${url}/api/system/health`, { signal: controller.signal, cache: "no-store" }); return response.ok; }
  catch { return false; } finally { clearTimeout(timer); }
}
