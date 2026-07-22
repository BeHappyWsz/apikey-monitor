# 密钥管理增强：筛选、历史、严格巡检、标签与模型刷新

## Goal

Improve daily key operations with focused discovery, observability, and scheduled validation. The work covers enhanced list filters, bounded probe history, opt-in periodic strict model checks, tags, and a manual remote-model refresh.

## Requirements

1. Operators can filter the paged key list by detected protocol, strict-probe adapter, whether a check model is configured, and an exact tag, in addition to the existing status/search/sort controls.
2. Each health or strict-model result records a bounded, non-secret history entry containing kind, status, latency, sanitized error, and timestamp. The UI shows a recent history/trend view for a key.
3. A global, opt-in strict-monitor setting runs strict probes only for monitored keys with a configured `check_model`, on a separate persisted cadence and without disturbing health-check scheduling.
4. Keys accept normalized free-form tags on create, edit, import/batch add, and sync payloads. Tags appear on cards and can be filtered.
5. Operators can manually refresh one key's remote model list using the current credentials. The result updates the existing model cache and returns a non-secret response.
6. Both SQLite and MySQL migrations must preserve existing installations. Existing list, monitor, strict verification, import/export, and masking behavior must remain compatible.
7. Public API and UI documentation describe the new contracts; test coverage includes DB, service/API, and frontend rendering/state where applicable.

## Acceptance Criteria

- [x] All four new filters work together with status, search, cursor paging, and list summaries.
- [x] Tags are normalized, stored, masked-row-safe, rendered, and retained through supported batch/sync flows.
- [x] History records health and strict outcomes without secrets, is bounded per query, and renders correctly when empty.
- [x] Strict scheduling respects enablement, configured model, monitoring state, cadence, and does not trigger an unbounded scan.
- [x] Manual model refresh updates models and handles an unreachable provider without exposing the API key.
- [x] SQLite and MySQL schema paths stay valid; existing tests plus new regression tests pass.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
