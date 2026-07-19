# Authentication and network deployment

## Bootstrap

On a database without users, the application reads `_bootstrap_admin_username`
and `_bootstrap_admin_password` from `config.json` (the username defaults to
`admin`). The password must contain at least 12 characters. It is hashed with
Argon2id before persistence; after the initial administrator has been created,
the bootstrap password is not used again. Deployments must replace the shipped
bootstrap password before first start.

All accounts are administrators. An authenticated administrator can create
another account from the user menu and can enable or disable another account.
Disabling an account immediately revokes all of its sessions; an administrator
cannot disable their own currently authenticated account. There are no roles,
tenants, self-service registration, or email recovery flows.

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
