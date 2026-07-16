# Services & Runtime

> Orchestration, concurrency leases, batch tasks, monitor loop, and process restart.

---

## Overview

| Singleton | Module | Role |
|-----------|--------|------|
| `KEYS` | `services/key_service.py` | CRUD orchestration, classify/health/model checks, batch check |
| `TASKS` | `services/task_service.py` | In-memory batch jobs + per-key leases |
| `SETTINGS` | `services/settings_service.py` | Read/validate/save settings; trigger restart |
| (functions) | `services/restart_service.py` | Safe host/port switch with rollback |
| (module) | `monitor.py` | Daemon tick every ~10s ? due keys ? `KEYS.batch_check(..., health=True)` |

HTTP must not reimplement lease/check logic; call these services from `api/router.py`.

---

## KeyService check modes

| Call | Probe function | Typical use |
|------|----------------|-------------|
| `KEYS.check(id)` | `core.classify` | Full protocol discovery after add/edit/manual check |
| `KEYS.check(id, health=True)` | `core.health_check` | Monitor path (uses stored protocol flags) |
| `KEYS.check_model(id, model)` | `core.model_check` | Optional model probe; may update `check_model` |
| `KEYS.batch_check(ids, health=?)` | wraps unleased worker | Returns a **task** object (HTTP 202) |

### Lease rules

- Single-key `check` / `check_model` call `TASKS.acquire(key_id)` or raise `RuntimeError` ? HTTP **409** `check_conflict`.
- Always `release` in `finally`.
- Batch workers use `_check_unleased` but each `run_one` still acquire/release inside `TaskService`.
- If acquire fails in batch, item counts as **skipped** (not failed).

### Add / update semantics

- `add`: `check_after_save` defaults **True** in service (`payload.pop("check_after_save", True)`).
- `update`: `check_after_save` defaults **False**.
- Changing `base_url` or `api_key` in `db.update_key` **resets** status/protocol/model fields to unknown/empty (see `db.py`).
- Partial update: empty `api_key` is stripped in validator so the secret is kept.

### Settings flag caveat

`auto_classify_on_add` is stored in settings / docs but **is not read by KeyService today**. Post-add detection is controlled by request field **`check_after_save`** (see `static/js/add.js`). If you wire the setting, do it deliberately in service/UI and add tests ? do not assume it already works.

---

## TaskService (in-memory)

- TTL default **3600s** after `finished_at`; expired tasks disappear from `get`.
- Not persisted across process restart ? correct for local tool; do not build multi-node job queues on this without redesign.
- Task shape (fields): `task_id`, `kind`, `status`, `total`, `completed`, `failed`, `skipped`, `errors` (max 10), timestamps.
- Terminal statuses: `completed` | `partial_failed` | `failed` (also intermediate `queued` / `running`).
- `task_id` format: `{kind}-{12 hex}` e.g. `check-a1b2c3d4e5f6`.

Concurrency for batch comes from settings `concurrency` (1?32).

---

## Monitor loop

`monitor.py`:

1. Thread name `monitor`, tick interval `_TICK = 10` seconds.
2. If `global_monitor_enabled != "1"`, return.
3. `db.get_due_keys(now, global_interval_sec, down_recheck_interval_sec)`.
4. `KEYS.batch_check(ids, health=True)`.

Tick exceptions are printed and must not kill the thread.

---

## Restart service

Purpose: change listen host/port without leaving the old port orphaned; on failure, restore old process.

High-level flow (`request_restart` / helper):

1. Persist target settings; spawn helper with restart id.
2. Old process shuts down; helper starts new `app.py` with target host/port.
3. Health check on target URL (`/api/system/health`).
4. Success ? status `succeeded`; failure ? start fallback with old settings ? `rolled_back`.

Status files: `{APIKEYCONFIG_RUNTIME_DIR}/restart-{id}.json`.

UI polls GET `/api/system/restart/{id}` and uses `restartCandidates` order from `state.js` (rollback prefers old URL first).

Test hook: `APIKEYCONFIG_TEST_FAIL_TARGET=1` forces target failure (integration test).

---

## Timeouts & limits (authoritative)

From `api/validators.py` unless noted:

| Limit | Value |
|-------|-------|
| JSON body | 256 KiB |
| Import parse body | 2 MiB |
| Batch items / ids | 1000 |
| `interval_sec` (per key) | 30?86400 or null |
| `global_interval_sec` / `down_recheck_interval_sec` | 30?86400 |
| `concurrency` | 1?32 |
| `request_timeout_sec` | 3?120 |
| `ui_refresh_interval_sec` | 0 or 3?3600 (0 = off) |
| `server_port` | 1024?65535 |
| `server_host` | `127.0.0.1` / `localhost` / `0.0.0.0` |
| Probe response read | `core.MAX_RESPONSE_BYTES` = 1 MiB |
| Task error message clip | ~180 chars |
| Task errors list | max 10 entries |

---

## Anti-patterns

- Starting extra monitor threads from the router.
- Holding a DB write transaction across `core.classify` network I/O.
- Persisting batch tasks in SQLite without a product decision (current design is memory-only).
- Calling `core.classify` from the frontend (browser cannot safely hold bulk secrets for server-side probes ? server already has the key).
- Documenting `auto_classify_on_add` as effective without implementing the read path.
