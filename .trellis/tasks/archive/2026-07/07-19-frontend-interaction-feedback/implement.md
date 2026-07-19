# Implementation plan: Frontend interaction feedback

## Ordered work

1. **Bootstrap & runtime**
   1.1. Pick exact Vue 3.x version; review the published source diff
   against the previously reviewed version. Place at
   `static/vendor/vue.global.js` with `vue.global.js.sha256` next to it.
   1.2. Replace `static/index.html` with a static boot/error region +
   `<script src="/vendor/vue.global.js">` + `<script type="module"
   src="/js/app-bootstrap.js">`.
   1.3. Write `static/js/app-bootstrap.js` — fetch the vendored script
   head-request check, set `window.Vue`, and lazily replace any
   `#fb-load-error` region with a clear Chinese recovery message if the
   file is missing.

2. **Shared infrastructure**
   2.1. Port `static/js/api.js` to `static/js/composables/api-client.js`
   unchanged in semantics: relative URLs, CSRF header, JSON envelopes.
   Add the global `inFlightCount` (reads/writes a `ref` exported to the
   store) and the idempotency set (`Map<key, Promise>`).
   2.2. Implement `use-app-store.js` — the reactive shape described in
   design.md. Single owner for everything Vue touches.
   2.3. Add `static/js/utils.js` (carried over): pure selectors, body
   hashing, fingerprint computation.

3. **Feedback primitives (deliver in this exact order, gate later steps
   on smoke)**
   3.1. `LoadingBar` — drives off `inFlightCount`; mount from
   `AppShell`.
   3.2. `BusyButton` — `<button>` wrapper, owns click lifecycle.
   3.3. `BusyOverlay` — region wrapper with `aria-busy` and
   `pointer-events: none`.
   3.4. `ToastStack` — reads `toasts` array, auto-dismiss, click-to-
   dismiss, `role=`.

4. **Application shell**
   4.1. `AppShell` — global layout, mount `LoadingBar` and `ToastStack`,
   host the `<router-view>`-equivalent region for current screen state.
   4.2. `BaseModal` — accessible modal primitive (escape, focus return,
   scroll lock, focus trap).

5. **Feature screens (port to Vue, preserving workflows)**
   5.1. Login + bootstrap-password flow (`AppShell` boot path).
   5.2. `KeyWorkspace` — load/revision refresh, metrics, filters,
   selection, drag ordering, list rendering. Card-style display matches
   current cards.
   5.3. `KeyFormModal` — add/edit, models, secret actions (`BusyButton`
   for save; `BusyButton` for show-secret; toast on copy).
   5.4. `ImportExportModal` — text/JSON parse preview (wrap preview in
   `BusyOverlay` while parsing); batch save; selected/all export; full
   backup. Toasts replace `alert(...)` and `confirm(...)`.
   5.5. `TaskProgressModal` — batch/probe polling, problem filtering,
   completion toast.
   5.6. `SettingsModals` — system + monitor settings save via
   `BusyButton`; safe-restart progress via `TaskProgressModal`-style
   modal.
   5.7. `SyncModal` — WebDAV actions with `BusyOverlay` during upload/
   merge/replace.
   5.8. `UserModals` — user list/create/password change; create/delete
   via `BusyButton`.

6. **Legacy cleanup**
   6.1. Smoke-test all current workflows through Vue UI.
   6.2. Delete `static/app.js` (replaced by bootstrap) and the retired
   `static/js/*` modules listed in design.md.
   6.3. `grep -nE 'alert\\(|confirm\\(' static/js/composables static/js/components`
   must be empty for production code (test fixtures may keep them).

7. **Acceptance matrix & validation**
   7.1. Run the validation commands.
   7.2. Browser smoke per the acceptance matrix (see below).
   7.3. Capture before/after screenshots at desktop 1280px and narrow
   375px for the visual fidelity comparison.

## Acceptance matrix

| Area | Required repeatable check |
| --- | --- |
| Runtime | Fresh checkout serves the page with Python alone. Browser requests `/vendor/vue.global.js`. Missing file → recovery region shows. |
| Auth | Login, logout, forced password change, CSRF failure, user list/create, unauthenticated rejection all behave as today. |
| Keys | Load/revision refresh, filter/search, select, reorder, add, edit, show/copy secret, models, single/batch check, delete confirmation, empty state. |
| Data movement | Text/JSON parse preview, batch save, selected export, whole backup, WebDAV upload/merge/replace — current warnings and error mapping preserved. |
| Operations | Monitoring/system settings validation, safe restart progress, batch task polling, problem filtering. |
| Visual fidelity | Side-by-side screenshot comparison before/after at 1280px and 375px. New visuals limited to LoadingBar, BusyOverlay, ToastStack. |
| Feedback | Every API button flips to busy (visual + `aria-busy`) for the full in-flight window. Double-click <100ms → exactly one network request (verified in DevTools). |
| Progress | Top bar starts within one animation frame of `fetch` start; one bar for concurrent requests; zero layout shift. |
| Overlay | Region overlay renders with `aria-busy="true"` and `pointer-events: none`; clears automatically on resolve. |
| Toast | Auto-dismiss on timeout; click-to-dismiss; correct `role`. No `alert(` in production code. |
| Accessibility | Visible focus, keyboard tab order, escape closes modals, focus returns to trigger. |

## Validation commands

```powershell
# Syntax & unit checks (existing + new)
node --check static/app-bootstrap.js
node --check static/js/composables/api-client.js
node --check static/js/composables/use-app-store.js
node --check static/js/components/LoadingBar.js
node --check static/js/components/BusyButton.js
node --check static/js/components/BusyOverlay.js
node --check static/js/components/ToastStack.js
node --check static/js/components/AppShell.js
node --check static/js/components/BaseModal.js
node --check static/js/components/KeyWorkspace.js
node --check static/js/components/KeyFormModal.js
node --check static/js/components/ImportExportModal.js
node --check static/js/components/TaskProgressModal.js
node --check static/js/components/SettingsModals.js
node --check static/js/components/SyncModal.js
node --check static/js/components/UserModals.js
node --test tests/state.test.mjs

# Browser smoke (manual)
python -m http.server 8765 --directory static
# open http://127.0.0.1:8765/ in a real browser
# complete the acceptance matrix in a fresh tab
# open DevTools → Network → repeat double-click test
```

## Rollback

1. `git revert <merge-commit>` restores the prior `static/` tree.
2. Server is unchanged; no DB rollback needed.
3. Recovery region already protects users against a missing Vue file.

## Time budget (within the user's 2-hour ask)

| Stage | Allocation |
| --- | --- |
| Steps 1–3 (bootstrap + primitives) | 35 min |
| Steps 4–5 (shell + 8 feature screens) | 60 min |
| Step 6 (legacy cleanup) | 10 min |
| Step 7 (validation, screenshots, fixes) | 15 min |
| Buffer for fixes | 20 min |
| **Total** | **140 min** |

If the budget is at risk, the priority order to compress is:
first defer screenshot capture to a follow-up, second cut docs to
in-code comments, third cut keyboard-trap tests (acceptance still
covered by manual smoke).
