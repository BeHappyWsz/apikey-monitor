import { $, toast, formatCheckSummary, withBusyButton } from "./utils.js";

export function initAdd({ api, load, openModal, closeModal }) {
  const open = () => {
    $("#add-name").value = "";
    $("#add-base-url").value = "";
    $("#add-api-key").value = "";
    $("#add-api-key").type = "password";
    $("#add-notes").value = "";
    $("#add-tags").value = "";
    $("#add-check-after").value = "1";
    openModal("modal-add");
    setTimeout(() => $("#add-base-url").focus(), 0);
  };

  $("#btn-add")?.addEventListener("click", () => withBusyButton($("#btn-add"), open, { busyLabel: "打开中…" }));
  $("#btn-empty-add")?.addEventListener("click", () => withBusyButton($("#btn-empty-add"), open, { busyLabel: "打开中…" }));
  $("#btn-toggle-add-key")?.addEventListener("click", () => withBusyButton($("#btn-toggle-add-key"), () => {
    $("#add-api-key").type = $("#add-api-key").type === "password" ? "text" : "password";
  }, { busyLabel: "" }));
  $("#btn-save-add")?.addEventListener("click", () => withBusyButton($("#btn-save-add"), () => save(false), { busyLabel: "保存中…" }));
  $("#btn-save-check-add")?.addEventListener("click", () => withBusyButton($("#btn-save-check-add"), () => save(true), { busyLabel: "保存并检测…" }));

  // Ctrl/Cmd+Enter -> save and check
  $("#modal-add")?.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      save(true);
    }
  });

  async function save(forceCheck) {
    const payload = {
      name: $("#add-name").value.trim(),
      base_url: $("#add-base-url").value.trim(),
      api_key: $("#add-api-key").value.trim(),
      notes: $("#add-notes").value.trim(),
      tags: $("#add-tags").value.trim(),
      check_after_save: forceCheck || $("#add-check-after").value === "1",
    };
    if (!payload.base_url || !payload.api_key) return toast("请填写 Base URL 和 API Key");
    const result = await api("POST", "/api/keys", payload);
    closeModal("modal-add");
    if (payload.check_after_save) {
      toast(`已添加 · ${formatCheckSummary(result)}`);
    } else {
      toast("已添加，稍后可手动检测");
    }
    await load();
  }

  return { open };
}
