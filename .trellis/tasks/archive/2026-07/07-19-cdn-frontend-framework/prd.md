# PRD: Adopt CDN frontend framework

## Status

Deferred by product decision. The attempted Vue rewrite did not preserve the
existing interface's visual and interaction contract, so the repository keeps
the established native ESM UI until a compatibility-first Vue migration can be
specified and implemented.

## Goal (when resumed)

Adopt Vue without changing the existing page structure, visual style, card
layout, or user workflows.

## Confirmed Facts

- The client is native HTML/CSS plus ES modules. `static/index.html` holds most markup; `static/app.js` owns mutable page state and initializes feature modules under `static/js/`.
- The project has no `package.json`, bundler, TypeScript, React, Vue, or Svelte runtime today.
- Existing frontend tests use Node only for native-module syntax/state tests; a Node installation must not become a runtime requirement for users.
- `index.html` currently has no CDN dependency. The security-sensitive UI includes API-key display/export and authenticated administrator management.

## Requirements

- R1: Load the selected framework from a version-pinned local static URL; adding npm, a bundler, or a compile step is out of scope.
- R2: Preserve direct serving by the existing Python static-file handler and current supported modern browsers.
- R3: Preserve the client/server API contract, secret-masking behavior, authenticated UI flow, and equivalent coverage for every current workflow. The visual system and information layout may be redesigned.
- R4: Provide a controlled migration path from `static/app.js` and `static/js/*` rather than creating two competing sources of UI state.
- R5: Ship the reviewed Vue build under `static/vendor/` and load it from one same-origin URL with an exact version. Document upgrade provenance and show a clear recovery message if the local file cannot be loaded.
- R6: Vue 3 is the only owner of client-side UI state and rendering after this migration. The existing `static/app.js` / `static/js/*` presentation modules must be retired or converted so no screen retains a parallel vanilla state owner.
- R7: The rewrite covers login/bootstrap-password flows, API-key list/card/detail/edit/add/import/export, filtering and bulk actions, monitoring/tasks, settings/restart, WebDAV sync, and administrator user management; equivalent user-visible behavior must remain available.
- R8: Use a light, minimalist visual system, with accessible contrast and responsive layouts. A dark theme or runtime theme switcher is out of scope.

## Acceptance Criteria

- [ ] A fresh checkout runs with Python alone; no `npm install` or build command is needed.
- [ ] Vue 3 is loaded from an exact, documented URL and the page gives a clear failure signal rather than silently losing controls if it is unavailable.
- [ ] The adopted UI scope has automated or repeatable smoke coverage for login, key list/edit/import/export, settings, tasks, and user management.
- [ ] The architecture documents the single owner for each migrated UI state and the path for remaining modules.
