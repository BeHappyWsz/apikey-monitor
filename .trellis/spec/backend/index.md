# Backend Development Guidelines

> Conventions for the Python HTTP server, services, SQLite layer, and probe logic in **apikey-monitor** (apiKeyConfig).

---

## Overview

Single-repo, **zero third-party Python dependency** local tool:

- Python **3.10+** standard library (`http.server`, `sqlite3`, `urllib`, `threading`, ?).
- Layering: `api/` (HTTP) ? `services/` (orchestration) ? `core/` / `db.py` / `monitor.py`.
- Secrets in SQLite **plaintext** today; list/detail APIs must stay masked.

Prefer extending current modules over inventing frameworks. For multi-machine setup, also read [Local Development & Portability](../guides/local-dev-and-portability.md).

---

## Pre-Development Checklist

1. [Directory Structure](./directory-structure.md) ? where new code belongs
2. [Services & Runtime](./services-runtime.md) ? leases, tasks, monitor, restart, limits
3. [Error Handling](./error-handling.md) ? `ApiError` JSON shape
4. [Database Guidelines](./database-guidelines.md) ? if touching schema, keys, settings
5. [Quality Guidelines](./quality-guidelines.md) ? secrets, deps, tests
6. [Logging Guidelines](./logging-guidelines.md) ? never log secrets

Also: `CONTRIBUTING.md`, `docs/api.md` for public HTTP changes.

---

## Guidelines Index

| Guide | Description | Status |
|-------|-------------|--------|
| [Directory Structure](./directory-structure.md) | Module layout and ownership | Filled |
| [Services & Runtime](./services-runtime.md) | KeyService, tasks, monitor, restart, limits | Filled |
| [Database Guidelines](./database-guidelines.md) | SQLite, migrations, public vs secret | Filled |
| [Error Handling](./error-handling.md) | ApiError, validation, status codes | Filled |
| [Quality Guidelines](./quality-guidelines.md) | Zero-deps, secrets, tests | Filled |
| [Logging Guidelines](./logging-guidelines.md) | Minimal logging | Filled |

---

## Verification Commands

```bash
python -m unittest discover -s tests -v
```

Integration tests spawn real `app.py` processes (`tests/test_integration.py`) and use env-isolated DB paths.

---

**Language**: Spec docs in **English**. Product UI/API messages may remain Chinese.
