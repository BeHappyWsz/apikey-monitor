# Database Guidelines

> SQLite/MySQL access, migrations, settings persistence, and secret masking for apikey-monitor.

---

## Overview

- Engines: SQLite by default and optional MySQL primary storage; no ORM.
- Default path: `<repo>/data.db` (override with `APIKEYCONFIG_DB_PATH`).
- Config seed path: `<repo>/config.json` (override with `APIKEYCONFIG_CONFIG_PATH`).
- Pattern: **open ? work ? close** per operation; use `connection(write=True)` for commits.
- Tables: `tbl_keys`, `tbl_settings`, `tbl_users`, `tbl_sessions`.
- Journal: `PRAGMA journal_mode=WAL` on init; `busy_timeout=5000`.

Reference: `db.py`.

---

## Connection Pattern

```python
with db.connection(write=True) as conn:
    conn.execute(...)
```

- `get_conn()` sets `row_factory=sqlite3.Row`.
- Do **not** cache connections across threads (`ThreadingHTTPServer` + monitor + task pool).
- Integration tests redirect `DB_PATH` / `CONFIG_PATH` via env so developer DBs stay untouched.

---

## Schema

### `tbl_keys`

| Column | Notes |
|--------|--------|
| `id` | INTEGER PK AUTOINCREMENT |
| `name`, `base_url`, `api_key` | identity; `api_key` plaintext at rest |
| `supports_openai`, `supports_anthropic` | 0/1 integers recording confirmed capability |
| `openai_status`, `anthropic_status` | Last independent protocol status: `unknown` / `up` / `down` / `auth_error` / `rate_limited` / `degraded` |
| `models` | JSON text array string, default `'[]'` |
| `status` | `unknown` / `up` / `down` / `auth_error` (UI may also filter experimental labels) |
| `latency_ms`, `last_check_at`, `last_error` | last protocol/health probe |
| `monitor_enabled`, `interval_sec`, `next_check_at` | per-key schedule (`interval_sec` nullable); indexed persisted next due time |
| `check_model`, `model_status`, `model_latency_ms`, `model_last_check_at`, `model_last_error` | optional model probe |
| `sort_order` | drag-and-drop; new keys get lower-than-min order (top of list) |
| `notes`, `created_at` | metadata |

List order SQL:

```sql
ORDER BY CASE WHEN sort_order=0 THEN 1 ELSE 0 END, sort_order ASC, id DESC
```

### `tbl_settings`

- Columns: `k TEXT PRIMARY KEY`, `v TEXT` (all values stored as strings), and
  backend-only `name TEXT` (the Chinese description of the setting key).
- Seeded once with `INSERT OR IGNORE` from `_load_defaults()` / `config.json`.
- `name` is backfilled during initialization and refreshed on every
  `set_settings` / `replace_settings` write. It is intentionally excluded from
  `get_all_settings()` and `/api/settings`; unknown legacy/custom keys use the
  deterministic label `自定义设置：<key>`.

Known keys (defaults in `_FALLBACK_DEFAULTS`):

| Key | Default | Bounds (validator) |
|-----|---------|---------------------|
| `serverHost` | `127.0.0.1` | only `127.0.0.1`, `localhost`, `0.0.0.0` |
| `serverPort` | `7878` | 1024?65535 |
| `globalMonitorEnabled` | `1` | `"0"` / `"1"` |
| `globalIntervalSec` | `300` | 30?86400 |
| `downRecheckIntervalSec` | `120` | 30?86400 |
| `concurrency` | `8` | 1?32 |
| `requestTimeoutSec` | `45` | 3?120 |
| `autoClassifyOnAdd` | `1` | stored; **not applied by KeyService yet** (see services-runtime) |
| `uiRefreshIntervalSec` | `15` | 0 or 3?3600 |

---

## Migrations

No external tool. Evolution path:

1. Run table-name migration before any target `CREATE TABLE IF NOT EXISTS`.
2. Update `CREATE TABLE IF NOT EXISTS` for fresh installs.
3. `_migrate(conn)`: `PRAGMA table_info` + conditional `ALTER TABLE ... ADD COLUMN`.
4. Set `PRAGMA user_version` (currently **10** after migrate).

When adding a column:

1. Add to CREATE TABLE defaults.
2. Append to `_migrate` loop.
3. Wire `update_key` / row dict / services if user-editable.
4. Keep old DBs bootable without manual SQL.
5. Add a unit test for the new field path.

## Scenario: Per-protocol probe status

### 1. Scope / Trigger

Use this contract when a key can be reachable through one protocol while a
second protocol is rate-limited, rejected, or unavailable. A single aggregate
`status` cannot represent that distinction without hiding useful diagnosis.

### 2. Signatures

- `tbl_keys.openai_status` and `tbl_keys.anthropic_status` are status strings
  defaulting to `unknown`.
- `core.probe._result_from_protocols(protocols)` returns both fields.
- `db.update_status(..., openai_status=None, anthropic_status=None)` persists
  them; `KeyService._save_result` passes the probe result through unchanged.

### 3. Contracts

- Each per-protocol status is one of `unknown`, `up`, `down`, `auth_error`,
  `rate_limited`, or `degraded` and reflects that protocol's most recent
  probe, not its historical capability flag.
- Aggregate `status` remains the availability state for filtering: it is `up`
  when any protocol is usable. `supports_openai` / `supports_anthropic` still
  record confirmed capability and must not be used as a substitute for the
  per-protocol statuses.
- Fresh and migrated rows start at `unknown`; only a new probe may claim `up`.
  Public key responses include the two statuses but never include `api_key`.

### 4. Validation & Error Matrix

| OpenAI | Anthropic | Aggregate `status` | Required card output |
| --- | --- | --- | --- |
| `up` | `rate_limited` | `up` | Online overall; Anthropic limited |
| `up` | `auth_error` | `up` | Online overall; Anthropic rejected |
| `auth_error` | `auth_error` | `auth_error` | Both protocol errors |
| `down` | `down` | `down` | Both protocol failures |
| `unknown` | `unknown` | existing aggregate | Both remain unknown until probed |

### 5. Good / Base / Bad Cases

- Good: a key with OpenAI 200 and Anthropic 429 remains usable and visibly
  reports the Anthropic limit.
- Base: a newly migrated key displays unknown protocol statuses until its next
  scheduled or manual check.
- Bad: deriving a current protocol status from `supports_*`; those flags can
  describe an older successful probe after a newer failure.

### 6. Tests Required

- `tests/test_core_db.py` asserts mixed probe results return each independent
  status while preserving aggregate availability.
- `tests/state.test.mjs` asserts the card renders OpenAI and Anthropic status
  labels independently and does not resurrect stale capability flags.
- Schema tests must cover fresh SQLite columns; configured MySQL integration
  must assert the two columns after `init_db()`.

### 7. Wrong vs Correct

#### Wrong

```python
# A secondary 429/403 vanishes when aggregate status is "up".
card_protocols = ["OpenAI"] if key["supports_openai"] else []
```

#### Correct

```python
# Show current probe outcomes independently of historical capability flags.
protocols = [("OpenAI", key["openai_status"]),
             ("Anthropic", key["anthropic_status"])]
```

## Scenario: `tbl_*` table-name migration

### 1. Scope / Trigger

Use this contract whenever a durable table name changes in SQLite or MySQL.
`db.init_db()` owns migration before normal CRUD begins, so deployed databases
retain API keys, settings, users, and sessions without a manual SQL step.

### 2. Signatures

- `db.init_db()` calls `_migrate_table_names_sqlite(conn)` or
  `_migrate_table_names_mysql(conn)` before target schema creation.
- Legacy-to-target mapping: `keys` → `tbl_keys`, `settings` →
  `tbl_settings`, `users` → `tbl_users`, `sessions` → `tbl_sessions`.
- SQLite discovers tables through `sqlite_master`; MySQL uses
  `information_schema.tables` and a quoted `RENAME TABLE` statement.

### 3. Contracts

- Fresh installations create only the four `tbl_*` tables.
- The migration preserves row values, primary keys, unique constraints,
  session-to-user foreign keys, and existing indexes.
- Runtime SQL must use target names only. Legacy names are allowed solely in
  the migration mapping and regression fixtures.
- SQLite's `PRAGMA user_version` is 7 after migration, but table presence is
  still authoritative because historic databases can have partial schemas.

### 4. Validation & Error Matrix

| Table state | Required behavior |
| --- | --- |
| Legacy exists, target absent | Rename atomically, then continue initialization. |
| Legacy absent, target exists | Treat as already migrated. |
| Both legacy and target exist | Raise `RuntimeError`; do not merge, overwrite, or delete. |
| Neither exists | Create the fresh target schema. |

### 5. Good / Base / Bad Cases

- Good: a copied legacy SQLite database starts once, exposes its existing
  records through the normal API, and starts again without DDL changes.
- Base: an old database predating user/session tables renames the tables it
  has, then creates missing target tables normally.
- Bad: creating an empty `tbl_keys` before checking for legacy `keys`, which
  looks like a collision and risks hiding the real data.

### 6. Tests Required

- `tests/test_core_db.py` must create a representative legacy SQLite schema
  with a key, setting, user, and session; assert target names, preserved rows,
  foreign-key target, and idempotent second initialization.
- Assert a legacy/target collision raises and leaves operator resolution to a
  verified backup.
- `tests/test_mysql_redis_integration.py`, when configured, must assert the
  target table set and session behavior after `init_db()`.

### 7. Wrong vs Correct

#### Wrong

```python
conn.execute("CREATE TABLE IF NOT EXISTS tbl_keys (...)")
conn.execute("ALTER TABLE keys RENAME TO tbl_keys")
```

#### Correct

```python
_migrate_table_names_sqlite(conn)
conn.execute("CREATE TABLE IF NOT EXISTS tbl_keys (...)")
```

The correct order makes existing data authoritative and turns ambiguous
legacy/target coexistence into an explicit recovery error.

---

## Public vs secret rows

### `mask_api_key`

- Short keys: heavy mask; longer keys keep small prefix/suffix (see implementation + `test_mask_api_key_short_and_long`).

### `public_key(entry, include_secret=False)`

Public mode **removes** plaintext `api_key` and adds:

- `api_key_masked`
- `has_api_key` (bool)

Also parses `models` JSON text into a Python/JSON list for API responses when possible.

| Need | API / call |
|------|------------|
| UI list/detail | `list_keys(public=True)` / `get_key(..., public=True)` |
| Export / probe | `public=False` |
| Explicit reveal | `KEYS.secret` ? `{id, api_key, api_key_masked}` |

**Never** reimplement masking in the router or frontend for list payloads.

### Endpoint credential change

If `update_key` receives `base_url` or `api_key`, it resets probe fields to unknown and clears protocol/model cache so stale `up` cannot linger after a secret rotation (`test_endpoint_edit_resets_status`).

Partial update: omitting/empty `api_key` keeps the previous secret (`test_partial_update_empty_api_key_keeps_secret`).

---

## Settings persistence and configuration seed

`set_settings(items)` UPSERTs settings into `tbl_settings` in the selected
primary store. `replace_settings(items)` replaces that table during restart
orchestration. Neither function writes `config.json`.

`config.json` is read only: `_load_defaults()` uses its public keys to seed a
new store once, while startup-only private keys (prefixed `_`) configure the
storage backend and bootstrap behavior. Keep real credentials out of the
tracked file; use environment overrides or an untracked `APIKEYCONFIG_CONFIG_PATH`.

`tbl_settings.k` is independent of the private `config.json` convention: all
persisted keys use camelCase. `_migrate_setting_keys()` upgrades existing
snake_case or underscore-prefixed rows before normal service reads, preserving
the new key if both forms already exist. `set_settings()` and
`replace_settings()` normalize every incoming key, so a new runtime write
cannot reintroduce snake_case. `webdavPassword` and `webdavLastSync` remain
explicitly excluded by `get_public_settings()`.

---

## Query Patterns

- Explicit column lists on INSERT/UPDATE for fields you touch.
- Batch insert dedupes on `(base_url, api_key)` within DB helper; returns skipped duplicate count.
- `reorder_keys(ids)` writes `sort_order = index * 10`.
- `get_due_keys(now, ..., limit)` reads only `monitor_enabled=1` rows with
  `next_check_at <= now` through `idx_keys_monitor_next`; do not return to a
  Python-side scan of every enabled key.

## Scenario: Indexed monitor scheduling and shared probe capacity

### 1. Scope / Trigger

Use this contract when periodic probing must scale beyond a small key set.
It prevents full-table due scans and prevents separate manual, batch, import,
and monitor executors from multiplying outbound requests.

### 2. Signatures

- `tbl_keys.next_check_at INTEGER/BIGINT DEFAULT 0`
- `idx_keys_monitor_next(monitor_enabled, next_check_at, last_check_at, id)`
- `db.monitor_next_check_at(entry, status, settings, checked_at=None)`
- `db.get_due_keys(now, ..., limit)`
- `TASKS.probe_slot(concurrency)` around every network probe in `KeyService`

### 3. Contracts

- Each classify or health result persists both `last_check_at` and the next
  due timestamp. A new/changed/reenabled key receives `next_check_at=0` so it
  can be considered promptly.
- `get_due_keys` selects only indexed due rows, ordered by due time, and
  never returns plaintext data to an API response.
- The configured `concurrency` is a process-wide network budget. Per-task
  thread pools may wait for a slot, but active provider probes across all task
  sources cannot exceed that budget.
- Base cadence respects per-key interval. Down, degraded, rate-limited, and
  auth-error states apply the documented minimum backoffs plus deterministic
  jitter; model-only checks do not alter connectivity scheduling.

### 4. Validation & Error Matrix

| Condition | Required behavior |
| --- | --- |
| `next_check_at <= now`, monitoring enabled | Eligible for indexed selection |
| Monitoring disabled or timestamp in future | Not selected |
| `rate_limited` / `auth_error` result | Schedule longer retry; do not spin immediately |
| Concurrent task sources exceed configured limit | Workers wait at `probe_slot`, not start extra I/O |
| Legacy DB lacks the column/index | Migration adds both before normal monitoring |

### 5. Good / Base / Bad Cases

- Good: thousands of enabled keys cost one limited indexed due query per tick;
  a manual check never raises the total network concurrency above the setting.
- Base: a fresh key has `next_check_at=0` and is picked by the capped monitor
  batch if it was not already classified on add.
- Bad: `SELECT * FROM tbl_keys WHERE monitor_enabled=1` followed by Python
  filtering, or one independent `ThreadPoolExecutor` budget per task source.

### 6. Tests Required

- `tests/test_monitor_efficiency.py` covers persisted due selection, ordering,
  backoff bounds, and the monitor per-tick cap.
- `tests/test_tasks.py` proves a shared probe-slot limit across concurrent
  callers.
- SQLite migration tests and the opt-in MySQL contract test assert
  `next_check_at` exists.

### 7. Wrong vs Correct

```python
# Wrong: scans every monitored key and lets each task own a full concurrency
# budget.
rows = conn.execute("SELECT * FROM tbl_keys WHERE monitor_enabled=1").fetchall()
with ThreadPoolExecutor(max_workers=concurrency): ...

# Correct: choose only due ids through the index and enter one shared slot
# before provider network I/O.
due = db.get_due_keys(now, limit=concurrency * 2)
with TASKS.probe_slot(concurrency):
    result = core.health_check(...)
```

## Scenario: Cursor-paged public key list

### 1. Scope / Trigger

Use this contract when a browser list can grow beyond a small collection. The
panel must not repeatedly transfer every masked key just to refresh counters or
append the next visible rows.

### 2. Signatures

- `db.list_keys_page(limit=50, cursor="", status_filter="all", search="")`
- `KeyService.page(limit, cursor, status_filter, search)`
- `GET /api/keys/page?limit=50&cursor=&status=all&q=`

### 3. Contracts

- The DB helper returns `{items, next_cursor, total, summary, revision}`.
- `items` are `public_key(...)` projections only; plaintext `api_key` must
  never cross this list path.
- `next_cursor` is opaque and encodes the stable SQL order
  (`sort_order=0` group last, then `sort_order ASC`, `id DESC`); clients only
  pass it back unchanged.
- `total` uses both the requested status and search; `summary` uses the search
  alone so status tabs retain useful counts while filtered.
- Status filters are `all`, `up`, `down`, `auth_error`, `unknown`, `issue`,
  and `problem`. A client that needs all records (export/sync) must use its
  explicit full-data service path, not page through public rows.

### 4. Validation & Error Matrix

| Input | Result |
| --- | --- |
| Empty cursor and supported filter | First masked page, at most 100 rows |
| Valid `next_cursor` from the same filter/search | Next stable page |
| Malformed cursor or unsupported status | `ValueError`; router maps to `400 invalid_page` |
| `limit` outside 1–100 | Constrain to the server bounds |

### 5. Good / Base / Bad Cases

- Good: 500 keys load as ten 50-row requests, and the final page has an empty
  `next_cursor`.
- Base: a search with no hits returns `items: []`, `total: 0`, but keeps its
  `summary` for the existing collection.
- Bad: returning `SELECT *` raw rows or using an offset cursor that drifts as
  `sort_order` changes.

### 6. Tests Required

- `tests/test_core_db.py` must cover page boundary, no duplicate ids across
  cursor pages, masked rows, status/search filtering, summaries, and invalid
  cursors/filters.
- `tests/test_integration.py` must call the authenticated HTTP endpoint and
  assert the empty-page response shape at minimum.

### 7. Wrong vs Correct

```python
# Wrong: every refresh transfers all rows and exposes the DB row shape.
return db.list_keys(public=False)

# Correct: the page helper owns ordering, filtering, cursor validation, and
# the public projection.
return db.list_keys_page(limit, cursor, status_filter, search)
```

---

## Scenario: WebDAV portable-key sync boundary

### 1. Scope / Trigger

Use this contract when changing WebDAV backup, export, import, or a storage
backend. It prevents a data-backup action from silently replacing local
operator configuration or authentication data.

### 2. Signatures

- `SyncService.upload()` reads `db.list_keys(public=False)` and calls
  `core.dumps_sync_payload(entries, exported_at)`.
- `core.build_sync_payload(entries, exported_at)` returns
  `{app, schema, exported_at, keys}`.
- `SyncService.download(mode)` calls `core.parse_sync_payload(...)`; its
  `replace` branch deletes existing key ids and calls `db.add_keys_batch(...)`.

### 3. Contracts

- Every remote key item contains only `name`, `base_url`, `api_key`,
  `check_model`, and `check_path`; IDs, probe state, notes, settings, users,
  sessions, and WebDAV credentials never cross the boundary.
- `merge` deduplicates by `(base_url, api_key)`. `replace` snapshots local
  keys first, then replaces **only** `tbl_keys` rows; it preserves local
  settings and administrator/session tables on SQLite and MySQL alike.
- The same `db` facade owns both engines, so sync code must not branch on a
  backend type or issue raw engine-specific SQL.

### 4. Validation & Error Matrix

| Condition | Required behavior |
| --- | --- |
| Remote payload has unsupported top-level metadata | Ignore it; parse only portable key items |
| Portable item has invalid URL or lacks key | Drop that item |
| `mode=merge` | Add new portable keys and preserve existing keys |
| `mode=replace` | Snapshot then replace only keys; preserve settings/users/sessions |
| Any backend selection | Use the same facade and payload contract |

### 5. Good / Base / Bad Cases

- Good: downloading a remote key set updates only the local key collection;
  a custom setting and administrator user remain available afterward.
- Base: an empty valid remote collection in replace mode clears local keys but
  still leaves settings and users intact.
- Bad: serializing `db.get_all_settings()`, copying `data.db`, or deleting
  settings/users as part of a key replacement.

### 6. Tests Required

- `tests/test_sync_service.py` asserts the exact envelope/key field sets and
  proves replace preserves a custom setting and administrator user.
- `tests/test_webdav.py` covers payload round-trip and invalid item removal.
- The opt-in MySQL/Redis contract test verifies the selected MySQL schema is
  compatible; live tests require explicit configured infrastructure.

### 7. Wrong vs Correct

```python
# Wrong: treats a cloud backup as a whole local database replacement.
replace_database(remote_blob)

# Correct: portable payload in, key rows only changed.
items = core.parse_sync_payload(remote_blob)
db.delete_keys(existing_key_ids)
db.add_keys_batch(items)
```

---

## Naming Conventions

- Tables: plural lowercase with the `tbl_` prefix (`tbl_keys`, `tbl_settings`, `tbl_users`, `tbl_sessions`).
- Columns: `snake_case`.
- Flags in `keys`: integers `0`/`1`.
- Flags in `settings`: strings `"0"`/`"1"`.

---

## Common Mistakes

| Mistake | Why it hurts |
|---------|----------------|
| Returning raw SQL rows to the browser | Leaks `api_key` |
| New column without `_migrate` | Existing user DBs crash or miss fields |
| Holding write lock during probes | Blocks UI; load credentials then close conn before HTTP |
| Assuming settings values are ints | Use `int(settings.get(...))` at use sites |
| Writing secrets into `config.json` | File may be synced/backed up less carefully than expected |
| Copying another machine's `data.db` into git | Secret leak + merge hell |

---

## Anti-patterns

- Introducing SQLAlchemy/Peewee/etc.
- Using TaskService-style memory state for keys (keys are durable; tasks are not).
- Changing sort semantics without updating both SQL ORDER BY and frontend `canReorder` rules.
