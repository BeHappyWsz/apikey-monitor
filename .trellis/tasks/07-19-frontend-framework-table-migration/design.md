# Design: Frontend framework and table-name migration

## Delivery Boundaries

The parent owns the combined compatibility contract. The two children have no runtime dependency and may be activated independently:

```text
Vue 3 UI rewrite                         tbl_* schema migration
static/index.html + static/*             db.py + tests + storage docs
          |                                         |
          +------------- existing HTTP API --------+
```

Both changes preserve the public HTTP payloads, runtime configuration keys,
authentication model, and API-key confidentiality rules. Table migration is
released with its backend tests; Vue is released only after all existing UI
workflows have equivalent coverage.

## Shared Release Safety

- Make a restorable database backup before the schema release. The new server
  code cannot safely run against a partially migrated database.
- Deploy and validate the table-name migration separately from the visual
  rewrite when practical, so a UI rollback cannot be confused with a data
  recovery operation.
- Neither task changes API routes or response fields. UI changes consume the
  current API contract; schema changes remain behind `db.py`.

## Integration Review

The final review verifies that a legacy SQLite database upgrades, the full
server test suite passes, and the Vue UI can authenticate and complete every
key-management workflow against that upgraded database.
