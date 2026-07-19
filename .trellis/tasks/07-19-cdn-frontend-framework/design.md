# Design: Vue 3 CDN UI rewrite

## Chosen Runtime

Ship the reviewed global build of Vue 3.0.5 in the static tree and load it before the application module:

```text
/static/vendor/vue.global.js
```

`static/index.html` keeps a small static boot/error region. A module-bootstrap
checks the same-origin Vue script and replaces that region with a clear Chinese
recovery message if it is missing. Vue is exposed as `window.Vue`, avoiding a package manager,
import map, bundler, TypeScript compiler, or local JavaScript installation.

The vendored file is a security-sensitive production dependency. Version changes
require an explicit source review, smoke test, and documentation update; do
not replace it with a floating CDN URL.

## Frontend Architecture

```text
index.html
  └─ #app / static fatal-load region
       └─ app.js bootstrap
            └─ Vue createApp(App)
                 ├─ composables/api-client.js       HTTP + CSRF + ApiError
                 ├─ composables/use-app-store.js    one reactive owner
                 ├─ components/AppShell.js          navigation + layout
                 ├─ components/KeyWorkspace.js      stats, filters, selection, list
                 ├─ components/KeyFormModal.js      add/edit and sensitive-key actions
                 ├─ components/ImportExportModal.js import/preview/export/backup
                 ├─ components/TaskProgressModal.js batch/probe task polling
                 ├─ components/SettingsModals.js    system/monitor settings + restart
                 ├─ components/SyncModal.js         WebDAV actions/status
                 ├─ components/UserModals.js        user list/create/password flow
                 └─ components/BaseModal.js + ToastStack.js
```

Components use Vue's in-browser template/compiler capability or render
functions; `.vue` single-file components are excluded because they require a
build step. Generic UI primitives own keyboard escape, focus return, overlay
close policy, validation messages, toast announcements, and disabled/busy
states. Feature components must not construct API URLs or duplicate API error
translation.

Because the shipped Vue global build compiles the application template in the
browser, CSP permits same-origin `script-src` plus `unsafe-eval`, but never
permits `unsafe-inline`. Moving to a precompiled or render-function-only UI is
the future path for removing this exception.

`use-app-store` is the single state owner for session user, bootstrap/password
requirements, keys, list revision, filters, selected IDs, modal intent,
settings, active task/restart state, and toasts. Existing pure selectors (such
as filtering, ordering, and revision fingerprints) may move to framework-free
utility modules and stay Node-testable. `api-client` remains the sole owner of
the relative `/api` contract and CSRF header behavior.

## Functional and Security Contracts

- No API endpoint, snake_case payload field, validator, or service behavior is
  changed. The rewrite only changes rendering and client-side orchestration.
- The application continues to request complete API keys only for an explicit
  copy/show/export action. List and normal edit data stay masked.
- Auth bootstrap, login, logout, forced password change, CSRF failures, and
  user creation retain their current server behavior. Session/CSRF data remain
  out of local/session storage.
- Polling still uses `/api/keys/revision` to avoid unnecessary list payloads;
  it is started/stopped by the reactive lifecycle and respects the current
  settings interval.
- All existing modals are represented as accessible Vue components, including
  import preview, add/edit, task/restart progress, models, export, WebDAV,
  users, and settings.

## Visual System

The redesign is light and minimalist: neutral page background, white elevated
surfaces, restrained blue primary actions, semantic status colors, ample
spacing, and legible typography. Desktop uses a concise header, overview
metrics, action bar, and data-first key workspace. Narrow screens collapse
actions/filter controls and show readable key cards rather than an unusable
wide table. The design must meet visible focus, keyboard, contrast, error,
loading, empty-state, and destructive-action confirmation requirements. Dark
mode and theme switching are not included.

## Legacy Module Retirement

Replace the DOM-mutating feature modules (`add`, `auth`, `cards`, `dialogs`,
`editor`, `export_ui`, `import`, `list_actions`, `list_ui`, `settings`, `sync`,
and `tasks`) with Vue components/composables in one release. Reuse or relocate
only framework-free helpers from `api`, `state`, and `utils`; do not leave two
owners for the same state or event handler. Remove unused legacy modules and
their imports once the Vue equivalents are verified.

## Risks and Recovery

- A missing/corrupt local Vue file prevents Vue from booting: show the static
  recovery message; operators restore the reviewed vendor file and reload.
- A full rewrite can omit an infrequent workflow: use the acceptance matrix
  below before removal of legacy code.
- Rendering a secret accidentally: keep masked list payloads and explicit
  secret endpoint calls; inspect browser requests during smoke tests.
- Static UI rollback is Git-based and does not require schema/data rollback.
