// feedback.js — 4 feedback primitives for the API-key monitor UI
//
// Exports:
//   LoadingBar     — global top progress bar driven by in-flight counter
//   BusyButton     — wraps a button so its click handler shows busy state
//   BusyOverlay    — wraps a region with a pointer-events-blocking mask
//   ToastStack     — singleton toast notifications
//
// All primitives share CSS variables defined in style.css under :root
// (--fb-progress, --fb-mask, --fb-spinner-size, --fb-toast-*,
//  --z-progress, --z-mask, --z-toast).

// ---------- shared in-flight counter ----------------------------------------
// Single source of truth for "is anything still pending?".
// Mutated by api-client and observed by LoadingBar.

const inFlight = { count: 0, listeners: new Set() };

export function onInFlightChange(listener) {
  inFlight.listeners.add(listener);
  listener(inFlight.count);
  return () => inFlight.listeners.delete(listener);
}

export function bumpInFlight(delta) {
  inFlight.count = Math.max(0, inFlight.count + delta);
  for (const l of inFlight.listeners) l(inFlight.count);
}

export function getInFlight() { return inFlight.count; }

// ---------- spinner SVG (shared by BusyButton / BusyOverlay) -----------------

const SPINNER_SVG = `
<svg class="fb-spinner" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
  <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-opacity="0.25" stroke-width="3"/>
  <path d="M21 12a9 9 0 0 0-9-9" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"/>
</svg>`;

// ---------- LoadingBar -------------------------------------------------------

let barEl = null;
let barFill = null;
let rafHandle = null;
let animStart = 0;
let barCount = 0;
let barVisible = false;

function ensureBar() {
  if (barEl) return;
  barEl = document.createElement("div");
  barEl.className = "fb-loading-bar";
  barEl.setAttribute("role", "progressbar");
  barEl.setAttribute("aria-valuemin", "0");
  barEl.setAttribute("aria-valuemax", "100");
  barEl.setAttribute("aria-hidden", "true");
  barFill = document.createElement("div");
  barFill.className = "fb-loading-bar-fill";
  barEl.appendChild(barFill);
  document.body.appendChild(barEl);
}

function animate(target, duration, onDone) {
  cancelAnimationFrame(rafHandle);
  const t0 = performance.now();
  const start = parseFloat(barFill.style.width) || 0;
  const change = target - start;
  function tick(now) {
    const t = Math.min(1, (now - t0) / duration);
    // easeOutCubic
    const eased = 1 - Math.pow(1 - t, 3);
    const w = start + change * eased;
    barFill.style.width = `${w}%`;
    barEl.setAttribute("aria-valuenow", String(Math.round(w)));
    if (t < 1) rafHandle = requestAnimationFrame(tick);
    else if (onDone) onDone();
  }
  rafHandle = requestAnimationFrame(tick);
}

function tickIndeterminate() {
  // Asymptotic advance: never reaches 100% while pending.
  const elapsed = performance.now() - animStart;
  const k = 0.6; // rate constant
  const w = 30 + 70 * (1 - Math.exp(-k * elapsed / 1000));
  barFill.style.width = `${Math.min(95, w)}%`;
  barEl.setAttribute("aria-valuenow", String(Math.round(w)));
  rafHandle = requestAnimationFrame(tickIndeterminate);
}

export function LoadingBar() {
  // mount the singleton and start observing the in-flight counter
  ensureBar();
  onInFlightChange((count) => {
    barCount = count;
    if (count > 0) {
      barEl.setAttribute("aria-hidden", "false");
      barEl.classList.add("active");
      barVisible = true;
      animStart = performance.now();
      cancelAnimationFrame(rafHandle);
      tickIndeterminate();
    } else if (barVisible) {
      cancelAnimationFrame(rafHandle);
      // complete to 100%, then fade out
      animate(100, 220, () => {
        barEl.classList.add("complete");
        setTimeout(() => {
          if (barCount === 0) {
            barEl.classList.remove("active", "complete");
            barEl.setAttribute("aria-hidden", "true");
            barFill.style.width = "0%";
            barVisible = false;
          }
        }, 260);
      });
    }
  });
}

// ---------- BusyButton ------------------------------------------------------
//
// Wrap a real <button> so a click automatically:
//   - sets aria-busy + disabled
//   - swaps label to busyLabel and prepends spinner
//   - awaits the provided async handler
//   - re-enables on completion (success or error)
//
// The button is rendered server-side in index.html, so we hook existing
// elements. New buttons can call bindBusyButton() to get the same wiring.

const busyRegistry = new WeakMap();

function setBusy(button, busy, busyLabel) {
  const data = button.dataset || (button.dataset = {});
  const hasClassList = Boolean(button.classList);
  if (busy) {
    if (!data.fbIdleLabel) {
      data.fbIdleLabel = button.textContent || "";
    }
    if (hasClassList) button.classList.add("fb-busy");
    button.setAttribute("aria-busy", "true");
    button.disabled = true;
    if (busyLabel) button.textContent = busyLabel;
    else if (button.querySelector && !button.querySelector(".fb-spinner") && button.insertAdjacentHTML) {
      button.insertAdjacentHTML("afterbegin", SPINNER_SVG);
    }
  } else {
    if (hasClassList) button.classList.remove("fb-busy");
    button.removeAttribute("aria-busy");
    button.disabled = false;
    if (data.fbIdleLabel) {
      // remove spinner if any
      const sp = button.querySelector?.(".fb-spinner");
      if (sp) sp.remove();
      button.textContent = data.fbIdleLabel;
    }
  }
}

export function bindBusyButton(button, handler, options = {}) {
  if (!button || busyRegistry.has(button)) return;
  const { busyLabel = "处理中…" } = options;
  const wrapped = async (event) => {
    if (button.disabled || button.classList.contains("fb-busy")) return;
    setBusy(button, true, busyLabel);
    try {
      await handler(event);
    } finally {
      setBusy(button, false);
    }
  };
  busyRegistry.set(button, wrapped);
  button.addEventListener("click", wrapped);
}

export function setButtonBusy(button, busy) {
  setBusy(button, busy, button.dataset?.fbBusyLabel);
}

// ---------- BusyOverlay -----------------------------------------------------
//
// Wrap any region so that setting busy=true shows a semi-transparent
// mask with a spinner, blocking pointer events.
//
// Usage:
//   const overlay = BusyOverlay(document.getElementById("key-list"));
//   overlay(true);    // mask on
//   overlay(false);   // mask off
//
// The region must be position:relative (or static, the wrapper injects
// one if needed). We never apply a global fixed overlay — the mask is
// scoped to the region.

export function BusyOverlay(region, options = {}) {
  if (!region) return () => {};
  const { text = "加载中…" } = options;
  // ensure positioning context
  if (getComputedStyle(region).position === "static") {
    region.style.position = "relative";
  }
  let mask = null;
  function ensureMask() {
    if (mask) return mask;
    mask = document.createElement("div");
    mask.className = "fb-busy-overlay";
    mask.setAttribute("aria-hidden", "true");
    mask.innerHTML = `<div class="fb-busy-overlay-inner">${SPINNER_SVG}<span class="fb-busy-overlay-text">${text}</span></div>`;
    region.appendChild(mask);
    return mask;
  }
  return function setBusy(active) {
    if (active) {
      const m = ensureMask();
      region.setAttribute("aria-busy", "true");
      region.classList.add("fb-busy-region");
      requestAnimationFrame(() => m.classList.add("active"));
    } else if (mask) {
      mask.classList.remove("active");
      region.removeAttribute("aria-busy");
      region.classList.remove("fb-busy-region");
      // leave mask in DOM for reuse
    }
  };
}

// ---------- ToastStack ------------------------------------------------------
//
// Singleton stack in the top-right. Auto-dismiss after ttlMs (errors
// get a longer ttl). Click to dismiss. role=status for non-errors,
// role=alert for errors.

let toastRoot = null;
let toastSeq = 0;
const activeToasts = new Map();

function ensureToastRoot() {
  if (toastRoot) return;
  toastRoot = document.createElement("div");
  toastRoot.className = "fb-toast-stack";
  toastRoot.setAttribute("role", "region");
  toastRoot.setAttribute("aria-label", "通知");
  document.body.appendChild(toastRoot);
}

function classifyMessage(message) {
  const m = String(message || "");
  if (/^(success|ok|saved|created|updated|deleted|copied|uploaded|completed|已保存|已创建|已更新|已删除|已复制|已上传|已完成|成功)/i.test(m) ||
      /✓/.test(m)) return "success";
  if (/^(error|fail|failed|invalid|forbidden|unauthorized|not found|错误|失败|无效|未授权|未找到|✗)/i.test(m) ||
      /[！!]/.test(m) && /(失败|错误)/.test(m)) return "error";
  return "info";
}

export function toast(message, ttlMs = 3000) {
  ensureToastRoot();
  const kind = classifyMessage(message);
  const ttl = kind === "error" ? Math.max(ttlMs, 6000) : ttlMs;
  const id = ++toastSeq;
  const el = document.createElement("div");
  el.className = `fb-toast fb-toast-${kind}`;
  el.setAttribute("role", kind === "error" ? "alert" : "status");
  el.dataset.id = String(id);
  el.textContent = message;
  toastRoot.appendChild(el);
  requestAnimationFrame(() => el.classList.add("active"));
  const handle = setTimeout(() => dismiss(id), ttl);
  activeToasts.set(id, { el, handle });
  el.addEventListener("click", () => dismiss(id));
  return id;
}

export function dismiss(id) {
  const entry = activeToasts.get(id);
  if (!entry) return;
  clearTimeout(entry.handle);
  entry.el.classList.remove("active");
  entry.el.classList.add("leaving");
  setTimeout(() => entry.el.remove(), 220);
  activeToasts.delete(id);
}

/**
 * Lightweight modal confirmation — replaces native `confirm()` so the
 * confirmation matches the page's visual style instead of the browser's
 * default chrome. Returns a Promise<boolean>.
 *
 * Usage:
 *   if (!await confirmAction("确认删除？")) return;
 */
export function confirmAction(message, { okLabel = "确认", cancelLabel = "取消", danger = false } = {}) {
  return new Promise((resolve) => {
    const mask = document.createElement("div");
    mask.className = "fb-confirm-mask";
    mask.innerHTML = `
      <div class="fb-confirm-card" role="alertdialog" aria-modal="true" aria-labelledby="fb-confirm-msg">
        <p id="fb-confirm-msg">${message}</p>
        <div class="fb-confirm-actions">
          <button type="button" class="btn ghost fb-confirm-cancel">${cancelLabel}</button>
          <button type="button" class="btn ${danger ? "danger" : "primary"} fb-confirm-ok">${okLabel}</button>
        </div>
      </div>`;
    document.body.appendChild(mask);
    requestAnimationFrame(() => mask.classList.add("active"));
    const cleanup = (result) => { mask.classList.remove("active"); setTimeout(() => mask.remove(), 160); resolve(result); };
    mask.querySelector(".fb-confirm-cancel").addEventListener("click", () => cleanup(false));
    mask.querySelector(".fb-confirm-ok").addEventListener("click", () => cleanup(true));
    mask.addEventListener("click", (event) => { if (event.target === mask) cleanup(false); });
    document.addEventListener("keydown", function onKey(event) {
      if (event.key === "Escape") { document.removeEventListener("keydown", onKey); cleanup(false); }
      else if (event.key === "Enter") { document.removeEventListener("keydown", onKey); cleanup(true); }
    });
    setTimeout(() => mask.querySelector(".fb-confirm-ok")?.focus(), 0);
  });
}

export function ToastStack() {
  ensureToastRoot();
}
