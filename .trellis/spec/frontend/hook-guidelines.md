# Module Init & Controller Guidelines

> Local equivalent of ?hooks?: ESM modules with `init*` setup and small controllers.
> **This project does not use React hooks.**

---

## Overview

Side-effectful UI wiring follows one pattern:

1. Export `initSomething(ctx)` (or a factory like `createTaskController`).
2. Call it once from `app.js` after DOM is ready.
3. Handlers close over `ctx` and call backend APIs.

Reference modules: `add.js`, `import.js`, `editor.js`, `settings.js`, `dialogs.js`, `tasks.js`.

---

## Init module pattern

```javascript
// static/js/example.js
export function initExample({ api, state, load, toast }) {
  document.querySelector("#btn-example")?.addEventListener("click", async () => {
    try {
      await api("POST", "/api/...", body);
      toast("??");
      await load();
    } catch (err) {
      toast(err.message || "??");
    }
  });
}
```

Rules:

- **Idempotent enough for single boot** ? do not register duplicate listeners if `init` might run twice (today it runs once).
- Use optional chaining on elements that may be missing in tests/partial HTML.
- Async handlers must `try/catch` and surface `toast(err.message)`.

---

## Controllers

`createTaskController` in `tasks.js` encapsulates polling lifecycle for batch jobs:

- Start polling a task id from POST 202 responses.
- Expose progress via pure helpers in `state.taskProgress`.
- Stop on completion/failure/expiry.

When adding another long-running server job, **reuse or extend** this controller rather than ad-hoc `setInterval` in `app.js`.

---

## Data fetching

- All JSON HTTP goes through `api.js` `request` / default export used as `api(method, path, body)`.
- `ApiError` carries server `message` for toasts.
- Health/restart waits use `waitForHealth`.

Do not sprinkle raw `fetch` in feature modules unless extending `api.js` itself.

---

## Naming

| Kind | Name |
|------|------|
| Boot strapper | `initImport`, `initEditor`, `initSettings`, `initAdd`, `initDialogs` |
| Factory | `createTaskController` |
| Pure helper | camelCase verb nouns in `state.js` / `utils.js` |

---

## Anti-patterns

- React/useEffect-style documentation or dependencies ? not applicable.
- Starting network calls at module top level on import.
- Holding plaintext secrets in module-level variables longer than the edit session requires (`editor.js` keeps `revealedSecret` scoped inside `initEditor`).
