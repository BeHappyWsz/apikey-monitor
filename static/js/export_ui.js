import { $, copyText, downloadText, exportFilename, toast, withBusyButton } from "./utils.js";
import { openModal, closeModal } from "./dialogs.js";

const EXPORT_FMT_KEY = "apikeyconfig.exportFmt";
const EXPORT_FMTS = ["claude", "codex", "env", "powershell", "json"];
const CCSWITCH_FMTS = new Set(["claude", "codex"]);

export function resolveCcswitchApp(key) {
  const adapter = key?.model_probe_adapter || "";
  if (adapter === "anthropic_messages") return "claude";
  if (adapter === "openai_chat" || adapter === "openai_responses") return "codex";
  const anth = Boolean(key?.supports_anthropic);
  const oai = Boolean(key?.supports_openai);
  if (anth && !oai) return "claude";
  if (oai && !anth) return "codex";
  return null;
}

function openDeepLink(deeplink) {
  if (!deeplink) return false;
  try {
    const anchor = document.createElement("a");
    anchor.href = deeplink;
    anchor.rel = "noopener";
    anchor.style.display = "none";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    return true;
  } catch {
    try {
      window.location.href = deeplink;
      return true;
    } catch {
      return false;
    }
  }
}

export function initExportUi({ api, state, openModal: openModalFn }) {
  const open = openModalFn || openModal;
  let pendingCcswitchKey = null;
  let lastDeeplink = "";

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

  function setCcswitchActionsVisible(show) {
    const openBtn = $("#btn-open-ccswitch");
    const copyLinkBtn = $("#btn-copy-deeplink");
    if (openBtn) openBtn.hidden = !show;
    if (copyLinkBtn) copyLinkBtn.hidden = !show;
  }

  function applyExportResult(result, fmt) {
    $("#exp-text").value = result?.text || "";
    lastDeeplink = result?.deeplink || "";
    setCcswitchActionsVisible(Boolean(lastDeeplink) && CCSWITCH_FMTS.has(fmt));
  }

  async function exportSelected() {
    if (!state.selected.size) return toast("请先选择要导出的项目");
    state.exportMode = "batch";
    state.exportId = null;
    lastDeeplink = "";
    setCcswitchActionsVisible(false);
    $("#exp-fmt").value = "json";
    $("#exp-fmt").disabled = true;
    $("#exp-meta").textContent = `批量 JSON · ${state.selected.size} 条`;
    open("modal-export");
    const result = await api("POST", "/api/keys/batch_export", { ids: [...state.selected], fmt: "json" });
    $("#exp-text").value = result.text || "";
  }

  async function updateExport() {
    if (state.exportMode === "batch" || state.exportMode === "backup") return;
    if (!state.exportId) return;
    const fmt = $("#exp-fmt").value;
    saveExportFmt(fmt);
    const result = await api("GET", `/api/keys/${state.exportId}/export?fmt=${fmt}`);
    applyExportResult(result, fmt);
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
    lastDeeplink = "";
    $("#exp-fmt").disabled = false;
    $("#exp-fmt").value = readSavedExportFmt();
    $("#exp-meta").textContent = key.name || key.base_url;
    open("modal-export");
    return updateExport();
  }

  async function openCcswitchImport(key, app) {
    const fmt = app === "codex" ? "codex" : "claude";
    const result = await api("GET", `/api/keys/${key.id}/export?fmt=${fmt}`);
    const deeplink = result?.deeplink || "";
    if (!deeplink) {
      toast("无法生成 CCSwitch 导入链接", 4200);
      return openSingleExport(key);
    }
    const opened = openDeepLink(deeplink);
    toast(opened
      ? "已尝试打开 CCSwitch；若未响应可到导出里复制配置"
      : "无法打开深链，请在导出中复制配置", 4200);
  }

  async function importToCcswitch(key) {
    const app = resolveCcswitchApp(key);
    if (app) return openCcswitchImport(key, app);
    pendingCcswitchKey = key;
    open("modal-ccswitch-app");
  }

  async function backupAll() {
    closeMoreMenu();
    if (!Number((state.summary?.pool ?? state.summary?.all) || state.total || 0)) return toast("还没有可备份的 Key");
    const result = await api("GET", "/api/keys/export_all");
    state.exportId = null;
    state.exportMode = "backup";
    lastDeeplink = "";
    setCcswitchActionsVisible(false);
    $("#exp-fmt").value = "json";
    $("#exp-fmt").disabled = true;
    $("#exp-meta").textContent = `全部备份 · ${result.count || state.keys.length} 条 JSON`;
    $("#exp-text").value = result.text || "";
    open("modal-export");
  }

  function openCurrentDeeplink() {
    if (!lastDeeplink) return toast("当前格式不支持 CCSwitch 深链");
    const ok = openDeepLink(lastDeeplink);
    toast(ok ? "已尝试打开 CCSwitch" : "打开失败，请复制深链或配置", 4200);
  }

  $("#btn-more")?.addEventListener("click", (event) => {
    event.stopPropagation();
    toggleMoreMenu();
  });
  document.addEventListener("click", (event) => {
    if (!event.target.closest?.("#more-menu")) closeMoreMenu();
  });
  $("#btn-backup-all")?.addEventListener("click", () => withBusyButton($("#btn-backup-all"), () => backupAll().catch(() => {}), { busyLabel: "备份中…" }));
  $("#btn-export-selected").addEventListener("click", () => withBusyButton($("#btn-export-selected"), () => { closeMoreMenu(); exportSelected(); }, { busyLabel: "导出中…" }));
  $("#btn-export-mobile")?.addEventListener("click", () => withBusyButton($("#btn-export-mobile"), () => $("#btn-export-selected").click(), { busyLabel: "导出中…" }));
  $("#exp-fmt").addEventListener("change", updateExport);
  $("#btn-copy").addEventListener("click", () => withBusyButton($("#btn-copy"), () => copyText($("#exp-text").value, "配置"), { busyLabel: "复制中…" }));
  $("#btn-download")?.addEventListener("click", () => withBusyButton($("#btn-download"), downloadCurrentExport, { busyLabel: "下载中…" }));
  $("#btn-open-ccswitch")?.addEventListener("click", () => withBusyButton($("#btn-open-ccswitch"), () => openCurrentDeeplink(), { busyLabel: "打开中…" }));
  $("#btn-copy-deeplink")?.addEventListener("click", () => withBusyButton($("#btn-copy-deeplink"), async () => {
    if (!lastDeeplink) return toast("当前没有可复制的深链");
    await copyText(lastDeeplink, "深链（含密钥，勿外传）");
  }, { busyLabel: "复制中…" }));

  $("#btn-ccswitch-claude")?.addEventListener("click", () => withBusyButton($("#btn-ccswitch-claude"), async () => {
    const key = pendingCcswitchKey;
    pendingCcswitchKey = null;
    closeModal("modal-ccswitch-app");
    if (key) await openCcswitchImport(key, "claude");
  }, { busyLabel: "导入中…" }));
  $("#btn-ccswitch-codex")?.addEventListener("click", () => withBusyButton($("#btn-ccswitch-codex"), async () => {
    const key = pendingCcswitchKey;
    pendingCcswitchKey = null;
    closeModal("modal-ccswitch-app");
    if (key) await openCcswitchImport(key, "codex");
  }, { busyLabel: "导入中…" }));

  return {
    closeMoreMenu,
    toggleMoreMenu,
    exportSelected,
    updateExport,
    openSingleExport,
    importToCcswitch,
    openCcswitchImport,
    resolveCcswitchApp,
    readSavedExportFmt,
    saveExportFmt,
  };
}
