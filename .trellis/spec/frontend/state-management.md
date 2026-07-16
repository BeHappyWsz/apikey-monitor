# State Management

> In-memory UI state, pure selectors, refresh races, and browser-only preferences.

---

## Overview

There is **no** Redux/MobX/Vuex. `static/app.js` owns one mutable `state` object. Pure derived logic lives in `static/js/state.js` and is unit-tested with Node (`tests/state.test.mjs`).

Server state is re-fetched; the client is not offline-first.

---

## Canonical `state` object (`app.js`)

```javascript
const state = {
  keys: [],                 // last GET /api/keys payload (masked)
  selected: new Set(),      // selected key ids
  status: "all",            // filter: all | up | down | auth_error | unknown | problem | issue | ...
  query: "",                // search string
  loading: true,
  loadError: "",
  checking: new Set(),      // ids currently in-flight check UX
  editId: null,
  exportId: null,
  exportMode: "single",     // single | batch | all
  modelId: null,
  candidates: [],           // import preview rows
  candidateSelected: new Set(),
  settings: {},             // GET /api/settings
  runtime: {},              // from health (pid/host/port/version) when loaded
  draggingId: null,
  fingerprint: "",          // keysFingerprint(keys) for silent refresh short-circuit
};
```

When adding fields, keep them on this object (or document a nested slice) ? do not create a second parallel store.

---

## Browser persistence (not secrets)

| Key | Storage | Purpose |
|-----|---------|---------|
| `apikeyconfig.exportFmt` | `localStorage` | Last export format preference (`claude`/`codex`/`env`/`powershell`/`json`) |

Do **not** store API keys in `localStorage` / `sessionStorage`.

---

## Pure selectors (`state.js`)

| Function | Behavior |
|----------|----------|
| `getVisibleKeys(keys, status, query)` | Status filter + case-insensitive search over name/url/model/notes/models |
| `selectCurrentResults(selected, visible, checked)` | Select/deselect all visible |
| `selectionSummary(selected, visible)` | total / visible / hidden counts |
| `taskProgress(task)` | percent, label, terminal flag |
| `restartCandidates(status)` | URL order for post-restart navigation (rollback prefers old URL) |
| `isLatestResponse(requestId, latestId)` | Stale response guard |
| `moveKey(keys, sourceId, targetId)` | Immutable reorder array |
| `canReorder(status, query)` | Reorder only when filter is `all` and query empty |
| `keysFingerprint(keys)` | Stable string of status-relevant fields for poll short-circuit |

**Rules:** no DOM, no `fetch` inside `state.js`. New filter math ? add Node tests.

### Filter semantics worth preserving

- `problem` ? not `up` (includes `down`, `auth_error`, `unknown`, plus reserved labels).
- `issue` currently targets `rate_limited` / `degraded` (reserved for future probe statuses).
- Search matches `name`, `base_url`, `check_model`, `notes`, and `models[]`.

---

## Load / refresh loop

`load({ silent })` in `app.js`:

1. Uses `request(..., { latest: true })` so older in-flight list fetches abort/ignore.
2. Computes `keysFingerprint`; if `silent` and fingerprint unchanged and no `checking`, skips full list re-render (still refreshes stats/selection chrome).
3. `preserveUi` path captures open `<details>`, scroll, focus around re-render.

UI poll interval: `settings.ui_refresh_interval_sec` (`0` disables). After mutations, call `load()` (non-silent as appropriate).

---

## HTTP helper interaction (`api.js`)

- `request(method, path, body, { latest })` returns `{ payload, id, isLatest }`.
- `app.js` `api()` wraps it, toasts on non-abort errors, returns **payload only**.
- Feature modules should use the injected `api` from context so toasts stay consistent.

---

## Selection & batch UX

- Batch actions disabled when selection empty.
- Reorder POST `/api/keys/reorder` must send the full desired id order; only when `canReorder` is true in UI.
- Import preview uses `candidates` / `candidateSelected`, separate from main list selection.

---

## Anti-patterns

- Duplicating filter logic in render and handlers.
- Expecting `api_key` on list rows.
- Multiple competing refresh timers.
- Applying silent poll results without `isLatest` / fingerprint guards.
- Persisting selection Sets to disk.
