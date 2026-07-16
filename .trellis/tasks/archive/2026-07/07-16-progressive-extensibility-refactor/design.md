# Design: Progressive Extensibility Refactor

## Approach

Convert monolithic `core.py` into package `core/` with facade re-exports. Introduce three tiny, explicit registries (dicts / ordered lists)—no plugin discovery.

## Target layout

```text
core/
  __init__.py          # public + test-facing re-exports
  urls.py              # normalize_base_url, join_api_path
  http.py              # _request, _read_limited, MAX_RESPONSE_BYTES
  parse.py             # paste + JSON importers + IMPORTERS registry
  protocol_base.py     # _protocol_result, _record_http, error extract, auth words
  protocols/
    __init__.py        # PROTOCOL_PROBES ordered registry + helpers
    openai.py          # probe_openai (+ model-check request helpers if natural)
    anthropic.py       # probe_anthropic
  probe.py             # classify, health_check, model_check, _aggregate
  export.py            # export_config/export_batch + EXPORT_FORMATS registry
```

Delete root `core.py` after package exists (package shadows module).

## Public contracts (stable)

| Symbol | Notes |
|--------|--------|
| `normalize_base_url`, `join_api_path` | Same validation and /v1 dedupe |
| `parse_import_text`, `parse_paste` | Same candidate shape |
| `classify`, `health_check`, `model_check` | Same result keys and status priority |
| `export_config`, `export_batch` | Same format names and text layouts |
| Result dict keys | Unchanged (`supports_*`, `status`, `protocols`, `model_*`, …) |

Internal helpers re-exported for existing unit tests where cheap: `_request`, `_protocol_result`, `_record_http`. Prefer patching `core.http._request` for HTTP mocks after move.

## Registries

### Protocol probes

```python
# core/protocols/__init__.py
PROTOCOL_PROBES = [
    ("openai", probe_openai),
    ("anthropic", probe_anthropic),
]

def get_probe(name: str): ...
def all_probes(): ...  # ordered list of callables
```

- `classify`: run all registered probes in order; map supports flags by protocol name (openai/anthropic remain first-class keys on the aggregate result for API compatibility).
- `health_check`: keep existing branching logic, but resolve probe callables via registry (`get_probe("openai")` etc.) so new protocols can register later without rewriting the switch forever.

For this task, **product result still only exposes `supports_openai` / `supports_anthropic`** (no generic `supports` map) to avoid API churn.

### Export formats

```python
EXPORT_FORMATS = {
    "claude": _fmt_claude,
    "codex": _fmt_codex,
    "env": _fmt_env,
    "powershell": _fmt_powershell,
    "json": _fmt_json,
}
```

`export_config` normalizes base/key once, looks up formatter, raises `ValueError("unsupported export format")` on miss. Batch JSON stays restricted to `json` only.

### Import parsers

```python
IMPORTERS = [
    try_parse_json_import,  # returns list or None to fall through
    parse_paste,            # always returns list (possibly empty)
]
```

`parse_import_text` walks importers until a non-empty success for JSON path; empty JSON that parses but yields no items falls through to paste—**preserve current behavior**.

## Data flow (unchanged)

```text
router / key_service
    -> core.* public API
        -> parse | probe(protocols registry) | export(formats registry)
```

## Compatibility & testing

- No DB migration.
- Update unit tests that patch `core._request` / `core.model_check` to patch implementation modules (`core.http._request`, `core.probe.model_check`) so mocks apply at call site.
- Keep a few re-exports on `core` package root for convenience.
- Full unittest suite is the regression gate.

## Tradeoffs

| Choice | Why |
|--------|-----|
| Package over root `core_*.py` files | Clearer extension folders; matches future growth |
| Explicit dict/list registries | Zero deps; discoverable in one file |
| No dynamic plugin load | Overkill for local single-user tool |
| Keep openai/anthropic-specific result fields | Avoids breaking API/UI |

## Rollout / rollback

- Single PR-sized change; rollback = restore previous `core.py` and drop `core/`.
- If import conflicts appear (`core.py` leftover), remove the file so the package wins.

## Follow-ups (not this task)

- Register a third protocol end-to-end (DB flags + UI).
- Per-key custom probe path.
- Frontend split of large modules.
