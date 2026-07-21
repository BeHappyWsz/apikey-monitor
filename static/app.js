import { request, waitForHealth } from "./js/api.js";
import { getVisibleKeys, keysFingerprint, selectCurrentResults } from "./js/state.js";
import { initDialogs, openModal, closeModal } from "./js/dialogs.js";
import { createTaskController } from "./js/tasks.js";
import { initImport } from "./js/import.js";
import { initAdd } from "./js/add.js";
import { initEditor } from "./js/editor.js";
import { initSettings } from "./js/settings.js";
import { initSync } from "./js/sync.js";
import { createListUi } from "./js/list_ui.js";
import { initExportUi } from "./js/export_ui.js";
import { initListActions } from "./js/list_actions.js";
import { $, $$, toast } from "./js/utils.js";
import { initAuth } from "./js/auth.js";
import { LoadingBar, BusyOverlay } from "./js/feedback.js";

// Mount the global top progress bar so every api() request becomes
// visible. id="toast" is unused now — the feedback module owns the toast
// stack.
LoadingBar();

// Region-level overlays used during list refresh / import parse / sync.
const listBusy = BusyOverlay(document.getElementById("key-list"), { text: "正在刷新…" });

const state = {
  keys: [], selected: new Set(), status: "all", query: "", sort: "default", loading: true, loadError: "",
  checking: new Set(), editId: null, exportId: null, exportMode: "single", modelId: null,
  candidates: [], candidateSelected: new Set(), settings: {}, runtime: {}, draggingId: null,
  fingerprint: "",
  revision: "",
  nextCursor: "", hasMore: false, total: 0, summary: {}, pageLoading: false, refreshPending: false,
};

async function api(method, path, body, options) {
  // Toast + in-flight bar are handled by api.js itself; pass silent for
  // background polls so they don't spam toasts.
  return (await request(method, path, body, { ...options, silent: options?.silent || false })).payload;
}

const listUi = {};

function pagePath(cursor = "") {
  const params = new URLSearchParams({ limit: "50", status: state.status || "all", sort: state.sort || "default" });
  if (state.query.trim()) params.set("q", state.query.trim());
  if (cursor) params.set("cursor", cursor);
  return `/api/keys/page?${params}`;
}

async function load({ silent = false, append = false } = {}) {
  if (append && (!state.hasMore || state.pageLoading)) return;
  if (!silent && !append) {
    state.loading = true;
    state.loadError = "";
    listBusy(true);
    listUi.render();
  }
  if (append) state.pageLoading = true;
  try {
    // Polling only reports a new revision; it must not jump a scrolled list.
    if (silent && !state.checking.size) {
      try {
        const revResult = await request("GET", "/api/keys/revision", undefined, { latest: true, silent: true });
        if (!revResult.isLatest()) return;
        const rev = String(revResult.payload?.revision || "");
        if (rev && rev === state.revision) return;
        state.refreshPending = true;
        listUi.render({ preserveUi: true });
        return;
      } catch { return; }
    }
    const result = await request("GET", pagePath(append ? state.nextCursor : ""), undefined, { latest: true });
    if (!result.isLatest()) return;
    const page = result.payload || {};
    state.keys = append ? [...state.keys, ...(page.items || [])] : (page.items || []);
    state.fingerprint = keysFingerprint(state.keys);
    state.nextCursor = String(page.next_cursor || "");
    state.hasMore = Boolean(page.next_cursor);
    state.total = Number(page.total || 0);
    state.summary = page.summary || {};
    state.revision = String(page.revision || "");
    state.refreshPending = false;
    state.loading = false;
    state.loadError = "";
    listUi.render({ preserveUi: append });
  } catch (error) {
    if (error.name === "AbortError" || silent) return;
    state.loading = false;
    state.loadError = error.message;
    listUi.render();
  } finally {
    state.pageLoading = false;
    listBusy(false);
  }
}

const loadMore = () => load({ append: true });

Object.assign(listUi, createListUi({ state, load, loadMore }));
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
      load();
      toast("已筛选：问题项（非在线）", 2800);
    }
  },
});
const editor = initEditor({ api, state, load, openModal, closeModal });
initDialogs();
initImport({ api, state, load, openModal, closeModal, startTask: taskController.startTask });
initAdd({ api, load, openModal, closeModal });
initSettings({ api, state, openModal, closeModal, waitForHealth, onSettingsApplied: applyUiRefreshFromSettings });
initSync({ api, load, openModal });
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
const auth = initAuth({ api, openModal, closeModal, onAuthenticated: async () => { await bootApp(); } });

$("#sel-all").addEventListener("change", (event) => {
  state.selected = selectCurrentResults(state.selected, getVisibleKeys(state.keys, state.status, state.query), event.target.checked);
  render();
});
let filterTimer = null;
$("#filter").addEventListener("input", (event) => {
  state.query = event.target.value;
  clearTimeout(filterTimer);
  filterTimer = setTimeout(() => load(), 260);
});
$("#status-filter").addEventListener("click", (event) => {
  const button = event.target.closest(".seg");
  if (button && button.dataset.status !== state.status) { state.status = button.dataset.status; load(); }
});
$("#sort-filter").addEventListener("click", (event) => {
  const button = event.target.closest(".seg");
  if (!button) return;
  const next = button.dataset.sort || "default";
  if (next === state.sort) return;
  state.sort = next;
  // Sort changes invalidate any in-flight next-cursor; force a fresh page.
  state.nextCursor = "";
  state.hasMore = false;
  $$("#sort-filter .seg").forEach((item) => item.classList.toggle("active", item.dataset.sort === state.sort));
  load();
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
  const sec = settings?.uiRefreshIntervalSec ?? 15;
  applyUiRefreshInterval(sec);
}

document.addEventListener("visibilitychange", () => {
  if (!document.hidden) load({ silent: true }).catch(() => {});
});

async function bootApp() {
  try {
    const settings = await api("GET", "/api/settings");
    state.settings = settings || {};
    applyUiRefreshFromSettings(state.settings);
  } catch {
    applyUiRefreshInterval(15);
  }
  await load();
}

async function boot() {
  try {
    const result = await request("GET", "/api/auth/me");
    auth.setAuthenticated(result.payload);
    await bootApp();
  } catch (error) {
    if (error.status === 401) auth.showLogin();
    else toast(error.message || "无法连接服务", 4200);
  }
}

boot();
