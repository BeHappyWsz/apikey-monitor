# PRD: Secure user authentication

## Goal

Add a secure login boundary that protects the application UI and API-key data without storing recoverable user passwords.

## Confirmed Facts

- The server is a Python stdlib `http.server` application with routing in `api/router.py`.
- No endpoint currently requires authentication; the UI requests `/api/*` directly.
- API keys are currently plaintext at rest in SQLite, but normal list/detail paths mask them. The WebDAV password is excluded from the settings API.
- The project has no third-party Python dependencies, so password hashing and session design must either use reviewed stdlib primitives or add an explicitly approved dependency.

## Requirements

- R1: Passwords must be salted, one-way hashed with a deliberately slow password-KDF; plaintext or reversible password storage is forbidden.
- R2: Authentication has no tenant or role model. Every authenticated account is an administrator and may create further user accounts.
- R3: Login, logout, session expiration, cookie security, CSRF protection, bootstrap/admin lifecycle, and brute-force controls must be specified before implementation.
- R4: Existing non-authenticated installations require an explicit, safe upgrade and recovery path.
- R5: Sensitive data must not be exposed through logs, error responses, browser storage, settings APIs, or backups without protection.
- R6: The system startup configuration must provide the initial-account bootstrap input without treating a plaintext default password as a durable runtime credential.
- R7: On an uninitialized primary store, `config.json` supplies the bootstrap username and known default password. The password is hashed before persistence; the bootstrap account is forced to change it after its first login, and later changes are never written back to `config.json`.
- R8: Authentication must support network deployment and future Docker deployment. HTTPS TLS termination is required for production login traffic; session cookies must be secure in that deployment mode.
- R9: Dockerfiles, Compose manifests, and certificate/proxy orchestration are out of scope for this release; configuration must remain usable by a later container deployment.
- R10: Password hashing uses `argon2-cffi` with Argon2id; the project may add this production dependency.

## Acceptance Criteria

- [x] Protected endpoints reject unauthenticated requests and the UI supplies the chosen session credential correctly.
- [x] Password hashes use a unique salt and configurable work factor; tests prove plaintext passwords are never persisted.
- [x] Login failure, lockout/rate limit, logout, expiry, CSRF, bootstrap, user creation, and administrator recovery paths have automated tests.
- [x] Existing SQLite data remains usable after authentication is enabled.
