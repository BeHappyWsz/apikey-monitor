import { request, waitForHealth } from "./js/api.js";
import { canReorder, getVisibleKeys, keysFingerprint, moveKey, selectCurrentResults, selectionSummary } from "./js/state.js";
import { initDialogs, openModal, closeModal } from "./js/dialogs.js";
import { createTaskController } from "./js/tasks.js";
import { initImport } from "./js/import.js";
import { initAdd } from "./js/add.js";
import { initEditor } from "./js/editor.js";
import { initSettings } from "./js/settings.js";
import { $, $$, copyText, downloadText, esc, exportFilename, formatCheckSummary, maskKey, relativeTime, statusLabel, toast } from "./js/utils.js";

const EXPORT_FMT_KEY = "apikeyconfig.exportFmt";
const EXPORT_FMTS = ["claude", "codex", "env", "powershell", "json"];

const state = {
  keys: [], selected: new Set(), status: "all", query: "", loading: true, loadError: "",
  checking: new Set(), editId: null, exportId: null, exportMode: "single", modelId: null,
  candidates: [], candidateSelected: new Set(), settings: {}, runtime: {}, draggingId: null,
  fingerprint: "",
};

async function api(method, path, body, options) {
  try {
    return (await request(method, path, body, options)).payload;
  } catch (error) {
    if (error.name !== "AbortError") toast(error.message || "????", 4200);
    throw error;
  }
}

async function load({ silent = false } = {}) {
  if (!silent) {
    state.loading = true;
    state.loadError = "";
    render();
  }
  try {
    const result = await request("GET", "/api/keys", undefined, { latest: true });
    if (!result.isLatest()) return;
    const nextKeys = result.payload;
    const nextFingerprint = keysFingerprint(nextKeys);
    const unchanged = silent && nextFingerprint === state.fingerprint && !state.checking.size;
    state.keys = nextKeys;
    state.fingerprint = nextFingerprint;
    state.loading = false;
    state.loadError = "";
    if (unchanged) {
      renderStats();
      renderFilterCounts();
      renderSelection();
      return;
    }
    render({ preserveUi: silent });
  } catch (error) {
    if (error.name === "AbortError" || silent) return;
    state.loading = false;
    state.loadError = error.message;
    render();
  }
}

function captureListUi() {
  const open = new Set();
  $$("#key-list details[open]").forEach((details) => {
    const id = Number(details.closest(".key-card")?.dataset.id);
    if (id) open.add(id);
  });
  return {
    open,
    scrollY: window.scrollY,
    activeId: document.activeElement?.closest?.(".key-card")?.dataset?.id || null,
    activeClass: document.activeElement?.className || "",
  };
}

function restoreListUi(ui) {
  if (!ui) return;
  for (const id of ui.open) {
    const details = $(`.key-card[data-id="${id}"] details`);
    if (details) details.open = true;
  }
  window.scrollTo(0, ui.scrollY || 0);
}

function render({ preserveUi = false } = {}) {
  const ui = preserveUi ? captureListUi() : null;
  renderStats();
  renderFilterCounts();
  const list = $("#key-list");
  const empty = $("#empty");
  if (state.loading) {
    list.innerHTML = Array.from({ length: 3 }, () => `<article class="key-card skeleton-card"><div></div><div></div><div></div></article>`).join("");
    empty.hidden = true;
    renderSelection();
    return;
  }
  if (state.loadError) {
    list.innerHTML = `<div class="inline-state error-state"><b>??????</b><span>${esc(state.loadError)}</span><button class="btn" id="btn-inline-retry">??</button></div>`;
    empty.hidden = true;
    $("#btn-inline-retry")?.addEventListener("click", () => load());
    renderSelection();
    return;
  }
  const rows = getVisibleKeys(state.keys, state.status, state.query);
  list.innerHTML = rows.map(card).join("");
  if (!state.keys.length) {
    empty.hidden = false;
    empty.querySelector(".empty-title").textContent = "??? Key";
    if (empty.querySelector(".empty-desc")) empty.querySelector(".empty-desc").textContent = "????????? ? ???? ? ??????????? / curl / JSON ??????????";
    const steps = empty.querySelector(".empty-steps"); if (steps) steps.hidden = false;
    const hint = empty.querySelector(".empty-hint"); if (hint) hint.hidden = false;
    const badge = empty.querySelector(".empty-badge"); if (badge) badge.hidden = false;
    empty.querySelector(".empty-actions").hidden = false;
  } else if (!rows.length) {
    empty.hidden = false;
    empty.querySelector(".empty-title").textContent = "????????";
    if (empty.querySelector(".empty-desc")) empty.querySelector(".empty-desc").textContent = "??????????????????";
    empty.querySelector(".empty-actions").hidden = true;
    const steps = empty.querySelector(".empty-steps"); if (steps) steps.hidden = true;
    const hint = empty.querySelector(".empty-hint"); if (hint) hint.hidden = true;
    const badge = empty.querySelector(".empty-badge"); if (badge) badge.hidden = true;
  } else {
    empty.hidden = true;
  }
  renderSelection(rows);
  if (preserveUi) restoreListUi(ui);
}

function card(key) {
  const busy = state.checking.has(key.id);
  const protocols = [key.supports_openai ? "OpenAI" : "", key.supports_anthropic ? "Anthropic" : ""].filter(Boolean);
  const models = key.models || [];
  const modelState = key.model_status || "unknown";
  const status = key.status || "unknown";
  const tone = status.replace(/_/g, "-");
  const sortable = canReorder(state.status, state.query);
  return `<article class="key-card status-${tone}" data-id="${key.id}" ${sortable ? 'draggable="true"' : ""}>
    <header class="card-head">
      <div class="card-title"><button class="drag-handle" type="button" ${sortable ? "" : "disabled"} title="????" aria-label="????">?</button><input class="row-sel" type="checkbox" ${state.selected.has(key.id) ? "checked" : ""} aria-label="?? ${esc(key.name || key.base_url)}"><div><h3>${esc(key.name || "??? Key")}</h3><button class="url-copy js-copy-url" type="button">${esc(key.base_url)} <span>?</span></button></div></div>
      <div class="status-panel">
        <span class="status-main ${tone}"><i class="dot ${tone}"></i>${busy ? "???" : statusLabel[status] || "??"}</span>
        <span class="status-meta"><b>${key.latency_ms == null ? "?" : `${key.latency_ms}ms`}</b><small>??</small></span>
        <span class="status-meta"><b>${relativeTime(key.last_check_at)}</b><small>????</small></span>
      </div>
    </header>
    <div class="card-body-grid">
      <div class="metric primary-metric"><span>API Key</span><b class="key-mask-line"><span>${esc(key.api_key_masked || maskKey(key.api_key))}</span><button class="link-btn js-copy-key" type="button" title="???? API Key">??</button></b></div>
      <div class="metric"><span>????</span><b>${protocols.length ? protocols.map((item) => `<em>${item}</em>`).join(" ") : "???"}</b></div>
      <div class="metric wide-metric"><span>????</span><b class="model-state ${modelState.replace(/_/g, "-")}">${esc(key.check_model || "???")} ? ${statusLabel[modelState] || "??"}</b></div>
    </div>
    <details class="card-details"><summary>??????????</summary><div><p><b>???</b>${models.length ? models.slice(0, 8).map((model) => `<span class="chip">${esc(model)}</span>`).join(" ") : "??"} ${models.length > 8 ? `<button class="link-btn js-models">???? ${models.length}</button>` : ""}</p>${key.notes ? `<p><b>???</b>${esc(key.notes)}</p>` : ""}${key.last_error ? `<p class="error-line"><b>???</b>${esc(key.last_error)}</p>` : ""}${key.model_last_error ? `<p class="error-line"><b>?????</b>${esc(key.model_last_error)}</p>` : ""}</div></details>
    <footer class="card-actions"><label class="monitor-toggle"><input class="row-mon" type="checkbox" ${key.monitor_enabled ? "checked" : ""}>??</label><button class="btn soft js-check" ${busy ? "disabled" : ""}>${busy ? "????" : "??"}</button><button class="btn ghost js-check-model">????</button><button class="btn ghost js-edit">??</button><button class="btn ghost js-export">??</button><button class="btn ghost js-copy-codex" type="button" title="???? Codex ??">Codex</button><button class="btn ghost js-copy-claude" type="button" title="???? Claude ??">Claude</button><button class="btn danger-soft js-del">??</button></footer>
  </article>`;
}

function countStatuses() {
  const counts = { all: state.keys.length, up: 0, down: 0, auth_error: 0, issue: 0, problem: 0, unknown: 0 };
  state.keys.forEach((key) => {
    const status = key.status || "unknown";
    if (status === "up") counts.up++;
    else if (status === "down") { counts.down++; counts.problem++; }
    else if (status === "auth_error") { counts.auth_error++; counts.problem++; }
    else if (status === "rate_limited" || status === "degraded") { counts.issue++; counts.problem++; }
    else { counts.unknown++; counts.problem++; }
  });
  return counts;
}

function renderStats() {
  const counts = countStatuses();
  let latencySum = 0, latencyN = 0;
  state.keys.forEach((key) => {
    if (key.latency_ms != null) { latencySum += key.latency_ms; latencyN++; }
  });
  $("#st-total").textContent = counts.all;
  $("#st-up").textContent = counts.up;
  $("#st-down").textContent = counts.down;
  $("#st-auth").textContent = counts.auth_error;
  $("#st-issue").textContent = counts.issue;
  $("#st-avg").textContent = latencyN ? `${Math.round(latencySum / latencyN)}ms` : "?";
}

function renderFilterCounts() {
  const counts = countStatuses();
  for (const [key, id] of Object.entries({
    all: "cnt-all", up: "cnt-up", down: "cnt-down", auth_error: "cnt-auth",
    issue: "cnt-issue", problem: "cnt-problem", unknown: "cnt-unknown",
  })) {
    const el = $("#" + id);
    if (el) el.textContent = counts[key];
  }
  $$(".seg").forEach((button) => button.classList.toggle("active", button.dataset.status === state.status));
}

function setBtnDisabled(el, disabled, titleWhenDisabled) {
  if (!el) return;
  if (!el.dataset.titleBase) el.dataset.titleBase = el.getAttribute("title") || "";
  el.disabled = !!disabled;
  if (disabled && titleWhenDisabled) el.title = titleWhenDisabled;
  else el.title = el.dataset.titleBase || "";
}

function updateBatchActions() {
  const hasSel = state.selected.size > 0;
  const hasKeys = state.keys.length > 0;
  setBtnDisabled($("#btn-check"), !hasSel, "??????????");
  setBtnDisabled($("#btn-export-selected"), !hasSel, "??????????");
  setBtnDisabled($("#btn-delete"), !hasSel, "??????????");
  setBtnDisabled($("#btn-check-mobile"), !hasSel, "??????????");
  setBtnDisabled($("#btn-export-mobile"), !hasSel, "??????????");
  setBtnDisabled($("#btn-delete-mobile"), !hasSel, "??????????");
  setBtnDisabled($("#btn-backup-all"), !hasKeys, "??????? Key");
}

function renderSelection(rows = getVisibleKeys(state.keys, state.status, state.query)) {
  const summary = selectionSummary(state.selected, rows);
  const bar = $("#selection-bar");
  $("#sel-all").checked = rows.length > 0 && summary.visible === rows.length;
  $("#sel-all").indeterminate = summary.visible > 0 && summary.visible < rows.length;
  $("#selection-summary").textContent = `??? ${summary.total} ??????? ${summary.resultTotal} ?${summary.hidden ? `????? ${summary.hidden} ?` : ""}?`;
  bar.classList.toggle("active", summary.total > 0);
  updateBatchActions();
}

function readSavedExportFmt() {
  try {
    const saved = localStorage.getItem(EXPORT_FMT_KEY);
    if (saved && EXPORT_FMTS.includes(saved)) return saved;
  } catch { /* ignore */ }
  return "claude";
}

function saveExportFmt(fmt) {
  try {
    if (EXPORT_FMTS.includes(fmt)) localStorage.setItem(EXPORT_FMT_KEY, fmt);
  } catch { /* ignore */ }
}

function closeMoreMenu() {
  const menu = $("#more-dropdown");
  const btn = $("#btn-more");
  if (!menu || menu.hidden) return;
  menu.hidden = true;
  if (btn) btn.setAttribute("aria-expanded", "false");
}

function toggleMoreMenu() {
  const menu = $("#more-dropdown");
  const btn = $("#btn-more");
  if (!menu) return;
  const next = !menu.hidden;
  menu.hidden = next;
  if (btn) btn.setAttribute("aria-expanded", next ? "false" : "true");
}

const taskController = createTaskController({
  api,
  load,
  openModal,
  closeModal,
  onTaskDone: ({ filter } = {}) => {
    if (filter) {
      state.status = filter;
      state.query = "";
      if ($("#filter")) $("#filter").value = "";
      render();
      toast("????????????", 2800);
    }
  },
});
const editor = initEditor({ api, state, load, openModal, closeModal });
initDialogs();
initImport({ api, state, load, openModal, closeModal, startTask: taskController.startTask });
initAdd({ api, load, openModal, closeModal });
initSettings({ api, state, openModal, closeModal, waitForHealth });

$("#sel-all").addEventListener("change", (event) => {
  state.selected = selectCurrentResults(state.selected, getVisibleKeys(state.keys, state.status, state.query), event.target.checked);
  render();
});
$("#filter").addEventListener("input", (event) => { state.query = event.target.value; render(); });
$("#status-filter").addEventListener("click", (event) => {
  const button = event.target.closest(".seg");
  if (button) { state.status = button.dataset.status; render(); }
});
$("#btn-refresh").addEventListener("click", () => { closeMoreMenu(); load(); });
$("#btn-more")?.addEventListener("click", (event) => {
  event.stopPropagation();
  toggleMoreMenu();
});
document.addEventListener("click", (event) => {
  if (!event.target.closest?.("#more-menu")) closeMoreMenu();
});
$("#btn-backup-all")?.addEventListener("click", async () => {
  closeMoreMenu();
  if (!state.keys.length) return toast("??????? Key");
  const result = await api("GET", "/api/keys/export_all");
  state.exportId = null;
  state.exportMode = "backup";
  $("#exp-fmt").value = "json";
  $("#exp-fmt").disabled = true;
  $("#exp-meta").textContent = `???? ? ${result.count || state.keys.length} ? JSON`;
  $("#exp-text").value = result.text || "";
  openModal("modal-export");
});

$("#key-list").addEventListener("click", async (event) => {
  const cardEl = event.target.closest(".key-card");
  const id = Number(cardEl?.dataset.id);
  const key = state.keys.find((value) => value.id === id);
  if (!key) return;
  if (event.target.closest(".js-copy-url")) return copyText(key.base_url, "Base URL");
  if (event.target.closest(".js-copy-key")) {
    try {
      const secret = await api("GET", `/api/keys/${id}/secret`);
      if (!secret.api_key) return toast("???????? API Key");
      return copyText(secret.api_key, "API Key");
    } catch { return; }
  }
  if (event.target.closest(".js-copy-codex")) return quickCopyExport(id, "codex", "Codex ??");
  if (event.target.closest(".js-copy-claude")) return quickCopyExport(id, "claude", "Claude ??");
  if (event.target.closest(".js-edit")) return editor.openEdit(key);
  if (event.target.closest(".js-models")) return openModels(key);
  if (event.target.closest(".js-export")) {
    state.exportId = id;
    state.exportMode = "single";
    $("#exp-fmt").disabled = false;
    $("#exp-fmt").value = readSavedExportFmt();
    $("#exp-meta").textContent = key.name || key.base_url;
    openModal("modal-export");
    return updateExport();
  }
  if (event.target.closest(".js-del")) return deleteOne(key);
  if (event.target.closest(".js-check") || event.target.closest(".js-check-model")) return checkOne(key, Boolean(event.target.closest(".js-check-model")));
});

$("#key-list").addEventListener("change", (event) => {
  const id = Number(event.target.closest(".key-card")?.dataset.id);
  if (event.target.classList.contains("row-sel")) {
    event.target.checked ? state.selected.add(id) : state.selected.delete(id);
    renderSelection();
  }
  if (event.target.classList.contains("row-mon")) {
    api("PUT", `/api/keys/${id}`, { monitor_enabled: event.target.checked ? 1 : 0 }).catch(() => load());
  }
});

$("#key-list").addEventListener("dragstart", (event) => {
  if (!canReorder(state.status, state.query)) return event.preventDefault();
  const cardEl = event.target.closest(".key-card");
  if (!cardEl) return;
  state.draggingId = Number(cardEl.dataset.id);
  cardEl.classList.add("dragging");
  event.dataTransfer.effectAllowed = "move";
  event.dataTransfer.setData("text/plain", String(state.draggingId));
});

$("#key-list").addEventListener("dragover", (event) => {
  if (!state.draggingId || !canReorder(state.status, state.query)) return;
  const cardEl = event.target.closest(".key-card");
  if (!cardEl || Number(cardEl.dataset.id) === state.draggingId) return;
  event.preventDefault();
  cardEl.classList.add("drag-over");
});

$("#key-list").addEventListener("dragleave", (event) => {
  event.target.closest(".key-card")?.classList.remove("drag-over");
});

$("#key-list").addEventListener("drop", async (event) => {
  const target = event.target.closest(".key-card");
  const sourceId = state.draggingId;
  clearDragState();
  if (!sourceId || !target || !canReorder(state.status, state.query)) return;
  const targetId = Number(target.dataset.id);
  const previous = state.keys;
  state.keys = moveKey(state.keys, sourceId, targetId);
  state.fingerprint = keysFingerprint(state.keys);
  render();
  try {
    await api("POST", "/api/keys/reorder", { ids: state.keys.map((key) => key.id) });
    toast("?????");
  } catch {
    state.keys = previous;
    state.fingerprint = keysFingerprint(state.keys);
    render();
  }
});

$("#key-list").addEventListener("dragend", clearDragState);

function clearDragState() {
  state.draggingId = null;
  $$(".key-card.dragging,.key-card.drag-over").forEach((item) => item.classList.remove("dragging", "drag-over"));
}

$("#btn-check").addEventListener("click", async () => {
  if (!state.selected.size) return toast("??????????");
  taskController.startTask(await api("POST", "/api/keys/batch_check", { ids: [...state.selected] }));
});
$("#btn-check-mobile").addEventListener("click", () => $("#btn-check").click());
$("#btn-delete-mobile").addEventListener("click", () => $("#btn-delete").click());
$("#btn-export-mobile")?.addEventListener("click", () => $("#btn-export-selected").click());
$("#btn-export-selected").addEventListener("click", () => { closeMoreMenu(); exportSelected(); });
$("#btn-delete").addEventListener("click", async () => {
  closeMoreMenu();
  const rows = getVisibleKeys(state.keys, state.status, state.query);
  const summary = selectionSummary(state.selected, rows);
  if (!summary.total) return toast("??????????");
  if (!confirm(`???? ${summary.total} ??${summary.hidden ? `?? ${summary.hidden} ???????` : ""}`)) return;
  const result = await api("POST", "/api/keys/batch_delete", { ids: [...state.selected] });
  state.selected.clear();
  toast(`??? ${result.deleted} ?`);
  await load();
});

function openModels(key) {
  state.modelId = key.id;
  $("#model-summary").textContent = `${key.name || key.base_url}?? ${(key.models || []).length} ???`;
  $("#model-list").innerHTML = (key.models || []).map((model) => `<div class="model-row"><span>${esc(model)}</span><button class="link-btn js-set-check-model" data-model="${esc(model)}">??????</button></div>`).join("") || "????";
  openModal("modal-models");
}

async function deleteOne(key) {
  if (!confirm(`?????${key.name || key.base_url}??`)) return;
  await api("DELETE", `/api/keys/${key.id}`);
  state.selected.delete(key.id);
  toast("???");
  await load();
}

async function checkOne(key, modelOnly) {
  if (modelOnly && !key.check_model) {
    toast("????????");
    return editor.openEdit(key);
  }
  state.checking.add(key.id);
  render({ preserveUi: true });
  try {
    const result = await api("POST", `/api/keys/${key.id}/${modelOnly ? "check_model" : "check"}`, modelOnly ? { model: key.check_model } : {});
    toast(formatCheckSummary(result, { modelOnly }));
  } finally {
    state.checking.delete(key.id);
    await load({ silent: true });
  }
}

async function quickCopyExport(id, fmt, label) {
  try {
    const result = await api("GET", `/api/keys/${id}/export?fmt=${fmt}`);
    if (!result?.text) return toast("??????");
    saveExportFmt(fmt);
    await copyText(result.text, label);
  } catch { /* toasted by api */ }
}

async function exportSelected() {
  if (!state.selected.size) return toast("??????????");
  state.exportMode = "batch";
  state.exportId = null;
  $("#exp-fmt").value = "json";
  $("#exp-fmt").disabled = true;
  $("#exp-meta").textContent = `?? JSON ? ${state.selected.size} ?`;
  openModal("modal-export");
  const result = await api("POST", "/api/keys/batch_export", { ids: [...state.selected], fmt: "json" });
  $("#exp-text").value = result.text || "";
}

async function updateExport() {
  if (state.exportMode === "batch" || state.exportMode === "backup") return;
  if (!state.exportId) return;
  const fmt = $("#exp-fmt").value;
  saveExportFmt(fmt);
  const result = await api("GET", `/api/keys/${state.exportId}/export?fmt=${fmt}`);
  $("#exp-text").value = result.text || "";
}

function downloadCurrentExport() {
  const text = $("#exp-text").value;
  if (!String(text || "").trim()) return toast("????????");
  let fmt = "json";
  let prefix = "apikey-export";
  if (state.exportMode === "backup") {
    fmt = "json";
    prefix = "apikey-backup";
  } else if (state.exportMode === "batch") {
    fmt = "json";
    prefix = "apikey-batch";
  } else {
    fmt = $("#exp-fmt").value || "json";
    prefix = `apikey-${fmt}`;
  }
  downloadText(exportFilename(fmt, prefix), text);
  toast("?????");
}

$("#exp-fmt").addEventListener("change", updateExport);
$("#btn-copy").addEventListener("click", () => copyText($("#exp-text").value, "??"));
$("#btn-download")?.addEventListener("click", downloadCurrentExport);
document.addEventListener("visibilitychange", () => { if (!document.hidden) load({ silent: true }); });
setInterval(() => { if (!document.hidden && !$(".modal.open")) load({ silent: true }).catch(() => {}); }, 5000);

load();
