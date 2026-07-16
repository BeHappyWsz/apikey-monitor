# Cross-platform start + bind risk UX + doc sync

## Goal

Make multi-machine launch reliable (Windows + macOS/Linux) and make non-loopback bind risk obvious in UI and docs, without adding access-password or encryption work.

## Requirements

### R1 — Unix start script
- Add repo-root `start.sh` for macOS/Linux that starts the app with `--no-browser`.
- Prefer `python3`, fall back to `python`.
- Resolve script directory so the app runs from the repo root even if invoked via a relative path.
- Be executable in intent (documented `chmod +x start.sh`); use a portable shebang (`#!/usr/bin/env bash` or `sh`).
- Support a simple foreground run by default; optional background mode is nice-to-have only if it stays tiny (no new deps).

### R2 — README / start path docs
- Document three ways to start: `python app.py` (all OS), Windows `start.vbs`, Unix `start.sh`.
- Keep existing CLI flag examples (`--host`, `--port`, `--no-browser`).
- Update project layout table to include `start.sh`.

### R3 — Stronger `0.0.0.0` risk UX
- Existing behavior must remain: `#lan-warning` toggle on host change; `confirm` on save when host is `0.0.0.0`.
- Polish:
  - When opening system settings, if current host is `0.0.0.0`, show `#lan-warning` immediately (do not wait for a `change` event).
  - Warning copy must clearly state: LAN exposure of the local admin UI + no access password yet + trusted network only.
  - Confirm dialog copy stays aligned with the same risk message.
  - If CSS for danger/warning note is weak or missing, strengthen visibility modestly (no design overhaul).

### R4 — Design / CHANGELOG sync
- Update `docs/design.md` “后续迭代”: mark completed MVP items as done or remove them from “next”; keep optional local access password (and any encryption) as future work.
- Update `CHANGELOG.md` `[Unreleased]`: record Added items for `start.sh`, bind-risk UX polish, doc alignment; keep Planned for password/encryption (and drop multi-platform start script from Planned once done).

### R5 — Quality bar
- No third-party dependencies.
- Secrets rules unchanged (list/detail never return plaintext keys).
- Existing unit/integration tests still pass.
- Frontend JS remains valid (`node --check` on touched modules if available).

## Out of scope

- Local access password / auth gate
- API key encryption at rest
- Enabling GitHub Actions workflow
- Large refactors of server or settings APIs

## Constraints

- Zero third-party Python/JS runtime deps
- Portable across Windows / macOS / Linux for the same git revision
- Chinese OK for product UI strings; keep Trellis specs English if touched
- Prefer small focused commit

## Acceptance Criteria

- [x] `start.sh` exists at repo root and launches `app.py --no-browser` from repo root (works when invoked as `./start.sh` or via path)
- [x] README documents Windows `start.vbs`, Unix `start.sh`, and `python app.py` paths
- [x] Opening system settings with host `0.0.0.0` shows a clear risk warning without needing to re-select the host
- [x] Saving system settings with host `0.0.0.0` still requires confirm
- [x] `docs/design.md` 后续迭代 no longer lists already-shipped MVP items as primary “next”
- [x] `CHANGELOG.md` `[Unreleased]` reflects this work; Planned no longer claims multi-platform start scripts as future-only
- [x] `python -m unittest discover -s tests -v` passes; no new third-party deps
