# Implement: Pluggable persistence and migration

1. Add pinned `PyMySQL` and `redis` dependencies plus documented MySQL/Redis environment variables and test variables.
2. Extract provider/repository interfaces from `db.py`; preserve its public facade while introducing SQLite implementation and a nonsecret control-plane store.
3. Implement the MySQL 8.0+ schema/migrations for keys, settings, users, and sessions, with parameterized queries, `utf8mb4`, indexes, and transactional tests shared with SQLite.
4. Implement provider selection at startup and safe nonsecret configuration validation. Keep SQLite as default and reject MySQL selection when required environment password/connection validation fails.
5. Implement `RedisCache` read-through paths, 60-second TTL, post-commit invalidation, redacted failures, and unavailable-cache fallback.
6. Implement migration lock/quiescence, schema creation, transactional copy, validation digest, control-plane activation, restart, rollback, and session invalidation.
7. Add administrator-only API/UI actions for datastore status/switch and API-key-only portable backup/restore; keep secrets and connection details off public settings APIs.
8. Add common SQLite/MySQL contract tests, migration failure/rollback tests, backup round trips, Redis behavior tests, and optional environment-gated MySQL/Redis integrations.
9. Update `docs/api.md`, `docs/design.md`, README/deployment guidance, changelog, and relevant Trellis specs. Run the full suite, frontend checks, and enabled external integrations.

## Risk checkpoints

- Do not remove or overwrite source data before target validation and control-plane activation.
- Do not invalidate Redis before a primary write commits.
- Do not make portable backups include users, settings, sessions, WebDAV values, or connection secrets.
- Keep authentication schema migration compatible with the preceding authentication child.

