import { request, waitForHealth } from "./js/api.js";
import { getVisibleKeys, keysFingerprint, selectCurrentResults } from "./js/state.js";
import { initDialogs, openModal, closeModal } from "./js/dialogs.js";
import { createTaskController } from "./js/tasks.js";
import { initImport } from "./js/import.js";
import { initAdd } from "./js/add.js";
import { initEditor } from "./js/editor.js";
import { initSettings } from "./js/settings.js";
import { createListUi } from "./js/list_ui.js";
import { initExportUi } from "./js/export_ui.js";
import { initListActions } from "./js/list_actions.js";
import { $, toast } from "./js/utils.js";

const state = {
  keys: [], selected: new Set(), status: "all", query: "", loading: true, loadError: "",
  checking: new Set(), editId: null, exportId: null, exportMode: "single", modelId: null,
  candidates: [], candidateSelected: new Set(), settings: {}, runtime: {}, draggingId: null,
  fingerprint: "",
  revision: "",
};

async function api(method, path, body, options) {
  try {
    return (await request(method, path, body, options)).payload;
  } catch (error) {
    if (error.name !== "AbortError") toast(error.message || "请求失败", 4200);
    throw error;
  }
}

// listUi assigned after createListUi; load closes over listUi methods via getters below.
const listUi = {};

async function load({ silent = false } = {}) {
  if (!silent) {
    state.loading = true;
    state.loadError = "";
    listUi.render();
  }
  try {
    // Silent path: cheap revision probe first — skip full list when unchanged.
    if (silent && !state.checking.size) {
      try {
        const revResult = await request("GET", "/api/keys/revision", undefined, { latest: true });
        if (!revResult.isLatest()) return;
        const rev = String(revResult.payload?.revision || "");
        if (rev && rev === state.revision) return;
      } catch {
        // Fall through to full list load on revision errors.
      }
    }
    const result = await request("GET", "/api/keys", undefined, { latest: true });
    if (!result.isLatest()) return;
    const nextKeys = result.payload;
    const nextFingerprint = keysFingerprint(nextKeys);
    const unchanged = silent && nextFingerprint === state.fingerprint && !state.checking.size;
    state.keys = nextKeys;
    state.fingerprint = nextFingerprint;
    state.loading = false;
    state.loadError = "";
    // Refresh revision token after a successful full fetch (monitor writes bump it).
    try {
      const revResult = await request("GET", "/api/keys/revision", undefined, { latest: true });
      if (revResult.isLatest()) state.revision = String(revResult.payload?.revision || "");
    } catch {
      state.revision = nextFingerprint;
    }
    if (unchanged) {
      listUi.renderStats();
      listUi.renderFilterCounts();
      listUi.renderSelection();
      return;
    }
    listUi.render({ preserveUi: silent });
  } catch (error) {
    if (error.name === "AbortError" || silent) return;
    state.loading = false;
    state.loadError = error.message;
    listUi.render();
  }
}

Object.assign(listUi, createListUi({ state, load }));
const { render, renderSelection } = listUi;

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
      toast("已筛选：问题项（非在线）", 2800);
    }
  },
});
const editor = initEditor({ api, state, load, openModal, closeModal });
initDialogs();
initImport({ api, state, load, openModal, closeModal, startTask: taskController.startTask });
initAdd({ api, load, openModal, closeModal });
initSettings({ api, state, openModal, closeModal, waitForHealth, onSettingsApplied: applyUiRefreshFromSettings });
const exportUi = initExportUi({ api, state, openModal });
initListActions({
  api,
  state,
  load,
  render,
  renderSelection,
  editor,
  exportUi,
  taskController,
});

$("#sel-all").addEventListener("change", (event) => {
  state.selected = selectCurrentResults(state.selected, getVisibleKeys(state.keys, state.status, state.query), event.target.checked);
  render();
});
$("#filter").addEventListener("input", (event) => { state.query = event.target.value; render(); });
$("#status-filter").addEventListener("click", (event) => {
  const button = event.target.closest(".seg");
  if (button) { state.status = button.dataset.status; render(); }
});
$("#btn-refresh").addEventListener("click", () => { exportUi.closeMoreMenu(); load(); });

let uiRefreshTimer = null;

function applyUiRefreshInterval(sec) {
  if (uiRefreshTimer != null) {
    clearInterval(uiRefreshTimer);
    uiRefreshTimer = null;
  }
  const n = Number(sec);
  if (!Number.isFinite(n) || n <= 0) return;
  const ms = Math.max(3, Math.floor(n)) * 1000;
  uiRefreshTimer = setInterval(() => {
    if (!document.hidden && !$(".modal.open")) load({ silent: true }).catch(() => {});
  }, ms);
}

function applyUiRefreshFromSettings(settings) {
  const sec = settings?.ui_refresh_interval_sec ?? 15;
  applyUiRefreshInterval(sec);
}

document.addEventListener("visibilitychange", () => {
  if (!document.hidden) load({ silent: true }).catch(() => {});
});

async function boot() {
  try {
    const settings = await api("GET", "/api/settings");
    state.settings = settings || {};
    applyUiRefreshFromSettings(state.settings);
  } catch {
    applyUiRefreshInterval(15);
  }
  await load();
}

boot();
