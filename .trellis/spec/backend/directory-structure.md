# Directory Structure

> How backend code is organized in apikey-monitor.

---

## Overview

There is **no** `src/` package layout. The app is a small flat tree with two packages (`api/`, `services/`) plus root modules.

Ownership rule:

| Concern | Put it in |
|---------|-----------|
| HTTP method/path dispatch | `api/router.py` |
| Request/response I/O, static files | `api/handler.py` |
| Input normalization / limits | `api/validators.py` |
| Multi-step use cases (check lease, batch task) | `services/*` |
| Pure parse / probe / export (no DB) | `core/` package (`import core` facade) |
| SQLite CRUD, settings, masking | `db.py` |
| Periodic due-key scheduling | `monitor.py` |
| Process listen / CLI entry | `app.py` |
| Safe host/port restart helper | `services/restart_service.py` |
| Version / User-Agent | `version.py` |

---

## Directory Layout

```text
apikey-monitor/
??? app.py                 # CLI + ThreadingHTTPServer lifecycle
??? monitor.py             # daemon tick ? KEYS.batch_check
|-- core/                  # package: parse / probe / export registries
|   |-- __init__.py        # public facade (`import core`)
|   |-- urls.py
|   |-- http.py
|   |-- parse.py           # IMPORTERS registry
|   |-- protocol_base.py
|   |-- probe.py           # classify / health_check / model_check
|   |-- export.py          # EXPORT_FORMATS registry
|   -- protocols/         # PROTOCOL_PROBES registry
|       |-- openai.py
|       -- anthropic.py
??? db.py                  # SQLite + public_key/mask_api_key + migrations
??? version.py
??? config.json            # seed defaults only (no secrets)
??? api/
?   ??? handler.py         # BaseHTTPRequestHandler
?   ??? router.py          # exact path routing + ApiError
?   ??? validators.py      # payload shapes and numeric bounds
??? services/
?   ??? key_service.py     # KEYS singleton
?   ??? task_service.py    # TASKS singleton (in-memory batch jobs)
?   ??? settings_service.py
?   ??? restart_service.py
??? tests/                 # unittest + one Node state test for frontend
??? docs/                  # api.md, design.md, CI example
```

---

## Module Organization

### Request path

1. `Handler._dispatch` parses body, calls `route(method, path, query, body, server)`.
2. `route` validates with `validators.*`, calls `KEYS` / `TASKS` / `SETTINGS` / `core` / `db`.
3. Handler serializes success JSON or `_error` for `ApiError`.

Reference: `api/handler.py`, `api/router.py`.

### Adding an endpoint

1. Add validation helpers in `api/validators.py` if the payload is non-trivial.
2. Add orchestration on the right service (do not put SQL in the router).
3. Register the exact path in `api/router.py` (regex helpers already exist for `/api/keys/{id}/?`).
4. Update `docs/api.md` and add a unittest or integration check when behavior is security- or restart-sensitive.

### Pure vs impure

- **`core/` must stay free of DB access.** Probe and export helpers take plain dicts/strings.
- **`db.py` must stay free of HTTP/network.** Masking and row shaping live here (`public_key`).
- **`services/key_service.py`** owns check leases, classify-after-add, and calling `core` + `db`.

---

## Naming Conventions

- Modules: `snake_case.py`.
- Functions: `snake_case`; private helpers prefix `_`.
- HTTP paths: `/api/...` with resource nouns (`keys`, `tasks`, `settings`, `system`).
- JSON fields for keys/settings: **snake_case** matching DB columns (`base_url`, `api_key`, `check_model`, `monitor_enabled`).
- Service singletons: module-level `KEYS = KeyService()`, `TASKS = TaskService()`, `SETTINGS = SettingsService()`.

---

## Examples

| Feature | Primary files |
|---------|----------------|
| List keys (masked) | `router` GET `/api/keys` ? `KEYS.list()` ? `db.list_keys(public=True)` |
| Paste import | POST `/api/import/parse` ? `core.parse_import_text` |
| Batch import | POST `/api/keys/batch` ? validators + `KEYS.add_batch` + background task |
| Background monitor | `monitor.tick` ? `db.get_due_keys` ? `KEYS.batch_check(..., health=True)` |
| Port switch | POST `/api/system/restart` ? `restart_service.request_restart` |

---

## Anti-patterns

- Adding Flask/FastAPI/Django or any pip dependency without an Issue discussion.
- Putting probe HTTP calls inside `db.py` or SQL inside `core/`.
- Returning full `api_key` from list/get detail handlers (must stay masked).
- Sharing one global `sqlite3` connection across threads (always use `db.connection()` / `get_conn()` per call).

---

## Environment entry points

| Concern | Location |
|---------|----------|
| Process CLI | `app.py` (`--host`, `--port`, `--no-browser`, `--version`) |
| DB/config paths | `db.DB_PATH`, `db.CONFIG_PATH` via env |
| Runtime/restart dir | `services/restart_service.py` ? `APIKEYCONFIG_RUNTIME_DIR` |
| Public version / UA | `version.py` (`__version__`, `USER_AGENT`) |

See [Local Development & Portability](../guides/local-dev-and-portability.md).

---

## `core/` package (keep pure)

Public import remains `import core`. Own pure domain logic here -- not in router or db:

- `urls.py`: `normalize_base_url`, `join_api_path`, `candidate_urls`
- `parse.py`: `parse_import_text` / `parse_paste` + `IMPORTERS` registry
- `http.py`: probe HTTP client (`_request`)
- `protocols/`: per-protocol probes + `PROTOCOL_PROBES` registry
- `probe.py`: `classify`, `health_check`, `model_check`
- `export.py`: `export_config`, `export_batch` + `EXPORT_FORMATS` registry

### Extension points

| Add | Where |
|------|-------|
| New protocol probe | Module under `core/protocols/` + entry in `PROTOCOL_PROBES` |
| New export format | Formatter + entry in `EXPORT_FORMATS` |
| New import shape | Callable + entry in `IMPORTERS` (order matters) |

Product flags/UI (`supports_*`, settings) for a new protocol are a separate cross-layer task.

No `sqlite3` imports under `core/`.
