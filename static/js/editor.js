import { $, esc, copyText, toast } from "./utils.js";

export function initEditor({ api, state, load, openModal, closeModal }) {
  $("#btn-save-edit").addEventListener("click", () => saveEdit(false));
  $("#btn-save-check-edit").addEventListener("click", () => saveEdit(true));
  $("#btn-toggle-key").addEventListener("click", () => toggleRevealKey());
  $("#btn-copy-base").addEventListener("click", () => copyText($("#edit-base-url").value, "Base URL"));
  $("#btn-copy-key").addEventListener("click", () => copySecretKey());
  $("#model-list").addEventListener("click", async (event) => {
    const button = event.target.closest(".js-set-check-model");
    if (!button) return;
    await api("PUT", `/api/keys/${state.modelId}`, { check_model: button.dataset.model });
    closeModal("modal-models");
    await load();
  });
  $("#btn-copy-models").addEventListener("click", () => {
    const key = state.keys.find((value) => value.id === state.modelId);
    copyText((key?.models || []).join("\n"), "????");
  });

  // Ctrl/Cmd+Enter ? ?????
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
      ? "??? API Key"
      : `?????????? ${key.api_key_masked || "????????"}?`;
    $("#edit-check-model").value = key.check_model || "";
    $("#edit-notes").value = key.notes || "";
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
      // Prefer newly typed value; otherwise load full secret for view.
      if (!input.value.trim()) {
        try {
          const full = await fetchSecret();
          if (full) input.value = full;
        } catch (err) {
          toast(err.message || "???? Key ??");
          return;
        }
      }
      input.type = "text";
    } else {
      // Leaving reveal mode: if value equals secret and user didn't intend to change,
      // clear so save keeps "blank = no change".
      if (revealedSecret && input.value === revealedSecret) {
        input.value = "";
        input.placeholder = `????????????? Key?`;
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
        toast("???????? API Key");
        return;
      }
      await copyText(full, "API Key");
    } catch (err) {
      toast(err.message || "???? Key ??");
    }
  }

  async function saveEdit(checkAfter) {
    const payload = {
      name: $("#edit-name").value.trim(),
      base_url: $("#edit-base-url").value.trim(),
      check_model: $("#edit-check-model").value.trim(),
      notes: $("#edit-notes").value.trim(),
      monitor_enabled: $("#edit-monitor").value === "1" ? 1 : 0,
      interval_sec: $("#edit-interval").value.trim() || null,
      check_after_save: checkAfter,
    };
    const apiKey = $("#edit-api-key").value.trim();
    // Only send api_key when user entered a new value (not just revealed the existing one).
    if (apiKey && apiKey !== revealedSecret) payload.api_key = apiKey;
    await api("PUT", `/api/keys/${state.editId}`, payload);
    closeModal("modal-edit");
    toast(checkAfter ? "????????" : "????????????????");
    await load();
  }

  return { openEdit };
}
