# Data Contracts & JS Conventions

> Runtime contracts without TypeScript ? keep multi-machine clients compatible with one backend.

---

## Overview

Plain **ES modules**. Safety comes from backend validators + consistent field names + explicit secret boundaries.

---

## Naming

Use **snake_case** API fields as returned by Python:

```javascript
key.base_url
key.api_key_masked
key.has_api_key
key.check_model
key.monitor_enabled
key.latency_ms
key.sort_order
key.model_status
```

Do not camelCase at the boundary (`baseUrl`) unless you map both directions everywhere (we do not).

---

## Public key object (list/detail)

Always assume:

- **Present:** `id`, `name`, `base_url`, `api_key_masked`, `has_api_key`, status/probe fields, `models` as **array** when public_key parsed it.
- **Absent:** plaintext `api_key`.

Card/export UI must call secret/export endpoints when full key is required.

---

## Secret endpoint

`GET /api/keys/{id}/secret` ?

```json
{ "id": 1, "api_key": "...", "api_key_masked": "..." }
```

Only on explicit user action (reveal/copy). Clear local copies when closing the editor when practical (`editor.js` scopes `revealedSecret` inside init).

---

## Write payloads

### Create / update key

Fields accepted by `validators.key_payload`:

- strings: `name`, `base_url`, `api_key`, `notes`, `check_model` (control chars rejected)
- `monitor_enabled`: 0/1
- `interval_sec`: int 30?86400 or empty/null
- `check_after_save`: bool (service default true on add, false on update)

Partial PUT: omit `api_key` or send empty to keep existing secret. `base_url` is normalized server-side (`core.normalize_base_url`).

### Settings POST

All values become strings in DB. Validator output keys:

`serverHost`, `serverPort`, `globalMonitorEnabled`, `globalIntervalSec`, `downRecheckIntervalSec`, `concurrency`, `requestTimeoutSec`, `autoClassifyOnAdd`, `uiRefreshIntervalSec`.

Hosts limited to `127.0.0.1` / `localhost` / `0.0.0.0`. See backend services-runtime for numeric bounds.

### Batch ids

```json
{ "ids": [1, 2, 3] }
```

Positive ints, deduped, max 1000.

---

## Errors

```javascript
// ApiError from api.js
err.message  // toast this
err.status
err.payload  // { error, message, request_id }
```

Success responses are bare JSON (object/array), not `{ data: ... }`.

Async acceptance: HTTP **202** with task or restart status body ? poll follow-up URLs.

---

## Task object (poll)

Fields used by UI: `task_id`, `status`, `total`, `completed`, `failed`, `skipped`, `errors[]`.

Terminal: `completed` | `partial_failed` | `failed` (`state.taskProgress`).

---

## Health object

`GET /api/system/health` ? `status`, `pid`, `host`, `port`, `name`, `version` (from `version.py`).

Used after restart to choose the live URL.

---

## Client validation

- Optional empty checks for better UX.
- Authoritative validation is server-side; always surface `message`.
- Do not reimplement full URL normalization in JS.

---

## Anti-patterns

- Introducing TypeScript-only modules without a project decision.
- Assuming list payloads include `api_key`.
- Silent `catch` without toast.
- Treating `models` as a string in new code (prefer array; guard with `|| []`).
- Sending camelCase bodies the backend will ignore.
