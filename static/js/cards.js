import { canReorder, hasStrictModelIssue } from "./state.js";
import { esc, formatCreatedAt, maskKey, relativeTime, statusLabel } from "./utils.js";

const adapterLabel = {
  openai_chat: "OpenAI chat/completions",
  openai_responses: "OpenAI /responses",
  anthropic_messages: "Anthropic Messages",
};

export function accessAdvice(key) {
  const status = key.status || "unknown";
  const modelState = key.model_status || "unknown";
  const strictModelVerified = Number(key.model_verification_version || 0) >= 1;
  const adapter = key.model_probe_adapter || "";
  if (status === "auth_error") {
    return { tone: "down", label: "Key \u9274\u6743\u5931\u8d25",
      title: "\u4e0d\u53ef\u63a5\u5165\uff1aKey \u9274\u6743\u5931\u8d25\uff1b\u8bf7\u66f4\u65b0 API Key \u540e\u91cd\u65b0\u4e25\u683c\u9a8c\u8bc1" };
  }
  if (strictModelVerified && modelState === "auth_error") {
    return { tone: "down", label: "\u6a21\u578b\u9274\u6743\u5931\u8d25",
      title: "\u4e0d\u53ef\u63a5\u5165\uff1a\u6a21\u578b\u9274\u6743\u5931\u8d25\uff1b\u8bf7\u786e\u8ba4\u6a21\u578b\u6743\u9650\u540e\u91cd\u65b0\u9a8c\u8bc1" };
  }
  if (status === "rate_limited" || (strictModelVerified && modelState === "rate_limited")) {
    return { tone: "rate-limited", label: "\u9650\u6d41 \u4e25\u683c\u9a8c\u8bc1",
      title: "\u6682\u7f13\u63a5\u5165\uff1a\u4e25\u683c\u9a8c\u8bc1\u9650\u6d41\uff1b\u7b49\u5f85\u989d\u5ea6\u6062\u590d\u540e\u518d\u7528\u4e8e ccswitch" };
  }
  if (!key.check_model) {
    return { tone: "unknown", label: "\u5f85\u914d\u7f6e\u6a21\u578b",
      title: "\u672a\u786e\u8ba4\uff1a\u7f3a\u5c11\u9a8c\u8bc1\u6a21\u578b\uff1b\u8bbe\u7f6e\u6a21\u578b\u540e\u6267\u884c\u4e25\u683c\u9a8c\u8bc1" };
  }
  if (!strictModelVerified) {
    return { tone: "unknown", label: "\u5f85\u4e25\u683c\u9a8c\u8bc1",
      title: "\u672a\u786e\u8ba4\uff1a\u8bf7\u5148\u4e25\u683c\u9a8c\u8bc1\uff1b\u6709 API Key \u4e0d\u4ee3\u8868\u53ef\u76f4\u63a5\u8c03\u7528" };
  }
  if (modelState !== "up") {
    return { tone: modelState.replace(/_/g, "-"),
      label: `\u4e0d\u5efa\u8bae ${statusLabel[modelState] || "\u5f02\u5e38"}`,
      title: `\u4e0d\u5efa\u8bae\u63a5\u5165\uff1a${statusLabel[modelState] || "\u6a21\u578b\u5f02\u5e38"}\uff1b\u5148\u5904\u7406\u6a21\u578b\u9a8c\u8bc1\u9519\u8bef` };
  }
  if (adapter === "openai_chat") {
    return { tone: "up", label: "\u76f4\u8fde Chat",
      title: "\u53ef\u76f4\u63a5\u63a5\u5165 ccswitch\uff1aOpenAI chat/completions \u53ef\u7528" };
  }
  if (adapter === "openai_responses") {
    return { tone: "degraded", label: "\u9700\u58f3 Responses",
      title: "\u9700 Responses \u517c\u5bb9\u58f3\uff1a\u4ec5 /responses \u4e25\u683c\u9a8c\u8bc1\u901a\u8fc7" };
  }
  if (adapter === "anthropic_messages") {
    return { tone: "degraded", label: "\u9700\u58f3 Messages",
      title: "\u9700 Anthropic Messages \u58f3\uff1a\u6309 Messages \u534f\u8bae\u9002\u914d\u540e\u63a5\u5165" };
  }
  return { tone: "degraded", label: "\u5f85\u786e\u8ba4\u63a5\u5165\u58f3",
    title: "\u53ef\u7528\u4f46\u63a5\u5165\u65b9\u5f0f\u672a\u8bc6\u522b\uff1b\u67e5\u770b\u7aef\u70b9\u6587\u6863\u540e\u914d\u7f6e\u9002\u914d\u58f3" };
}

/** Build HTML for a single key card. Pure string template (no DOM). */
export function renderCard(key, state) {
  const busy = state.checking.has(key.id);
  const status = key.status || "unknown";
  const protocols = [
    ["OpenAI", key.openai_status || "unknown"],
    ["Anthropic", key.anthropic_status || "unknown"],
  ].filter(([, protocolStatus]) => protocolStatus === "up");
  const models = key.models || [];
  const modelState = key.model_status || "unknown";
  const strictModelVerified = Number(key.model_verification_version || 0) >= 1;
  const modelLabel = !key.check_model ? "未配置" : !strictModelVerified ? "未严格验证" : (statusLabel[modelState] || "未知");
  const modelTone = strictModelVerified ? modelState.replace(/_/g, "-") : "unknown";
  const monitorCount = Number(key.monitor_count || 0);
  const strictCount = Number(key.strict_count || 0);
  const advice = accessAdvice(key);
  const accessProblem = hasStrictModelIssue(key);
  const tone = status.replace(/_/g, "-");
  const sortable = canReorder(state.status, state.query, state.sort);
  return `<article class="key-card status-${tone}${accessProblem ? " access-problem" : ""}" data-id="${key.id}" ${sortable ? 'draggable="true"' : ""}>
    <header class="card-head">
      <div class="card-title" title="${sortable ? '拖拽卡片可调整顺序' : ''}"><input class="row-sel" type="checkbox" ${state.selected.has(key.id) ? "checked" : ""} aria-label="选择 ${esc(key.name || key.base_url)}"><div><h3>${esc(key.name || "未命名 Key")}</h3><button class="url-copy js-copy-url" type="button">${esc(key.base_url)} <span>⧉</span></button><div class="card-meta" title="入库时间：${esc(formatCreatedAt(key.created_at))}"><i class="meta-dot" aria-hidden="true"></i><span>入库 ${formatCreatedAt(key.created_at)}</span><span class="meta-sep" aria-hidden="true">·</span><span>${relativeTime(key.created_at)}</span></div></div></div>
      <div class="status-panel">
        <span class="status-main ${tone}" title="整体状态：${esc(busy ? "检测中" : statusLabel[status] || "未知")}"><i class="dot ${tone}"></i>${busy ? "检测中" : statusLabel[status] || "未知"}</span>
        <div class="status-stats">
          <span class="status-meta" title="延迟：${key.latency_ms == null ? "暂无" : `${key.latency_ms}ms`}"><b>${key.latency_ms == null ? "—" : `${key.latency_ms}ms`}</b><small>延迟</small></span>
          <span class="status-meta" title="最近检测：${esc(relativeTime(key.last_check_at))}"><b>${relativeTime(key.last_check_at)}</b><small>检测</small></span>
          <span class="status-meta count-meta" title="已进行监测 ${monitorCount} 次"><b>${monitorCount}</b><small>监测</small></span>
          <span class="status-meta count-meta" title="已进行严格验证 ${strictCount} 次"><b>${strictCount}</b><small>严格验证</small></span>
        </div>
      </div>
    </header>
    <div class="card-body-grid">
      <div class="metric primary-metric"><span>API Key</span><b class="key-mask-line"><span class="masked-key">${esc(key.api_key_masked || maskKey(key.api_key))}</span><button class="link-btn js-copy-key" type="button" title="复制完整 API Key">复制</button></b></div>
      <div class="metric"><span>在线协议</span><b class="protocol-statuses">${protocols.length ? protocols.map(([name, protocolStatus]) => `<em class="protocol-state ${protocolStatus.replace(/_/g, "-")}">${name} · ${statusLabel[protocolStatus] || "未知"}</em>`).join("") : "未确认"}</b></div>
      <div class="metric model-metric"><span>严格验证模型</span><b class="model-state ${modelTone}">${esc(key.check_model || "未设置")} · ${modelLabel}</b></div>
      <div class="metric access-metric" title="${esc(advice.title)}"><b class="access-state ${advice.tone}" title="${esc(advice.title)}"><em>${esc(advice.label)}</em></b></div>
    </div>
    <details class="card-details"><summary>模型、备注与错误详情</summary><div><p><b>模型：</b>${models.length ? models.slice(0, 8).map((model) => `<span class="chip">${esc(model)}</span>`).join(" ") : "暂无"} ${models.length > 8 ? `<button class="link-btn js-models">查看全部 ${models.length}</button>` : ""}</p>${key.check_model ? `<p><b>最近严格验证：</b>${strictModelVerified ? relativeTime(key.model_last_check_at) : "未完成"}</p>` : ""}<p class="count-summary"><b>检测统计：</b>监测 ${monitorCount} 次 · 严格验证 ${strictCount} 次</p>${(key.model_probe_adapter && strictModelVerified && key.model_status === "up") ? `<p><b>验证壳：</b>${esc(adapterLabel[key.model_probe_adapter] || key.model_probe_adapter)}</p>` : ""}${key.notes ? `<p><b>备注：</b>${esc(key.notes)}</p>` : ""}${(key.last_error && key.status !== "up") ? `<p class="error-line"><b>错误：</b>${esc(key.last_error)}</p>` : ""}${(key.model_last_error && strictModelVerified && key.model_status !== "up") ? `<p class="error-line"><b>模型错误：</b>${esc(key.model_last_error)}</p>` : ""}</div></details>
    <footer class="card-actions"><label class="monitor-toggle"><input class="row-mon" type="checkbox" ${key.monitor_enabled ? "checked" : ""}>监测</label><button class="btn soft js-check" ${busy ? "disabled" : ""}>${busy ? "检测中…" : "检测"}</button><button class="btn ghost js-check-model">严格验证</button><button class="btn ghost js-edit">编辑</button><button class="btn ghost js-export">导出</button><button class="btn soft js-import-ccswitch" type="button" title="一键导入到 CCSwitch">导入CCSwitch</button><button class="btn danger-soft js-del">删除</button></footer>
  </article>`;
}

export function captureListUi() {
  const open = new Set();
  document.querySelectorAll("#key-list details[open]").forEach((details) => {
    const id = Number(details.closest(".key-card")?.dataset.id);
    if (id) open.add(id);
  });
  return {
    open,
    scrollY: window.scrollY,
    activeId: document.activeElement?.closest?.(".key-card")?.dataset?.id || null,
    activeClass: document.activeElement?.className || "",
  };
}

export function restoreListUi(ui) {
  if (!ui) return;
  for (const id of ui.open) {
    const details = document.querySelector(`.key-card[data-id="${id}"] details`);
    if (details) details.open = true;
  }
  window.scrollTo(0, ui.scrollY || 0);
}
