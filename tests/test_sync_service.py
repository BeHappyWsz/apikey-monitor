# -*- coding: utf-8 -*-
"""Verification for the sync orchestration + /api/sync routes.

The pure WebDAV client (core/webdav.py) and payload codec (core/export.py) are
covered by test_webdav.py. This module covers the two layers it leaves
untouched:

* services/sync_service.py — SyncService: credentials, test/upload,
  download merge|replace, status, pre-replace local snapshot.
* api/router.py — /api/sync/{config,status,test,upload,download}: success
  paths plus the WebDAVError -> ApiError mapping the frontend relies on
  (config/auth -> 400, upstream -> 502).

A self-contained stub WebDAV server (GET/PUT/PROPFIND/HEAD, Basic-auth gated)
stands in for 坚果云 so no network is touched.
"""
import base64
import json
import os
import socket
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import core  # noqa: E402
import db  # noqa: E402
from api import router  # noqa: E402
from api.router import ApiError  # noqa: E402
from services import sync_service  # noqa: E402

_LAST_MODIFIED = "Wed, 17 Jul 2026 10:00:00 GMT"


# ---------------------------------------------------------------------------
# Stub WebDAV server (independent of test_webdav's, to avoid shared state)
# ---------------------------------------------------------------------------
class _State:
    def __init__(self):
        self.data = {}
        self.auth = None


class _StubDAV(BaseHTTPRequestHandler):
    state = None  # set on a per-server Handler subclass

    def log_message(self, *args):
        pass

    def _authorized(self):
        if self.state.auth is not None and self.headers.get("Authorization") != self.state.auth:
            self.send_response(401)
            self.end_headers()
            return False
        return True

    def do_GET(self):
        if not self._authorized():
            return
        blob = self.state.data.get(self.path)
        if blob is None:
            self.send_response(404); self.end_headers(); return
        self.send_response(200)
        self.send_header("Content-Length", str(len(blob)))
        self.send_header("Last-Modified", _LAST_MODIFIED)
        self.end_headers()
        self.wfile.write(blob)

    def do_HEAD(self):
        if not self._authorized():
            return
        if self.path in self.state.data:
            self.send_response(200)
            self.send_header("Last-Modified", _LAST_MODIFIED)
            self.end_headers()
        else:
            self.send_response(404); self.end_headers()

    def do_PUT(self):
        if not self._authorized():
            return
        length = int(self.headers.get("Content-Length", 0))
        self.state.data[self.path] = self.rfile.read(length)
        self.send_response(200); self.send_header("ETag", '"abc"'); self.end_headers()

    def do_PROPFIND(self):
        if not self._authorized():
            return
        if self.path in self.state.data:
            self.send_response(207)
            self.send_header("Last-Modified", _LAST_MODIFIED)
            self.end_headers()
        else:
            self.send_response(404); self.end_headers()


def _start_stub(auth_userpass="user:pass"):
    """Start a stub DAV server on a free port. Returns (base_url, state, stop)."""
    state = _State()
    if auth_userpass:
        state.auth = "Basic " + base64.b64encode(auth_userpass.encode("utf-8")).decode("ascii")

    class Handler(_StubDAV):
        pass
    Handler.state = state

    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def stop():
        server.shutdown()
        server.server_close()
    return f"http://127.0.0.1:{port}/dav/", state, stop


def _dead_port():
    """A localhost port that is closed (for connection_error cases)."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class _DBPatchedCase(unittest.TestCase):
    """Isolated DB + backup dir, restored on teardown."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old_db = db.DB_PATH
        self._old_cfg = db.CONFIG_PATH
        self._old_backup = sync_service.BACKUP_DIR
        db.DB_PATH = os.path.join(self.tmp.name, "data.db")
        db.CONFIG_PATH = os.path.join(self.tmp.name, "config.json")
        sync_service.BACKUP_DIR = os.path.join(self.tmp.name, "backups")
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self._old_db
        db.CONFIG_PATH = self._old_cfg
        sync_service.BACKUP_DIR = self._old_backup
        self.tmp.cleanup()


# ---------------------------------------------------------------------------
# SyncService orchestration
# ---------------------------------------------------------------------------
class SyncServiceTests(_DBPatchedCase):
    @classmethod
    def setUpClass(cls):
        cls.base, cls.state, cls.stop_stub = _start_stub()

    @classmethod
    def tearDownClass(cls):
        cls.stop_stub()

    def setUp(self):
        super().setUp()
        self.state.data.clear()
        self.remote = "/apikey-monitor/backup.json"
        db.set_settings({
            "webdavServer": self.base,
            "webdavUsername": "user",
            "webdavPassword": "pass",
            "webdavRemotePath": self.remote,
        })

    def svc(self):
        return sync_service.SyncService()

    def test_get_config_unconfigured(self):
        # set_settings only upserts, so clear by overwriting with empties
        # (a fresh DB simply has these keys absent -> same "" defaults).
        db.set_settings({"webdavServer": "", "webdavUsername": "",
                         "webdavPassword": "", "webdavRemotePath": ""})
        cfg = self.svc().get_config()
        self.assertFalse(cfg["configured"])
        self.assertFalse(cfg["has_password"])

    def test_save_config_marks_configured_and_masks_password(self):
        cfg = self.svc().save_config({
            "server": self.base, "username": "user",
            "remote_path": self.remote, "password": "brand-new",
        })
        self.assertTrue(cfg["configured"])
        self.assertTrue(cfg["has_password"])
        self.assertNotIn("password", cfg)
        self.assertNotIn("brand-new", json.dumps(cfg, ensure_ascii=False))
        # The password stays internal even though its stored key is camelCase.
        self.assertEqual(db.get_all_settings().get("webdavPassword"), "brand-new")

    def test_save_config_empty_password_keeps_existing(self):
        svc = self.svc()
        svc.save_config({"server": self.base, "username": "user",
                         "remote_path": self.remote, "password": "first"})
        # User re-saves without retyping the password (common UI flow).
        svc.save_config({"server": self.base, "username": "user",
                         "remote_path": self.remote, "password": ""})
        self.assertEqual(db.get_all_settings().get("webdavPassword"), "first")
        self.assertTrue(self.svc().get_config()["configured"])

    def test_save_config_directory_remote_path_uses_backup_json(self):
        cfg = self.svc().save_config({
            "server": self.base, "username": "user",
            "remote_path": "apikey-monitor", "password": "pass",
        })
        self.assertEqual(cfg["remote_path"], "apikey-monitor/backup.json")
        self.assertEqual(db.get_all_settings().get("webdavRemotePath"), "apikey-monitor/backup.json")

    def test_save_config_json_remote_path_is_preserved(self):
        cfg = self.svc().save_config({
            "server": self.base, "username": "user",
            "remote_path": "/apikey-monitor/custom.JSON", "password": "pass",
        })
        self.assertEqual(cfg["remote_path"], "/apikey-monitor/custom.JSON")

    def test_test_connection_against_stub(self):
        result = self.svc().test()
        self.assertTrue(result["ok"])
        self.assertFalse(result["exists"])  # nothing uploaded yet

    def test_upload_writes_envelope_and_records_status(self):
        db.add_keys_batch([{"name": "A", "base_url": "https://a.com", "api_key": "sk-a"}])
        res = self.svc().upload()
        self.assertEqual(res["count"], 1)
        # The stub received a JSON envelope at the remote path.
        env = json.loads(self.state.data["/dav" + self.remote])
        self.assertEqual(env["app"], "apikey-monitor")
        self.assertEqual(len(env["keys"]), 1)
        self.assertEqual(env["keys"][0]["api_key"], "sk-a")
        # last-sync is recorded.
        self.assertIn("upload", self.svc().status()["last_sync"])

    def test_sync_payload_and_replace_only_touch_api_keys(self):
        db.add_key({"name": "local", "base_url": "https://local.com", "api_key": "sk-local"})
        db.set_settings({"customSetting": "must-survive"})
        user_id = db.create_user("operator", "hash", enabled=True)
        self.svc().upload()
        envelope = json.loads(self.state.data["/dav" + self.remote])
        self.assertEqual(set(envelope), {"app", "schema", "exported_at", "keys"})
        self.assertEqual(set(envelope["keys"][0]), {"name", "base_url", "api_key", "check_model", "check_path"})
        self.state.data["/dav" + self.remote] = core.dumps_sync_payload([
            {"name": "remote", "base_url": "https://remote.com", "api_key": "sk-remote"},
        ], 1).encode("utf-8")
        self.svc().download("replace")
        self.assertEqual(db.get_all_settings()["customSetting"], "must-survive")
        self.assertEqual(db.get_user(user_id)["username"], "operator")

    def test_download_merge_adds_without_removing(self):
        db.add_keys_batch([{"name": "local", "base_url": "https://local.com", "api_key": "sk-l"}])
        self.state.data["/dav" + self.remote] = core.dumps_sync_payload([
            {"name": "r1", "base_url": "https://r1.com", "api_key": "sk-r1"},
            {"name": "r2", "base_url": "https://r2.com", "api_key": "sk-r2"},
        ], 1).encode("utf-8")
        res = self.svc().download("merge")
        self.assertEqual(res["count"], 2)
        self.assertEqual(res["mode"], "merge")
        urls = {row["base_url"] for row in db.list_keys()}
        self.assertEqual(urls, {"https://local.com", "https://r1.com", "https://r2.com"})

    def test_download_merge_dedups_existing_markers(self):
        db.add_keys_batch([{"name": "A", "base_url": "https://a.com", "api_key": "sk-a"}])
        self.state.data["/dav" + self.remote] = core.dumps_sync_payload([
            {"name": "A2", "base_url": "https://a.com", "api_key": "sk-a"},  # same (url,key)
            {"name": "B", "base_url": "https://b.com", "api_key": "sk-b"},
        ], 1).encode("utf-8")
        res = self.svc().download("merge")
        self.assertEqual(res["count"], 1)            # only B added
        self.assertEqual(res["skipped_duplicate"], 1)

    def test_download_replace_removes_local_and_snapshots(self):
        db.add_keys_batch([{"name": "local", "base_url": "https://local.com", "api_key": "sk-l"}])
        self.state.data["/dav" + self.remote] = core.dumps_sync_payload([
            {"name": "r1", "base_url": "https://r1.com", "api_key": "sk-r1"},
        ], 1).encode("utf-8")
        res = self.svc().download("replace")
        self.assertEqual(res["count"], 1)
        self.assertEqual(res["mode"], "replace")
        urls = {row["base_url"] for row in db.list_keys()}
        self.assertEqual(urls, {"https://r1.com"})   # local entry gone
        # A pre-replace local snapshot was written and reflects the old state.
        self.assertIsNotNone(res["backup_path"])
        self.assertTrue(os.path.exists(res["backup_path"]))
        with open(res["backup_path"], encoding="utf-8") as handle:
            snapshot = json.loads(handle.read())
        self.assertEqual(snapshot[0]["base_url"], "https://local.com")

    def test_download_invalid_mode_raises(self):
        with self.assertRaises(ValueError):
            self.svc().download("bogus")

    def test_status_reports_last_sync_token(self):
        self.assertEqual(self.svc().status(), {"last_sync": ""})
        self.svc().upload()  # records via _record
        self.assertTrue(self.svc().status()["last_sync"].startswith("upload|"))

    def test_last_sync_stays_in_db_only(self):
        # Runtime state lives in the settings table; config.json is a read-only
        # seed the runtime never rewrites. Calls _record directly to avoid the
        # optional HTTP stub.
        self.svc()._record("upload", 3, None)
        self.assertTrue(self.svc().status()["last_sync"].startswith("upload|"))
        self.assertFalse(os.path.exists(db.CONFIG_PATH))


# ---------------------------------------------------------------------------
# /api/sync routes — success paths + WebDAVError -> ApiError mapping
# ---------------------------------------------------------------------------
class RouterSyncTests(_DBPatchedCase):
    @classmethod
    def setUpClass(cls):
        cls.base, cls.state, cls.stop_stub = _start_stub()  # auth = user:pass

    @classmethod
    def tearDownClass(cls):
        cls.stop_stub()

    def setUp(self):
        super().setUp()
        self.remote = "/apikey-monitor/backup.json"
        self.state.data.clear()

    def _creds(self, password="pass"):
        db.set_settings({
            "webdavServer": self.base, "webdavUsername": "user",
            "webdavPassword": password, "webdavRemotePath": self.remote,
        })

    def test_get_config_route_unconfigured(self):
        status, body = router.route("GET", "/api/sync/config", "", {}, None)
        self.assertEqual(status, 200)
        self.assertFalse(body["configured"])

    def test_get_status_route(self):
        status, body = router.route("GET", "/api/sync/status", "", {}, None)
        self.assertEqual((status, body), (200, {"last_sync": ""}))

    def test_save_config_route_then_configured(self):
        self._creds()
        status, body = router.route("POST", "/api/sync/config", "", {
            "server": self.base, "username": "user",
            "remote_path": self.remote, "password": "xyz",
        }, None)
        self.assertEqual(status, 200)
        self.assertTrue(body["configured"])
        self.assertNotIn("password", body)

    def test_save_config_route_rejects_invalid(self):
        with self.assertRaises(ApiError) as ctx:
            router.route("POST", "/api/sync/config", "", {"server": "no-scheme"}, None)
        self.assertEqual(ctx.exception.status, 400)
        self.assertEqual(ctx.exception.code, "invalid_sync_config")

    def test_upload_route_success(self):
        self._creds()
        db.add_keys_batch([{"name": "A", "base_url": "https://a.com", "api_key": "sk-a"}])
        status, body = router.route("POST", "/api/sync/upload", "", {}, None)
        self.assertEqual(status, 200)
        self.assertEqual(body["count"], 1)
        self.assertIn("/dav" + self.remote, self.state.data)

    def test_download_merge_route_success(self):
        self._creds()
        self.state.data["/dav" + self.remote] = core.dumps_sync_payload(
            [{"name": "r1", "base_url": "https://r1.com", "api_key": "sk-r1"}], 1
        ).encode("utf-8")
        status, body = router.route("POST", "/api/sync/download", "", {"mode": "merge"}, None)
        self.assertEqual(status, 200)
        self.assertEqual(body["count"], 1)

    def test_test_route_success(self):
        self._creds()
        status, body = router.route("POST", "/api/sync/test", "", {}, None)
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertFalse(body["exists"])

    def test_config_error_maps_400_sync_not_configured(self):
        # No credentials stored -> build_url raises config_error.
        with self.assertRaises(ApiError) as ctx:
            router.route("POST", "/api/sync/upload", "", {}, None)
        self.assertEqual(ctx.exception.status, 400)
        self.assertEqual(ctx.exception.code, "sync_not_configured")

    def test_auth_error_maps_400_webdav_auth_failed(self):
        self._creds(password="wrong")  # stub still expects user:pass -> 401
        with self.assertRaises(ApiError) as ctx:
            router.route("POST", "/api/sync/test", "", {}, None)
        self.assertEqual(ctx.exception.status, 400)
        self.assertEqual(ctx.exception.code, "webdav_auth_failed")

    def test_connection_error_maps_502_webdav_error(self):
        db.set_settings({
            "webdavServer": f"http://127.0.0.1:{_dead_port()}/dav/",
            "webdavUsername": "u", "webdavPassword": "p",
            "webdavRemotePath": "/x.json",
        })
        with self.assertRaises(ApiError) as ctx:
            router.route("POST", "/api/sync/test", "", {}, None)
        self.assertEqual(ctx.exception.status, 502)
        self.assertEqual(ctx.exception.code, "webdav_error")

    def test_download_invalid_mode_maps_400_invalid_sync(self):
        self._creds()
        with self.assertRaises(ApiError) as ctx:
            router.route("POST", "/api/sync/download", "", {"mode": "bogus"}, None)
        self.assertEqual(ctx.exception.status, 400)
        self.assertEqual(ctx.exception.code, "invalid_sync")


if __name__ == "__main__":
    unittest.main()
