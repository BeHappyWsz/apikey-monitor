import { getVisibleKeys, hasIssueStatus, isHealthyOnline, selectionSummary, cardFingerprint } from "./state.js";
import { renderCard, captureListUi, restoreListUi } from "./cards.js";
import { $, $$, esc } from "./utils.js";

export function createListUi({ state, load, loadMore }) {
  let pageObserver = null;
  function countStatuses() {
    if (state.summary && Object.keys(state.summary).length) {
      return { all: 0, up: 0, down: 0, auth_error: 0, rate_limited: 0, issue: 0, problem: 0, unknown: 0, ...state.summary };
    }
    const counts = { all: state.keys.length, up: 0, down: 0, auth_error: 0, rate_limited: 0, issue: 0, problem: 0, unknown: 0 };
    state.keys.forEach((key) => {
      const status = key.status || "unknown";
      if (status === "up") {
        if (isHealthyOnline(key)) counts.up++;
        else counts.problem++;
        if (hasIssueStatus(key)) counts.issue++;
      } else if (status === "down") { counts.down++; counts.problem++; }
      else if (status === "auth_error") { counts.auth_error++; counts.problem++; }
      else if (status === "rate_limited") { counts.rate_limited++; counts.issue++; counts.problem++; }
      else if (status === "degraded") { counts.issue++; counts.problem++; }
      else { counts.unknown++; counts.problem++; }
    });
    return counts;
  }

  function renderStats() {
    const counts = countStatuses();
    if (state.summary && Object.keys(state.summary).length) {
      $("#st-total").textContent = counts.all || 0;
      $("#st-up").textContent = counts.up || 0;
      $("#st-down").textContent = counts.down || 0;
      $("#st-auth").textContent = counts.auth_error || 0;
      $("#st-issue").textContent = counts.issue || 0;
      $("#st-avg").textContent = counts.avg_latency_ms == null ? "—" : `${counts.avg_latency_ms}ms`;
      return;
    }
    let latencySum = 0, latencyN = 0;
    state.keys.forEach((key) => {
      if (key.latency_ms != null) { latencySum += key.latency_ms; latencyN++; }
    });
    $("#st-total").textContent = counts.all;
    $("#st-up").textContent = counts.up;
    $("#st-down").textContent = counts.down;
    $("#st-auth").textContent = counts.auth_error;
    $("#st-issue").textContent = counts.issue;
    $("#st-avg").textContent = latencyN ? `${Math.round(latencySum / latencyN)}ms` : "—";
  }

  function renderFilterCounts() {
    const counts = countStatuses();
    for (const [key, id] of Object.entries({
      all: "cnt-all", up: "cnt-up", down: "cnt-down", auth_error: "cnt-auth",
      rate_limited: "cnt-rate-limited", issue: "cnt-issue", problem: "cnt-problem", unknown: "cnt-unknown",
    })) {
      const el = $("#" + id);
      if (el) el.textContent = counts[key];
    }
    $$("#status-filter .seg").forEach((button) => button.classList.toggle("active", button.dataset.status === state.status));
  }

  function setBtnDisabled(el, disabled, titleWhenDisabled) {
    if (!el) return;
    if (!el.dataset.titleBase) el.dataset.titleBase = el.getAttribute("title") || "";
    el.disabled = !!disabled;
    if (disabled && titleWhenDisabled) el.title = titleWhenDisabled;
    else el.title = el.dataset.titleBase || "";
  }

  function updateBatchActions() {
    const hasSel = state.selected.size > 0;
    // `total` is scoped to the active server-side filter. Backup remains
    // available when that filter has no matches but the account still has keys.
    const hasKeys = Number(state.summary?.all || 0) > 0;
    setBtnDisabled($("#btn-check"), !hasSel, "请先勾选要检测的项目");
    setBtnDisabled($("#btn-export-selected"), !hasSel, "请先勾选要导出的项目");
    setBtnDisabled($("#btn-delete"), !hasSel, "请先勾选要删除的项目");
    setBtnDisabled($("#btn-check-mobile"), !hasSel, "请先勾选要检测的项目");
    setBtnDisabled($("#btn-export-mobile"), !hasSel, "请先勾选要导出的项目");
    setBtnDisabled($("#btn-delete-mobile"), !hasSel, "请先勾选要删除的项目");
    setBtnDisabled($("#btn-backup-all"), !hasKeys, "还没有可备份的 Key");
  }

  function renderSelection(rows = getVisibleKeys(state.keys, state.status, state.query)) {
    const summary = selectionSummary(state.selected, rows);
    const bar = $("#selection-bar");
    $("#sel-all").checked = rows.length > 0 && summary.visible === rows.length;
    $("#sel-all").indeterminate = summary.visible > 0 && summary.visible < rows.length;
    const hiddenPart = summary.hidden ? `，隐藏选择 ${summary.hidden} 条` : "";
    $("#selection-summary").textContent = `已选择 ${summary.total} 条（当前结果共 ${summary.resultTotal} 条${hiddenPart}）`;
    bar.classList.toggle("active", summary.total > 0);
    updateBatchActions();
  }

  function bindPageFooter(list) {
    $(".js-load-more", list)?.addEventListener("click", () => loadMore());
    $(".js-page-refresh", list)?.addEventListener("click", () => load());
    pageObserver?.disconnect();
    const moreButton = $(".js-load-more", list);
    if (moreButton && "IntersectionObserver" in window) {
      pageObserver = new IntersectionObserver((entries) => {
        if (entries.some((entry) => entry.isIntersecting)) loadMore();
      }, { rootMargin: "360px 0px" });
      pageObserver.observe(moreButton);
    }
  }

  function patchKeyList(list, rows) {
    const existing = new Map();
    for (const node of list.querySelectorAll(".key-card[data-id]")) {
      existing.set(String(node.dataset.id), node);
    }
    const frag = document.createDocumentFragment();
    for (const key of rows) {
      const id = String(key.id);
      const fp = cardFingerprint(key, state);
      const prev = existing.get(id);
      if (prev && prev.dataset.fp === fp) {
        frag.appendChild(prev);
        existing.delete(id);
        continue;
      }
      const wrap = document.createElement("div");
      wrap.innerHTML = renderCard(key, state).trim();
      const card = wrap.firstElementChild;
      if (card) {
        card.dataset.fp = fp;
        frag.appendChild(card);
      }
      existing.delete(id);
    }
    list.replaceChildren(frag);
    if (state.total) {
      const loadedLabel = "已加载";
      const refreshLabel = "发现更新，刷新列表";
      const loadingLabel = "加载中…";
      const moreLabel = "加载更多";
      const pending = state.refreshPending
        ? `<button class="btn ghost js-page-refresh" type="button">${refreshLabel}</button>`
        : "";
      const more = state.hasMore
        ? `<button class="btn js-load-more" type="button" ${state.pageLoading ? "disabled" : ""}>${state.pageLoading ? loadingLabel : moreLabel}</button>`
        : "";
      const foot = document.createElement("div");
      foot.className = "page-load";
      foot.dataset.pageFooter = "1";
      foot.innerHTML = `<span>${loadedLabel} ${state.keys.length} / ${state.total}</span>${pending}${more}`;
      list.appendChild(foot);
    }
    bindPageFooter(list);
  }

  function render({ preserveUi = false } = {}) {
    const ui = preserveUi ? captureListUi() : null;
    renderStats();
    renderFilterCounts();
    const list = $("#key-list");
    const empty = $("#empty");
    if (state.loading) {
      list.innerHTML = Array.from({ length: 3 }, () => `<article class="key-card skeleton-card"><div></div><div></div><div></div></article>`).join("");
      empty.hidden = true;
      renderSelection();
      return;
    }
    if (state.loadError) {
      list.innerHTML = `<div class="inline-state error-state"><b>列表加载失败</b><span>${esc(state.loadError)}</span><button class="btn" id="btn-inline-retry">重试</button></div>`;
      empty.hidden = true;
      $("#btn-inline-retry")?.addEventListener("click", () => load());
      renderSelection();
      return;
    }
    const rows = state.keys;
    patchKeyList(list, rows);
    if (!state.total && !Number(state.summary?.all || 0)) {
      empty.hidden = false;
      empty.querySelector(".empty-title").textContent = "还没有 Key";
      if (empty.querySelector(".empty-desc")) empty.querySelector(".empty-desc").textContent = "三步开始：粘贴配置 → 预览确认 → 自动检测。支持环境变量 / curl / JSON 备份，也可手动添加。";
      const steps = empty.querySelector(".empty-steps"); if (steps) steps.hidden = false;
      const hint = empty.querySelector(".empty-hint"); if (hint) hint.hidden = false;
      const badge = empty.querySelector(".empty-badge"); if (badge) badge.hidden = false;
      empty.querySelector(".empty-actions").hidden = false;
    } else if (!rows.length) {
      empty.hidden = false;
      empty.querySelector(".empty-title").textContent = "当前筛选没有结果";
      if (empty.querySelector(".empty-desc")) empty.querySelector(".empty-desc").textContent = "试试切换状态筛选，或清空搜索关键字。";
      empty.querySelector(".empty-actions").hidden = true;
      const steps = empty.querySelector(".empty-steps"); if (steps) steps.hidden = true;
      const hint = empty.querySelector(".empty-hint"); if (hint) hint.hidden = true;
      const badge = empty.querySelector(".empty-badge"); if (badge) badge.hidden = true;
    } else {
      empty.hidden = true;
    }
    renderSelection(rows);
    if (preserveUi) restoreListUi(ui);
  }

  return {
    render,
    renderStats,
    renderFilterCounts,
    renderSelection,
    updateBatchActions,
    countStatuses,
  };
}
