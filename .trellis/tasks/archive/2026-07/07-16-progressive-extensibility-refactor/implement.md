# Implement: Progressive Extensibility Refactor

## Checklist

### 0. Baseline

- [x] Run `python -m unittest discover -s tests -v` and note green baseline.

### 1. Create package skeleton

- [x] Add `core/` package modules: `urls.py`, `http.py`, `protocol_base.py`, `parse.py`, `probe.py`, `export.py`, `protocols/openai.py`, `protocols/anthropic.py`, `protocols/__init__.py`, `__init__.py`.
- [x] Move code with **behavior-preserving** edits only.
- [x] Remove root `core.py` once package imports work.

### 2. Wire registries

- [x] Protocol registry in `core/protocols/__init__.py`; `classify` / `health_check` use it.
- [x] Export format registry in `core/export.py`.
- [x] Importer order in `core/parse.py`.

### 3. Compatibility facade

- [x] `core/__init__.py` re-exports public API used by `api/`, `services/`, tests.
- [x] Re-export `_request`, `_protocol_result`, `_record_http` if tests/callers need them.

### 4. Tests

- [x] Update patches to implementation modules where required.
- [x] Add focused tests for registries (list known protocols / formats; unknown export raises).
- [x] Run full unittest suite.

### 5. Specs / docs

- [x] Update `.trellis/spec/backend/directory-structure.md` for `core/` layout + extension points.
- [x] Update `docs/design.md` architecture modules section.

### 6. Quality gate

- [x] `python -m unittest discover -s tests -v`
- [x] Smoke: import `core` and call `normalize_base_url` / `export_config` / `parse_import_text` quickly.

## Validation commands

```bash
python -m unittest discover -s tests -v
python -c "import core; print(core.normalize_base_url('https://x.com/v1/models')); print(core.export_config({'base_url':'https://x.com','api_key':'k'},'json')[:40])"
```

## Review gates

- No intentional behavior change in probe status matrix or export strings.
- No new third-party deps.
- `core` remains free of `db` / HTTP server imports.

## Rollback

Restore previous single-file `core.py` from git and delete `core/` package if suite regresses.
