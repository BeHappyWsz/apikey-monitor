# PRD: Progressive Extensibility Refactor

## Background

`core.py` currently mixes URL helpers, paste/JSON import parsing, protocol probing, and export formatting in one ~474-line module. Callers (`api/`, `services/`, tests) already depend on a stable public surface (`import core`). Extending protocols, importers, or export formats requires editing the same dense file.

This task raises generality/extensibility **without** product-behavior change or new dependencies.

## Goals

1. Split pure domain logic into a `core/` package with clear ownership (url / parse / http / protocol / probe / export).
2. Introduce **minimal registries** for:
   - protocol probes (OpenAI, Anthropic today)
   - export formats (claude, codex, env, powershell, json)
   - import parsers (JSON backup, paste text)
3. Keep **public `import core` API and runtime behavior** compatible for existing callers and data.
4. Update backend directory-structure guidance so future work extends registries instead of growing a god module.
5. Keep zero third-party dependencies and pure-domain rules (`core` still has no DB/HTTP server coupling beyond urllib client probes).

## Non-goals

- New protocols, export formats, or import formats as product features.
- Frontend refactor or new UI.
- DI frameworks, plugin package discovery, entry-point systems.
- Schema/API field renames, multi-user/auth, or SaaS packaging.
- Changing probe semantics, status aggregation priority, or export text layout (except identical refactors).

## Constraints

- Python 3.10+ stdlib only.
- Existing `data.db` and HTTP API remain valid without migration.
- List/detail secret masking unchanged (out of scope for `core`).
- Tests that mock probe HTTP must still be able to intercept requests.
- Prefer small, reviewable steps; no big-bang rewrite of `api/` or `services/`.

## User-visible behavior

- No intentional user-visible change.
- Paste import, classify/health/model checks, and all export formats produce the same results for the same inputs (modulo network).

## Acceptance criteria

1. `core.py` module file is replaced by a `core/` package; `import core` still exposes at least:
   - `normalize_base_url`, `join_api_path`
   - `parse_import_text`, `parse_paste`
   - `classify`, `health_check`, `model_check`
   - `export_config`, `export_batch`
2. Protocol probes are registered in one place; `classify` / `health_check` obtain probes via the registry (not hard-coded dual calls only).
3. Export formats are registered in one place; unsupported format still raises `ValueError`.
4. Import path tries registered importers in order (JSON then paste) with same outcomes as today.
5. `python -m unittest discover -s tests -v` passes.
6. `.trellis/spec/backend/directory-structure.md` documents the new `core/` layout and extension points.
7. `docs/design.md` architecture section mentions the split/registries at a high level.

## Out of scope for later tasks

- Adding a third protocol implementation.
- Custom check endpoints per key.
- Frontend export/import plugin UI.
- Deeper model_check protocol abstraction beyond reusing shared HTTP/status helpers.
