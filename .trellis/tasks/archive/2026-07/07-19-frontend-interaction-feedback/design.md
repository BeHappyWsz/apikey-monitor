# Design: Frontend interaction feedback (Vue 3 rewrite with feedback primitives)

## Chosen runtime

Reuse the vendored build slot the deferred task already calls for:

```text
/static/vendor/vue.global.js   (Vue 3.x, exact pinned version)
```

`static/index.html` keeps a static boot/error region. A module-bootstrap
checks the same-origin Vue script and replaces that region with a clear
Chinese recovery message if it is missing. Vue is exposed as `window.Vue`.
No package manager, import map, bundler, or TypeScript compiler.

The vendored file is security-sensitive: any version bump requires an
explicit source review and documentation update, not a floating CDN URL.

## Frontend architecture

```text
index.html
  └─ #app / static fatal-load region
       └─ app.js bootstrap
            └─ Vue createApp(App)
                 ├─ composables/api-client.js       HTTP + CSRF + ApiError + in-flight counter
                 ├─ composables/use-app-store.js    single reactive owner
                 ├─ components/AppShell.js          navigation + layout
                 ├─ components/LoadingBar.js        global top progress (R2)
                 ├─ components/BusyOverlay.js       region mask (R3)
                 ├─ components/ToastStack.js        toast notifications (R4)
                 ├─ components/BaseModal.js         accessible modal primitive
                 ├─ components/KeyWorkspace.js      stats, filters, selection, list
                 ├─ components/KeyFormModal.js      add/edit and sensitive-key actions
                 ├─ components/ImportExportModal.js import/preview/export/backup
                 ├─ components/TaskProgressModal.js batch/probe task polling
                 ├─ components/SettingsModals.js    system/monitor settings + restart
                 ├─ components/SyncModal.js         WebDAV actions/status
                 └─ components/UserModals.js        user list/create/password flow
```

Components use Vue's in-browser template/compiler capability or render
functions; `.vue` SFCs are excluded (would require a build step). Because
the shipped Vue global build compiles application templates in the
browser, CSP must permit same-origin `script-src` plus `unsafe-eval`,
but never `unsafe-inline`. Future compiled/render-function-only UI
removes the exception.

`use-app-store` is the single state owner for: session user, bootstrap/
password requirements, key list, list revision, filters, selected IDs,
modal intent, settings, active task/restart state, toasts, in-flight
counters, and busy regions. Pure selectors (filter, ordering, revision
fingerprints) stay framework-free in `static/js/utils.js` so the Node
unit tests keep passing.

## Feedback primitive contracts

These four primitives are the foundation every feature component must
use. Each declares its own CSS variables and z-index via the shared
token table in §"Layered visuals".

### `LoadingBar` (R2)

- Single global instance mounted by `AppShell`.
- Driven by a Vue `ref` counter `inFlightCount` on the store: incremented
  before `api-client` dispatches `fetch`, decremented in `finally`.
- Bar width is `min(95%, 30 + 70 * (1 - e^(-k * elapsedMs / 1000)) )%`,
  so quick requests show a small advance and long ones asymptote near
  100%. On counter returning to 0, width jumps to 100% then fades out
  in 240ms.
- `position: fixed; top: 0; left: 0; height: 2px;` — no layout shift,
  no insertion of placeholder elements.
- `role="progressbar"` with `aria-valuenow`/`aria-valuemin`/`aria-valuemax`
  bound to the animated width.

### `BusyButton` (R1)

- A wrapper component `<BusyButton :action="fn" idle-label="..." busy-label="..." :variant="...">`
  that renders a `<button>` and owns the click lifecycle.
- `action` is an `(payload) => Promise` (or returns an object with an
  `invoke()` method returning a Promise).
- On click:
  1. Sets `isBusy = true`, applies `disabled`, `aria-busy="true"`,
     swaps label/icon to `busy-label`/spinner.
  2. Calls `action()`. Always wraps the result with the request-layer
     idempotency key so the same logical request can't be re-issued.
  3. In `finally` clears `isBusy`. On error the parent modal/toast layer
     surfaces a toast; the button returns to idle regardless.
- Re-clicks during `isBusy` are absorbed silently (the underlying button
  is `disabled`, AND the request layer rejects duplicates — defense in
  depth).

### `BusyOverlay` (R3)

- A scoped slot wrapper around any region: `<BusyOverlay :busy="regionBusy">
    <KeyWorkspace ... />
  </BusyOverlay>`.
- When `busy === true`:
  - Region container gets `position: relative; pointer-events: none;`
    with an absolutely-positioned `aria-busy="true"` overlay containing
    a centered spinner.
  - Focus inside the region is still reachable for screen readers but
    clicks are absorbed.
- The overlay inherits the existing `--surface` token at 70% opacity and
  uses the same spinner asset as `BusyButton`.

### `ToastStack` (R4)

- A singleton mounted by `AppShell` at a fixed z-index above overlays.
- Reads `toasts` (array of `{id, kind, text, ttlMs}`) from the store.
- Each toast: `role="status"` for `kind ∈ {info, success, warning}`,
  `role="alert"` for `kind === 'error'`. Auto-dismiss in `ttlMs`
  (default 3000, errors 6000). Click anywhere on a toast dismisses it
  immediately. New toasts animate in from the right.
- `api-client` automatically emits a toast on error unless `silent: true`
  is passed; success is opt-in via explicit `notify.success(...)` calls
  from feature code.

## API client (`api-client.js`)

Owns every `/api/*` request. Behavior:

- Builds relative URLs against the current origin (no host switch).
- Adds CSRF header from `<meta name="csrf-token">` (server already
  exposes it).
- Wraps `fetch` in a Promise and:
  1. Increments the global `inFlightCount` before `fetch`.
  2. Increments the API idempotency set with a key
     `key = sha1(method + " " + normalizedPath + " " + sha1(body ?? ""))`.
     If the key is already pending, rejects the new Promise with an
     `ApiError('duplicate', 409)` without dispatching the request.
     This set is cleared when the request resolves.
  3. On JSON response >= 400, throws `ApiError(status, body)`. On network
     failure, throws `ApiError('network', 0, cause)`.
  4. Emits an error toast (unless `silent: true`); success toasts are
     explicit.
  5. Decrements the global `inFlightCount` in `finally`.
- Exposes `api.get/post/put/delete/upload(patch)` returning unwrapped
  JSON. `api.action(name, payload)` is the new shorthand that feature
  components should prefer — it composes the same URL, error, and
  toast plumbing.

## State store (`use-app-store.js`)

Shape (reactive, in-memory only):

```text
session:       { user, csrfToken, needsBootstrap, needsPasswordChange }
keys:          { list: [...], revision, fingerprint }
filters:       { query, providers, status, selectedIds: Set<string> }
modals:        { intent: null|'add'|'edit'|'import'|'export'|'sync'|'users'|'settings'|'tasks', payload }
settings:      { monitor, system }
task:          { id, status, processed, total, problems }
restart:       { id, status, message, lastError }
toasts:        [{ id, kind, text, ttlMs }]
busy:          { region: 'keys'|'import'|'sync'|'form'|null }
inFlightCount: number
```

`api-client` writes `inFlightCount`, `toasts`, `busy`. Feature components
read everything and dispatch actions only through the store. The store
exposes pure helper functions for selectors so they remain Node-testable.

## Visual system

Reuse the existing CSS custom properties already declared in
`static/style.css`. The new primitives only add:

```css
:root {
  --fb-progress:        var(--primary);          /* same hue family */
  --fb-progress-track:  transparent;
  --fb-mask:            color-mix(in srgb, var(--surface) 70%, transparent);
  --fb-spinner-size:    18px;
  --fb-toast-bg:        #1f2937;                 /* neutral dark */
  --fb-toast-fg:        #f9fafb;
  --fb-toast-error:     #b91c1c;
  --fb-toast-success:   #15803d;
  --fb-toast-warning:   #b45309;

  --z-progress:         1200;
  --z-mask:             1100;
  --z-toast:            1300;
  --z-modal:            1000;                    /* existing */
}
```

Visual elements added:

1. Top progress bar — 2px high, fixed, blends with primary color.
2. Region mask — 70% surface, centered 18px spinner.
3. Toast stack — right-aligned, 280px wide, rounded 8px, 12px padding.

Layout, typography, palette, and modals are reused unchanged. No new
color tokens; no new fonts; no grid rewrites.

## Legacy module retirement

The DOM-mutating modules under `static/js/` retire in one release:

| Old module | Replaced by |
| --- | --- |
| `add.js`, `editor.js` | `KeyFormModal` + `BusyButton` |
| `auth.js` | Login bootstrap inside `AppShell` |
| `cards.js`, `list_ui.js` | `KeyWorkspace` |
| `dialogs.js` | `BaseModal` (shared) |
| `export_ui.js` | `ImportExportModal` + toasts |
| `import.js` | `ImportExportModal` (with `BusyOverlay` for preview) |
| `list_actions.js` | `KeyWorkspace` + `BusyButton` + toasts |
| `settings.js` | `SettingsModals` |
| `sync.js` | `SyncModal` (+ `BusyOverlay` during upload) |
| `tasks.js` | `TaskProgressModal` |

After smoke validation, the legacy modules and their imports are
deleted in one commit (`static/app.js` is replaced by the module
bootstrap and removes the import list).

## Functional and security contracts

- No API endpoint, snake_case payload field, validator, or service
  behavior changes. The rewrite only changes rendering and client-side
  orchestration.
- List payloads stay masked. Complete API keys are still fetched only
  for explicit copy/show/export actions.
- CSRF, session, and the `/api/keys/revision` polling contract remain
  identical. Polling respects the current `monitor.intervalSec` and is
  started/stopped by the reactive lifecycle.
- Session/CSRF data remain out of `localStorage` / `sessionStorage`.
- Vendored Vue is a security-sensitive production dependency; version
  bumps are not silent.

## Accessibility

- `aria-busy="true"` on every busy button and masked region.
- `role="progressbar"` with `aria-valuenow` for the loading bar.
- `role="status"` (info/success/warning) and `role="alert"` (error) on
  toasts, with `aria-live="polite"` / `aria-live="assertive"` matching.
- Modal escape closes; focus returns to the trigger button.
- Visible focus indicators preserved on every focusable element; CSS
  uses `:focus-visible`.
- Color contrast meets WCAG AA for the toast palette against the page
  background and against itself.

## Risks and recovery

- **Missing Vue vendored build**: shows static recovery region; operator
  restores the reviewed file and reloads.
- **Workflow omission in rewrite**: cross-checked against the
  implementation acceptance matrix before legacy code is deleted.
- **Secret exposure regression**: keep list payloads masked; explicit
  copy/show/export hits the dedicated secret endpoint; smoke tests
  inspect network requests.
- **Duplicate-click race**: defense in depth — button disabled AND
  request-layer idempotency (`api-client` set), so a JS error or
  disabled-state visual glitch cannot cause a duplicate dispatch.
- **Static UI rollback**: Git-based, no schema rollback required.
