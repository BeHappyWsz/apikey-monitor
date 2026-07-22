# Frontend Development Guidelines

> Conventions for the **vanilla** HTML/CSS/ESM UI under `static/`.

---

## Overview

No React, Vue, TypeScript, bundler, or npm runtime toolchain.

- Entry: `static/index.html` + `static/app.js`
- Feature modules: `static/js/*.js`
- Styles: `static/style.css`
- Optional Node 18+ for syntax/unit checks

API fields are **snake_case**. Multi-machine notes: [Local Development & Portability](../guides/local-dev-and-portability.md).

---

## Pre-Development Checklist

1. [Directory Structure](./directory-structure.md)
2. [State Management](./state-management.md) ? exact `state` shape, fingerprint refresh
3. [Type Safety](./type-safety.md) ? request/response contracts
4. [Component Guidelines](./component-guidelines.md) ? modals, cards, escaping
5. [Hook Guidelines](./hook-guidelines.md) ? `init*` modules (not React hooks)
6. [Quality Guidelines](./quality-guidelines.md)

Cross-layer: JSON shape changes require `docs/api.md` + backend validators + UI updates together.

---

## Guidelines Index

| Guide | Description | Status |
|-------|-------------|--------|
| [Directory Structure](./directory-structure.md) | File layout | Filled |
| [Component Guidelines](./component-guidelines.md) | DOM modules, modals, cards | Filled |
| [Hook Guidelines](./hook-guidelines.md) | `init*` and task controller | Filled |
| [State Management](./state-management.md) | In-memory state + pure selectors | Filled |
| [Type Safety](./type-safety.md) | JS contracts without TypeScript | Filled |
| [Quality Guidelines](./quality-guidelines.md) | Checks, secrets in UI | Filled |
| [Interaction Feedback](./interaction-feedback.md) | LoadingBar / BusyOverlay / withBusyButton / toast / confirmAction | Filled |

---

## Verification Commands

```bash
node --check static/app.js
node --check static/js/cards.js
node --check static/js/list_ui.js
node --check static/js/export_ui.js
node --check static/js/list_actions.js
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

CI example: `docs/ci.workflow.example.yml`.

---

**Language**: Spec docs in English. UI copy may be Chinese.

## List rendering

- Page items may be thin (`view=list`); hydrate with `GET /api/keys/{id}` before edit/models.
- `list_ui` patches cards by `data-id` + `cardFingerprint` instead of full `innerHTML` rebuilds.

