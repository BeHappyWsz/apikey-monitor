# Error Handling

> How failures are represented across HTTP, services, and probes.

---

## Overview

| Layer | Pattern |
|-------|---------|
| Router / validators | Raise `ApiError(status, code, message)` |
| Handler | Catch `ApiError` ? JSON error; unexpected ? 500 |
| Services | `KeyError` / `ValueError` / `RuntimeError`; router maps them |
| `core` probes | Result dicts with `status` / `error` ? remote failures are not HTTP 500 |
| Monitor tick | Catch `Exception`, print, continue |

---

## Error Types

### `ApiError` (`api/router.py`)

```python
class ApiError(Exception):
    def __init__(self, status, code, message):
        ...
        self.status, self.code, self.message = status, code, message
```

- `status`: HTTP status
- `code`: stable machine string (`key_not_found`, `invalid_json`, `body_too_large`, ?)
- `message`: human-readable (often Chinese)

### Service exceptions (router mapping)

| Exception | Typical mapping |
|-----------|-----------------|
| `KeyError` | 404 `key_not_found` |
| `ValueError` | 400 `invalid_*` |
| `RuntimeError` | 409 `check_conflict` / `restart_conflict` |

### Probe results

DB/UI statuses: `unknown` | `up` | `down` | `auth_error`.  
`KeyService._save_result` persists them. Management HTTP stays 200 with body fields for single checks.

---

## API Error Responses

```json
{
  "error": "invalid_json",
  "message": "JSON ????",
  "request_id": "a1b2c3d4e5f6"
}
```

Rules:

- Always `error` + `message` + short `request_id` (handler generates 12 hex chars).
- Success payloads are bare JSON ? **not** `{ "data": ... }`.
- `Cache-Control: no-store` on JSON.
- Handler access log is disabled (`log_message` no-op).

### Status codes used in this project

| Code | When |
|------|------|
| 200 | Sync success (including check results) |
| 201 | Single key created |
| 202 | Async accepted (batch import/check, restart) |
| 400 | Validation / bad export / bad JSON |
| 404 | Unknown key, task, restart id, or route |
| 409 | Check lease conflict, restart conflict, target unavailable |
| 413 | Body over size limit |
| 500 | Unhandled exception |

---

## Validation

- `api/validators.py`: `key_payload`, `settings_payload`, `ids_payload`, `normalize_int`.
- Validators raise **`ValueError`**; router wraps as `ApiError`.
- Import path allows larger body (`MAX_IMPORT_BODY`).
- Control characters rejected in URLs/keys (`core.normalize_base_url`, key_payload).

Authoritative numeric bounds: [Services & Runtime](./services-runtime.md).

---

## Patterns

### Do

- Map domain failures at the router edge.
- Truncate long errors before DB write.
- Keep monitor/batch failures isolated per key.

### Do not

- Return Python tracebacks to clients.
- Log or put full API keys in `message`.
- Treat probe `auth_error` as HTTP 401 on the management API.
- Swallow restart failures without status file updates.

---

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| `Exception("not found")` from service | `KeyError` ? 404 |
| String-only `{ "error": "..." }` | Match `{error, message, request_id}` |
| Probe failure as 500 | Persist status on key; return structured result |
| Ignoring 409 on concurrent check | UI should toast and avoid double-submit |

Reference tests: `tests/test_core_db.py`, `tests/test_integration.py`, `tests/test_tasks.py`.
