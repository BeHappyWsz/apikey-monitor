# PRD: Custom Check Path

## Parent

`07-16-progressive-ext-next`

## Goal

Allow each key to optionally set a **custom check path** used during probe/health (and possibly model check) instead of built-in default endpoints only.

## Confirmed facts

- Keys already have `check_model` for model-specific check.
- Probes use `candidate_urls(base, endpoint)` with fixed endpoints (`models`, `messages`, `chat/completions`).
- Update allowlist in `db.update_key` is closed: name, base_url, api_key, monitor, interval, notes, check_model.

## Draft requirements

1. New optional field on key, e.g. `check_path` (empty = current default behavior).
2. When set, probe attempts the custom path (relative to normalized `base_url`) with the appropriate protocol auth, without breaking default dual-protocol classify when empty.
3. Validated on API write (must be path-like, no scheme/host injection if relative-only).
4. Editor UI: optional field + help text.
5. Migration additive; export JSON may include the field for round-trip.
6. Tests for validation, default fallback, and custom path request URL construction.

## Open decisions

- Relative-only vs allow absolute URL (recommend **relative-only** under base_url).
- Applies to classify only, health only, or both (recommend **both** when field set).
- Interaction with multi-protocol: path applies per active probe vs only primary (recommend document as "preferred probe path for HTTP attempts when provided").

## Non-goals

- Full request template engine (headers/body DSL).
- Per-protocol different custom paths in v1 of this child (single path field first).
