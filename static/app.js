import { request, waitForHealth } from "./js/api.js";
import { canReorder, getVisibleKeys, keysFingerprint, moveKey, selectCurrentResults, selectionSummary } from "./js/state.js";
import { initDialogs, openModal, closeModal } from "./js/dialogs.js";
import { createTaskController } from "./js/tasks.js";
import { initImport } from "./js/import.js";
import { initAdd } from "./js/add.js";
import { initEditor } from "./js/editor.js";
import { initSettings } from "./js/settings.js";
import { $, $$, copyText, esc, formatCheckSummary, maskKey, relativeTime, statusLabel, toast } from "./js/utils.js";

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
    if (error.name !== "AbortError") toast(error.message || "请求失败", 4200);
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
    list.innerHTML = `<div class="inline-state error-state"><b>列表加载失败</b><span>${esc(state.loadError)}</span><button class="btn" id="btn-inline-retry">重试</button></div>`;
    empty.hidden = true;
    $("#btn-inline-retry")?.addEventListener("click", () => load());
    renderSelection();
    return;
  }
  const rows = getVisibleKeys(state.keys, state.status, state.query);
  list.innerHTML = rows.map(card).join("");
  if (!state.keys.length) {
    empty.hidden = false;
    empty.querySelector(".empty-title").textContent = "还没有 Key";
    if (empty.querySelector(".empty-desc")) empty.querySelector(".empty-desc").textContent = "三步开始：粘贴配置 → 预览确认 → 自动检测。支持环境变量 / curl / JSON 备份，也可手动添加。";
      const steps = empty.querySelector(".empty-steps"); if (steps) steps.hidden = false;
      const hint = empty.querySelector(".empty-hint"); if (hint) hint.hidden = false;
      const badge = empty.querySelector(".empty-badge"); if (badge) badge.hidden = false;
    empty.querySelector(".empty-actions").hidden = false;
  } else if (!rows.length) {
    empty.hidden = false;
    empty.querySelector(".empty-title").textContent = "当前筛选没有结果";
    if (empty.querySelector(".empty-desc")) empty.querySelector(".empty-desc").textContent = "试试切换状态筛选，或清空搜索关键字。";
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
      <div class="card-title"><button class="drag-handle" type="button" ${sortable ? "" : "disabled"} title="拖拽排序" aria-label="拖拽排序">☰</button><input class="row-sel" type="checkbox" ${state.selected.has(key.id) ? "checked" : ""} aria-label="选择 ${esc(key.name || key.base_url)}"><div><h3>${esc(key.name || "未命名 Key")}</h3><button class="url-copy js-copy-url" type="button">${esc(key.base_url)} <span>⧉</span></button></div></div>
      <div class="status-panel">
        <span class="status-main ${tone}"><i class="dot ${tone}"></i>${busy ? "检测中" : statusLabel[status] || "未知"}</span>
        <span class="status-meta"><b>${key.latency_ms == null ? "—" : `${key.latency_ms}ms`}</b><small>延迟</small></span>
        <span class="status-meta"><b>${relativeTime(key.last_check_at)}</b><small>最近检测</small></span>
      </div>
    </header>
    <div class="card-body-grid">
      <div class="metric primary-metric"><span>API Key</span><b class="key-mask-line"><span>${esc(key.api_key_masked || maskKey(key.api_key))}</span><button class="link-btn js-copy-key" type="button" title="复制完整 API Key">复制</button></b></div>
      <div class="metric"><span>协议能力</span><b>${protocols.length ? protocols.map((item) => `<em>${item}</em>`).join(" ") : "待检测"}</b></div>
      <div class="metric wide-metric"><span>模型检测</span><b class="model-state ${modelState.replace(/_/g, "-")}">${esc(key.check_model || "未设置")} · ${statusLabel[modelState] || "未知"}</b></div>
    </div>
    <details class="card-details"><summary>模型、备注与错误详情</summary><div><p><b>模型：</b>${models.length ? models.slice(0, 8).map((model) => `<span class="chip">${esc(model)}</span>`).join(" ") : "暂无"} ${models.length > 8 ? `<button class="link-btn js-models">查看全部 ${models.length}</button>` : ""}</p>${key.notes ? `<p><b>备注：</b>${esc(key.notes)}</p>` : ""}${key.last_error ? `<p class="error-line"><b>错误：</b>${esc(key.last_error)}</p>` : ""}${key.model_last_error ? `<p class="error-line"><b>模型错误：</b>${esc(key.model_last_error)}</p>` : ""}</div></details>
    <footer class="card-actions"><label class="monitor-toggle"><input class="row-mon" type="checkbox" ${key.monitor_enabled ? "checked" : ""}>监测</label><button class="btn soft js-check" ${busy ? "disabled" : ""}>${busy ? "检测中…" : "检测"}</button><button class="btn ghost js-check-model">模型检测</button><button class="btn ghost js-edit">编辑</button><button class="btn ghost js-export">导出</button><button class="btn danger-soft js-del">删除</button></footer>
  </article>`;
}

function renderStats() {
  const counts = { total: state.keys.length, up: 0, down: 0, auth_error: 0, issue: 0, unknown: 0 };
  let latencySum = 0, latencyN = 0;
  state.keys.forEach((key) => {
    const status = key.status || "unknown";
    if (status === "up") counts.up++;
    else if (status === "down") counts.down++;
    else if (status === "auth_error") counts.auth_error++;
    else if (status === "rate_limited" || status === "degraded") counts.issue++;
    else counts.unknown++;
    if (key.latency_ms != null) { latencySum += key.latency_ms; latencyN++; }
  });
  $("#st-total").textContent = counts.total;
  $("#st-up").textContent = counts.up;
  $("#st-down").textContent = counts.down;
  $("#st-auth").textContent = counts.auth_error;
  $("#st-issue").textContent = counts.issue;
  $("#st-avg").textContent = latencyN ? `${Math.round(latencySum / latencyN)}ms` : "—";
}

function renderFilterCounts() {
  const counts = { all: state.keys.length, up: 0, down: 0, auth_error: 0, issue: 0, unknown: 0 };
  state.keys.forEach((key) => {
    const status = key.status || "unknown";
    if (status === "up") counts.up++;
    else if (status === "down") counts.down++;
    else if (status === "auth_error") counts.auth_error++;
    else if (status === "rate_limited" || status === "degraded") counts.issue++;
    else counts.unknown++;
  });
  for (const [key, id] of Object.entries({ all: "cnt-all", up: "cnt-up", down: "cnt-down", auth_error: "cnt-auth", issue: "cnt-issue", unknown: "cnt-unknown" })) {
    $("#" + id).textContent = counts[key];
  }
  $$(".seg").forEach((button) => button.classList.toggle("active", button.dataset.status === state.status));
}

function renderSelection(rows = getVisibleKeys(state.keys, state.status, state.query)) {
  const summary = selectionSummary(state.selected, rows);
  const bar = $("#selection-bar");
  $("#sel-all").checked = rows.length > 0 && summary.visible === rows.length;
  $("#sel-all").indeterminate = summary.visible > 0 && summary.visible < rows.length;
  $("#selection-summary").textContent = `已选择 ${summary.total} 条（当前结果共 ${summary.resultTotal} 条${summary.hidden ? `，隐藏选择 ${summary.hidden} 条` : ""}）`;
  bar.classList.toggle("active", summary.total > 0);
}

const taskController = createTaskController({ api, load, openModal });
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
$("#btn-refresh").addEventListener("click", () => load());
$("#btn-backup-all")?.addEventListener("click", async () => {
  if (!state.keys.length) return toast("还没有可备份的 Key");
  const result = await api("GET", "/api/keys/export_all");
  state.exportId = null;
  state.exportMode = "backup";
  $("#exp-fmt").value = "json";
  $("#exp-fmt").disabled = true;
  $("#exp-meta").textContent = `全部备份 · ${result.count || state.keys.length} 条 JSON`;
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
      if (!secret.api_key) return toast("当前没有可复制的 API Key");
      return copyText(secret.api_key, "API Key");
    } catch { return; }
  }
  if (event.target.closest(".js-edit")) return editor.openEdit(key);
  if (event.target.closest(".js-models")) return openModels(key);
  if (event.target.closest(".js-export")) {
    state.exportId = id;
    state.exportMode = "single";
    $("#exp-fmt").disabled = false;
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
    toast("顺序已保存");
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
  if (!state.selected.size) return toast("请先选择要检测的项目");
  taskController.startTask(await api("POST", "/api/keys/batch_check", { ids: [...state.selected] }));
});
$("#btn-check-mobile").addEventListener("click", () => $("#btn-check").click());
$("#btn-delete-mobile").addEventListener("click", () => $("#btn-delete").click());
$("#btn-export-mobile")?.addEventListener("click", () => $("#btn-export-selected").click());
$("#btn-export-selected").addEventListener("click", exportSelected);
$("#btn-delete").addEventListener("click", async () => {
  const rows = getVisibleKeys(state.keys, state.status, state.query);
  const summary = selectionSummary(state.selected, rows);
  if (!summary.total) return toast("请先选择要删除的项目");
  if (!confirm(`确认删除 ${summary.total} 条？${summary.hidden ? `其中 ${summary.hidden} 条当前不可见。` : ""}`)) return;
  const result = await api("POST", "/api/keys/batch_delete", { ids: [...state.selected] });
  state.selected.clear();
  toast(`已删除 ${result.deleted} 条`);
  await load();
});

function openModels(key) {
  state.modelId = key.id;
  $("#model-summary").textContent = `${key.name || key.base_url}：共 ${(key.models || []).length} 个模型`;
  $("#model-list").innerHTML = (key.models || []).map((model) => `<div class="model-row"><span>${esc(model)}</span><button class="link-btn js-set-check-model" data-model="${esc(model)}">设为检测模型</button></div>`).join("") || "暂无模型";
  openModal("modal-models");
}

async function deleteOne(key) {
  if (!confirm(`确认删除“${key.name || key.base_url}”？`)) return;
  await api("DELETE", `/api/keys/${key.id}`);
  state.selected.delete(key.id);
  toast("已删除");
  await load();
}

async function checkOne(key, modelOnly) {
  if (modelOnly && !key.check_model) {
    toast("请先设置检测模型");
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

async function exportSelected() {
  if (!state.selected.size) return toast("请先选择要导出的项目");
  state.exportMode = "batch";
  state.exportId = null;
  $("#exp-fmt").value = "json";
  $("#exp-fmt").disabled = true;
  $("#exp-meta").textContent = `批量 JSON · ${state.selected.size} 条`;
  openModal("modal-export");
  const result = await api("POST", "/api/keys/batch_export", { ids: [...state.selected], fmt: "json" });
  $("#exp-text").value = result.text || "";
}

async function updateExport() {
  if (state.exportMode === "batch") return;
  if (!state.exportId) return;
  const result = await api("GET", `/api/keys/${state.exportId}/export?fmt=${$("#exp-fmt").value}`);
  $("#exp-text").value = result.text || "";
}

$("#exp-fmt").addEventListener("change", updateExport);
$("#btn-copy").addEventListener("click", () => copyText($("#exp-text").value, "配置"));
document.addEventListener("visibilitychange", () => { if (!document.hidden) load({ silent: true }); });
setInterval(() => { if (!document.hidden && !$(".modal.open")) load({ silent: true }).catch(() => {}); }, 5000);

load();
