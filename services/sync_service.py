# -*- coding: utf-8 -*-
"""WebDAV cloud-sync orchestration for portable key payloads.

Build/push/pull a JSON envelope (see ``core.export``) against a WebDAV server
such as 坚果云. All operations are user-triggered; nothing syncs silently.

Credentials live in the settings table. The password uses a ``_`` prefix so
``SettingsService.get()`` and ``config.json`` never expose it; sync reads it
back from the DB directly.
"""
import os
import time

import core
import db
from api import validators
from core import webdav

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNTIME_DIR = os.environ.get("APIKEYCONFIG_RUNTIME_DIR", os.path.join(ROOT_DIR, ".runtime"))
BACKUP_DIR = os.path.join(RUNTIME_DIR, "backups")

_WD_SERVER = "webdav_server"
_WD_USERNAME = "webdav_username"
_WD_REMOTE = "webdav_remote_path"
_WD_PASSWORD = "_webdav_password"  # "_" prefix: excluded from config.json + masked API
# Last-sync is runtime state (rewritten every sync). The "_" prefix keeps it in
# the DB only — out of the tracked config.json snapshot and the /api/settings
# surface — while /api/sync/status still reads it back via get_all_settings().
_WD_LAST = "_webdav_last_sync"

_SYNC_TIMEOUT = 30


def _creds():
    s = db.get_all_settings()
    return {
        "server": s.get(_WD_SERVER, ""),
        "username": s.get(_WD_USERNAME, ""),
        "password": s.get(_WD_PASSWORD, ""),
        "remote_path": s.get(_WD_REMOTE, ""),
    }


class SyncService:
    def get_config(self):
        c = _creds()
        configured = bool(c["server"] and c["username"] and c["remote_path"] and c["password"])
        return {
            "configured": configured,
            "server": c["server"],
            "username": c["username"],
            "remote_path": c["remote_path"],
            "has_password": bool(c["password"]),
        }

    def save_config(self, payload):
        values = validators.webdav_config_payload(payload, _creds())
        password = values.get("password") or ""
        items = {
            _WD_SERVER: values["server"],
            _WD_USERNAME: values["username"],
            _WD_REMOTE: values["remote_path"],
        }
        if password:
            items[_WD_PASSWORD] = password  # empty => keep whatever is already stored
        db.set_settings(items)
        return self.get_config()

    def test(self):
        c = _creds()
        return webdav.test_connection(c["server"], c["username"], c["password"], c["remote_path"], _SYNC_TIMEOUT)

    def upload(self):
        c = _creds()
        entries = db.list_keys(public=False)
        text = core.dumps_sync_payload(entries, time.time()).encode("utf-8")
        info = webdav.upload(c["server"], c["username"], c["password"], c["remote_path"], text, _SYNC_TIMEOUT)
        self._record("upload", len(entries), info.get("last_modified"))
        return {"count": len(entries), "remote_modified": info.get("last_modified")}

    def download(self, mode="merge"):
        if mode not in ("merge", "replace"):
            raise ValueError("mode must be merge or replace")
        c = _creds()
        result = webdav.download(c["server"], c["username"], c["password"], c["remote_path"], _SYNC_TIMEOUT)
        items = core.parse_sync_payload(result["data"])
        backup_path = None
        if mode == "replace":
            backup_path = self._snapshot_local()
            existing = [row["id"] for row in db.list_keys(public=False)]
            if existing:
                db.delete_keys(existing)
        ids, skipped = db.add_keys_batch(items)
        self._record(f"download:{mode}", len(ids), result.get("last_modified"), skipped)
        return {
            "count": len(ids),
            "skipped_duplicate": skipped,
            "mode": mode,
            "backup_path": backup_path,
            "remote_modified": result.get("last_modified"),
        }

    def status(self):
        return {"last_sync": db.get_all_settings().get(_WD_LAST, "")}

    def _record(self, action, count, remote_modified, skipped=0):
        parts = [action, f"count={count}", f"skipped={skipped}", f"ts={int(time.time())}"]
        if remote_modified:
            parts.append(f"remote={remote_modified}")
        # persist=False: runtime state must not trigger a config.json rewrite.
        db.set_settings({_WD_LAST: "|".join(parts)}, persist=False)

    def _snapshot_local(self):
        """Best-effort local JSON snapshot before a destructive replace."""
        os.makedirs(BACKUP_DIR, exist_ok=True)
        text = core.export_batch(db.list_keys(public=False), "json")
        path = os.path.join(BACKUP_DIR, f"sync-replace-{int(time.time())}.json")
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)
        except OSError:
            return None
        return path


SYNC = SyncService()
