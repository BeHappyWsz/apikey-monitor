# PRD: Migrate database tables to tbl naming

## Goal

Rename durable application tables to the `tbl_*` convention without changing their data semantics or breaking existing SQLite/MySQL installations.

## Confirmed Facts

- `db.py` is the persistence boundary for SQLite and MySQL. It initializes and directly queries `keys`, `settings`, `users`, and `sessions`.
- `sessions.user_id` has a foreign key to `users`; `idx_sessions_expires_at` supports session expiry. `keys` also has a MySQL monitoring index.
- SQLite migrations currently use `PRAGMA user_version` and additive `ALTER TABLE` changes. MySQL performs its schema checks through `information_schema`.
- Tests contain direct SQL against the current table names, so they must be updated with the migration and must exercise an old-schema upgrade.
- The `keys` name requires special quoting in the MySQL cursor adapter; moving to `tbl_keys` removes that reserved-word workaround.

## Requirements

- R1: Fresh SQLite and MySQL installations create only `tbl_keys`, `tbl_settings`, `tbl_users`, and `tbl_sessions`; indexes follow the existing schema behavior.
- R2: A pre-change database upgrades in place, retaining all rows, primary keys, unique constraints, foreign-key relationships, and data values.
- R3: Migration is transactional/atomic where the backend supports it, idempotent after a successful upgrade, and fails clearly without silently replacing or merging divergent old/new tables.
- R4: All persistence SQL, schema-introspection code, tests, and relevant operator documentation use the new names. No application runtime path keeps querying legacy names after migration.
- R5: The SQLite `user_version` and the MySQL upgrade path identify the table naming migration explicitly so later migrations can reason about it.
- R6: The release specifies a pre-upgrade backup and a safe rollback/recovery procedure; database content must never be deleted as part of normal upgrade.

## Acceptance Criteria

- [ ] Fresh SQLite and MySQL schema tests verify only the four `tbl_*` tables are created and all key/user/session/settings operations work.
- [ ] Fixture databases with each legacy table name upgrade successfully with unchanged row counts and representative values, including user/session foreign-key data.
- [ ] Re-running initialization after migration is a no-op, and a legacy/new table collision is reported safely.
- [ ] The full Python test suite and MySQL integration tests (when configured) pass with no runtime SQL references to legacy names.

## Out of Scope

- Changing column names, record formats, API payloads, or storage backends.
- Renaming Redis cache keys or application configuration keys.
