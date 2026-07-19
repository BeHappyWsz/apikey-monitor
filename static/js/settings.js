import { restartCandidates } from "./state.js";
import { $, copyText, esc, toast, withBusyButton, confirmAction } from "./utils.js";

export function initSettings({ api, state, openModal, closeModal, waitForHealth, onSettingsApplied }) {
  async function loadSettings() {
    const settings = await api("GET", "/api/settings");
    let runtime;
    try {
      runtime = await api("GET", "/api/system/health");
    } catch {
      runtime = {
        status: "unknown",
        host: settings.serverHost,
        port: settings.serverPort,
        health_unavailable: true,
      };
    }
    state.settings = settings;
    state.runtime = runtime;
    return settings;
  }

  $("#btn-system-settings").addEventListener("click", () => withBusyButton($("#btn-system-settings"), async () => {
    try {
      const settings = await loadSettings();
      $("#set-host").value = settings.serverHost;
      $("#set-port").value = settings.serverPort;
      $("#lan-warning").hidden = settings.serverHost !== "0.0.0.0";
      openModal("modal-system-settings");
    } catch {
      // api() has already shown the actionable server error.
    }
  }));

  function setMonitorEnabled(value) {
    const on = String(value) === "1";
    $("#set-enabled-on").classList.toggle("active", on);
    $("#set-enabled-off").classList.toggle("active", !on);
    $("#set-enabled-on").setAttribute("aria-pressed", String(on));
    $("#set-enabled-off").setAttribute("aria-pressed", String(!on));
  }
  function currentMonitorEnabled() {
    return $("#set-enabled-on").classList.contains("active") ? "1" : "0";
  }

  $("#btn-monitor-settings").addEventListener("click", () => withBusyButton($("#btn-monitor-settings"), async () => {
    try {
      const settings = await loadSettings();
      setMonitorEnabled(settings.globalMonitorEnabled);
      $("#set-interval").value = settings.globalIntervalSec;
      $("#set-down").value = settings.downRecheckIntervalSec;
      $("#set-conc").value = settings.concurrency;
      $("#set-timeout").value = settings.requestTimeoutSec;
      $("#set-ui-refresh").value = settings.uiRefreshIntervalSec ?? 15;
      openModal("modal-monitor-settings");
    } catch {
      // api() has already shown the actionable server error.
    }
  }));

  $("#set-enabled-on").addEventListener("click", () => { setMonitorEnabled("1"); autoSaveMonitor(true); });
  $("#set-enabled-off").addEventListener("click", () => { setMonitorEnabled("0"); autoSaveMonitor(true); });

  // Auto-save on field change. Numeric inputs debounce 600ms so a
  // burst of keystrokes only triggers one save; the toggle is
  // immediate. The save status line below the form confirms state.
  let monitorSaveTimer = null;
  let monitorSaving = false;
  function collectMonitorPayload() {
    return {
      ...state.settings,
      globalMonitorEnabled: currentMonitorEnabled(),
      globalIntervalSec: $("#set-interval").value,
      downRecheckIntervalSec: $("#set-down").value,
      concurrency: $("#set-conc").value,
      requestTimeoutSec: $("#set-timeout").value,
      uiRefreshIntervalSec: $("#set-ui-refresh").value,
    };
  }
  function setMonitorStatus(text, kind = "info") {
    const el = $("#monitor-save-status");
    if (!el) return;
    el.textContent = text;
    el.dataset.kind = kind;
  }
  async function autoSaveMonitor(immediate = false) {
    if (monitorSaving) return;
    clearTimeout(monitorSaveTimer);
    const run = async () => {
      monitorSaving = true;
      setMonitorStatus("正在保存…", "saving");
      try {
        const payload = collectMonitorPayload();
        const saved = await api("POST", "/api/settings", payload, { silent: true });
        state.settings = saved || payload;
        if (typeof onSettingsApplied === "function") onSettingsApplied(state.settings);
        setMonitorStatus("已自动保存", "saved");
      } catch (err) {
        setMonitorStatus(err.message || "保存失败", "error");
      } finally {
        monitorSaving = false;
      }
    };
    if (immediate) await run();
    else monitorSaveTimer = setTimeout(run, 600);
  }
  ["#set-interval", "#set-down", "#set-conc", "#set-timeout", "#set-ui-refresh"].forEach((sel) => {
    $(sel)?.addEventListener("input", () => autoSaveMonitor());
    $(sel)?.addEventListener("change", () => autoSaveMonitor(true));
  });

  $("#set-host").addEventListener("change", () => {
    $("#lan-warning").hidden = $("#set-host").value !== "0.0.0.0";
  });

  $("#btn-copy-start").addEventListener("click", () => withBusyButton($("#btn-copy-start"), () => copyText(`python app.py --host ${$("#set-host").value} --port ${$("#set-port").value}`, "启动命令"), { busyLabel: "复制中…" }));

  $("#btn-save-system-settings").addEventListener("click", () => withBusyButton($("#btn-save-system-settings"), async () => {
    const host = $("#set-host").value;
    const port = $("#set-port").value.trim();
    if (host === "0.0.0.0" && !await confirmAction("确认将监听地址设为 0.0.0.0？局域网内其他设备可访问本管理页面，且当前未启用访问密码。请只在可信网络使用。", { okLabel: "确认", danger: true })) return;
    await api("POST", "/api/settings", { ...state.settings, serverHost: host, serverPort: port });
    closeModal("modal-system-settings");
    const runtimeHost = state.runtime.host || state.settings.serverHost;
    const runtimePort = state.runtime.port ?? state.settings.serverPort;
    if (runtimeHost === host && String(runtimePort) === String(port)) return toast("系统设置已保存，无需重启");
    if (!await confirmAction("将关闭旧端口并切换到新端口；若失败会自动恢复旧端口。确认立即重启？", { okLabel: "立即重启" })) {
      return toast("设置已保存，可稍后重新打开系统设置执行重启");
    }
    followRestart(await api("POST", "/api/system/restart", {}));
  }, { busyLabel: "保存中…" }));

  async function followRestart(status) {
    openModal("modal-restart", true);
    for (;;) {
      $("#restart-state").textContent = status.message || status.status;
      $("#restart-steps").innerHTML = (status.steps || []).map((step) => `<li class="${esc(step.status)}">${esc(step.message || step.status)}</li>`).join("");
      if (["succeeded", "rolled_back", "failed", "no_change"].includes(status.status)) break;
      await new Promise((resolve) => setTimeout(resolve, 700));
      for (const base of restartCandidates(status)) {
        try {
          status = await api("GET", `${base}/api/system/restart/${status.restart_id}`);
          break;
        } catch {}
      }
    }
    if (status.status === "failed") {
      $("#modal-restart").dataset.forced = "0";
      return toast("重启失败，请手动启动服务", 5000);
    }
    for (const base of restartCandidates(status)) {
      if (await waitForHealth(base, 1200)) {
        window.location.href = base + `/?restart=${status.status}`;
        return;
      }
    }
    $("#modal-restart").dataset.forced = "0";
    toast("服务已处理重启，但浏览器暂时无法连接", 5000);
  }
}
