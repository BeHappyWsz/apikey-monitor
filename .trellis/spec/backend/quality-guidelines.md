# Quality Guidelines

> Standards, forbidden patterns, and verification for backend work.

---

## Project Principles (from CONTRIBUTING)

1. **Zero third-party Python dependencies** by default. Discuss in an Issue before adding any.
2. **Secret safety**: list/detail APIs never return plaintext `api_key`.
3. **Small PRs**: one focused change with tests or manual steps.
4. **Local data compatibility**: schema changes must migrate existing `data.db`.

---

## Code Standards

- Target Python **3.10+**; keep code readable over clever.
- Prefer clear module boundaries (see [Directory Structure](./directory-structure.md)).
- User-visible API error messages may be Chinese; codes stay ASCII `snake_case`.
- Keep pure helpers in `core/` / `db.py` unit-testable without HTTP when possible.
- File encoding UTF-8; match existing module header style.

---

## Security Rules (non-negotiable)

| Rule | Reference |
|------|-----------|
| List/get key responses use `public=True` | `db.public_key`, GET `/api/keys` |
| Full secret only via `/secret`, export, or internal check | `router.py`, `KEYS.secret` |
| Default bind `127.0.0.1` | `config.json`, `app.py` |
| Body size limits | `MAX_JSON_BODY`, `MAX_IMPORT_BODY` |
| No credentials embedded in `base_url` | `core.normalize_base_url` |
| Partial update empty key keeps secret | `test_partial_update_empty_api_key_keeps_secret` |
| Never commit `data.db` or real keys | `.gitignore`, CONTRIBUTING |

---

## Testing Requirements

```bash
python -m unittest discover -s tests -v
```

| Area | File |
|------|------|
| Parse / export / status matrix / masking / reorder / dedupe | `tests/test_core_db.py` |
| Batch task progress + lease | `tests/test_tasks.py` |
| Settings bounds (`ui_refresh`) | `tests/test_ui_refresh_settings.py` |
| Live smoke, 413, restart success/rollback | `tests/test_integration.py` |

### Isolation rules for tests

- Prefer temp `APIKEYCONFIG_DB_PATH` / `CONFIG_PATH` / `RUNTIME_DIR` (see integration test harness).
- Do not assume port `7878` is free; allocate an ephemeral port.
- Probe tests should not call real public AI APIs; use fakes/mocks or local handlers where the suite already does.
- When mocking probe HTTP after the `core/` package split, patch **`core.http._request`** (module attribute). Protocol modules call `http_mod._request(...)`; patching a re-exported `core._request` name will not intercept calls.
- Prefer `core.probe.model_check` when stubbing model checks used by `classify`.

When changing:

- Probe semantics ? status matrix tests
- Schema / masking ? `db` unit tests
- Restart ? integration tests
- New route ? smoke assertion

---

## Forbidden Patterns

- Adding pip dependencies without discussion.
- Returning `api_key` on GET list/detail.
- Breaking `_migrate` for existing DBs.
- Synchronous long network I/O inside DB transactions.
- Global shared sqlite connection.
- Committing secrets or `data.db`.
- Multi-user SaaS auth against design non-goals without explicit product decision.
- Documenting unimplemented settings as live behavior (e.g. `auto_classify_on_add` until wired).

---

## PR / Commit Hygiene

- Messages: `feat:`, `fix:`, `docs:`, ? (Chinese or English).
- Update `docs/api.md` when routes/fields change.
- Update `CHANGELOG.md` `[Unreleased]` for user-visible behavior.
- Bump `version.py` only during intentional release.
- Include `.trellis/spec` updates in the same PR when you change conventions.

---

## Common Mistakes

| Mistake | Correct approach |
|---------|------------------|
| Only manual browser test for probe logic | Unit test with controlled results |
| Duplicating export formatting in router | `core.export_config` / `export_batch` |
| New setting without validator bounds | Extend `settings_payload` + tests |
| Forgetting lease release | `try/finally` around `TASKS.acquire` |
| Testing against developer `data.db` | Env-isolated temp paths |
