# Implementation Plan: Vue 3 CDN UI rewrite

## Ordered Work

1. Inspect every existing `static/index.html` control and the handler in
   `static/app.js` / `static/js/*`; create a checked migration matrix covering
   its API action, client state, loading/error behavior, and Vue owner.
2. Replace `index.html` with a minimal `#app` host, static loading/failure
   region, exact pinned Vue CDN script, and the module bootstrap. Keep no
   server-side template or build dependency.
3. Create the API composable by porting the existing relative request,
   `ApiError`, CSRF, and health-poll behavior unchanged. Add a reactive store
   and retain framework-free selectors as pure testable modules.
4. Implement the app shell and light minimalist tokens/layout. Add shared
   accessible modal, confirmation, toast, empty/loading/error, and form-field
   primitives before feature screens.
5. Port authentication and bootstrap-password UI, then the key workspace:
   initial load, revision refresh, metrics, filters/search, selection, drag
   ordering, add/edit, copy/show secret, models, and single/batch checking.
6. Port import preview/save, selected/all exports and backup, batch delete,
   task progress/problem filtering, WebDAV sync, system/monitor settings and
   restart progress, and user list/create controls.
7. Test all workflows against the unchanged API, delete unused legacy
   DOM-mutating modules/imports, and update frontend architecture/dependency
   documentation to replace vanilla-only claims.

## Acceptance Matrix

| Area | Required repeatable check |
| --- | --- |
| Runtime | Fresh checkout serves the page with Python alone; browser requests the exact Vue URL and boot failure displays the recovery region. |
| Authentication | Login, logout, forced password change, CSRF failure, user list/create, and unauthenticated API rejection behave as today. |
| Keys | Load/revision refresh, filter/search, select, reorder, add, edit, show/copy secret, models, single/batch check, delete confirmation, and empty state work. |
| Data movement | Text/JSON parse preview, batch save, selected export, whole backup, and WebDAV upload/merge/replace retain their current warnings and response handling. |
| Operations | Monitoring/system settings validation, safe restart progress, batch task polling, and problem filtering work. |
| Responsive/accessibility | Keyboard modal close/focus return, visible focus, error text, destructive confirmation, and narrow viewport layout work. |

## Validation Commands

```powershell
python -m unittest discover -s tests -v
node --check static/app.js
node --check static/js/composables/api-client.js
node --check static/js/composables/use-app-store.js
node --test tests/state.test.mjs
```

Run the acceptance matrix in a current desktop browser and a narrow responsive
viewport. Inspect network requests to verify masked list payloads and explicit
secret retrieval. Do not run a Node dependency install as part of validation.

## Rollback

If smoke validation fails, restore the prior committed `static/` tree and
redeploy it against the same API/database. The Vue child makes no schema or API
change, so its rollback is independent of the `tbl_*` migration.
