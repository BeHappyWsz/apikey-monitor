# Component Guidelines

> DOM structure, modals, cards, import preview, and export UX (no framework components).

---

## Overview

?Components? means **HTML regions + JS modules**, not React. Markup mostly lives in `index.html`; dynamic pieces (cards, import rows) are HTML strings with `esc()`.

---

## Patterns

### Modals

- `openModal(id)` / `closeModal(id)` from `dialogs.js`.
- Known ids include `modal-edit`, import/settings/export-related roots in `index.html`.
- One modal helper stack ? do not invent a second.

### List cards (`app.js`)

- Built from masked GET `/api/keys` rows.
- Show status, latency, protocol flags, models summary.
- Copy full key / export actions must call secret or export APIs, never invent keys client-side.

### Forms

- Edit: empty API key means **leave unchanged** (do not send dummy values).
- Add: `check_after_save` from form (`add.js`); not from settings flag today.
- Settings: bind all validator keys; after host/port change, restart flow is mandatory for listen address to move.

### Import preview

- `import.js` parses via POST `/api/import/parse` ? `candidates`.
- User can edit rows before POST `/api/keys/batch`.
- Surface `skipped_invalid` / `skipped_duplicate` / task progress from response.

### Export

- Formats: `claude`, `codex`, `env`, `powershell`, `json` (see `EXPORT_FMTS` in `app.js`).
- Remember last format in `localStorage` key `apikeyconfig.exportFmt` only.
- Batch/all export: server returns text; use `downloadText` / `copyText` from `utils.js`.
- JSON export fields are portable config only: `name`, `base_url`, `api_key`, `check_model`.

### HTML safety

- Always `esc()` for untrusted interpolation.
- Prefer `textContent` for single-node text updates.

---

## Context object (module ?props?)

`init*` modules receive an explicit context from `app.js`, typically:

- `api`, `state`, `load`, toast helpers, `$` / `$$` if provided
- callbacks for open edit / selection refresh as needed

Keep dependencies visible at the call site.

---

## Composition

- Cross-feature communication via shared `state` + `load()`, not custom buses.
- Disable batch toolbar actions when selection is empty.
- Long-running jobs: `createTaskController` (`tasks.js`).

---

## Anti-patterns

- Mini frameworks / JSX.
- Secrets in DOM attributes or storage.
- `innerHTML` with unescaped errors or keys.
- Duplicating toast/copy/download helpers.
- Client-side ?probe? of third-party APIs with user keys (server already probes).
