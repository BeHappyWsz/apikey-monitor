# Implementation Plan: Frontend framework and table-name migration

1. Complete and review both child designs and plans before activation.
2. Implement and validate `tbl_*` migration first, including a legacy-database
   fixture and a documented backup/recovery procedure.
3. Implement the Vue rewrite against the unchanged HTTP API; use the upgraded
   database in browser smoke validation.
4. Run the combined Python suite, frontend syntax/pure-state checks, and the
   manual workflow matrix from the Vue child plan.
5. Re-read this PRD before release to confirm the two children did not expand
   into API, storage-backend, or offline-CDN work.

## Rollback Points

- Before applying schema migration: retain a database backup and the prior
  application revision.
- Before replacing the static UI: retain the current `static/` implementation
  in Git; static rollback does not require a database rollback.
