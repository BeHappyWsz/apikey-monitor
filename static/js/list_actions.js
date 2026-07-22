import { canReorder, getVisibleKeys, keysFingerprint, moveKey, selectionSummary } from "./state.js";
import { $, $$, copyText, esc, formatCheckSummary, formatCreatedAt, statusLabel, toast, withBusyButton, confirmAction } from "./utils.js";
import { openModal } from "./dialogs.js";

export function initListActions({
  api,
  state,
  load,
  render,
  renderSelection,
  editor,
  exportUi,
  taskController,
}) {
  function clearDragState() {
    state.draggingId = null;
    $$(".key-card.dragging,.key-card.drag-over").forEach((item) => item.classList.remove("dragging", "drag-over"));
  }

  function openModels(key) {
    state.modelId = key.id;
    $("#model-summary").textContent = `${key.name || key.base_url}：共 ${(key.models || []).length} 个模型`;
    $("#model-list").innerHTML = (key.models || []).map((model) => `<div class="model-row"><span>${esc(model)}</span><button class="link-btn js-set-check-model" data-model="${esc(model)}">设为检测模型</button></div>`).join("") || "暂无模型";
    openModal("modal-models");
  }

  async function openHistory(key) {
    $("#history-summary").textContent = `${key.name || key.base_url} 的最近检测结果`;
    $("#history-list").textContent = "正在加载…";
    openModal("modal-history");
    const result = await api("GET", `/api/keys/${key.id}/history?limit=30`);
    const rows = result.items || [];
    $("#history-list").innerHTML = rows.map((row) => `<div class="history-row status-${esc((row.status || "unknown").replace(/_/g, "-"))}"><span>${row.kind === "strict" ? "严格验证" : "连通性"}</span><b>${esc(statusLabel[row.status] || row.status || "未知")}</b><span>${row.latency_ms == null ? "—" : `${row.latency_ms}ms`}</span><time title="${esc(formatCreatedAt(row.created_at))}">${esc(formatCreatedAt(row.created_at))}</time>${row.error ? `<small title="${esc(row.error)}">${esc(row.error)}</small>` : ""}</div>`).join("") || "暂无检测历史";
  }

  async function refreshModels(trigger) {
    if (!state.modelId) return;
    const result = await api("POST", `/api/keys/${state.modelId}/models/refresh`, {});
    await load({ silent: true });
    const key = state.keys.find((item) => item.id === state.modelId);
    if (key) openModels(key);
    toast(result.count ? `已刷新 ${result.count} 个模型` : (result.error || "未获取到模型"));
  }
  $("#btn-refresh-models").addEventListener("click", () => withBusyButton($("#btn-refresh-models"), (button) => refreshModels(button), { busyLabel: "刷新中…" }));

  async function deleteOne(key, triggerBtn) {
    if (!await confirmAction(`确认删除"${key.name || key.base_url}"？`, { okLabel: "删除", danger: true })) return;
    await withBusyButton(triggerBtn, async () => {
      await api("DELETE", `/api/keys/${key.id}`);
      state.selected.delete(key.id);
      toast("已删除");
      await load();
    }, { busyLabel: "删除中…" });
  }

  async function checkOne(key, modelOnly, triggerBtn) {
    if (modelOnly && !key.check_model) {
      toast("请先设置验证模型，严格验证会产生一次最小模型调用");
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

  $("#key-list").addEventListener("click", async (event) => {
    const cardEl = event.target.closest(".key-card");
    const id = Number(cardEl?.dataset.id);
    const key = state.keys.find((value) => value.id === id);
    if (!key) return;
    if (event.target.closest(".js-copy-url")) return withBusyButton(event.target.closest(".js-copy-url"), () => copyText(key.base_url, "Base URL"), { busyLabel: "复制中…" });
    if (event.target.closest(".js-copy-key")) {
      const trigger = event.target.closest(".js-copy-key");
      return withBusyButton(trigger, async () => {
        try {
          const secret = await api("GET", `/api/keys/${id}/secret`);
          if (!secret.api_key) return toast("当前没有可复制的 API Key");
          return copyText(secret.api_key, "API Key");
        } catch { return; }
      }, { busyLabel: "复制中…" });
    }
    if (event.target.closest(".js-edit")) return editor.openEdit(key);
    if (event.target.closest(".js-models")) return openModels(key);
    if (event.target.closest(".js-history")) return openHistory(key);
    if (event.target.closest(".js-export")) return exportUi.openSingleExport(key);
    if (event.target.closest(".js-import-ccswitch")) {
      const trigger = event.target.closest(".js-import-ccswitch");
      return withBusyButton(trigger, () => exportUi.importToCcswitch(key), { busyLabel: "导入中…" });
    }
    if (event.target.closest(".js-del")) return deleteOne(key, event.target.closest(".js-del"));
    if (event.target.closest(".js-check") || event.target.closest(".js-check-model")) {
      return checkOne(key, Boolean(event.target.closest(".js-check-model")), event.target.closest(".js-check, .js-check-model"));
    }
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
    if (!canReorder(state.status, state.query, state.sort, state.filters)) return event.preventDefault();
    // Whole-card drag: do not start reorder from interactive controls.
    if (event.target.closest("button, input, a, select, textarea, label, summary, .url-copy")) {
      return event.preventDefault();
    }
    const cardEl = event.target.closest(".key-card");
    if (!cardEl) return;
    state.draggingId = Number(cardEl.dataset.id);
    cardEl.classList.add("dragging");
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", String(state.draggingId));
  });

  $("#key-list").addEventListener("dragover", (event) => {
    if (!state.draggingId || !canReorder(state.status, state.query, state.sort, state.filters)) return;
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
    if (!sourceId || !target || !canReorder(state.status, state.query, state.sort, state.filters)) return;
    const targetId = Number(target.dataset.id);
    const previous = state.keys;
    state.keys = moveKey(state.keys, sourceId, targetId);
    state.fingerprint = keysFingerprint(state.keys);
    render();
    try {
      await api("POST", "/api/keys/move", { id: sourceId, before_id: targetId });
      toast("顺序已保存");
    } catch {
      state.keys = previous;
      state.fingerprint = keysFingerprint(state.keys);
      render();
    }
  });

  $("#key-list").addEventListener("dragend", clearDragState);

  $("#btn-check").addEventListener("click", () => withBusyButton($("#btn-check"), async () => {
    if (!state.selected.size) return toast("请先选择要检测的项目");
    taskController.startTask(await api("POST", "/api/keys/batch_check", { ids: [...state.selected] }));
  }, { busyLabel: "启动中…" }));
  $("#btn-check-mobile").addEventListener("click", () => withBusyButton($("#btn-check-mobile"), () => $("#btn-check").click(), { busyLabel: "启动中…" }));
  $("#btn-delete-mobile").addEventListener("click", () => withBusyButton($("#btn-delete-mobile"), () => $("#btn-delete").click(), { busyLabel: "删除中…" }));
  $("#btn-delete").addEventListener("click", () => withBusyButton($("#btn-delete"), async () => {
    exportUi.closeMoreMenu();
    const rows = getVisibleKeys(state.keys, state.status, state.query);
    const summary = selectionSummary(state.selected, rows);
    if (!summary.total) return toast("请先选择要删除的项目");
    if (!await confirmAction(`确认删除 ${summary.total} 条？${summary.hidden ? `其中 ${summary.hidden} 条当前不可见。` : ""}`, { okLabel: "删除", danger: true })) return;
    const result = await api("POST", "/api/keys/batch_delete", { ids: [...state.selected] });
    state.selected.clear();
    toast(`已删除 ${result.deleted} 条`);
    await load();
  }, { busyLabel: "删除中…" }));

  return { checkOne, deleteOne, openModels };
}
