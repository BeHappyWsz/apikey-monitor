# Database Guidelines

> SQLite access, migrations, settings dual-write, and secret masking for apikey-monitor.

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
| `supports_openai`, `supports_anthropic` | 0/1 integers |
| `models` | JSON text array string, default `'[]'` |
| `status` | `unknown` / `up` / `down` / `auth_error` (UI may also filter experimental labels) |
| `latency_ms`, `last_check_at`, `last_error` | last protocol/health probe |
| `monitor_enabled`, `interval_sec` | per-key schedule (`interval_sec` nullable) |
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
| `server_host` | `127.0.0.1` | only `127.0.0.1`, `localhost`, `0.0.0.0` |
| `server_port` | `7878` | 1024?65535 |
| `global_monitor_enabled` | `1` | `"0"` / `"1"` |
| `global_interval_sec` | `300` | 30?86400 |
| `down_recheck_interval_sec` | `120` | 30?86400 |
| `concurrency` | `8` | 1?32 |
| `request_timeout_sec` | `15` | 3?120 |
| `auto_classify_on_add` | `1` | stored; **not applied by KeyService yet** (see services-runtime) |
| `ui_refresh_interval_sec` | `15` | 0 or 3?3600 |

---

## Migrations

No external tool. Evolution path:

1. Run table-name migration before any target `CREATE TABLE IF NOT EXISTS`.
2. Update `CREATE TABLE IF NOT EXISTS` for fresh installs.
3. `_migrate(conn)`: `PRAGMA table_info` + conditional `ALTER TABLE ... ADD COLUMN`.
4. Set `PRAGMA user_version` (currently **7** after migrate).

When adding a column:

1. Add to CREATE TABLE defaults.
2. Append to `_migrate` loop.
3. Wire `update_key` / row dict / services if user-editable.
4. Keep old DBs bootable without manual SQL.
5. Add a unit test for the new field path.

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

## Settings dual-write

`set_settings(items, persist=True)`:

1. UPSERT into SQLite `settings`.
2. If `persist`, merge all settings and `write_config_atomic` to `config.json` (temp file + `os.replace`, UTF-8).

`config.json` may gain a `_comment` field; loaders ignore keys starting with `_`.

---

## Query Patterns

- Explicit column lists on INSERT/UPDATE for fields you touch.
- Batch insert dedupes on `(base_url, api_key)` within DB helper; returns skipped duplicate count.
- `reorder_keys(ids)` writes `sort_order = index * 10`.
- `get_due_keys` respects global monitor intervals, per-key `monitor_enabled` / `interval_sec`, and up vs down recheck cadence.

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
