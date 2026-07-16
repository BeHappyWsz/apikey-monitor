export const $ = (selector, root = document) => root.querySelector(selector);
export const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

export const statusLabel = {
  up: "??",
  down: "??",
  auth_error: "????",
  rate_limited: "??",
  degraded: "??",
  unknown: "??",
};

export function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[char]));
}

export function toast(message, timeout = 2600) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.add("show");
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.classList.remove("show"), timeout);
}

export async function copyText(text, label = "??") {
  try {
    await navigator.clipboard.writeText(text || "");
    toast(`${label}???`);
  } catch {
    toast("??????????", 4200);
  }
}

/** Trigger browser download for a text blob. */
export function downloadText(filename, text) {
  const blob = new Blob([text ?? ""], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename || "download.txt";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Timestamped export filename, e.g. apikey-backup-20260716-1530.json */
export function exportFilename(fmt, prefix = "apikey-export") {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  const stamp = `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}`;
  const ext = { json: "json", env: "env", powershell: "ps1", claude: "sh", codex: "sh" }[fmt] || "txt";
  return `${prefix}-${stamp}.${ext}`;
}

export function relativeTime(ts) {
  if (!ts) return "??";
  const diff = Math.max(0, Math.floor(Date.now() / 1000 - ts));
  if (diff < 60) return `${diff}??`;
  if (diff < 3600) return `${Math.floor(diff / 60)}???`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}???`;
  return `${Math.floor(diff / 86400)}??`;
}

export function maskKey(key) {
  key = String(key || "");
  return key.length < 12 ? "????????" : `${key.slice(0, 5)}??????${key.slice(-4)}`;
}

export function formatImportSummary(result) {
  const added = Number(result?.count || 0);
  const dup = Number(result?.skipped_duplicate || 0);
  const invalid = Number(result?.skipped_invalid || 0);
  const parts = [`?? ${added} ?`];
  if (dup) parts.push(`???? ${dup}`);
  if (invalid) parts.push(`?? ${invalid}`);
  return parts.join(" ? ");
}

export function formatCheckSummary(result, { modelOnly = false } = {}) {
  const labelMap = statusLabel;
  if (modelOnly) {
    const status = result?.model_status || "unknown";
    const latency = result?.model_latency_ms;
    const err = result?.model_error || "";
    const base = `${labelMap[status] || status}${latency != null ? ` ? ${latency}ms` : ""}`;
    return err && status !== "up" ? `${base} ? ${String(err).slice(0, 60)}` : base;
  }
  const status = result?.status || "unknown";
  const latency = result?.latency_ms;
  const err = result?.error || "";
  const base = `${labelMap[status] || status}${latency != null ? ` ? ${latency}ms` : ""}`;
  return err && status !== "up" ? `${base} ? ${String(err).slice(0, 60)}` : base;
}
