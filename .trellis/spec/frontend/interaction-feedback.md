# Interaction Feedback (frontend primitives)

> How every API action gets visible feedback and duplicate-click protection.

---

## Why this exists

The vanilla UI shipped without per-button loading state, without a global
activity indicator, and without a confirmation modal style. Users could not
tell whether a click registered, frequently double-clicked, and got silent
errors. This doc captures the convention introduced by the
`frontend-interaction-feedback` task so future modules follow it.

## The four primitives

All four live in `static/js/feedback.js`:

| Primitive | Purpose | Mounted by |
| --- | --- | --- |
| `LoadingBar()` | Thin top progress bar driven by an in-flight counter. Single shared instance; no layout shift. | `app.js` on boot |
| `BusyOverlay(region, { text })` | Wraps a region so it gets a pointer-events-blocking mask + spinner while a long-running operation is in flight. Returns `(busy: boolean) => void`. | Feature code (list refresh, import parse, sync) |
| `withBusyButton(button, fn, { busyLabel })` | Wraps a click handler so the button shows spinner + busy label + `aria-busy="true"` + `disabled` for the duration of `fn`. Re-clicks during busy are silently ignored. | Every API button in the module init functions |
| `toast(message, ttlMs?)` | Right-aligned toast stack with auto-dismiss. Auto-classifies as success / error / info / warning; errors get a 6s ttl. Click to dismiss. | Anywhere |
| `confirmAction(message, { okLabel, cancelLabel, danger })` | Modal confirmation styled to match the page; returns `Promise<boolean>`. Replaces `confirm()`. | Destructive actions (delete, restart, replace, 0.0.0.0) |

## In-flight counter

`feedback.js` exposes a single shared counter:

```js
import { bumpInFlight, getInFlight, onInFlightChange } from "./feedback.js";
```

The `request()` function in `api.js` is the only writer: `+1` before
`fetch`, `-1` in `finally`. The `LoadingBar` reads it via
`onInFlightChange`. Anything that dispatches fetch through `api.js`
automatically appears in the bar.

## Idempotency against duplicate clicks

Two layers, defense in depth:

1. **Visual**: `withBusyButton` disables the button and adds
   `aria-busy="true"`; the underlying `<button>` will not dispatch a
   second click.
2. **Request layer**: `api.js` keeps a `Map<key, true>` keyed by
   `METHOD PATH hash(body)` for every non-GET in-flight request. A second
   identical request is rejected with `ApiError("请求正在进行中，请勿重复提交", 409, { duplicate: true })` *without* dispatching `fetch`.

This means even if a JS bug fails to disable the button, the server
cannot receive a duplicate.

## Rules for new modules

- Every `addEventListener("click", ...)` that triggers an API call
  **must** be wrapped in `withBusyButton(button, () => ..., { busyLabel })`.
- Every `confirm(...)` call **must** be replaced with `await confirmAction(...)`.
- Every long-running region operation (parse, sync, batch) **should**
  use `BusyOverlay(region)` to mask the region.
- `alert(...)` is forbidden in production code; use `toast(...)`.
- Toast classification is automatic for short Chinese/English status
  phrases; if the message does not match, default is `info`. Pass
  `toast.success(...)` / `toast.error(...)` if explicit classification is
  needed.

## CSS variables

Add to `:root` in `style.css`:

```css
--fb-progress, --fb-mask, --fb-spinner-size,
--fb-toast-bg, --fb-toast-fg,
--fb-toast-error, --fb-toast-success, --fb-toast-warning,
--z-progress (1200), --z-mask (1100), --z-toast (1300)
```

## Testing

- `node --check` on every file in `static/js/`.
- `node --test tests/state.test.mjs` (existing state tests must still pass).
- Manual smoke: open `/`, click any action, observe the top bar starts,
  the button shows spinner + busy label, and the toast appears.
- Duplicate-click test: rapid double-click on save / delete / sync
  upload; only one network request fires (DevTools → Network).

## Implementation notes (07-19)

What actually shipped in this task, vs. the deferred Vue 3 rewrite
task (`cdn-frontend-framework`). The Vue task remains deferred; this
work is the live, vanilla implementation of the same feedback goals.

### Primitives that landed (`static/js/feedback.js`)

- `LoadingBar()` — global top progress bar; mounted once from
  `app.js` on boot; observes the shared in-flight counter.
- `BusyOverlay(region, { text })` — used by `app.js` to mask
  `#key-list` during list refresh.
- `withBusyButton(button, fn, { busyLabel })` — wraps every mutating
  button click in `editor.js`, `list_actions.js`, `settings.js`,
  `sync.js`, `add.js`, `export_ui.js`, `import.js`, `auth.js`.
- `toast(message, ttlMs?)` — replaces the old `#toast` element. Auto
  classifies success / error / info / warning. Errors get a 6s ttl.
- `confirmAction(message, opts)` — replaces every remaining
  `confirm(...)` call in production code (delete, restart, replace,
  0.0.0.0 LAN warning).

### Idempotency dedupe (`static/js/api.js`)

`request()` keeps a `Map<key, true>` keyed by
`METHOD PATH hash(body)` for every non-GET in-flight request. A second
identical request is rejected with `ApiError("请求正在进行中，请勿重复提交", 409, { duplicate: true })` *without* dispatching
`fetch`. Combined with the visual `disabled` + `aria-busy`, this is
defense in depth — a JS bug that fails to disable the button cannot
cause a duplicate dispatch.

### Monitor settings auto-save (modal-monitor-settings)

The save button was removed. All numeric inputs now auto-save on
`input` (debounced 600ms) or on `change` (immediate). The
`enabled` seg-toggle fires immediately. Status line at the bottom of
the modal shows `正在保存…` → `已自动保存` (green) or error (red). All
auto-save calls use `silent: true` to suppress the global error
toast — the inline status is the only feedback channel.

### Modal / toolbar consolidations (`static/index.html`)

- 13 modal titles got a `.modal-icon` glyph (SYS/MON/DAV merged into
  the modal-head title, three internal `section-title` blocks deleted).
- "刷新" button extracted from `#more-dropdown` to the main toolbar
  (`#btn-refresh` is now a sibling of `#btn-more`).
- All text "取消"/"关闭" buttons removed from modal-foot. Closing is
  via the modal-head `×`, click-mask, or Esc.
- The "启用定时监测" select was replaced with a seg-group
  (`#set-enabled-on` / `#set-enabled-off` with `.active`) matching the
  status-filter row in the toolbar.
- `auth-gate` login form and `password-change-form` keep their `<form>`
  wrappers (Enter-to-submit); `user-create-form` likewise — see
  "Attempted but reverted" below for why we did not unify all forms.

### Attempted but reverted: unifying the `user-create` input style

Several attempts were made to give the "用户名" and "密码" inputs in
the "新增管理员" modal identical visual size. They were rejected
after browser measurement (Chrome headless `getBoundingClientRect`):

- The two inputs already measure the same (520 x 35 px before padding,
  480 x 35 px after `.modal-card { padding: 20px }`) regardless of
  whether they are inside `<form>` or `<div>`.
- The `<form>` vs `<div>` wrapper difference is not the cause.
- Earlier attempts (`.input-line` + `icon-btn`, `.field-with-action` +
  `.icon-btn-inline`, `:has()`-driven full-width `input-line`) all
  changed more behavior than necessary and were reverted. The
  `user-create-form` keeps the original `.password-field` container
  with a `password-toggle` text button, identical to the "修改初始密码"
  modal.

If a future contributor wants to "make the inputs look the same", the
answer is that they already do — remeasure with DevTools before
restructuring.

### Cross-task alignment with `cdn-frontend-framework`

The Vue rewrite remains the long-term path. When it ships, the four
primitives in `feedback.js` become Vue components (`<LoadingBar>`,
`<BusyButton>`, `<BusyOverlay>`, `<ToastStack>`); the API dedupe moves
into `composables/api-client.js`; the monitor settings auto-save is
expressed declaratively via `v-model` + watchers. The conventions
documented here should be preserved.