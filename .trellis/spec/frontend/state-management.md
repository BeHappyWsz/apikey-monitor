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
  keys: [],                 // loaded masked rows for the active server-side page sequence
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
  fingerprint: "",          // keysFingerprint(keys) for rendered rows
  nextCursor: "",           // opaque next page cursor from GET /api/keys/page
  hasMore: false,
  total: 0,                 // total matching active status + query
  summary: {},              // status counters matching query, before status filter
  pageLoading: false,
  refreshPending: false,    // revision changed; wait for user to refresh first page
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
Include strict-model access metadata such as `model_probe_adapter` in
`keysFingerprint(keys)` because the card can change its ccswitch guidance
without any status label changing.

### Filter semantics worth preserving

- `problem` ? not `up` (includes `down`, `auth_error`, `unknown`, plus reserved labels).
- `issue` currently targets `rate_limited` / `degraded` (reserved for future probe statuses).
- Status and search are sent to the page endpoint after a short input debounce;
  do not reintroduce client-only filtering over an assumed complete `keys`
  collection.

---

## Load / refresh loop

`load({ silent, append })` in `app.js`:

1. An explicit load fetches `GET /api/keys/page?limit=50&status=&q=` and
   replaces the loaded rows. `append: true` sends `nextCursor` and appends only
   the next page.
2. Uses `request(..., { latest: true })` so older in-flight list fetches abort/ignore.
3. A silent refresh only asks `GET /api/keys/revision`. If it changed, set
   `refreshPending` and show an explicit refresh action; do not replace a
   scrolled list in the background.
4. `preserveUi` path captures open `<details>`, scroll, focus around append
   renders.

UI poll interval: `settings.uiRefreshIntervalSec` (`0` disables). After mutations, call `load()` (non-silent as appropriate).

## Scenario: List-revision SSE refresh prompt

### 1. Scope / Trigger

Use this contract when a list mutation should reach an open panel sooner than
the configured revision poll, without disrupting a paged, scrolled, selected,
or edited list.

### 2. Signatures

- `GET /api/keys/events` returns authenticated `text/event-stream`.
- Event name: `revision`; payload: `{ "revision": "opaque-revision" }`.
- `services.list_events.notify_list_changed(revision)` broadcasts from
  `db.touch_list_generation()` after public-list cache invalidation.

### 3. Contracts

- The server emits one initial revision event, sends heartbeat comments while
  idle, and has no replay/history guarantee. `EventSource` reconnects normally.
- `static/app.js` owns the one `EventSource`. A new revision only sets
  `state.refreshPending` and renders the existing refresh affordance with
  `preserveUi`; it must not fetch and replace the current page automatically.
- Existing revision polling remains a recovery path. While SSE is connected it
  may run less frequently; setting `uiRefreshIntervalSec=0` disables polling,
  not SSE.
- No secrets, key rows, or mutable list state travel through the event; the
  normal masked page endpoint remains the source of list data.

### 4. Validation & Error Matrix

| Condition | Required behavior |
| --- | --- |
| Missing/expired session | HTTP `401 unauthenticated`, no stream |
| Password change required | HTTP `403 password_change_required`, no stream |
| List write changes revision | Broadcast one latest `revision` payload |
| Idle stream | Send a comment heartbeat; do not fabricate a revision |
| Event JSON malformed/client unsupported | Ignore it and retain revision polling |
| Write failure after SSE headers | Close/reconnect; never append a JSON error to the stream |

### 5. Good/Base/Bad Cases

- Good: another tab adds a key; the current tab shows its refresh prompt and
  retains its scroll, selection, and open modal.
- Base: a reconnect receives the current initial revision and continues to use
  the normal list endpoint when the operator refreshes.
- Bad: handling a revision event with `load({ silent: true })`, which replaces
  a partially loaded page and violates the explicit-refresh contract.

### 6. Tests Required

- `tests/test_list_events.py` asserts a notification advances the sequence and
  returns the latest revision.
- `tests/test_integration.py` asserts the endpoint rejects unauthenticated
  access, returns `text/event-stream` after login, sends its initial revision,
  and emits a different revision after an authenticated list write.
- Run `node --check static/app.js`, `node --test tests/state.test.mjs`, and the
  full Python suite after changing this path.

### 7. Wrong vs Correct

```javascript
// Wrong: changes the operator's current page behind their back.
eventSource.addEventListener("revision", () => load({ silent: true }));

// Correct: keep list UI stable until an explicit refresh.
eventSource.addEventListener("revision", () => {
  state.refreshPending = true;
  listUi.render({ preserveUi: true });
});
```

---

## HTTP helper interaction (`api.js`)

- `request(method, path, body, { latest })` returns `{ payload, id, isLatest }`.
- `app.js` `api()` wraps it, toasts on non-abort errors, returns **payload only**.
- Feature modules should use the injected `api` from context so toasts stay consistent.

---

## Selection & batch UX

- Batch actions disabled when selection empty.
- Select-all covers loaded rows only. It must not imply that unloaded matching
  rows are selected.
- Reorder POST `/api/keys/reorder` must send the full desired id order; only when `canReorder` is true in UI.
- Import preview uses `candidates` / `candidateSelected`, separate from main list selection.

---

## Anti-patterns

- Duplicating filter logic in render and handlers.
- Expecting `api_key` on list rows.
- Multiple competing refresh timers.
- Applying silent poll results without `isLatest` / fingerprint guards.
- Persisting selection Sets to disk.
