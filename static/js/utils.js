export const $ = (selector, root = document) => root.querySelector(selector);
export const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

export const statusLabel = {
  up: "在线",
  down: "离线",
  auth_error: "认证失效",
  rate_limited: "限流",
  degraded: "异常",
  unknown: "未知",
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

/**
 * Run a user-triggered action once while making its button unavailable.
 * Keeping the original label avoids layout shifts in compact toolbars.
 */
export async function withBusyButton(button, action) {
  if (!button || button.disabled) return undefined;
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  try {
    return await action();
  } finally {
    button.disabled = false;
    button.removeAttribute("aria-busy");
  }
}

export async function copyText(text, label = "内容") {
  try {
    await navigator.clipboard.writeText(text || "");
    toast(`${label}已复制`);
  } catch {
    toast("复制失败，请手动复制", 4200);
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
  if (!ts) return "从未";
  const diff = Math.max(0, Math.floor(Date.now() / 1000 - ts));
  if (diff < 60) return `${diff}秒前`;
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`;
  return `${Math.floor(diff / 86400)}天前`;
}

export function maskKey(key) {
  key = String(key || "");
  return key.length < 12 ? "••••••••" : `${key.slice(0, 5)}••••••${key.slice(-4)}`;
}

export function formatImportSummary(result) {
  const added = Number(result?.count || 0);
  const dup = Number(result?.skipped_duplicate || 0);
  const invalid = Number(result?.skipped_invalid || 0);
  const parts = [`新增 ${added} 条`];
  if (dup) parts.push(`跳过重复 ${dup}`);
  if (invalid) parts.push(`无效 ${invalid}`);
  return parts.join(" · ");
}

export function formatCheckSummary(result, { modelOnly = false } = {}) {
  const labelMap = statusLabel;
  if (modelOnly) {
    const status = result?.model_status || "unknown";
    const latency = result?.model_latency_ms;
    const err = result?.model_error || "";
    const base = `${labelMap[status] || status}${latency != null ? ` · ${latency}ms` : ""}`;
    return err && status !== "up" ? `${base} · ${String(err).slice(0, 60)}` : base;
  }
  const status = result?.status || "unknown";
  const latency = result?.latency_ms;
  const err = result?.error || "";
  const base = `${labelMap[status] || status}${latency != null ? ` · ${latency}ms` : ""}`;
  return err && status !== "up" ? `${base} · ${String(err).slice(0, 60)}` : base;
}
