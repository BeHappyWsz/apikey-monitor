# Authentication and network deployment

## Bootstrap

On a database without users, the application reads `_bootstrap_admin_username`
from `config.json` (default `admin`) and reads the initial password from
`APIKEYCONFIG_BOOTSTRAP_PASSWORD`. The password must contain at least 12
characters. It is hashed with Argon2id before persistence and is never written
back to `config.json`.

All accounts are administrators. An authenticated administrator can create
another account from the user menu. There are no roles, tenants, self-service
registration, or email recovery flows.

## HTTP protection

All API routes other than health, bootstrap state, and login require an opaque
session cookie. The server stores only a SHA-256 digest of the session token.
Unsafe requests must also send the session-specific `X-CSRF-Token` returned by
`GET /api/auth/me`. Sessions expire after eight hours and logout revokes them.

Login endpoints return generic credential errors and rate-limit repeated
username/IP failures. Passwords, raw session cookies, and CSRF tokens must not
be logged or placed in browser storage.

## Network deployment

Keep the default loopback binding for local development. A public `0.0.0.0`
binding requires a TLS-terminating reverse proxy and
`APIKEYCONFIG_TRUST_PROXY=1`; only in that explicitly trusted configuration is
the session cookie marked `Secure` based on `X-Forwarded-Proto: https`.

Container files and certificate orchestration are intentionally deferred.

