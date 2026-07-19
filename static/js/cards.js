import { canReorder } from "./state.js";
import { esc, maskKey, relativeTime, statusLabel } from "./utils.js";

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
  const tone = status.replace(/_/g, "-");
  const sortable = canReorder(state.status, state.query);
  return `<article class="key-card status-${tone}" data-id="${key.id}" ${sortable ? 'draggable="true"' : ""}>
    <header class="card-head">
      <div class="card-title" title="${sortable ? '拖拽卡片可调整顺序' : ''}"><input class="row-sel" type="checkbox" ${state.selected.has(key.id) ? "checked" : ""} aria-label="选择 ${esc(key.name || key.base_url)}"><div><h3>${esc(key.name || "未命名 Key")}</h3><button class="url-copy js-copy-url" type="button">${esc(key.base_url)} <span>⧉</span></button></div></div>
      <div class="status-panel">
        <span class="status-main ${tone}"><i class="dot ${tone}"></i>${busy ? "检测中" : statusLabel[status] || "未知"}</span>
        <span class="status-meta"><b>${key.latency_ms == null ? "—" : `${key.latency_ms}ms`}</b><small>延迟</small></span>
        <span class="status-meta"><b>${relativeTime(key.last_check_at)}</b><small>最近检测</small></span>
      </div>
    </header>
    <div class="card-body-grid">
      <div class="metric primary-metric"><span>API Key</span><b class="key-mask-line"><span>${esc(key.api_key_masked || maskKey(key.api_key))}</span><button class="link-btn js-copy-key" type="button" title="复制完整 API Key">复制</button></b></div>
      <div class="metric"><span>在线协议</span><b class="protocol-statuses">${protocols.length ? protocols.map(([name, protocolStatus]) => `<em class="protocol-state ${protocolStatus.replace(/_/g, "-")}">${name} · ${statusLabel[protocolStatus] || "未知"}</em>`).join("") : "未确认"}</b></div>
      <div class="metric wide-metric"><span>模型检测</span><b class="model-state ${modelState.replace(/_/g, "-")}">${esc(key.check_model || "未设置")} · ${statusLabel[modelState] || "未知"}</b></div>
    </div>
    <details class="card-details"><summary>模型、备注与错误详情</summary><div><p><b>模型：</b>${models.length ? models.slice(0, 8).map((model) => `<span class="chip">${esc(model)}</span>`).join(" ") : "暂无"} ${models.length > 8 ? `<button class="link-btn js-models">查看全部 ${models.length}</button>` : ""}</p>${key.notes ? `<p><b>备注：</b>${esc(key.notes)}</p>` : ""}${(key.last_error && key.status !== "up") ? `<p class="error-line"><b>错误：</b>${esc(key.last_error)}</p>` : ""}${(key.model_last_error && key.model_status !== "up") ? `<p class="error-line"><b>模型错误：</b>${esc(key.model_last_error)}</p>` : ""}</div></details>
    <footer class="card-actions"><label class="monitor-toggle"><input class="row-mon" type="checkbox" ${key.monitor_enabled ? "checked" : ""}>监测</label><button class="btn soft js-check" ${busy ? "disabled" : ""}>${busy ? "检测中…" : "检测"}</button><button class="btn ghost js-check-model">模型检测</button><button class="btn ghost js-edit">编辑</button><button class="btn ghost js-export">导出</button><button class="btn danger-soft js-del">删除</button></footer>
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
