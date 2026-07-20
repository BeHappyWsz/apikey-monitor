# Authentication Contract

## Scenario: Local administrator authentication

### 1. Scope / Trigger

Authentication crosses HTTP, `AuthService`, SQLite migration, browser state,
and network proxy configuration. All accounts are administrators; there are no
roles or tenants.

### 2. Signatures

- `services.auth_service.AUTH`: `ensure_bootstrap()`, `login(username, password, source_ip)`, `current(token)`, `logout(token)`, `create_user(username, password)`.
- `GET /api/auth/me`, `POST /api/auth/login`, `POST /api/auth/logout`, `GET|POST /api/auth/users`.
- SQLite tables: `users(id, username, password_hash, created_at)` and `sessions(token_hash, user_id, csrf_token, created_at, expires_at, last_seen_at)`.

### 3. Contracts

- First start reads `_bootstrap_admin_username` and `_bootstrap_admin_password`
  from the private startup `config.json`. Passwords are Argon2id hashes only.
- Login returns `{user:{id,username}, csrf_token}` and sets the raw opaque token only in the `apikeymonitor_session` HttpOnly cookie.
- `GET /api/auth/me` returns the per-session CSRF token. Every cookie-authenticated POST/PUT/DELETE sends it as `X-CSRF-Token`.
- `APIKEYCONFIG_TRUST_PROXY=1` is required when binding publicly; trust forwarded HTTPS only in that mode.

### 4. Validation & Error Matrix

| Condition | HTTP error |
| --- | --- |
| Missing/expired cookie | `401 unauthenticated` |
| Missing/mismatched CSRF token | `403 csrf_failed` |
| Wrong username/password | `401 invalid_login` (uniform response) |
| Five failed username/IP attempts in 15 minutes | `429 login_rate_limited` |
| Username invalid or password under 12 chars | `400 invalid_username` / `invalid_password` |
| Existing username | `409 username_taken` |

### 5. Good / Base / Bad Cases

- Good: bootstrap password is read only at first start, is hashed once, and the browser keeps only the HttpOnly cookie.
- Base: local loopback deployment uses `SameSite=Lax` cookies and all data API calls require login.
- Bad: writing a raw password/hash to a public settings response, localStorage, logs, or `config.json`; accepting `X-Forwarded-Proto` without the explicit trust flag.

### 6. Tests Required

- `tests/test_auth.py`: bootstrap hash never equals plaintext, sessions persist only a token digest, logout and CSRF behavior, username/password validation, and rate limit.
- `tests/test_integration.py`: unauthenticated API is 401, login works, unsafe request without CSRF is 403, and authenticated restart flow remains valid.

### 7. Wrong vs Correct

#### Wrong

```python
db.set_settings({"admin_password": password})
```

#### Correct

```python
db.create_user(username, PasswordHasher().hash(password))
# Store only sha256(session_token), then send the raw token as HttpOnly cookie.
```
