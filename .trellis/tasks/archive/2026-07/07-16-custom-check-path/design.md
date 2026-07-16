# Design: Custom Check Path

## Locked decisions

- Field: `check_path` TEXT, default empty
- Relative-only under `base_url` (`core.normalize_check_path`)
- classify + health use custom path when set; model_check does not
- Same path tried with each protocol auth
- JSON export/import include the field

## Flow

UI editor → validators → db.update_key → key_service.classify/health → protocol.probe(..., check_path) → probe_urls()
