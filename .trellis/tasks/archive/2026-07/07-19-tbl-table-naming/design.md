# Design: `tbl_*` database naming migration

## Target Schema

| Legacy table | Target table | Preserved relationships |
| --- | --- | --- |
| `keys` | `tbl_keys` | key rows, ordering, monitor fields, MySQL monitor index |
| `settings` | `tbl_settings` | all public and `_`-prefixed private values |
| `users` | `tbl_users` | username uniqueness, password hash, bootstrap flag |
| `sessions` | `tbl_sessions` | `user_id` foreign key, CSRF/session timestamps, expiry index |

This is a table-identifier migration only. Column names, API shapes, export
formats, settings keys, Redis key names, and cache payloads do not change.
Existing index names may remain unchanged because the requested convention is
for tables, not indexes.

## Initialization and Migration Order

`init_db()` must perform table-name migration before creating the target schema
or applying existing column migrations. This avoids creating an empty target
table that masks legacy data. Fresh installs create only `tbl_*` tables.

Migration detection is based on actual table presence, not only a version
number: installations from different historical releases may have only some of
the four legacy tables. For each mapping:

- legacy absent + target absent: normal fresh-schema creation will create it;
- legacy present + target absent: rename it;
- legacy absent + target present: already migrated;
- legacy present + target present: abort startup with a precise collision
  error and recovery instructions. Never copy, merge, delete, or guess which
  table is authoritative.

After names are stable, all schema introspection, additive migration, CRUD,
and test SQL use the targets. SQLite records a new `PRAGMA user_version` for
the table-name migration while still checking table presence for idempotence.

## Backend-specific Mechanisms

### SQLite

Within the existing write transaction, discover names with `sqlite_master` and
issue `ALTER TABLE <legacy> RENAME TO <target>` for all required mappings.
SQLite DDL participates in the transaction; a failed rename rolls the
transaction back. Verify the `tbl_sessions` foreign key and expiry index after
migration, then run existing additive column migrations against `tbl_keys` and
`tbl_users`.

### MySQL

Query `information_schema.tables` for the configured database. Build one
quoted `RENAME TABLE old TO new, ...` statement for the subset requiring a
rename, so the subset changes atomically. Establish the new tables before
running column checks. Keep the legacy-identifier quoting path only where the
migration needs to address old `keys`; remove the general `keys` workaround
from the SQL adapter once all application SQL targets `tbl_keys`.

The implementation must verify MySQL's resulting foreign-key metadata and
indexes with the configured integration database. If a backend cannot perform
the rename safely, it must fail before mutation and direct the operator to
restore/resolve from backup.

## Data Flow and Recovery

```text
database backup
  → table-presence/collision check
  → atomic backend rename
  → create-if-missing target schema
  → additive column migration + schema assertions
  → normal db.py API operations
```

Document pre-upgrade backup and recovery separately for SQLite and MySQL. A
rollback before any new-release writes may rename target tables back using the
same mapping and prior application revision. After new-release writes, restore
the pre-upgrade backup before running old code; do not attempt a lossy reverse
merge.
