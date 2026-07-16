# Design: Frontend Module Split

## Approach

Extract coherent responsibilities from `static/app.js` into ESM modules under `static/js/`. Keep vanilla ESM; no bundler. Behavior-preserving refactor only.

## Module map

| New module | Responsibility |
|------------|----------------|
| `js/cards.js` | Pure `renderCard(key, state)` HTML + list UI capture/restore |
| `js/list_ui.js` | `createListUi` → render, stats, filters, selection |
| `js/export_ui.js` | `initExportUi` → export modal, more-menu, backup/batch/single |
| `js/list_actions.js` | `initListActions` → key-list click/change/drag, check/delete |
| `app.js` | State, api/load, toolbar filters, init modules, boot |

## Validation

node --check on all modules + node --test tests/state.test.mjs
