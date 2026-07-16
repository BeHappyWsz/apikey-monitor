# Database Guidelines

> SQLite access, migrations, settings dual-write, and secret masking for apikey-monitor.

---

## Overview

- Engine: **stdlib `sqlite3` only** ? no ORM.
- Default path: `<repo>/data.db` (override with `APIKEYCONFIG_DB_PATH`).
- Config seed path: `<repo>/config.json` (override with `APIKEYCONFIG_CONFIG_PATH`).
- Pattern: **open ? work ? close** per operation; use `connection(write=True)` for commits.
- Tables: `keys`, `settings` (key/value strings).
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

### `keys`

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

### `settings`

- Columns: `k TEXT PRIMARY KEY`, `v TEXT` (all values stored as strings).
- Seeded once with `INSERT OR IGNORE` from `_load_defaults()` / `config.json`.

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
| `ui_refresh_interval_sec` | `5` | 0 or 3?3600 |

---

## Migrations

No external tool. Evolution path:

1. Update `CREATE TABLE IF NOT EXISTS` for fresh installs.
2. `_migrate(conn)`: `PRAGMA table_info` + conditional `ALTER TABLE ... ADD COLUMN`.
3. Set `PRAGMA user_version` (currently **3** after migrate).

When adding a column:

1. Add to CREATE TABLE defaults.
2. Append to `_migrate` loop.
3. Wire `update_key` / row dict / services if user-editable.
4. Keep old DBs bootable without manual SQL.
5. Add a unit test for the new field path.

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

- Tables: plural lowercase (`keys`, `settings`).
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
