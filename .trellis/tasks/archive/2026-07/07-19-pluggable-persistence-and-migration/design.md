# Design: Pluggable persistence and migration

## Storage architecture

Refactor the SQLite-specific `db.py` implementation behind a stable repository facade so existing services can retain their current calls during the first migration. Providers implement keys, settings, users, sessions, revisions, and explicit transactions:

- `SQLiteStore`: current `data.db`, WAL, foreign keys, and per-operation connections.
- `MySQLStore`: MySQL 8.0+ via `PyMySQL`, `utf8mb4`, dictionary rows, explicit commit/rollback, and equivalent indexes/constraints.
- `RedisCache`: optional `redis` client, JSON cache entries for public key lists/details and public settings only; never cache API-key secrets, passwords, sessions, or connection credentials.
- `ControlPlane`: a separate local SQLite file containing `active_backend`, migration state, and format version only. It selects the primary store at process startup and lets a completed cutover survive restart without rewriting `config.json`.

`db.py` remains a compatibility facade while callers are progressively moved to repository interfaces. Each write uses the selected primary provider’s transaction; cache invalidation occurs only after commit. Cache exceptions are isolated and fall back to the primary provider.

## Configuration

SQLite is the default. The verified development targets are MySQL `127.0.0.1:3306`, database `apikey-monitor`, and Redis `127.0.0.1:6379`, DB `0`, ACL user `root`. Nonsecret host/port/name defaults are code/documentation defaults, not editable UI fields. No connection secret is returned by settings, logged, cached, or exported.

## Controlled cutover

An authenticated administrator starts a primary-store switch. The service takes a process-wide migration lock, rejects new writes, pauses monitor/task issuance, waits for in-flight work, opens the target, creates/migrates its schema, and copies keys/settings/users/hashed sessions in transactions. It validates counts, stable IDs/required fields, and a content digest for each table. It writes a prepared control-plane record, activates it atomically, invalidates Redis, and requests a restart. Failure rolls back the target transaction/control-plane change and leaves the original provider active. Active sessions may be invalidated at cutover, requiring re-login.

## Portable API-key backup

Backup is distinct from cutover. Administrator-only export/import uses a versioned JSON envelope containing API-key records and required fields only. It includes no users, settings, WebDAV/DB credentials, sessions, or cache state and has no passphrase/encryption. The API/UI must display a sensitivity warning. Restore validates schema/version and normalizes every record before a single selected-store transaction; replace/merge semantics and duplicate reporting mirror the existing import conventions.

## Redis behavior

Cache public key list/detail and public settings values for 60 seconds. Primary-store writes to keys/settings/status immediately invalidate/update their affected entries after commit. Redis connection loss, serialization failure, or timeout records a redacted operational warning and returns the primary-store response. Redis is single-instance 8.0+; Sentinel/Cluster is excluded.

## Validation and rollback

Common provider contract tests run for SQLite and, when test environment variables provide services, MySQL/Redis integration tests run against MySQL 8.0+ and Redis 8.0+. The regular suite must not require external servers. Rollback retains source data and its control-plane selection until target validation succeeds; a reverse controlled migration is the recovery path after activation.
