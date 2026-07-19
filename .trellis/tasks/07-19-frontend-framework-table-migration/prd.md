# PRD: Frontend framework and table-name migration

## Goal

Modernize the application's client-side foundation without adding a local JavaScript build/install step, and normalize persistent table names to the `tbl_*` convention while preserving every existing SQLite or MySQL deployment.

## Confirmed Facts

- The project is a Python application serving one static HTML page with native ES modules in `static/app.js` and `static/js/*`; it currently has no browser framework or JavaScript package manager.
- The existing frontend specification explicitly describes the vanilla-ESM architecture, so adopting a framework requires an intentional replacement of those conventions rather than a cosmetic script include.
- Persistence is implemented centrally in `db.py`, serving both SQLite and MySQL. It currently creates and queries `keys`, `settings`, `users`, and `sessions`.
- Deployed SQLite databases can contain API keys, settings, administrator accounts, and active sessions. The MySQL backend is also supported.
- Earlier authentication/persistence planning treats compatibility and safe, reversible upgrades as release requirements.

## Child Deliverables

1. `07-19-cdn-frontend-framework`: replace the complete UI with Vue 3 loaded from a version-pinned URL, with no npm/bundler dependency.
2. `07-19-tbl-table-naming`: move the four durable tables to `tbl_*` names across SQLite and MySQL, using an idempotent, data-preserving migration.

## Cross-Deliverable Requirements

- R1: Neither child may overwrite user data, secrets, authentication state, or the current committed UI behavior.
- R2: Browser runtime dependencies must not introduce a required local Node, npm, bundler, or build step. Target deployments have public-network access, so a version-pinned Vue CDN URL is the supported runtime source; an offline fallback is out of scope.
- R3: Existing installations must have a tested upgrade path and a documented recovery/rollback procedure.
- R4: Each child must remain independently testable; table renaming has no functional dependency on framework adoption.
- R5: Vue 3 is the frontend standard. This release replaces the complete current UI rather than introducing a partial or parallel framework migration.
- R6: The Vue rewrite may deliberately redesign the visual system and information layout, but must retain equivalent functional coverage for every current user workflow.
- R7: The redesign uses a light, minimalist visual system. A dark theme or theme switcher is out of scope for this release.

## Acceptance Criteria

- [ ] Both children contain reviewed requirements, design, and implementation plans before activation.
- [ ] The completed release has no required JavaScript installation/build command and safely upgrades pre-existing SQLite and MySQL schemas.
- [ ] Full automated tests and targeted frontend/runtime checks cover both deliverables.
