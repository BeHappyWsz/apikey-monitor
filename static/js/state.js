const issueStatuses = new Set(["rate_limited", "degraded"]);
const problemStatuses = new Set(["down", "auth_error", "rate_limited", "degraded", "unknown"]);
const strictProblemStatuses = new Set(["down", "auth_error", "rate_limited", "degraded"]);

export function hasStrictModelIssue(key) {
  return Number(key?.model_verification_version || 0) >= 1
    && strictProblemStatuses.has(key?.model_status || "unknown");
}

export function hasIssueStatus(key) {
  return issueStatuses.has(key?.status || "unknown") || (
    Number(key?.model_verification_version || 0) >= 1
    && issueStatuses.has(key?.model_status || "unknown")
  );
}

export function hasProblemStatus(key) {
  return problemStatuses.has(key?.status || "unknown") || hasStrictModelIssue(key);
}

export function getVisibleKeys(keys, status = "all", query = "") {
  const q = String(query || "").trim().toLowerCase();
  return keys.filter((key) => {
    const state = key.status || "unknown";
    if (status === "issue") {
      if (!hasIssueStatus(key)) return false;
    } else if (status === "problem") {
      if (!hasProblemStatus(key)) return false;
    } else if (status !== "all" && state !== status) {
      return false;
    }
    if (!q) return true;
    return [key.name, key.base_url, key.check_model, key.notes, ...(key.models || [])]
      .some((value) => String(value || "").toLowerCase().includes(q));
  });
}

export function selectCurrentResults(selected, visible, checked) {
  const next = new Set(selected);
  for (const key of visible) checked ? next.add(key.id) : next.delete(key.id);
  return next;
}

export function selectionSummary(selected, visible) {
  const visibleIds = new Set(visible.map((key) => key.id));
  const visibleSelected = [...selected].filter((id) => visibleIds.has(id)).length;
  return { total: selected.size, visible: visibleSelected, hidden: selected.size - visibleSelected, resultTotal: visible.length };
}

export function taskProgress(task) {
  const total = Number(task?.total || 0);
  const completed = Number(task?.completed || 0);
  return { percent: total ? Math.round(completed * 100 / total) : 100,
    label: `${completed}/${total}`, terminal: ["completed", "partial_failed", "failed"].includes(task?.status) };
}

export function restartCandidates(status) {
  if (!status) return [];
  if (["rolled_back", "restoring_old_config", "starting_fallback", "verifying_fallback"].includes(status.status))
    return [status.old_url, status.target_url].filter(Boolean);
  return [status.target_url, status.old_url].filter(Boolean);
}

export function isLatestResponse(requestId, latestId) { return requestId === latestId; }

export function moveKey(keys, sourceId, targetId) {
  if (sourceId === targetId) return keys.slice();
  const next = keys.slice();
  const from = next.findIndex((key) => key.id === sourceId);
  const to = next.findIndex((key) => key.id === targetId);
  if (from < 0 || to < 0) return keys.slice();
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

export function canReorder(status, query, sort = "default", filters = {}) {
  return status === "all" && !String(query || "").trim() && (sort || "default") === "default"
    && Object.values(filters || {}).every((value) => !value || value === "all");
}

export function keysFingerprint(keys) {
  return (keys || []).map((key) => [
    key.id, key.status, key.latency_ms, key.last_check_at, key.last_error,
    key.model_status, key.model_latency_ms, key.model_last_check_at, key.model_last_error,
    key.model_verification_version, key.model_probe_adapter, key.monitor_enabled, key.name,
    key.base_url, key.check_model, key.notes, (key.models || []).join(","),
    key.supports_openai, key.supports_anthropic, key.openai_status, key.anthropic_status, key.sort_order,
    key.api_key_masked || "", key.has_api_key ? 1 : 0, key.monitor_count || 0, key.strict_count || 0,
    key.tags || "",
  ].join(":")).join("|");
}
