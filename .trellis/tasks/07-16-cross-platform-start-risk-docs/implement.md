# Implement checklist — Package A

## Order

1. **A1** Add `start.sh` (repo root)
2. **A3** Polish system-settings LAN warning (HTML + `settings.js` + CSS if needed)
3. **A2** README start paths + layout table
4. **A4** `docs/design.md` 后续迭代 + `CHANGELOG.md` Unreleased
5. **A5** Verify + commit

## A1 — start.sh

- `#!/usr/bin/env bash`
- `cd` to script directory
- Prefer `python3`, else `python`
- Exec `app.py --no-browser "$@"` so extra args can pass through
- Optional: if first arg is `--bg` / `bg`, run with `nohup` in background and print PID — only if simple; otherwise foreground-only is OK
- Do not invent Windows support inside the shell script

## A3 — bind risk UX

- Files: `static/js/settings.js`, `static/index.html`, style file that owns `.setting-note` / `.danger-note` (find under `static/`)
- On system-settings open after setting `#set-host` value, set `$("#lan-warning").hidden = host !== "0.0.0.0"`
- Align warning + confirm copy
- Keep existing save confirm gate

## A2 — README

- Under 快速启动: subsection for Unix `start.sh` next to Windows `start.vbs`
- Environment table: mention both scripts
- Layout table: `start.sh`

## A4 — design + changelog

- design 后续迭代: items 1–4 are largely done in v0.1.0 → reframe as “已完成（v0.1.0）” or replace list with true next items (access password, encryption, multi-user, etc.)
- CHANGELOG Unreleased Added: start.sh, LAN warning polish on open, docs sync
- CHANGELOG Planned: drop multi-platform start scripts; keep password/encryption

## Validation

```bash
# syntax / portable review of start.sh (manual on Windows if bash missing)
# bash -n start.sh   # when bash available

python -m unittest discover -s tests -v
node --check static/js/settings.js
```

Manual smoke (when UI available): open system settings with host 0.0.0.0 → warning visible; change away and back → toggle; save → confirm.

## Commit message (suggested)

```
feat: add start.sh and harden non-loopback bind warnings
```

## Rollback

- Revert the single commit; no schema or API contract changes expected.
