# Quality Guidelines

> Frontend standards, secret handling, and checks that work on every developer machine.

---

## Principles

1. Stay **vanilla ESM** ? no build step to run the UI.
2. Never display/store secrets except explicit reveal/copy/export actions.
3. Escape untrusted text before HTML interpolation (`esc`).
4. Keep pure logic testable under Node (`state.js`).
5. Do not assume a fixed absolute path or OS ? only browser + relative `/api/...` URLs.

---

## Verification

```bash
node --check static/app.js
node --check static/js/editor.js
node --check static/js/state.js
node --check static/js/import.js
node --check static/js/add.js
node --check static/js/utils.js
node --check static/js/api.js
node --check static/js/dialogs.js
node --check static/js/settings.js
node --check static/js/tasks.js
node --test tests/state.test.mjs
```

Add new `static/js/*.js` files to CI example checks when introduced.

Manual smoke after UX changes:

1. `python app.py --no-browser`
2. Open `http://127.0.0.1:7878` (or the port you configured)
3. Exercise import ? list ? edit/secret ? export ? batch check paths you touched

---

## Secret handling in UI

| Allowed | Not allowed |
|---------|-------------|
| Show `api_key_masked` | `console.log` full keys |
| Fetch `/secret` on reveal/copy | `localStorage` for keys |
| Export/download after click | Third-party analytics with payloads |
| Password input default in editor | Full key in list HTML |

Only non-secret preference currently persisted: export format key `apikeyconfig.exportFmt`.

---

## Accessibility & UX baselines

- Keep `Ctrl/Cmd+Enter` save on edit modal if the modal remains.
- Disable batch/destructive actions when selection empty.
- Toast errors; no silent failure.
- Preserve Chinese copy style used in `index.html` / toasts.
- Silent refresh must not collapse open cards carelessly (`preserveUi` / fingerprint path).

---

## Forbidden patterns

- React/Vue/Angular or CSS-in-JS frameworks.
- npm dependencies required at runtime for shipped UI.
- Large inline style blocks ? extend `style.css`.
- Bypassing `esc()` for dynamic HTML.
- Prefetching secrets on every list poll.
- Hard-coding `http://127.0.0.1:7878` inside modules when relative `/api` works (restart UI may need absolute URLs from health/restart status ? use those payloads, do not invent).

---

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Only browser happy path | Node tests for `state.js` helpers |
| Hard-coded 5s refresh | Honor `ui_refresh_interval_sec` |
| Reimplemented copy/download | `utils.js` helpers |
| Reorder while filtered | `canReorder` must be true |
| Stale list overwrite | `latest: true` + fingerprint |
