# Design: Secure user authentication

## Boundaries

- Add `users` and `sessions` persistence to the existing SQLite schema through additive migration. The later storage child must implement their equivalent MySQL schema and migrate their contents during primary-store cutover.
- Add an `AuthService` for bootstrap, password verification, user creation, session lifecycle, CSRF checks, and login throttling. Route guards belong near `api/router.py`; HTTP cookie/header parsing belongs in the request handler, not in business services.
- Static assets stay public only so the login UI can load. All state-changing and data-bearing `/api/*` routes require an authenticated session, except health, login, and the narrowly scoped bootstrap state needed by the login screen.

## Credentials and sessions

- On an empty `users` table, read `_bootstrap_admin_username` (default `admin`) and `_bootstrap_admin_password` from `config.json`. Hash the password with `argon2-cffi` Argon2id. Mark this account `must_change_password`; until it changes the known default, only login/session/password-change/logout routes are available.
- Every newly created user is an administrator. There are no roles, tenants, password-recovery emails, or self-registration routes.
- Generate opaque 256-bit session tokens with `secrets`; store only a SHA-256 token digest, expiry, creation and last-used timestamps. Send the raw token only in a `HttpOnly`, `SameSite=Lax` cookie. Use `Secure` when a trusted HTTPS proxy is configured; binding publicly without that configuration must be rejected or prominently fail closed.
- Store a per-session CSRF secret server-side and require it in `X-CSRF-Token` for unsafe cookie-authenticated requests. Login additionally validates same-origin intent. Logout deletes the server-side session.
- Apply bounded in-memory login attempts by source IP and username; return uniform failed-login responses without account enumeration.

## UI and API contract

- Add login/logout and create-user controls. Do not store passwords or session tokens in localStorage/sessionStorage.
- Introduce `/api/auth/login`, `/api/auth/logout`, `/api/auth/me`, and administrator-only `/api/auth/users`. API errors use existing JSON error conventions: `401 unauthenticated`, `403 csrf_failed`, `429 login_rate_limited`.
- The client receives a CSRF token from authenticated `me` data and attaches it only to unsafe requests. Existing API-key masking rules remain unchanged.

## Security and compatibility

No plaintext password enters logs, API responses, configuration rewrites, normal backups, or browser storage. Existing installations get an additive database migration and must supply the one-time bootstrap environment password before the server exposes protected data. Production TLS and reverse-proxy deployment are documented; Docker assets are deferred.
