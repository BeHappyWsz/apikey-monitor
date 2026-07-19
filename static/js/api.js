import { bumpInFlight, toast } from "./feedback.js";

let sequence = 0;
let activeController = null;
let csrfToken = "";
const pendingRequests = new Map(); // idempotency dedupe: key -> true

export function setCsrfToken(value) { csrfToken = String(value || ""); }

export class ApiError extends Error {
  constructor(message, status, payload) { super(message); this.status = status; this.payload = payload; }
}

function hashBody(body) {
  if (body == null) return "";
  try { return JSON.stringify(body); } catch { return String(body); }
}

function dedupeKey(method, path, body) {
  return `${method} ${path} ${hashBody(body)}`;
}

export async function request(method, path, body, { latest = false, silent = false } = {}) {
  let key = null;
  if (method !== "GET" && method !== "HEAD") {
    key = dedupeKey(method, path, body);
    if (pendingRequests.has(key)) {
      throw new ApiError("请求正在进行中，请勿重复提交", 409, { duplicate: true });
    }
    pendingRequests.set(key, true);
  }

  const id = ++sequence;
  bumpInFlight(+1);

  if (latest && activeController) activeController.abort();
  const controller = new AbortController();
  if (latest) activeController = controller;

  const options = { method, signal: controller.signal, headers: {} };
  if ((method === "POST" || method === "PUT" || method === "DELETE") && csrfToken) {
    options.headers["X-CSRF-Token"] = csrfToken;
  }
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }

  try {
    const response = await fetch(path, options);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const err = new ApiError(payload.message || payload.error || `HTTP ${response.status}`, response.status, payload);
      if (!silent) toast(err.message, 4200);
      throw err;
    }
    return { payload, id, isLatest: () => !latest || id === sequence };
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error.name === "AbortError") throw error;
    if (!silent) toast(error.message || "网络请求失败", 4200);
    throw error;
  } finally {
    bumpInFlight(-1);
    if (latest && activeController === controller) activeController = null;
    if (key) pendingRequests.delete(key);
  }
}

export async function waitForHealth(url, timeout = 1500) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(`${url}/api/system/health`, { signal: controller.signal, cache: "no-store" });
    return response.ok;
  } catch { return false; }
  finally { clearTimeout(timer); }
}