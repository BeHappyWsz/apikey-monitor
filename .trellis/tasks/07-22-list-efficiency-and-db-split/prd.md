# PRD: List efficiency, CI, and db split

## Goal
Ship the mid-term list efficiency work from design.md, add minimal CI, and split the db persistence module by responsibility without changing public import paths.

## Requirements
1. **Thin list payload**: `GET /api/keys/page` (and equivalent `list_keys_page`) omits heavy fields `models[]` and full `notes`; exposes `models_count` and `has_notes`. Detail/edit/models flows load full public key when needed.
2. **Partial DOM patch**: list re-render reuses unchanged card nodes by id/fingerprint; only mutated cards and page-load footer are rewritten; preserve open details and scroll when `preserveUi`.
3. **Minimal CI**: add `.github/workflows/ci.yml` from the documented example (unittest + node checks + state tests).
4. **db split**: replace monolithic `db.py` with a `db/` package (connection, cache, migrate, settings, auth, keys, schedule) while keeping `import db` and existing attribute surface.
5. Tests cover thin payload shape and partial-render helper/fingerprint behavior where practical.

## Non-goals
- SSE push
- Vue migration
- Role permissions / third protocol
- Redis for SQLite

## Acceptance
- [ ] Page items lack `models`/`notes` bodies; have counts/flags
- [ ] Opening edit/models still shows full notes/models
- [ ] List silent refresh does not rebuild every card HTML when data unchanged
- [ ] CI workflow present and local unittest + node checks pass
- [ ] `import db` works; suite green
