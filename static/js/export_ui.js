import { $, copyText, downloadText, exportFilename, toast } from "./utils.js";

const EXPORT_FMT_KEY = "apikeyconfig.exportFmt";
const EXPORT_FMTS = ["claude", "codex", "env", "powershell", "json"];

export function initExportUi({ api, state, openModal }) {
  function readSavedExportFmt() {
    try {
      const saved = localStorage.getItem(EXPORT_FMT_KEY);
      if (saved && EXPORT_FMTS.includes(saved)) return saved;
    } catch { /* ignore */ }
    return "claude";
  }

  function saveExportFmt(fmt) {
    try {
      if (EXPORT_FMTS.includes(fmt)) localStorage.setItem(EXPORT_FMT_KEY, fmt);
    } catch { /* ignore */ }
  }

  function closeMoreMenu() {
    const menu = $("#more-dropdown");
    const btn = $("#btn-more");
    if (!menu || menu.hidden) return;
    menu.hidden = true;
    if (btn) btn.setAttribute("aria-expanded", "false");
  }

  function toggleMoreMenu() {
    const menu = $("#more-dropdown");
    const btn = $("#btn-more");
    if (!menu) return;
    const next = menu.hidden;
    menu.hidden = !next;
    if (btn) btn.setAttribute("aria-expanded", next ? "true" : "false");
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
    if (state.exportMode === "batch" || state.exportMode === "backup") return;
    if (!state.exportId) return;
    const fmt = $("#exp-fmt").value;
    saveExportFmt(fmt);
    const result = await api("GET", `/api/keys/${state.exportId}/export?fmt=${fmt}`);
    $("#exp-text").value = result.text || "";
  }

  function downloadCurrentExport() {
    const text = $("#exp-text").value;
    if (!String(text || "").trim()) return toast("没有可下载的内容");
    let fmt = "json";
    let prefix = "apikey-export";
    if (state.exportMode === "backup") {
      fmt = "json";
      prefix = "apikey-backup";
    } else if (state.exportMode === "batch") {
      fmt = "json";
      prefix = "apikey-batch";
    } else {
      fmt = $("#exp-fmt").value || "json";
      prefix = `apikey-${fmt}`;
    }
    downloadText(exportFilename(fmt, prefix), text);
    toast("已开始下载");
  }

  async function openSingleExport(key) {
    state.exportId = key.id;
    state.exportMode = "single";
    $("#exp-fmt").disabled = false;
    $("#exp-fmt").value = readSavedExportFmt();
    $("#exp-meta").textContent = key.name || key.base_url;
    openModal("modal-export");
    return updateExport();
  }

  async function backupAll() {
    closeMoreMenu();
    if (!Number(state.summary?.all || state.total || 0)) return toast("还没有可备份的 Key");
    const result = await api("GET", "/api/keys/export_all");
    state.exportId = null;
    state.exportMode = "backup";
    $("#exp-fmt").value = "json";
    $("#exp-fmt").disabled = true;
    $("#exp-meta").textContent = `全部备份 · ${result.count || state.keys.length} 条 JSON`;
    $("#exp-text").value = result.text || "";
    openModal("modal-export");
  }

  $("#btn-more")?.addEventListener("click", (event) => {
    event.stopPropagation();
    toggleMoreMenu();
  });
  document.addEventListener("click", (event) => {
    if (!event.target.closest?.("#more-menu")) closeMoreMenu();
  });
  $("#btn-backup-all")?.addEventListener("click", () => { backupAll().catch(() => {}); });
  $("#btn-export-selected").addEventListener("click", () => { closeMoreMenu(); exportSelected(); });
  $("#btn-export-mobile")?.addEventListener("click", () => $("#btn-export-selected").click());
  $("#exp-fmt").addEventListener("change", updateExport);
  $("#btn-copy").addEventListener("click", () => copyText($("#exp-text").value, "配置"));
  $("#btn-download")?.addEventListener("click", downloadCurrentExport);

  return {
    closeMoreMenu,
    toggleMoreMenu,
    exportSelected,
    updateExport,
    openSingleExport,
    readSavedExportFmt,
    saveExportFmt,
  };
}
