# Implementation Plan: `tbl_*` database naming migration

## Ordered Work

1. Search every SQL string and schema reference in `db.py`, tests, services,
   docs, and adapters. Record the four table mappings and verify no raw SQL
   bypasses `db.py` in runtime code.
2. Refactor SQLite initialization so table-name detection/rename runs before
   `CREATE TABLE IF NOT EXISTS`. Create fresh `tbl_*` DDL, update all CRUD and
   `PRAGMA table_info` references, and bump/document `user_version`.
3. Implement the MySQL table-presence check and one-statement subset rename;
   update fresh DDL, `information_schema` checks, and the cursor adapter so
   application SQL no longer depends on the legacy `keys` quoting workaround.
4. Add explicit collision errors, post-migration schema assertions, and
   operator-facing backup/recovery documentation in `docs/storage.md` and
   affected architecture docs.
5. Update direct test SQL and MySQL integration expectations. Add SQLite
   fixtures that create representative legacy tables/rows (including a
   user/session foreign key), run `init_db()`, prove data preservation, prove
   the second initialization is a no-op, and prove an old/new collision fails
   safely. Add the analogous configured-MySQL coverage where available.
6. Search again for runtime legacy table references, run the full suite, and
   inspect a migration against a copied real-format SQLite database before
   release.

## Validation Commands

```powershell
rg -n "\b(keys|settings|users|sessions)\b" db.py services api monitor.py tests docs
python -m unittest discover -s tests -v
```

When `APIKEYCONFIG_STORAGE_BACKEND=mysql` integration settings are available,
run `python -m unittest tests.test_mysql_redis_integration -v` and verify the
actual `information_schema` table list plus session foreign key. The default
SQLite suite must never require MySQL or Redis.

## Rollback and Review Gates

- Take and verify a SQLite file backup or MySQL logical backup before upgrade.
- Stop on a legacy/target collision; do not auto-merge tables.
- Confirm no service process is writing the database during manual rollback.
- Roll back static/UI changes independently. Roll back the database only from
  the documented pre-upgrade backup once post-migration writes have occurred.
