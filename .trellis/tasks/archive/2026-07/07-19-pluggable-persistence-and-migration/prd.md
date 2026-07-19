# PRD: Pluggable persistence and migration

## Goal

Support SQLite and MySQL as durable primary datastores, add Redis as a dynamically refreshed cache, and make validated SQLite/MySQL backup and restore operations available without data loss.

## Confirmed Facts

- `db.py` directly imports and uses `sqlite3`; callers across API, services, and monitor access module-level functions.
- The `keys` and `settings` tables are currently initialized and migrated inside `db.py`.
- `config.json` is only a first-run settings seed; runtime mutations are stored in SQLite.
- Existing background monitoring and restart flows rely on settings reads/writes, so an unsafe mid-operation backend swap could create inconsistent state.
- No MySQL/Redis drivers, data models, cache abstraction, transactional repository abstraction, or database backup format exists.

## Requirements

- R1: SQLite and MySQL are the only durable primary-store options. Each write that changes related records must be atomic in its selected store.
- R2: Redis is an optional cache only. It must have explicit keys, TTL/invalidation, and refresh behavior; cache loss or staleness must fall back safely to the primary store.
- R3: System configuration must select the datastore and redact connection secrets from UI/API/config seed/logs.
- R4: Switching a primary datastore must use an explicit migration/cutover workflow, quiesce or reject conflicting writes, validate source/target data, and support rollback.
- R5: SQLite-to-MySQL and MySQL-to-SQLite backups/restores must use a versioned portable API-key-only format with schema/version validation and integrity checks. It must not include users, settings, database connection credentials, sessions, WebDAV credentials, or Redis cache state.
- R6: Existing SQLite deployments must remain the default and upgrade without destructive schema changes.
- R7: Container images, Compose manifests, and service orchestration are out of scope; connection configuration must be consumable from a future container deployment.
- R8: The project may add pinned `PyMySQL` and `redis` production dependencies rather than implement database or cache protocols itself.
- R9: SQLite/MySQL primary-store changes are controlled migrations, not zero-downtime hot swaps: block new writes, quiesce active work, copy and validate data, atomically activate the new configuration, then restart. Failure must retain the original store.
- R10: Portable backups do not use a backup passphrase or extra encryption. Export/restore is restricted to authenticated administrators, warns that its contents are sensitive, and contain only API-key records and the fields required to restore them.
- R11: Redis is an optional read-through cache for API-key lists/details and public settings. Writes immediately invalidate or update affected cache entries; cache TTL is 60 seconds; cache failures fall back to the selected primary store.
- R12: Redis deployment is a single instance running Redis 8.0+; Sentinel, Cluster, and high-availability orchestration are out of scope.
- R13: MySQL deployment is a single instance running MySQL 8.0+; replication, read/write splitting, and high-availability orchestration are out of scope. Implementation uses verified current stable dependency versions and supported modern features, with reproducible version constraints.
- R14: SQLite is the default primary store. The development MySQL target is single-instance `127.0.0.1:3306` database `apikey-monitor`; Redis is `127.0.0.1:6379`, DB 0, ACL user `root`. Connection secrets are never returned by UI/API or ordinary backups. The UI does not need runtime editing controls for these connection details in this release.

## Acceptance Criteria

- [ ] SQLite and MySQL run the same repository contract and pass a common transactional test suite.
- [ ] Redis cache hit, miss, invalidation, TTL expiry, and unavailable-cache fallback are tested.
- [ ] A configured datastore change is rejected or staged safely while work is in flight; no request observes a partially migrated store.
- [ ] Primary-store cutovers preserve supported API-key records, settings, users, and hashed sessions; API-key-only portable backup round trips preserve API-key records only.
- [ ] Connection strings/passwords never appear in public APIs, config seed files, logs, or ordinary backup payloads.
