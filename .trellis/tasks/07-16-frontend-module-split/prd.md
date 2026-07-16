# PRD: Frontend Large Module Split

## Parent

`07-16-progressive-ext-next`

## Goal

Progressively split oversized frontend modules for maintainability **without UX/API behavior change**.

## Confirmed facts (line counts)

| File | ~Lines |
|------|--------|
| `static/app.js` | 534 |
| `static/style.css` | 924 |
| `static/index.html` | 324 |
| Other `static/js/*` | already modular (25–155) |

Primary pain: **`static/app.js`** still owns list rendering, selection, export flows, event wiring, poll/refresh.

## Draft acceptance

1. Extract coherent modules from `app.js` (e.g. `cards.js` / `export_ui.js` / `list_actions.js` — exact names in design).
2. `app.js` remains thin orchestrator: init + wire events + call modules.
3. No intentional UI copy/behavior change.
4. `node --check` on all touched JS; existing `node --test tests/state.test.mjs` still passes.
5. Frontend directory-structure spec updated.

## Non-goals

- Introduce React/Vue/TypeScript/bundler.
- Full CSS redesign or mandatory CSS split (optional follow-up if easy).
- Feature work for protocols/paths in this child (those land in other children; this child may leave seams for them).

## Suggested order

Do this **first** among children so later protocol/path UI edits land in smaller modules.
