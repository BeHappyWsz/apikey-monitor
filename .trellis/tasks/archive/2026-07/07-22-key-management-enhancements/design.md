# Key Management Enhancements Design

## Scope

Five related operator features share the current key-list and probe pipeline: filters, result history, periodic strict checks, tags, and model refresh. No new dependencies or background service are introduced.

## Data and API Contracts

- `tbl_keys.tags` is a normalized comma-separated value used only as key metadata. `public_key()` exposes both `tags` and `tag_list`.
- `tbl_keys.next_strict_check_at` is an indexed persisted due timestamp. It is separate from `next_check_at`, so strict verification cannot change health-check cadence.
- `tbl_check_history` stores `key_id`, `kind` (`health` or `strict`), status, latency, truncated error, and timestamp. Queries are newest-first and limited; API responses never include credentials.
- `GET /api/keys/page` accepts `protocol`, `adapter`, `has_model`, and `tag`, validates each value, and forwards the entire filter set through `KeyService` to `db.list_keys_page`.
- `GET /api/keys/{id}/history` returns the latest bounded public history rows. `POST /api/keys/{id}/models/refresh` reuses `KeyService` and returns the refreshed public key plus model list.

## Runtime Flow

```text
monitor tick -> due health rows -> KeyService health result -> db status + health history
monitor tick -> due strict rows -> KeyService strict result -> db model status + strict history
manual model refresh -> KeyService -> core.models_list -> db models -> public response
```

The monitor selects due strict rows through `idx_keys_strict_next`; eligibility requires global strict monitoring, key monitoring, and a non-empty `check_model`. A completed strict probe writes its next due time with deterministic jitter. Manual strict checks remain immediate and do not schedule a separate health probe.

## UI

The list toolbar adds compact selects for protocol, adapter, model configuration, and tag. Filters are held in the existing state object, reset pagination on change, and are included in page requests.

Tags are editable in the existing key editor and render as chips on cards. Card details expose recent check history with a compact status/latency sequence. The existing model details action gains a refresh command with busy feedback; it refreshes only the selected key.

## Compatibility and Safety

Migrations are additive for SQLite and MySQL. SQL uses syntax shared by both engines (no SQLite-incompatible functions in the shared query path). History errors are truncated and never log or serialize keys. Existing `env`, import/export, and list cursor contracts remain unchanged except for additive public fields and optional query parameters.

## Validation

Database tests cover migrations, tag filtering, page cache keys, history bounds, and strict due selection. Service/API tests cover filter forwarding, model refresh failure/success, and strict scheduling. Frontend tests cover state/filter parameters and safe card rendering. Full Python and Node test suites plus syntax checks are required.
