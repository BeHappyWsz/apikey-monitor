# Implement: Authentication and pluggable storage

1. Review both child designs and activate `secure-user-authentication` first.
2. Verify its SQLite authentication migration and protected API/UI behavior.
3. Activate `pluggable-persistence-and-migration`; migrate the shared keys/settings/users/session contract to both primary stores.
4. Execute cross-child integration checks:
   - Bootstrap with `config.json` username plus `APIKEYCONFIG_BOOTSTRAP_PASSWORD`.
   - Login, create a user, logout, expiry, and rejection of unauthenticated API access.
   - SQLite → MySQL cutover and MySQL → SQLite cutover with settings/users retained.
   - Redis hit/miss/invalidation/unavailable fallback.
   - API-key-only portable backup round trips in both primary stores.
5. Update API/deployment documentation, run the full suite plus optional MySQL/Redis integrations, then perform the parent review before archival.

