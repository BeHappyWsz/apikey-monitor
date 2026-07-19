# Implement: Secure user authentication

1. Add pinned `argon2-cffi` dependency and document the required bootstrap environment variable.
2. Add additive SQLite migrations plus repository functions for users and hashed sessions; test fresh and existing database upgrades.
3. Implement `AuthService`: Argon2id hash/verify/rehash, empty-store bootstrap, opaque session issue/lookup/revoke, CSRF validation, and throttling.
4. Extend the HTTP handler and router with cookie/header input, auth middleware, auth endpoints, and trusted-proxy secure-cookie policy.
5. Add the vanilla login state, authenticated API wrapper, logout control, and administrator user-creation UI without persisting credentials in browser storage.
6. Add regression tests for password non-persistence, login failure uniformity/rate limits, expiry, logout, CSRF, unauthorized route rejection, and existing API behavior after login.
7. Update `docs/api.md`, deployment/security documentation, and changelog. Run full Python tests and frontend syntax/state checks.

## Rollback

The migration is additive. Reverting code keeps user/session tables unused; do not delete them. If bootstrap configuration is incorrect, correct the environment input before startup rather than modifying stored hashes manually.

