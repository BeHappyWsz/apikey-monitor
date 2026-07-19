import { $, toast, withBusyButton } from "./utils.js";

export function initSync({ api, load, openModal }) {
  function toggleHttpWarn() {
    const value = String($("#sync-server").value || "").toLowerCase();
    $("#sync-warn-http").hidden = !value.startsWith("http://");
  }

  function collect() {
    return {
      server: $("#sync-server").value.trim(),
      username: $("#sync-username").value.trim(),
      remote_path: $("#sync-remote").value.trim(),
      password: $("#sync-password").value,
    };
  }

  async function fillConfig() {
    try {
      const cfg = await api("GET", "/api/sync/config");
      $("#sync-server").value = cfg.server || "";
      $("#sync-username").value = cfg.username || "";
      $("#sync-remote").value = cfg.remote_path || "";
      $("#sync-password").value = "";
      $("#sync-password").placeholder = cfg.has_password ? "已设置（留空保持不变）" : "应用密码";
      toggleHttpWarn();
    } catch { /* surface handled by api() toast */ }
  }

  async function refreshStatus() {
    try {
      const status = await api("GET", "/api/sync/status");
      $("#sync-status").textContent = status.last_sync ? `上次同步：${status.last_sync}` : "未同步。";
    } catch { /* ignore */ }
  }

  $("#btn-sync").addEventListener("click", () => withBusyButton($("#btn-sync"), async () => {
    $("#sync-status").textContent = "正在加载同步配置…";
    openModal("modal-sync");
    await fillConfig();
    await refreshStatus();
  }));

  $("#sync-server").addEventListener("input", toggleHttpWarn);
  $("#btn-sync-save").addEventListener("click", async () => {
    try {
      await api("POST", "/api/sync/config", collect());
      await fillConfig();
      toast("WebDAV 设置已保存");
    } catch { /* surfaced */ }
  });

  // Persist current fields first, then probe — guarantees the test uses what the user typed.
  $("#btn-sync-test").addEventListener("click", async () => {
    try {
      await api("POST", "/api/sync/config", collect());
      const result = await api("POST", "/api/sync/test", {});
      const parts = [result.exists ? "远程文件已存在" : "远程文件不存在（首次将新建）"];
      if (result.last_modified) parts.push(`更新于 ${result.last_modified}`);
      toast("连接成功：" + parts.join(" · "), 4200);
    } catch { /* surfaced */ }
  });

  $("#btn-sync-upload").addEventListener("click", async () => {
    try {
      const result = await api("POST", "/api/sync/upload", {});
      toast(`已上传 ${result.count} 条到云端` + (result.remote_modified ? `（${result.remote_modified}）` : ""));
      refreshStatus();
    } catch { /* surfaced */ }
  });

  $("#btn-sync-download-merge").addEventListener("click", async () => {
    try {
      const result = await api("POST", "/api/sync/download", { mode: "merge" });
      const parts = [`新增 ${result.count} 条`];
      if (result.skipped_duplicate) parts.push(`跳过重复 ${result.skipped_duplicate}`);
      toast("合并完成：" + parts.join(" · "), 3600);
      await load();
      refreshStatus();
    } catch { /* surfaced */ }
  });

  // Destructive: confirm in UI (a local snapshot is taken server-side before replacing).
  $("#btn-sync-download-replace").addEventListener("click", async () => {
    if (!confirm("全量替换将以云端为准覆盖本机全部 Key（替换前会自动本地备份一份）。确认继续？")) return;
    try {
      const result = await api("POST", "/api/sync/download", { mode: "replace" });
      toast(`已替换为云端 ${result.count} 条` + (result.backup_path ? "，本地备份已保存" : ""), 3600);
      await load();
      refreshStatus();
    } catch { /* surfaced */ }
  });
}
