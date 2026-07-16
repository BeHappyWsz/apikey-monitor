import { $, toast, formatCheckSummary } from "./utils.js";

export function initAdd({ api, load, openModal, closeModal }) {
  const open = () => {
    $("#add-name").value = "";
    $("#add-base-url").value = "";
    $("#add-api-key").value = "";
    $("#add-api-key").type = "password";
    $("#add-notes").value = "";
    $("#add-check-after").value = "1";
    openModal("modal-add");
    setTimeout(() => $("#add-base-url").focus(), 0);
  };

  $("#btn-add")?.addEventListener("click", open);
  $("#btn-empty-add")?.addEventListener("click", open);
  $("#btn-toggle-add-key")?.addEventListener("click", () => {
    $("#add-api-key").type = $("#add-api-key").type === "password" ? "text" : "password";
  });
  $("#btn-save-add")?.addEventListener("click", () => save(false));
  $("#btn-save-check-add")?.addEventListener("click", () => save(true));

  // Ctrl/Cmd+Enter ? ?????
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
      check_after_save: forceCheck || $("#add-check-after").value === "1",
    };
    if (!payload.base_url || !payload.api_key) return toast("??? Base URL ? API Key");
    const result = await api("POST", "/api/keys", payload);
    closeModal("modal-add");
    if (payload.check_after_save) {
      toast(`??? ? ${formatCheckSummary(result)}`);
    } else {
      toast("???????????");
    }
    await load();
  }

  return { open };
}
