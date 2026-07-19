# PRD: Frontend interaction feedback

## Status

Draft. Awaiting user review before `task.py start`.

## Background & Problem

The current vanilla HTML/CSS/ESM UI gives almost no feedback when a user
clicks a button that triggers an asynchronous action. There is no loading
state on the button, no global activity indicator, and no mask to block
interaction. As a result:

- Users cannot tell whether the click registered.
- Users frequently double-click and trigger duplicated requests
  (duplicate API-key creation, repeat imports, repeat restart, etc.).
- Errors are surfaced as silent failures or unrelated page state; users
  cannot tell a successful save from a network failure.

The deferred Vue 3 rewrite (`cdn-frontend-framework`) provides the natural
vehicle to introduce a unified interaction-feedback layer: declarative
button states, a top progress bar, a card/list overlay, and a toast stack.
This new task is the live, scoped version of that rewrite focused on
interaction feedback, and reuses the architecture already drafted in the
deferred task.

## Goal

Rewrite the existing `static/` UI onto Vue 3 (CDN, local vendored build,
no bundler) and add a first-class interaction-feedback layer so every
mutating user action gives unambiguous visual feedback and is
idempotent against accidental duplicate clicks. Visual style must remain
indistinguishable from the current page.

## Confirmed Facts

- The client is native HTML/CSS plus ES modules. `static/index.html`
  holds most markup; `static/app.js` owns mutable page state and
  initializes feature modules under `static/js/`.
- `static/vendor/` already exists for vendored runtime assets.
- The project has no `package.json`, bundler, TypeScript, or npm-based
  build today. A Node install must not become a runtime requirement.
- The UI handles security-sensitive actions: API-key display/export,
  import, and authenticated user management.
- `cdn-frontend-framework` is a deferred sibling task whose PRD/design/
  implement already cover the architectural shape this task re-uses.

## Non-Goals

- Changing any API endpoint, snake_case payload field, server validator,
  or backend behavior. CSRF, secret-masking, and auth bootstrap remain
  identical.
- Dark theme, runtime theme switching, or layout redesign.
- Reintroducing npm, a bundler, or a compile step.
- Touching `cdn-frontend-framework`'s deferred status in this task. This
  task stands alone; the two converge once both ship.

## Requirements

### R1 — Interaction feedback is mandatory for every API trigger

R1.1. Every control that issues an API request (login, key
create/edit/delete/copy/show/probe, import, export, settings save,
restart, sync, user create/delete, batch actions, polling-driven refresh
controls) must show one of the following during the in-flight window:
- Button-level loading state: text/icon swap, `disabled` attribute set,
  `aria-busy="true"`, and the same visual contract as a passive button
  when not loading.
- Card/region overlay (semi-transparent mask + spinner) for actions that
  affect a region rather than a single button (e.g. import preview,
  batch probe).

R1.2. A request is in-flight from the moment the click handler dispatches
the request until the response is processed (success or error). During
this window the originating control must not accept another click.

R1.3. The interface does not assume a fixed network latency; the loading
state is bound to the actual promise lifecycle (`fetch` start → resolve
or reject), not a timer.

R1.4. If a control can be re-clicked after completion, the visual state
must return to the clickable idle state without a full page reload.

### R2 — Global activity indicator

R2.1. A thin top progress bar appears at the top of the viewport the
moment any in-flight API request starts, animates to indicate ongoing
activity, and reaches 100% on completion (then fades). The bar must not
occlude page content or trigger layout shift.

R2.2. The bar uses CSS variables consistent with the existing primary
color so it blends into the current visual.

R2.3. The bar is a single shared instance — concurrent requests must not
spawn multiple bars. Bar start/stop is driven by a single in-flight
counter on the shared state store.

### R3 — Region overlay (mask) for long-running operations

R3.1. When an operation affects a region (key list during batch save,
import preview while parsing, WebDAV sync during upload), the region
gets a semi-transparent overlay with a centered spinner, pointer-events
disabled on the region, and `aria-busy="true"` on the region container.

R3.2. The overlay is dismissible implicitly by completion only — no
manual close button. The mask is removed atomically when the underlying
operation resolves.

R3.3. The overlay inherits the existing `--surface` / `--mask` color
tokens; no new color tokens are introduced.

### R4 — Toast notifications

R4.1. Success, warning, and error messages surface in a right-aligned
toast stack near the top of the viewport. Toasts auto-dismiss after a
short timeout (default 3s, errors 6s), stack vertically with newest on
top, and can be dismissed by clicking them.

R4.2. Toasts replace the existing `alert(...)` calls scattered across
`static/js/*`. The migration removes every `alert`/`confirm` usage in
production code paths (test fixtures may keep them).

R4.3. Toasts must announce themselves to screen readers via
`role="status"` for info/success and `role="alert"` for errors.

### R5 — Idempotency against duplicate clicks

R5.1. Even if a control is rendered incorrectly or the loading state
fails to apply, the request layer must refuse to dispatch a second
request while the first is still pending for the same logical key. The
key is composed of `(method, normalized-URL, body-hash)`.

R5.2. The idempotency guard lives in the single API client (`api.js` or
its Vue-era replacement). It is bypassed for explicitly retry-flagged
calls (intentional retries are unaffected).

### R6 — Vue 3 ownership of UI state

R6.1. After this rewrite, Vue 3 is the only owner of client-side UI
state and rendering. The existing `static/app.js` and DOM-mutating
modules under `static/js/` (add, auth, cards, dialogs, editor,
export_ui, import, list_actions, list_ui, settings, sync, tasks) are
retired or converted. No screen retains parallel vanilla and Vue state
owners.

R6.2. The selected Vue runtime is the same vendored local build
considered by `cdn-frontend-framework` (`static/vendor/vue.global.js`),
loaded from one same-origin URL with an exact pinned version. A clear
recovery message replaces the static failure region if the file is
missing.

R6.3. Vue runtime, shared composables (`api-client`, `use-app-store`),
and base UI primitives (`BaseModal`, `ToastStack`, `LoadingBar`,
`BusyOverlay`, `BusyButton`) form the foundation; feature components
(`KeyWorkspace`, `KeyFormModal`, `ImportExportModal`, `TaskProgressModal`,
`SettingsModals`, `SyncModal`, `UserModals`) compose on top. None of
those feature components constructs API URLs or duplicates error
translation.

### R7 — Visual fidelity

R7.1. The rewritten page is visually indistinguishable from the current
page at default zoom: same color palette, same typography, same spacing,
same layout. The only new visual elements are the loading bar (R2),
overlay mask (R3), and toast (R4), each using existing CSS variables.

R7.2. Focus styles, keyboard navigation, and existing modal escape/focus
behavior must remain intact. Toasts, masks, and loading bars must not
trap focus or break keyboard tab order.

### R8 — Operational & security contracts

R8.1. List payloads stay masked. Complete API keys are still fetched only
for explicit copy/show/export actions.

R8.2. CSRF headers, session cookies, and the `/api/keys/revision`
polling contract are unchanged.

R8.3. Session/CSRF data continue to be kept out of local and session
storage. The implementation must not add `localStorage` usage for
secrets or sessions.

R8.4. Vendored Vue is a security-sensitive production dependency. Any
version change requires an explicit source review and documentation
update, not a floating CDN URL.

## Acceptance Criteria

### AC-R1 Button loading & duplicate click guard
- [ ] Every API trigger button (login, key create/edit/copy/show,
      delete, probe, import, export, settings save, restart, sync, user
      create/delete, batch actions) shows a loading state during the
      in-flight window and disables repeated clicks.
- [ ] Clicking the same logical action twice in <100ms produces exactly
      one network request (verified by network log in dev tools).

### AC-R2 Top progress bar
- [ ] The progress bar appears within one animation frame of the
      in-flight start and reaches 100% before fading on completion.
- [ ] Two concurrent requests show one bar, not two.
- [ ] The bar causes zero layout shift on the page.

### AC-R3 Region overlay
- [ ] Batch operations, import preview, and WebDAV sync render the
      overlay on the affected region with pointer-events disabled.
- [ ] The overlay clears automatically when the operation resolves.
- [ ] The region exposes `aria-busy="true"` while masked.

### AC-R4 Toasts
- [ ] No production code calls `alert(...)` after this migration.
      `confirm(...)` is replaced by modal confirmation where needed.
- [ ] Toasts auto-dismiss on the configured timeout.
- [ ] Toasts announce via `role="status"` (info/success) or
      `role="alert"` (error).

### AC-R5 Vue ownership
- [ ] `static/index.html` contains the static boot/error region plus
      Vue and the module bootstrap; no inline UI template remains.
- [ ] All `static/js/*` DOM-mutating modules listed in R6.1 are removed
      or converted; the surviving files are only framework-free utilities.
- [ ] Vue build is loaded from the same-origin vendored URL; a missing
      file shows the recovery region.
- [ ] A single `useAppStore` owns session, key list, revision, filters,
      selection, modal intent, settings, active task, and toasts.

### AC-R6 Visual fidelity
- [ ] Side-by-side screenshots of the current page and the rewritten
      page at desktop and narrow widths show no unintended differences
      outside the new loading bar, overlay, and toast.
- [ ] Keyboard tab order in the rewritten page matches the current
      page; focus is restored to the trigger button after modal close.

### AC-R7 Operational
- [ ] Fresh checkout runs with Python alone; no `npm install`.
- [ ] Browser network log shows no increase in API endpoints or new
      fields in `/api` requests.
- [ ] No secrets or sessions are stored in `localStorage` /
      `sessionStorage`.

### AC-R8 Accessibility
- [ ] Loading buttons have `aria-busy="true"`; masked regions have
      `aria-busy="true"`; toasts have the correct `role`.
- [ ] Visible focus indicator is preserved on every focusable element.

## Risks & Recovery

- **Missing Vue vendored build**: recovery region renders; operators
  restore the reviewed vendor file and reload. Same path the deferred
  task already documents.
- **Missing a workflow during rewrite**: use the acceptance matrix in
  the implementation plan as the cross-check before retiring legacy
  modules.
- **Accidentally rendering an unmasked secret**: keep list payloads
  masked; explicit copy/show/export still hits the dedicated secret
  endpoint; smoke test reviews browser requests.
- **Toast/overlay z-index conflict**: layer order is centralized; each
  feedback component declares its z-index via the same token.
- **Static UI rollback is Git-based** and does not require schema or
  data rollback.

## Out-of-Scope Reminders

- No npm, no bundler, no `.vue` SFCs, no TypeScript, no service worker.
- No dark theme or runtime theme switching.
- No change to backend behavior or API shape.
- Does not retroactively resolve the `cdn-frontend-framework` deferred
  status; that task keeps its own plan and converges here once both
  ship.
