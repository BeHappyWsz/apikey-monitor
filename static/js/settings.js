import { restartCandidates } from "./state.js";
import { $, copyText, esc, toast } from "./utils.js";

export function initSettings({ api, state, openModal, closeModal, waitForHealth }) {
  async function loadSettings() {
    const settings = await api("GET", "/api/settings");
    let runtime;
    try {
      runtime = await api("GET", "/api/system/health");
    } catch {
      runtime = {
        status: "unknown",
        host: settings.server_host,
        port: settings.server_port,
        health_unavailable: true,
      };
    }
    state.settings = settings;
    state.runtime = runtime;
    return settings;
  }

  $("#btn-system-settings").addEventListener("click", async () => {
    const settings = await loadSettings();
    $("#set-host").value = settings.server_host;
    $("#set-port").value = settings.server_port;
    openModal("modal-system-settings");
  });

  $("#btn-monitor-settings").addEventListener("click", async () => {
    const settings = await loadSettings();
    $("#set-enabled").value = settings.global_monitor_enabled;
    $("#set-interval").value = settings.global_interval_sec;
    $("#set-down").value = settings.down_recheck_interval_sec;
    $("#set-conc").value = settings.concurrency;
    $("#set-timeout").value = settings.request_timeout_sec;
    openModal("modal-monitor-settings");
  });

  $("#set-host").addEventListener("change", () => {
    $("#lan-warning").hidden = $("#set-host").value !== "0.0.0.0";
  });

  $("#btn-copy-start").addEventListener("click", () => copyText(`python app.py --host ${$("#set-host").value} --port ${$("#set-port").value}`, "启动命令"));

  $("#btn-save-monitor-settings").addEventListener("click", async () => {
    await api("POST", "/api/settings", {
      ...state.settings,
      global_monitor_enabled: $("#set-enabled").value,
      global_interval_sec: $("#set-interval").value,
      down_recheck_interval_sec: $("#set-down").value,
      concurrency: $("#set-conc").value,
      request_timeout_sec: $("#set-timeout").value,
    });
    closeModal("modal-monitor-settings");
    toast("监测设置已保存");
  });

  $("#btn-save-system-settings").addEventListener("click", async () => {
    const host = $("#set-host").value;
    const port = $("#set-port").value.trim();
    if (host === "0.0.0.0" && !confirm("0.0.0.0 会允许局域网设备访问本页面。当前项目未启用访问密码，确认继续？")) return;
    await api("POST", "/api/settings", { ...state.settings, server_host: host, server_port: port });
    closeModal("modal-system-settings");
    const runtimeHost = state.runtime.host || state.settings.server_host;
    const runtimePort = state.runtime.port ?? state.settings.server_port;
    if (runtimeHost === host && String(runtimePort) === String(port)) return toast("系统设置已保存，无需重启");
    if (!confirm("将关闭旧端口并切换到新端口；若失败会自动恢复旧端口。确认立即重启？")) {
      return toast("设置已保存，可稍后重新打开系统设置执行重启");
    }
    followRestart(await api("POST", "/api/system/restart", {}));
  });

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
