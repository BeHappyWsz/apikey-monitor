import { canReorder, getVisibleKeys, keysFingerprint, moveKey, selectionSummary } from "./state.js";
import { $, $$, copyText, esc, formatCheckSummary, toast } from "./utils.js";
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

  async function deleteOne(key) {
    if (!confirm(`确认删除“${key.name || key.base_url}”？`)) return;
    await api("DELETE", `/api/keys/${key.id}`);
    state.selected.delete(key.id);
    toast("已删除");
    await load();
  }

  async function checkOne(key, modelOnly) {
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
    if (event.target.closest(".js-export")) return exportUi.openSingleExport(key);
    if (event.target.closest(".js-del")) return deleteOne(key);
    if (event.target.closest(".js-check") || event.target.closest(".js-check-model")) {
      return checkOne(key, Boolean(event.target.closest(".js-check-model")));
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
    if (!canReorder(state.status, state.query)) return event.preventDefault();
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
      await api("POST", "/api/keys/move", { id: sourceId, before_id: targetId });
      toast("顺序已保存");
    } catch {
      state.keys = previous;
      state.fingerprint = keysFingerprint(state.keys);
      render();
    }
  });

  $("#key-list").addEventListener("dragend", clearDragState);

  $("#btn-check").addEventListener("click", async () => {
    if (!state.selected.size) return toast("请先选择要检测的项目");
    taskController.startTask(await api("POST", "/api/keys/batch_check", { ids: [...state.selected] }));
  });
  $("#btn-check-mobile").addEventListener("click", () => $("#btn-check").click());
  $("#btn-delete-mobile").addEventListener("click", () => $("#btn-delete").click());
  $("#btn-delete").addEventListener("click", async () => {
    exportUi.closeMoreMenu();
    const rows = getVisibleKeys(state.keys, state.status, state.query);
    const summary = selectionSummary(state.selected, rows);
    if (!summary.total) return toast("请先选择要删除的项目");
    if (!confirm(`确认删除 ${summary.total} 条？${summary.hidden ? `其中 ${summary.hidden} 条当前不可见。` : ""}`)) return;
    const result = await api("POST", "/api/keys/batch_delete", { ids: [...state.selected] });
    state.selected.clear();
    toast(`已删除 ${result.deleted} 条`);
    await load();
  });

  return { checkOne, deleteOne, openModels };
}
