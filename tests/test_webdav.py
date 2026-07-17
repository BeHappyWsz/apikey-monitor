# -*- coding: utf-8 -*-
import base64
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import export, webdav  # noqa: E402
import db  # noqa: E402
from services.settings_service import SETTINGS  # noqa: E402


# ---------------------------------------------------------------------------
# Pure-function tests
# ---------------------------------------------------------------------------
class BuildUrlTests(unittest.TestCase):
    def test_join_server_and_relative_path(self):
        url = webdav.build_url("https://dav.jianguoyun.com/dav/", "/apikey/backup.json")
        self.assertEqual(url, "https://dav.jianguoyun.com/dav/apikey/backup.json")

    def test_path_without_leading_slash_is_normalized(self):
        url = webdav.build_url("https://host/dav", "folder//file.json")
        self.assertEqual(url, "https://host/dav/folder/file.json")

    def test_rejects_traversal(self):
        with self.assertRaises(webdav.WebDAVError) as ctx:
            webdav.build_url("https://host/dav/", "/../etc/passwd")
        self.assertEqual(ctx.exception.code, "config_error")

    def test_rejects_absolute_remote_and_query(self):
        for bad in ("https://evil/x", "/a?b=1", "/a#frag"):
            with self.assertRaises(webdav.WebDAVError):
                webdav.build_url("https://host/dav/", bad)

    def test_rejects_credentials_in_server(self):
        with self.assertRaises(webdav.WebDAVError):
            webdav.build_url("https://u:p@host/dav/", "/x.json")


class AuthHeaderTests(unittest.TestCase):
    def test_basic_auth_header_value(self):
        header = webdav._auth_header("me@example.com", "app-secret")
        self.assertEqual(header, "Basic " + base64.b64encode(b"me@example.com:app-secret").decode())

    def test_missing_username_raises(self):
        with self.assertRaises(webdav.WebDAVError) as ctx:
            webdav._auth_header("", "x")
        self.assertEqual(ctx.exception.code, "config_error")


class PayloadTests(unittest.TestCase):
    def test_build_envelope_shape(self):
        payload = export.build_sync_payload(
            [{"name": "n", "base_url": "https://a.com/v1/models", "api_key": "sk", "check_model": "m", "check_path": "/v1/models"}],
            123,
        )
        self.assertEqual(payload["app"], export.SYNC_APP)
        self.assertEqual(payload["schema"], export.SCHEMA_VERSION)
        self.assertEqual(payload["exported_at"], 123)
        self.assertEqual(len(payload["keys"]), 1)
        self.assertEqual(payload["keys"][0]["base_url"], "https://a.com")  # /v1/models suffix stripped

    def test_parse_envelope_array_single(self):
        envelope = '{"app":"apikey-monitor","schema":1,"keys":[{"base_url":"https://a.com","api_key":"k","name":"x"}]}'
        bare = '[{"base_url":"https://b.com","api_key":"k2"}]'
        single = '{"base_url":"https://c.com","api_key":"k3","check_path":"//bad\\"path"}'
        self.assertEqual(len(export.parse_sync_payload(envelope)), 1)
        self.assertEqual(len(export.parse_sync_payload(bare)), 1)
        one = export.parse_sync_payload(single)[0]
        self.assertEqual(one["base_url"], "https://c.com")
        self.assertEqual(one["check_path"], "")  # invalid path cleared, entry kept

    def test_parse_drops_entries_without_url_or_key(self):
        text = '[{"base_url":"https://a.com","api_key":""},{"api_key":"k"}]'
        self.assertEqual(export.parse_sync_payload(text), [])

    def test_roundtrip_preserves_portable_fields(self):
        entries = [{"name": "a", "base_url": "https://a.com", "api_key": "sk-a", "check_model": "gpt", "check_path": "/v1/models"}]
        text = export.dumps_sync_payload(entries, 1)
        parsed = export.parse_sync_payload(text)
        self.assertEqual(parsed[0]["api_key"], "sk-a")
        self.assertEqual(parsed[0]["check_model"], "gpt")


# ---------------------------------------------------------------------------
# Stub WebDAV server round-trip
# ---------------------------------------------------------------------------
class _Store:
    data = {}
    auth = None


class _StubHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _authorized(self):
        if _Store.auth is not None and self.headers.get("Authorization") != _Store.auth:
            self.send_response(401)
            self.end_headers()
            return False
        return True

    def do_GET(self):
        if not self._authorized():
            return
        data = _Store.data.get(self.path)
        if data is None:
            self.send_response(404); self.end_headers(); return
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Last-Modified", "Wed, 17 Jul 2026 10:00:00 GMT")
        self.end_headers()
        self.wfile.write(data)

    def do_HEAD(self):
        if not self._authorized():
            return
        if self.path in _Store.data:
            self.send_response(200)
            self.send_header("Last-Modified", "Wed, 17 Jul 2026 10:00:00 GMT")
            self.end_headers()
        else:
            self.send_response(404); self.end_headers()

    def do_PUT(self):
        if not self._authorized():
            return
        length = int(self.headers.get("Content-Length", 0))
        _Store.data[self.path] = self.rfile.read(length)
        self.send_response(200); self.send_header("ETag", '"abc"'); self.end_headers()

    def do_PROPFIND(self):
        if not self._authorized():
            return
        if self.path in _Store.data:
            self.send_response(207)
            self.send_header("Last-Modified", "Wed, 17 Jul 2026 10:00:00 GMT")
            self.end_headers()
        else:
            self.send_response(404); self.end_headers()


class StubServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _Store.data = {}
        _Store.auth = "Basic " + base64.b64encode(b"user:pass").decode()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _StubHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def _base(self):
        return f"http://127.0.0.1:{self.port}/dav/"

    def test_test_connection_missing_then_present(self):
        result = webdav.test_connection(self._base(), "user", "pass", "/k/backup.json", timeout=5)
        self.assertTrue(result["ok"])
        self.assertFalse(result["exists"])
        webdav.upload(self._base(), "user", "pass", "/k/backup.json", b"{}", timeout=5)
        result = webdav.test_connection(self._base(), "user", "pass", "/k/backup.json", timeout=5)
        self.assertTrue(result["exists"])
        self.assertEqual(result["last_modified"], "Wed, 17 Jul 2026 10:00:00 GMT")

    def test_upload_download_roundtrip(self):
        payload = export.dumps_sync_payload(
            [{"name": "n", "base_url": "https://a.com", "api_key": "sk"}], 1
        ).encode("utf-8")
        webdav.upload(self._base(), "user", "pass", "/k/rt.json", payload, timeout=5)
        got = webdav.download(self._base(), "user", "pass", "/k/rt.json", timeout=5)
        parsed = export.parse_sync_payload(got["data"])
        self.assertEqual(parsed[0]["api_key"], "sk")

    def test_auth_failure(self):
        with self.assertRaises(webdav.WebDAVError) as ctx:
            webdav.test_connection(self._base(), "user", "wrong", "/k/backup.json", timeout=5)
        self.assertEqual(ctx.exception.code, "auth_error")

    def test_error_message_redacts_credentials(self):
        # A connection error string must not echo embedded user:pass@.
        redacted = webdav._redact("URLError: <https://user:secret@host/dav/x.json>")
        self.assertNotIn("user:secret", redacted)
        self.assertNotIn("secret", redacted)


# ---------------------------------------------------------------------------
# Settings masking (password never leaks via the settings API surface)
# ---------------------------------------------------------------------------
class SettingsMaskingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old_db = db.DB_PATH
        self._old_cfg = db.CONFIG_PATH
        db.DB_PATH = os.path.join(self.tmp.name, "data.db")
        db.CONFIG_PATH = os.path.join(self.tmp.name, "config.json")
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self._old_db
        db.CONFIG_PATH = self._old_cfg
        self.tmp.cleanup()

    def test_password_masked_in_settings_get(self):
        db.set_settings({"webdav_server": "https://dav.example.com/dav/",
                         "webdav_username": "me", "webdav_remote_path": "/k/b.json",
                         "_webdav_password": "super-secret"})
        exposed = SETTINGS.get()
        self.assertNotIn("_webdav_password", exposed)
        self.assertNotIn("super-secret", str(exposed))
        self.assertEqual(exposed["webdav_server"], "https://dav.example.com/dav/")

    def test_runtime_never_writes_config_json(self):
        # config.json is a read-only seed; runtime mutations stay in the DB
        # only, so secrets never reach config.json (the file is not even created).
        db.set_settings({"_webdav_password": "super-secret", "server_port": "9999"})
        self.assertEqual(db.get_all_settings().get("_webdav_password"), "super-secret")
        self.assertEqual(db.get_all_settings().get("server_port"), "9999")
        self.assertFalse(os.path.exists(db.CONFIG_PATH))


if __name__ == "__main__":
    unittest.main()
