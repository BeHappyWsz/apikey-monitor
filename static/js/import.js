import { $, esc, maskKey, toast, formatImportSummary } from "./utils.js";

const SAMPLE_TEXT = `ANTHROPIC_BASE_URL=https://api.example.com
ANTHROPIC_AUTH_TOKEN=sk-ant-example-key-please-replace

OPENAI_BASE_URL=https://api.example.com/v1
OPENAI_API_KEY=sk-example-key-please-replace

https://another.example.com sk-another-example-key`;

const SAMPLE_JSON = `[
  {
    "name": "demo-openai",
    "base_url": "https://api.example.com/v1",
    "api_key": "sk-example-key-please-replace",
    "check_model": "gpt-4o-mini"
  },
  {
    "name": "demo-anthropic",
    "base_url": "https://api.example.com",
    "api_key": "sk-ant-example-key-please-replace",
    "check_model": ""
  }
]
`;

export function initImport({ api, state, load, openModal, closeModal, startTask }) {
  $("#btn-import").addEventListener("click", () => openImport());
  $("#btn-empty-import")?.addEventListener("click", () => openImport());
  $("#btn-empty-json")?.addEventListener("click", () => openImport(SAMPLE_JSON.trim() + "\n", { jsonHint: true }));
  $("#btn-fill-sample")?.addEventListener("click", () => {
    $("#paste-area").value = SAMPLE_TEXT;
    toast("???????????????");
  });
  $("#btn-fill-json-sample")?.addEventListener("click", () => {
    $("#paste-area").value = SAMPLE_JSON.trim() + "\n";
    toast("??? JSON ????????????");
  });

  async function parsePaste() {
    const text = $("#paste-area").value;
    if (!text.trim()) return toast("??????");
    const result = await api("POST", "/api/import/parse", { text });
    state.candidates = (result.candidates || []).map((item) => ({
      name: item.name || "",
      base_url: item.base_url || "",
      api_key: item.api_key || "",
      check_model: item.check_model || "",
      notes: item.notes || "",
      show_key: false,
    }));
    state.candidateSelected = new Set(state.candidates.map((_, index) => index));
    renderCandidates(state);
  }

  async function saveCandidates() {
    const items = [...state.candidateSelected].map((index) => {
      const candidate = state.candidates[index];
      return {
        name: (candidate.name || "").trim(),
        base_url: (candidate.base_url || "").trim(),
        api_key: (candidate.api_key || "").trim(),
        check_model: (candidate.check_model || "").trim(),
        notes: (candidate.notes || "").trim(),
      };
    }).filter((item) => item.base_url && item.api_key);
    if (!items.length) return toast("?????????");
    const result = await api("POST", "/api/keys/batch", { items });
    closeModal("modal-import");
    toast(formatImportSummary(result));
    await load();
    if (result.task) startTask(result.task);
  }

  $("#btn-parse").addEventListener("click", () => parsePaste());
  $("#btn-save-cand").addEventListener("click", () => saveCandidates());

  // Ctrl/Cmd+Enter??????????????
  $("#modal-import")?.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      if (state.candidates.length) saveCandidates();
      else parsePaste();
    }
  });

  $("#cand-body").addEventListener("change", (event) => {
    const row = event.target.closest("tr");
    if (!row) return;
    const index = Number(row.dataset.i);
    if (event.target.classList.contains("cand-sel")) {
      event.target.checked ? state.candidateSelected.add(index) : state.candidateSelected.delete(index);
    }
  });

  $("#cand-body").addEventListener("input", (event) => {
    const row = event.target.closest("tr");
    if (!row) return;
    const index = Number(row.dataset.i);
    const candidate = state.candidates[index];
    if (!candidate) return;
    if (event.target.classList.contains("cand-name")) candidate.name = event.target.value;
    if (event.target.classList.contains("cand-url")) candidate.base_url = event.target.value;
    if (event.target.classList.contains("cand-key")) candidate.api_key = event.target.value;
    if (event.target.classList.contains("cand-model")) candidate.check_model = event.target.value;
  });

  $("#cand-body").addEventListener("click", (event) => {
    const toggle = event.target.closest(".js-cand-toggle");
    if (!toggle) return;
    const row = toggle.closest("tr");
    const index = Number(row.dataset.i);
    const candidate = state.candidates[index];
    if (!candidate) return;
    candidate.show_key = !candidate.show_key;
    const input = row.querySelector(".cand-key");
    if (input) input.type = candidate.show_key ? "text" : "password";
    toggle.textContent = candidate.show_key ? "?" : "?";
    toggle.title = candidate.show_key ? "?? API Key" : "?? API Key";
  });

  $("#cand-all").addEventListener("change", (event) => {
    state.candidateSelected = event.target.checked ? new Set(state.candidates.map((_, index) => index)) : new Set();
    renderCandidates(state);
  });

  function openImport(prefill = "", { jsonHint = false } = {}) {
    state.candidates = [];
    state.candidateSelected = new Set();
    $("#paste-area").value = prefill;
    $("#cand-body").innerHTML = "";
    $("#parse-info").textContent = jsonHint
      ? "?????/??? JSON???????????????????"
      : "???Ctrl+Enter ?????????? Ctrl+Enter ????";
    openModal("modal-import");
  }

  return { openImport, SAMPLE_TEXT, SAMPLE_JSON };
}

function renderCandidates(state) {
  $("#parse-info").textContent = state.candidates.length
    ? `??? ${state.candidates.length} ???????? / URL / Key / ?????? Ctrl+Enter ??`
    : "??????";
  $("#cand-body").innerHTML = state.candidates.map((candidate, index) => `<tr data-i="${index}">
    <td><input class="cand-sel" type="checkbox" ${state.candidateSelected.has(index) ? "checked" : ""}></td>
    <td><input class="cand-name" value="${esc(candidate.name || "")}" placeholder="????"></td>
    <td><input class="cand-url" value="${esc(candidate.base_url || "")}" placeholder="https://..."></td>
    <td><div class="input-line cand-key-line">
      <input class="cand-key" type="${candidate.show_key ? "text" : "password"}" value="${esc(candidate.api_key || "")}" autocomplete="off">
      <button class="icon-btn js-cand-toggle" type="button" title="${candidate.show_key ? "?? API Key" : "?? API Key"}">${candidate.show_key ? "?" : "?"}</button>
    </div></td>
    <td><input class="cand-model" value="${esc(candidate.check_model || "")}" placeholder="????"></td>
  </tr>`).join("");
}
