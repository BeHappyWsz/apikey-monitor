import { $, esc, copyText, toast, withBusyButton } from "./utils.js";

export function initEditor({ api, state, load, openModal, closeModal }) {
  $("#btn-save-edit").addEventListener("click", () => withBusyButton($("#btn-save-edit"), () => saveEdit(false), { busyLabel: "保存中…" }));
  $("#btn-save-check-edit").addEventListener("click", () => withBusyButton($("#btn-save-check-edit"), () => saveEdit(true), { busyLabel: "保存并检测…" }));
  $("#btn-toggle-key").addEventListener("click", () => withBusyButton($("#btn-toggle-key"), () => toggleRevealKey(), { busyLabel: "" }));
  $("#btn-copy-base").addEventListener("click", () => withBusyButton($("#btn-copy-base"), () => copyText($("#edit-base-url").value, "Base URL"), { busyLabel: "复制中…" }));
  $("#btn-copy-key").addEventListener("click", () => withBusyButton($("#btn-copy-key"), () => copySecretKey(), { busyLabel: "复制中…" }));
  $("#model-list").addEventListener("click", async (event) => {
    const button = event.target.closest(".js-set-check-model");
    if (!button) return;
    await api("PUT", `/api/keys/${state.modelId}`, { check_model: button.dataset.model });
    closeModal("modal-models");
    await load();
  });
  $("#btn-copy-models").addEventListener("click", () => withBusyButton($("#btn-copy-models"), () => {
    const key = state.keys.find((value) => value.id === state.modelId);
    copyText((key?.models || []).join("\n"), "模型列表");
  }, { busyLabel: "复制中…" }));

  // Ctrl/Cmd+Enter -> save and check
  $("#modal-edit")?.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      saveEdit(true);
    }
  });

  let revealedSecret = "";

  function openEdit(key) {
    state.editId = key.id;
    revealedSecret = "";
    $("#edit-name").value = key.name || "";
    $("#edit-base-url").value = key.base_url || "";
    $("#edit-api-key").value = "";
    $("#edit-api-key").type = "password";
    $("#edit-api-key").placeholder = key.has_api_key === false
      ? "请输入 API Key"
      : `留空表示不修改（当前 ${key.api_key_masked || "••••••••"}）`;
    $("#edit-check-model").value = key.check_model || "";
    $("#edit-check-path").value = key.check_path || "";
    $("#edit-notes").value = key.notes || "";
    $("#edit-tags").value = key.tags || (key.tag_list || []).join(", ");
    $("#edit-monitor").value = key.monitor_enabled ? "1" : "0";
    $("#edit-interval").value = key.interval_sec || "";
    $("#model-suggestions").innerHTML = (key.models || []).map((model) => `<option value="${esc(model)}">`).join("");
    openModal("modal-edit");
  }

  async function fetchSecret() {
    if (revealedSecret) return revealedSecret;
    const secret = await api("GET", `/api/keys/${state.editId}/secret`);
    revealedSecret = secret.api_key || "";
    return revealedSecret;
  }

  async function toggleRevealKey() {
    const input = $("#edit-api-key");
    if (input.type === "password") {
      if (!input.value.trim()) {
        try {
          const full = await fetchSecret();
          if (full) input.value = full;
        } catch (err) {
          toast(err.message || "获取完整 Key 失败");
          return;
        }
      }
      input.type = "text";
    } else {
      if (revealedSecret && input.value === revealedSecret) {
        input.value = "";
        input.placeholder = `留空表示不修改（当前已保存 Key）`;
      }
      input.type = "password";
    }
  }

  async function copySecretKey() {
    const typed = $("#edit-api-key").value.trim();
    if (typed) {
      await copyText(typed, "API Key");
      return;
    }
    try {
      const full = await fetchSecret();
      if (!full) {
        toast("当前没有可复制的 API Key");
        return;
      }
      await copyText(full, "API Key");
    } catch (err) {
      toast(err.message || "获取完整 Key 失败");
    }
  }

  async function saveEdit(checkAfter) {
    const payload = {
      name: $("#edit-name").value.trim(),
      base_url: $("#edit-base-url").value.trim(),
      check_model: $("#edit-check-model").value.trim(),
      check_path: $("#edit-check-path").value.trim(),
      notes: $("#edit-notes").value.trim(),
      tags: $("#edit-tags").value.trim(),
      monitor_enabled: $("#edit-monitor").value === "1" ? 1 : 0,
      interval_sec: $("#edit-interval").value.trim() || null,
      check_after_save: checkAfter,
    };
    const apiKey = $("#edit-api-key").value.trim();
    if (apiKey && apiKey !== revealedSecret) payload.api_key = apiKey;
    await api("PUT", `/api/keys/${state.editId}`, payload);
    closeModal("modal-edit");
    toast(checkAfter ? "已保存并完成检测" : "已保存，连接信息变化时状态已重置");
    await load();
  }

  return { openEdit };
}
