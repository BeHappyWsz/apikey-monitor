# Logging Guidelines

> Minimal stdout logging for a local single-user tool.

---

## Overview

This project does **not** use a structured logging framework (`logging` module is unused in the main path). Feedback is:

- Startup / shutdown `print` lines from `app.py`.
- Monitor tick errors: `print("[monitor] tick error:", exc)`.
- HTTP access log: **disabled** (`Handler.log_message` is a no-op) to avoid noise and accidental secret leakage in URLs.

Do not introduce heavy logging stacks unless product requirements change.

---

## Log Levels

There is no formal level system. Practical convention:

| Severity | How |
|----------|-----|
| Startup info | `print` with `[apiKeyConfig]` prefix |
| Background fault | `print` with `[monitor]` (or similar module tag) |
| User-facing API errors | JSON `message` only ? not stdout |
| Debug during development | Temporary local prints; remove before commit |

---

## What to Log

- Process listen URL and DB path at startup (`app.py`).
- Unexpected exceptions in long-running loops (`monitor._loop`) so the daemon does not die silently.
- Restart helper state is persisted to a status JSON file under the runtime dir (`restart_service`), not only printed.

---

## What NOT to Log

**Never** write to stdout, files, or error messages:

- Full `api_key` / tokens / Authorization headers
- Paste import raw bodies (may contain secrets)
- Export payload contents
- Browser cookies / local secrets

Also avoid:

- Logging every successful health check (too noisy; UI polls status instead).
- Re-enabling default `BaseHTTPRequestHandler` access logs without filtering query strings.

---

## Patterns

```text
[apiKeyConfig] ?????: http://127.0.0.1:7878
[apiKeyConfig] ???: .../data.db
[monitor] tick error: ...
```

If you add a new background worker, use a short `[component]` prefix and catch per-tick exceptions the same way as `monitor.py`.

---

## Common Mistakes

| Mistake | Why |
|---------|-----|
| `print(entry)` while debugging checks | Dumps secrets into terminal history |
| Enabling verbose urllib debug globally | May print headers with keys |
| Writing secrets into restart status JSON | Status files live on disk for the UI to poll |
