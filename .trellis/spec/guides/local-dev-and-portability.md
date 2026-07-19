# Local Development & Portability

> How to run and develop **apikey-monitor** reliably on multiple machines (Windows / macOS / Linux).

---

## Product constraints (do not break)

| Constraint | Implication |
|------------|-------------|
| Pinned Python dependencies | Install `requirements.txt` before running. Add, remove, or upgrade a package only with an explicit review and matching documentation/test update. |
| Zero frontend build step | Edit `static/**` and refresh the browser. No webpack/vite required to run. |
| Local administrator tool | Default bind `127.0.0.1`. Administrator login, opaque sessions, and CSRF protection are required; secrets in the primary store remain plaintext, so protect OS file permissions. |
| Portable data | Schema changes must go through `db._migrate` so an existing `data.db` still opens. |

---

## Runtime requirements

| Tool | Version | Required for |
|------|---------|----------------|
| Python | **3.10+** (3.11?3.13 recommended) | App + unit/integration tests |
| Python packages | `argon2-cffi==25.1.0`, `PyMySQL==1.1.2`, `redis==7.1.0` | Authentication; optional MySQL primary storage and Redis cache |
| Modern browser | ES modules | UI |
| Node.js | **18+** optional | `node --check`, `node --test tests/state.test.mjs` |

Clone the same git revision on every machine. Do **not** copy `data.db` between machines unless you intentionally want those keys (they are real secrets).

---

## Start the app

```bash
# from repo root
python -m pip install -r requirements.txt
python app.py
# or without opening a browser
python app.py --no-browser
# override listen address for this process only
python app.py --host 127.0.0.1 --port 7878 --no-browser
```

- Default URL: `http://127.0.0.1:7878`
- CLI `--host` / `--port` override DB settings **for the current process** (`app.py` builds `server.runtime_settings`).
- Windows silent launch: `start.vbs` (uses `pythonw` when available, adds `--no-browser`).
- macOS / Linux: `./start.sh` (prefers `python3`, adds `--no-browser`; optional `--bg` for background).

---

## Files that must not be treated as source of truth across PCs

| Path | Commit? | Notes |
|------|---------|--------|
| `data.db` | **No** | Live secrets + settings. Created on first `init_db()`. |
| `.runtime/` | **No** | Restart status JSON (`APIKEYCONFIG_RUNTIME_DIR`). |
| `config.json` | Tracked seed only | Read at startup for first-run public defaults and private startup options; runtime never rewrites it. Do not put real credentials in the tracked file; use environment variables or an untracked path via `APIKEYCONFIG_CONFIG_PATH`. |
| Local key dumps / Review notes | **No** | Never commit real keys. |

If two developers each run the app, they each get their own empty or local DB. Share configuration via JSON **export/import**, not by syncing `data.db` over cloud drive while the app is running.

---

## Environment variables (tests & isolation)

Defined mainly in `db.py` and `services/restart_service.py`:

| Variable | Effect |
|----------|--------|
| `APIKEYCONFIG_DB_PATH` | SQLite file path (default: `<repo>/data.db`) |
| `APIKEYCONFIG_CONFIG_PATH` | JSON config path (default: `<repo>/config.json`) |
| `APIKEYCONFIG_RUNTIME_DIR` | Restart status directory (default: `<repo>/.runtime`) |
| `APIKEYCONFIG_TEST_FAIL_TARGET` | Test-only: force restart target failure / rollback path (`"1"`) |

Integration tests (`tests/test_integration.py`) set the first three to a temp directory so they never touch the developer?s real `data.db`.

When debugging restart on another machine, point these vars at a temp folder the same way.

---

## Settings precedence

1. **Process CLI** `--host` / `--port` ? effective listen address for this process.
2. **SQLite `settings` table** ? source of truth at runtime for monitor, concurrency, UI refresh, etc.
3. **`config.json`** ? read-only seed on first DB initialization (`INSERT OR IGNORE`) and private startup configuration. Saving settings does not rewrite it.
4. **`_FALLBACK_DEFAULTS` in `db.py`** ? if config file missing/corrupt.

`server.runtime_settings` on the HTTP server object is the process snapshot used by health and restart (may differ from DB if CLI overrode host/port).

---

## Encoding & line endings

- Python sources use UTF-8 (`# -*- coding: utf-8 -*-` on modules).
- Read `config.json` with `encoding="utf-8"`; runtime writes settings only to the selected primary store.
- UI and many API messages are Chinese; keep new user-facing strings consistent.
- Prefer LF in git; do not reformat entire files when touching one function.

---

## OS-specific notes

| Topic | Detail |
|-------|--------|
| Windows | `start.vbs`; integration teardown uses `tasklist` / `taskkill` helpers for detached PIDs. |
| macOS / Linux | Use `python app.py`; no first-party shell launcher yet (planned). Restart still works via subprocess helper. |
| Ports | Integration tests bind free `127.0.0.1` ports; close leftover `python app.py` processes if health checks hang. |
| Firewall | Binding `0.0.0.0` is allowed by validator but **not recommended**. For network deployment, use a TLS-terminating reverse proxy and the documented `APIKEYCONFIG_TRUST_PROXY=1` setting; do not rely on loopback assumptions. |

Supported `serverHost` values in validator: only `127.0.0.1`, `localhost`, `0.0.0.0`.

---

## Verify on a fresh machine

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
node --check static/app.js
node --check static/js/state.js
node --test tests/state.test.mjs
python app.py --no-browser
# then open http://127.0.0.1:7878 and smoke: import ? list ? export
```

If Python tests fail only on integration, check that another process is not holding the default port and that temp dirs are writable.

---

## Cross-machine workflow tips

1. Develop on a feature branch; commit source + specs, never personal DB.
2. After pull: run unit tests once before coding.
3. If schema migrated in a pull, just start the app ? `_migrate` runs inside `init_db()`.
4. Share sample fixtures as **redacted** JSON export (`name` / `base_url` / fake `api_key`), not production keys.
5. Read `.trellis/spec/backend/index.md` and `frontend/index.md` before non-trivial edits so AI/human changes match this repo.

---

## Related docs

- `CONTRIBUTING.md` ? contribution principles
- `docs/design.md` ? architecture and non-goals
- `docs/api.md` ? HTTP contract
- Backend [Services & Runtime](../backend/services-runtime.md)
