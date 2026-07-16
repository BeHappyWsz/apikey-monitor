# Directory Structure

> Frontend layout for the native ESM UI.

---

## Overview

All browser assets live under `static/`. There is no component library directory and no `src/` frontend package.

---

## Directory Layout

```text
static/
??? index.html          # Shell markup: toolbar, list host, modals
??? style.css           # Global styles (single file)
??? app.js              # Boot: state, load loop, render, wire modules
??? js/
    ??? api.js          # fetch wrapper + ApiError + waitForHealth
    ??? state.js        # pure selectors / reorder helpers (unit-tested)
    ??? utils.js        # toast, esc, copy, download, labels
    ??? dialogs.js      # modal open/close
    ??? tasks.js        # polling controller for batch tasks
    ??? import.js       # paste import flow
    ??? add.js          # manual add flow
    ??? editor.js       # edit modal + secret reveal/copy
    ??? settings.js     # settings + restart UX
```

Tests for pure state logic: `tests/state.test.mjs` (Node, not browser).

---

## Module Organization

| Module | Responsibility |
|--------|----------------|
| `app.js` | Owns shared `state` object, list rendering, selection, refresh timer, top-level actions |
| Feature `initX(ctx)` | Bind DOM events; call `ctx.api` / `ctx.load` / toast; avoid owning global state |
| `state.js` | **Pure** functions only ? easy to test without DOM |
| `api.js` | Single HTTP boundary |

### Adding a feature

1. Prefer a new `static/js/<feature>.js` exporting `initFeature(ctx)` if the flow is multi-step.
2. Keep markup in `index.html` (ids/classes) unless generating list items in `app.js`.
3. Add styles to `style.css` using existing naming patterns.
4. Wire `initFeature` from `app.js` once.

---

## Naming Conventions

- Files: `kebab-case` not used; existing files are short **lowercase** names (`editor.js`).
- DOM ids: kebab-case (`modal-edit`, `edit-api-key`).
- Exported functions: camelCase (`initEditor`, `getVisibleKeys`).
- CSS: existing utility/BEM-like classes already in `style.css` ? match neighbors rather than inventing a new system.

---

## Examples

| UX flow | Files |
|---------|--------|
| Import paste ? preview ? batch POST | `import.js`, `app.js` load |
| Edit + reveal secret | `editor.js` ? GET `/api/keys/{id}/secret` |
| Settings save + restart poll | `settings.js`, `api.waitForHealth` |
| Batch check progress | `tasks.js` + `state.taskProgress` |

---

## Anti-patterns

- Introducing React/Vue/Svelte or a bundler ?just because?.
- Adding `node_modules` dependencies for the shipped UI.
- Putting pure list math only inside `app.js` when it can live in `state.js` with tests.
- Fetching with raw `fetch` outside `api.js` (diverges error handling).
