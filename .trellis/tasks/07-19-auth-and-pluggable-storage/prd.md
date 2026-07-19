# PRD: Authentication and pluggable storage

## Goal

Evolve the local API-key monitor into a deployment that can require secure user login and select a durable primary datastore at runtime, while preserving existing SQLite installations and enabling verified SQLite/MySQL backups.

## Confirmed Facts

- The application is Python 3.10+ with no third-party runtime dependencies today.
- `db.py` is a SQLite-specific persistence facade; each call opens its own connection and stores keys plus settings in `data.db`.
- Runtime settings already live in the database and are exposed through `/api/settings`; `config.json` is a read-only first-run seed.
- There is no user, authentication, session, MySQL, or Redis implementation today.
- Existing APIs and UI assume an unauthenticated, single local operator. API keys and the WebDAV password are sensitive data.

## Child Deliverables

1. `07-19-secure-user-authentication`: local account identity, password hashing, login/session lifecycle, and protected API/UI access.
2. `07-19-pluggable-persistence-and-migration`: SQLite/MySQL primary-store abstraction, Redis cache invalidation/refresh, runtime datastore selection, and verified backup/restore paths.

## Requirements

- R1: The two child deliverables must remain independently testable but share one compatibility contract for existing SQLite data and protected secrets.
- R2: SQLite and MySQL must be durable, transaction-safe primary stores. Redis must not be the sole source of truth.
- R3: Database selection, credentials, migration controls, and backups must not expose secrets through public settings APIs or `config.json`.
- R4: Existing local SQLite users must have a documented, reversible upgrade path.
- R5: Authentication is not multi-tenant and has no role hierarchy. Every authenticated user is an administrator and may create other users.
- R6: On an uninitialized primary store, startup configuration seeds the initial administrator username and password. The password is hashed into the primary store and is never written back after a user changes it. The bootstrap account must change the known default password immediately after login.
- R7: The application must support network deployment, including future Docker deployment. Production login traffic must be protected by HTTPS TLS termination and secure session-cookie handling.
- R8: Container images, Compose manifests, and certificate/proxy orchestration are explicitly deferred. This release must instead expose documented runtime configuration suitable for a later container deployment.
- R9: The project may add pinned production dependencies: `PyMySQL` for MySQL, `redis` for Redis caching, and `argon2-cffi` for Argon2id password hashing.
- R10: SQLite/MySQL primary-store changes are controlled migrations, not zero-downtime hot swaps: block new writes, quiesce active work, copy and validate data, atomically activate the new configuration, then restart. Failure must retain the original store.
- R11: Portable backups do not use a backup passphrase or extra encryption. Export/restore is restricted to authenticated administrators, warns that its contents are sensitive, and contain only API-key records and the fields required to restore them. They exclude users, settings, database connection credentials, sessions, WebDAV credentials, and Redis cache state.
- R12: Redis is an optional read-through cache for API-key lists/details and public settings. Writes immediately invalidate or update affected cache entries; cache TTL is 60 seconds; cache failures fall back to the selected primary store.
- R13: Redis deployment is a single instance running Redis 8.0+; Sentinel, Cluster, and high-availability orchestration are out of scope.
- R14: MySQL deployment is a single instance running MySQL 8.0+; replication, read/write splitting, and high-availability orchestration are out of scope. Implementation uses verified current stable dependency versions and supported modern features, with reproducible version constraints.
- R15: SQLite is the default primary store. MySQL and Redis use documented fixed default host/port/database settings; their passwords are read only from environment variables and never saved by UI/API or `config.json`. The UI does not need runtime editing controls for these connection details in this release.

## Acceptance Criteria

- [ ] Each child has reviewed requirements, design, and implementation plans before activation.
- [ ] The combined release preserves existing key data and public API behavior apart from deliberately added authentication.
- [ ] Backup/restore across SQLite and MySQL is verified by integrity and record-count/content checks.
