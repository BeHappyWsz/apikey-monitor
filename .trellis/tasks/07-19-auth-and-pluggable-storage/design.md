# Design: Authentication and pluggable storage

## Delivery shape

This parent owns cross-child contracts only. `secure-user-authentication` establishes the account/session contract first. `pluggable-persistence-and-migration` then moves keys, settings, users, and hashed sessions through the same primary-store abstraction. Portable backups remain API-key-only.

## Shared invariants

- SQLite or MySQL is the sole primary store at any instant; Redis never owns authoritative data.
- A small local control-plane SQLite database records only active backend, schema version, and migration state. It contains neither keys, users, sessions, nor connection passwords.
- SQLite remains the default primary store. MySQL/Redis connection secrets come only from environment variables.
- All public data APIs require a valid authenticated session after bootstrap. Every account has identical administrator authority.
- Network deployments require TLS at a trusted reverse proxy. The app only trusts forwarded-protocol headers when explicitly enabled by environment configuration.

## Coordination and order

1. Complete and activate the authentication child, using SQLite initially and defining user/session records.
2. Complete the storage child, preserving the authentication schema while introducing MySQL, Redis, switching, and backup support.
3. Run a parent integration review: authenticated API access, SQLite/MySQL data parity, Redis fallback, and API-key-only backup round trips.

## Compatibility and rollback

Existing SQLite `data.db` remains valid. Authentication adds tables additively. A store cutover preserves source data until the target has passed validation and the process restarts. On failure, the control plane continues to select the source. Portable backup restore never changes active-store selection.

