import { canReorder } from "./state.js";
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
    return { tone: "down", label: "不可接入：Key 鉴权失败", detail: "请更新 API Key 后重新严格验证" };
  }
  if (strictModelVerified && modelState === "auth_error") {
    return { tone: "down", label: "不可接入：模型鉴权失败", detail: "请确认模型权限后重新验证" };
  }
  if (status === "rate_limited" || (strictModelVerified && modelState === "rate_limited")) {
    return { tone: "rate-limited", label: "暂缓接入：严格验证限流", detail: "等待额度恢复后再用于 ccswitch" };
  }
  if (!key.check_model) {
    return { tone: "unknown", label: "未确认：缺少验证模型", detail: "设置模型后执行严格验证" };
  }
  if (!strictModelVerified) {
    return { tone: "unknown", label: "未确认：请先严格验证", detail: "有 API Key 不代表可直接调用" };
  }
  if (modelState !== "up") {
    return { tone: modelState.replace(/_/g, "-"), label: `不建议接入：${statusLabel[modelState] || "模型异常"}`, detail: "先处理模型验证错误" };
  }
  if (adapter === "openai_chat") {
    return { tone: "up", label: "可直接接入 ccswitch", detail: "OpenAI chat/completions 可用" };
  }
  if (adapter === "openai_responses") {
    return { tone: "degraded", label: "需 Responses 兼容壳", detail: "仅 /responses 严格验证通过" };
  }
  if (adapter === "anthropic_messages") {
    return { tone: "degraded", label: "需 Anthropic Messages 壳", detail: "按 Messages 协议适配后接入" };
  }
  return { tone: "degraded", label: "可用但接入方式未识别", detail: "查看端点文档后配置适配壳" };
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
  const advice = accessAdvice(key);
  const tone = status.replace(/_/g, "-");
  const sortable = canReorder(state.status, state.query, state.sort);
  return `<article class="key-card status-${tone}" data-id="${key.id}" ${sortable ? 'draggable="true"' : ""}>
    <header class="card-head">
      <div class="card-title" title="${sortable ? '拖拽卡片可调整顺序' : ''}"><input class="row-sel" type="checkbox" ${state.selected.has(key.id) ? "checked" : ""} aria-label="选择 ${esc(key.name || key.base_url)}"><div><h3>${esc(key.name || "未命名 Key")}</h3><button class="url-copy js-copy-url" type="button">${esc(key.base_url)} <span>⧉</span></button><div class="card-meta" title="入库时间：${esc(formatCreatedAt(key.created_at))}"><i class="meta-dot" aria-hidden="true"></i><span>入库 ${formatCreatedAt(key.created_at)}</span><span class="meta-sep" aria-hidden="true">·</span><span>${relativeTime(key.created_at)}</span></div></div></div>
      <div class="status-panel">
        <span class="status-main ${tone}"><i class="dot ${tone}"></i>${busy ? "检测中" : statusLabel[status] || "未知"}</span>
        <span class="status-meta"><b>${key.latency_ms == null ? "—" : `${key.latency_ms}ms`}</b><small>延迟</small></span>
        <span class="status-meta"><b>${relativeTime(key.last_check_at)}</b><small>最近检测</small></span>
      </div>
    </header>
    <div class="card-body-grid">
      <div class="metric primary-metric"><span>API Key</span><b class="key-mask-line"><span class="masked-key">${esc(key.api_key_masked || maskKey(key.api_key))}</span><button class="link-btn js-copy-key" type="button" title="复制完整 API Key">复制</button></b></div>
      <div class="metric"><span>在线协议</span><b class="protocol-statuses">${protocols.length ? protocols.map(([name, protocolStatus]) => `<em class="protocol-state ${protocolStatus.replace(/_/g, "-")}">${name} · ${statusLabel[protocolStatus] || "未知"}</em>`).join("") : "未确认"}</b></div>
      <div class="metric wide-metric"><span>严格验证</span><b class="model-state ${modelTone}">${esc(key.check_model || "未设置")} · ${modelLabel}</b></div>
      <div class="metric access-metric"><span>接入建议</span><b class="access-state ${advice.tone}">${esc(advice.label)}</b><small>${esc(advice.detail)}</small></div>
    </div>
    <details class="card-details"><summary>模型、备注与错误详情</summary><div><p><b>模型：</b>${models.length ? models.slice(0, 8).map((model) => `<span class="chip">${esc(model)}</span>`).join(" ") : "暂无"} ${models.length > 8 ? `<button class="link-btn js-models">查看全部 ${models.length}</button>` : ""}</p>${key.check_model ? `<p><b>最近严格验证：</b>${strictModelVerified ? relativeTime(key.model_last_check_at) : "未完成"}</p>` : ""}${(key.model_probe_adapter && strictModelVerified && key.model_status === "up") ? `<p><b>验证壳：</b>${esc(adapterLabel[key.model_probe_adapter] || key.model_probe_adapter)}</p>` : ""}${key.notes ? `<p><b>备注：</b>${esc(key.notes)}</p>` : ""}${(key.last_error && key.status !== "up") ? `<p class="error-line"><b>错误：</b>${esc(key.last_error)}</p>` : ""}${(key.model_last_error && strictModelVerified && key.model_status !== "up") ? `<p class="error-line"><b>模型错误：</b>${esc(key.model_last_error)}</p>` : ""}</div></details>
    <footer class="card-actions"><label class="monitor-toggle"><input class="row-mon" type="checkbox" ${key.monitor_enabled ? "checked" : ""}>监测</label><button class="btn soft js-check" ${busy ? "disabled" : ""}>${busy ? "检测中…" : "检测"}</button><button class="btn ghost js-check-model">严格验证</button><button class="btn ghost js-edit">编辑</button><button class="btn ghost js-export">导出</button><button class="btn danger-soft js-del">删除</button></footer>
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
