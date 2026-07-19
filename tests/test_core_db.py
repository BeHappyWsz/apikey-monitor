# -*- coding: utf-8 -*-
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import core
import db


class CoreTests(unittest.TestCase):
    def test_url_join_deduplicates_v1(self):
        self.assertEqual(core.join_api_path("https://example.com/v1", "/v1/models"), "https://example.com/v1/models")
        self.assertEqual(core.join_api_path("https://example.com/proxy", "/v1/models"), "https://example.com/proxy/v1/models")

    def test_control_characters_are_rejected(self):
        with self.assertRaises(ValueError): core.normalize_base_url("https://example.com\nBAD=x")
        with self.assertRaises(ValueError): core.export_config({"base_url": "https://example.com", "api_key": "ok\nBAD=x"}, "codex")

    def test_export_quotes_values(self):
        text = core.export_config({"base_url": "https://example.com/v1", "api_key": "a'b"}, "codex")
        self.assertIn("OPENAI_BASE_URL='https://example.com/v1'", text)
        self.assertIn("OPENAI_API_KEY='a'\"'\"'b'", text)

    def test_anthropic_401_is_auth_error(self):
        responses = [(404, "", 1, "HTTP 404"), (404, "", 1, "HTTP 404"),
                     (401, '{"error":{"message":"invalid api key"}}', 2, "HTTP 401")]
        with patch("core.http._request", side_effect=responses):
            result = core.classify("https://example.com", "sk-test")
        self.assertEqual(result["status"], "auth_error")
        self.assertFalse(result["supports_anthropic"])

    def test_mixed_protocol_auth_and_success_is_up(self):
        responses = [(401, "", 2, "HTTP 401"), (200, '{"content":[{"type":"text","text":"OK"}]}', 3, None)]
        with patch("core.http._request", side_effect=responses):
            result = core.classify("https://example.com", "sk-test")
        self.assertEqual(result["status"], "up")
        self.assertFalse(result.get("error"))
        self.assertFalse(result["supports_openai"])
        self.assertTrue(result["supports_anthropic"])

    def test_mixed_protocol_success_clears_secondary_error(self):
        """OpenAI-only success must not keep Anthropic 404 as last_error."""
        responses = [(200, '{"data":[]}', 1, None), (404, "", 1, "HTTP 404"), (404, "", 1, "HTTP 404")]
        with patch("core.http._request", side_effect=responses):
            result = core.classify("https://example.com", "sk-test")
        self.assertEqual(result["status"], "up")
        self.assertFalse(result.get("error"))
        self.assertTrue(result["supports_openai"])
        self.assertFalse(result["supports_anthropic"])
        self.assertEqual(result["openai_status"], "up")
        self.assertEqual(result["anthropic_status"], "down")

    def test_aggregate_errors_only_from_winning_status(self):
        protocols = [
            {"protocol": "openai", "status": "up", "latency_ms": 10, "error": ""},
            {"protocol": "anthropic", "status": "down", "latency_ms": 5, "error": "HTTP 404"},
        ]
        status, latency, error = core.probe._aggregate(protocols)
        self.assertEqual(status, "up")
        self.assertEqual(latency, 10)
        self.assertEqual(error, "")

    def test_aggregate_auth_error_keeps_auth_message(self):
        protocols = [
            {"protocol": "openai", "status": "auth_error", "latency_ms": 8, "error": "key rejected (401)"},
            {"protocol": "anthropic", "status": "down", "latency_ms": None, "error": "unreachable"},
        ]
        status, latency, error = core.probe._aggregate(protocols)
        self.assertEqual(status, "auth_error")
        self.assertIn("key rejected", error)
        self.assertNotIn("unreachable", error)


    def test_protocol_status_matrix(self):
        expected = {200: "up", 400: "degraded", 401: "auth_error", 403: "auth_error",
                    429: "rate_limited", 500: "degraded", 0: "down"}
        for code, status in expected.items():
            with self.subTest(code=code):
                result = core._protocol_result("anthropic")
                raw = '{"error":{"message":"invalid request"}}' if code == 400 else "{}"
                core._record_http(result, code, raw, 5, "timeout" if code == 0 else f"HTTP {code}", validation_400=True)
                self.assertEqual(result["status"], status)

    def test_both_protocols_auth_failure(self):
        responses = [(401, "", 1, "HTTP 401"), (403, "", 2, "HTTP 403")]
        with patch("core.http._request", side_effect=responses):
            result = core.classify("https://example.com", "sk-test")
        self.assertEqual(result["status"], "auth_error")
        self.assertFalse(result["supports_openai"])
        self.assertFalse(result["supports_anthropic"])
        self.assertEqual(result["openai_status"], "auth_error")
        self.assertEqual(result["anthropic_status"], "auth_error")

    def test_model_result_does_not_replace_protocol_status(self):
        responses = [(200, '{"data":[]}', 1, None), (404, "", 1, "HTTP 404"), (404, "", 1, "HTTP 404")]
        with patch("core.http._request", side_effect=responses), patch("core.probe.model_check", return_value={
            "model_status": "auth_error", "model_latency_ms": 9, "model_error": "model rejected"}):
            result = core.classify("https://example.com", "sk-test", check_model="gpt-test")
        self.assertEqual(result["status"], "up")
        self.assertEqual(result["model_status"], "auth_error")

    def test_strict_openai_model_check_requires_generated_text(self):
        with patch("core.http._request", return_value=(200,
                '{"choices":[{"message":{"content":"OK"}}]}', 7, None)):
            result = core.model_check("https://example.com", "sk-test", "gpt-test", supports_openai=True)
        self.assertEqual(result["model_status"], "up")
        self.assertTrue(result["model_verified"])
        self.assertEqual(result["model_verification_version"], 1)

    def test_strict_openai_model_check_rejects_empty_or_proxy_response(self):
        with patch("core.http._request", return_value=(200, "{}", 7, None)):
            result = core.model_check("https://example.com", "sk-test", "gpt-test", supports_openai=True)
        self.assertEqual(result["model_status"], "degraded")
        self.assertFalse(result["model_verified"])
        self.assertIn("invalid OpenAI completion response", result["model_error"])

    def test_strict_anthropic_model_check_requires_text_block(self):
        with patch("core.http._request", return_value=(200,
                '{"content":[{"type":"text","text":"OK"}]}', 7, None)):
            result = core.model_check("https://example.com", "sk-test", "claude-test", supports_anthropic=True)
        self.assertEqual(result["model_status"], "up")
        self.assertTrue(result["model_verified"])


    def test_export_formats(self):
        entry = {"id": 1, "name": "demo", "base_url": "https://example.com/v1", "api_key": "sk-demo"}
        env = core.export_config(entry, "env")
        self.assertIn("OPENAI_BASE_URL=", env)
        self.assertIn("ANTHROPIC_AUTH_TOKEN=", env)
        ps = core.export_config(entry, "powershell")
        self.assertIn("$env:OPENAI_API_KEY = 'sk-demo'", ps)
        js = core.export_config(entry, "json")
        self.assertIn('"api_key": "sk-demo"', js)
        self.assertIn('"base_url":', js)
        self.assertIn('"check_model":', js)
        self.assertNotIn('"id"', js)
        self.assertNotIn('"status"', js)
        self.assertNotIn('"supports_openai"', js)
        batch = core.export_batch([entry, {**entry, "id": 2, "name": "b"}], "json")
        self.assertIn('"name": "demo"', batch)
        self.assertIn('"name": "b"', batch)
        self.assertNotIn('"id"', batch)
        with self.assertRaises(ValueError):
            core.export_batch([entry], "env")


    def test_parse_import_json_array_and_object(self):
        arr = core.parse_import_text("""[
          {"name": "a", "base_url": "https://a.example/v1", "api_key": "sk-aaaaaaaaaaaa", "check_model": "gpt"},
          {"name": "b", "base_url": "https://b.example", "api_key": "sk-bbbbbbbbbbbb"}
        ]""")
        self.assertEqual(len(arr), 2)
        self.assertEqual(arr[0]["check_model"], "gpt")
        self.assertEqual(arr[0]["name"], "a")
        one = core.parse_import_text('{"base_url":"https://c.example","api_key":"sk-cccccccccccc","name":"c"}')
        self.assertEqual(len(one), 1)
        self.assertEqual(one[0]["name"], "c")
        wrapped = core.parse_import_text('{"items":[{"base_url":"https://d.example","api_key":"sk-dddddddddddd"}]}')
        self.assertEqual(len(wrapped), 1)
        # still supports env paste
        paste = core.parse_import_text("OPENAI_BASE_URL=https://e.example\nOPENAI_API_KEY=sk-eeeeeeeeeeee")
        self.assertEqual(len(paste), 1)
        self.assertEqual(paste[0]["base_url"], "https://e.example")

    def test_parse_import_tolerates_chat_text_and_fenced_json(self):
        mixed = """这里是说明，不要把普通链接当作密钥： https://docs.example/help

```json
{"keys":[{"name":"copied","base_url":"https://api.example/v1","api_key":"sk-embedded-1234567890"}]}
```

上面是备份，后续对话内容不应影响解析。
"""
        parsed = core.parse_import_text(mixed)
        self.assertEqual([(item["name"], item["base_url"], item["api_key"])
                          for item in parsed],
                         [("copied", "https://api.example/v1", "sk-embedded-1234567890")])

    def test_parse_import_does_not_pair_distant_chat_hash_with_url(self):
        chat = """请阅读 https://docs.example/guide ，这是普通文档链接。
这几行都是说明文字，并不是配置。
继续讨论如何配置模型。
这里的会话校验串 abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKL 也不是 API Key。
"""
        self.assertEqual(core.parse_import_text(chat), [])

    def test_parse_import_accepts_raw_url_and_token_on_same_line(self):
        parsed = core.parse_import_text("https://gateway.example/v1 token-value-0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJK")
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["base_url"], "https://gateway.example/v1")

    def test_export_roundtrip_fields(self):
        entry = {"name": "n", "base_url": "https://example.com/v1", "api_key": "sk-demo-key-xx", "check_model": "m"}
        text = core.export_config(entry, "json")
        back = core.parse_import_text(text)
        self.assertEqual(len(back), 1)
        self.assertEqual(back[0]["base_url"], "https://example.com/v1")
        self.assertEqual(back[0]["api_key"], "sk-demo-key-xx")
        self.assertEqual(back[0]["check_model"], "m")



    def test_registries_expose_builtin_extensions(self):
        self.assertEqual(core.list_protocol_names(), ["openai", "anthropic"])
        self.assertIn("claude", core.list_export_formats())
        self.assertIn("json", core.EXPORT_FORMATS)
        self.assertTrue(core.IMPORTERS)
        with self.assertRaises(ValueError):
            core.export_config({"base_url": "https://example.com", "api_key": "k"}, "nope")




    def test_normalize_check_path(self):
        self.assertEqual(core.normalize_check_path(""), "")
        self.assertEqual(core.normalize_check_path("  /v1/models  "), "/v1/models")
        self.assertEqual(core.normalize_check_path("openai/v1/models"), "/openai/v1/models")
        with self.assertRaises(ValueError):
            core.normalize_check_path("https://evil.example/v1/models")
        with self.assertRaises(ValueError):
            core.normalize_check_path("//evil.example/v1")
        with self.assertRaises(ValueError):
            core.normalize_check_path("/v1/models?x=1")
        with self.assertRaises(ValueError):
            core.normalize_check_path("/v1/models#frag")

    def test_probe_urls_custom_path(self):
        urls = core.probe_urls("https://example.com/proxy", "models", "/custom/models")
        self.assertEqual(urls, ["https://example.com/proxy/custom/models"])
        default = core.probe_urls("https://example.com", "models", "")
        self.assertEqual(default, core.candidate_urls("https://example.com", "models"))

    def test_classify_uses_custom_check_path(self):
        seen = []
        def fake_request(method, url, headers, body, timeout):
            seen.append(url)
            return (200, '{"data":[]}', 1, None)
        with patch("core.http._request", side_effect=fake_request):
            result = core.classify("https://example.com", "sk-test", check_path="/gateway/models")
        self.assertTrue(any(u.endswith("/gateway/models") for u in seen))
        self.assertTrue(all("/gateway/models" in u for u in seen))
        self.assertEqual(result["status"], "up")

class DbTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_db, self.old_config = db.DB_PATH, db.CONFIG_PATH
        db.DB_PATH = os.path.join(self.temp.name, "data.db")
        db.CONFIG_PATH = os.path.join(self.temp.name, "config.json")
        db.init_db()
    def tearDown(self):
        db.DB_PATH, db.CONFIG_PATH = self.old_db, self.old_config
        self.temp.cleanup()
    def test_endpoint_edit_resets_status(self):
        key_id = db.add_key({"base_url": "https://a.example", "api_key": "sk-old"})
        db.update_status(key_id, "up", 12, "", True, True, ["x"])
        db.update_model_status(key_id, "up", 5, "")
        db.update_key(key_id, {"api_key": "sk-new"})
        row = db.get_key(key_id)
        self.assertEqual(row["status"], "unknown")
        self.assertEqual(row["models"], [])
        self.assertIsNone(row["last_check_at"])
        self.assertEqual(row["model_status"], "unknown")
        self.assertEqual(row["model_verification_version"], 0)

    def test_reorder_keys_persists_list_order(self):
        first = db.add_key({"base_url": "https://a.example", "api_key": "sk-a"})
        second = db.add_key({"base_url": "https://b.example", "api_key": "sk-b"})
        third = db.add_key({"base_url": "https://c.example", "api_key": "sk-c"})
        db.reorder_keys([first, third, second])
        self.assertEqual([row["id"] for row in db.list_keys()], [first, third, second])

    def test_new_key_after_reorder_goes_to_top(self):
        first = db.add_key({"base_url": "https://a.example", "api_key": "sk-a"})
        second = db.add_key({"base_url": "https://b.example", "api_key": "sk-b"})
        db.reorder_keys([first, second])
        third = db.add_key({"base_url": "https://c.example", "api_key": "sk-c"})
        self.assertEqual(db.list_keys()[0]["id"], third)

    def test_batch_skips_duplicates(self):
        first = db.add_key({"base_url": "https://a.example", "api_key": "sk-a"})
        ids, skipped = db.add_keys_batch([
            {"base_url": "https://a.example", "api_key": "sk-a"},
            {"base_url": "https://b.example", "api_key": "sk-b"},
        ])
        self.assertEqual(skipped, 1)
        self.assertEqual(len(ids), 1)
        self.assertNotEqual(ids[0], first)

    def test_cursor_page_is_masked_filtered_and_has_summary(self):
        ids = [db.add_key({"name": f"key-{index}", "base_url": f"https://{index}.example", "api_key": f"sk-{index}"})
               for index in range(4)]
        for index, key_id in enumerate(ids):
            db.update_status(key_id, "up" if index % 2 == 0 else "down", index + 1, "")
        first = db.list_keys_page(limit=2)
        self.assertEqual(len(first["items"]), 2)
        self.assertTrue(first["next_cursor"])
        self.assertEqual(first["total"], 4)
        self.assertEqual(first["summary"]["up"], 2)
        self.assertNotIn("api_key", first["items"][0])
        second = db.list_keys_page(limit=2, cursor=first["next_cursor"])
        self.assertEqual(len(second["items"]), 2)
        self.assertFalse(second["next_cursor"])
        self.assertEqual({row["id"] for row in first["items"] + second["items"]}, set(ids))
        filtered = db.list_keys_page(limit=10, status_filter="up", search="key")
        self.assertEqual(filtered["total"], 2)
        self.assertEqual(len(filtered["items"]), 2)

    def test_cursor_page_rejects_invalid_cursor_and_filter(self):
        db.add_key({"base_url": "https://a.example", "api_key": "sk-a"})
        with self.assertRaisesRegex(ValueError, "invalid page cursor"):
            db.list_keys_page(cursor="not-a-cursor")
        with self.assertRaisesRegex(ValueError, "invalid status filter"):
            db.list_keys_page(status_filter="anything")

    def test_move_key_before_does_not_need_full_client_order(self):
        first = db.add_key({"base_url": "https://a.example", "api_key": "sk-a"})
        second = db.add_key({"base_url": "https://b.example", "api_key": "sk-b"})
        third = db.add_key({"base_url": "https://c.example", "api_key": "sk-c"})
        self.assertTrue(db.move_key_before(first, third))
        # New keys start at the top: [third, second, first]. Moving `first`
        # before `third` therefore produces [first, third, second] without
        # requiring the browser to send every id.
        self.assertEqual([row["id"] for row in db.list_keys()], [first, third, second])


    def test_public_list_masks_api_key(self):
        key_id = db.add_key({"name": "n1", "base_url": "https://a.example", "api_key": "sk-abcdefghijklmnopqrstuvwxyz"})
        public_rows = db.list_keys(public=True)
        self.assertEqual(len(public_rows), 1)
        row = public_rows[0]
        self.assertNotIn("api_key", row)
        self.assertTrue(row["has_api_key"])
        self.assertEqual(row["api_key_masked"], db.mask_api_key("sk-abcdefghijklmnopqrstuvwxyz"))
        self.assertEqual(row["id"], key_id)

        full = db.get_key(key_id, public=False)
        self.assertEqual(full["api_key"], "sk-abcdefghijklmnopqrstuvwxyz")
        public_one = db.get_key(key_id, public=True)
        self.assertNotIn("api_key", public_one)
        self.assertEqual(public_one["api_key_masked"], row["api_key_masked"])

    def test_partial_update_empty_api_key_keeps_secret(self):
        from api import validators
        key_id = db.add_key({"base_url": "https://a.example", "api_key": "sk-keep-me-secret-xx"})
        payload = validators.key_payload({
            "name": "renamed",
            "base_url": "https://a.example",
            "api_key": "",
            "notes": "x",
        }, partial=True)
        self.assertNotIn("api_key", payload)
        db.update_key(key_id, payload)
        row = db.get_key(key_id)
        self.assertEqual(row["api_key"], "sk-keep-me-secret-xx")
        self.assertEqual(row["name"], "renamed")

    def test_mask_api_key_short_and_long(self):
        self.assertEqual(db.mask_api_key(""), "••••••••")
        self.assertEqual(db.mask_api_key("short"), "••••••••")
        self.assertEqual(db.mask_api_key("sk-1234567890abcdef"), "sk-12••••••cdef")





    def test_check_path_roundtrip(self):
        key_id = db.add_key({
            "name": "p", "base_url": "https://example.com", "api_key": "sk-aaaaaaaaaaaa",
            "check_path": "/v1/models",
        })
        entry = db.get_key(key_id)
        self.assertEqual(entry.get("check_path"), "/v1/models")
        db.update_key(key_id, {"check_path": "/custom/health"})
        entry = db.get_key(key_id)
        self.assertEqual(entry.get("check_path"), "/custom/health")
        pub = db.public_key(entry)
        self.assertEqual(pub.get("check_path"), "/custom/health")
        self.assertNotIn("api_key", pub)

    def test_legacy_tables_migrate_without_losing_data(self):
        legacy_path = os.path.join(self.temp.name, "legacy.db")
        conn = sqlite3.connect(legacy_path)
        try:
            conn.executescript("""
            CREATE TABLE keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT DEFAULT '', base_url TEXT NOT NULL,
                api_key TEXT NOT NULL, supports_anthropic INTEGER DEFAULT 0,
                supports_openai INTEGER DEFAULT 0, models TEXT DEFAULT '[]', status TEXT DEFAULT 'unknown',
                latency_ms INTEGER, last_check_at INTEGER, last_error TEXT DEFAULT '',
                monitor_enabled INTEGER DEFAULT 1, interval_sec INTEGER, notes TEXT DEFAULT '',
                created_at INTEGER, check_model TEXT DEFAULT '', model_status TEXT DEFAULT 'unknown',
                model_latency_ms INTEGER, model_last_check_at INTEGER, model_last_error TEXT DEFAULT '',
                sort_order INTEGER DEFAULT 0, check_path TEXT DEFAULT ''
            );
            CREATE TABLE settings (k TEXT PRIMARY KEY, v TEXT);
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL, must_change_password INTEGER DEFAULT 0, created_at INTEGER NOT NULL
            );
            CREATE TABLE sessions (
                token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                csrf_token TEXT NOT NULL, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL, last_seen_at INTEGER NOT NULL
            );
            CREATE INDEX idx_sessions_expires_at ON sessions(expires_at);
            """)
            conn.execute("INSERT INTO keys(id,name,base_url,api_key,models,sort_order) VALUES(?,?,?,?,?,?)",
                         (7, "legacy", "https://legacy.example", "sk-legacy", '["model-a"]', -10))
            conn.execute("INSERT INTO settings(k,v) VALUES(?,?)", ("custom", "preserved"))
            conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(?,?,?,?)",
                         (4, "legacy-admin", "$argon2id$legacy", 100))
            conn.execute("INSERT INTO sessions(token_hash,user_id,csrf_token,created_at,expires_at,last_seen_at) VALUES(?,?,?,?,?,?)",
                         ("legacy-token", 4, "csrf", 100, 200, 100))
            conn.commit()
        finally:
            conn.close()
        previous_path = db.DB_PATH
        try:
            db.DB_PATH = legacy_path
            db.init_db()
            with db.connection() as conn:
                tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                foreign_keys = conn.execute("PRAGMA foreign_key_list(tbl_sessions)").fetchall()
                key_columns = {row[1] for row in conn.execute("PRAGMA table_info(tbl_keys)")}
            self.assertTrue({"tbl_keys", "tbl_settings", "tbl_users", "tbl_sessions"} <= tables)
            self.assertFalse({"keys", "settings", "users", "sessions"} & tables)
            self.assertTrue({"openai_status", "anthropic_status", "model_verification_version", "next_check_at"} <= key_columns)
            self.assertEqual(db.get_key(7)["api_key"], "sk-legacy")
            self.assertEqual(db.get_key(7)["models"], ["model-a"])
            self.assertEqual(db.get_all_settings()["custom"], "preserved")
            with db.connection() as check_conn:
                legacy_setting = check_conn.execute(
                    "SELECT name FROM tbl_settings WHERE k='custom'").fetchone()
            self.assertEqual(legacy_setting["name"], "自定义设置：custom")
            self.assertEqual(db.get_session("legacy-token")["username"], "legacy-admin")
            self.assertEqual(foreign_keys[0][2], "tbl_users")
            db.init_db()
            self.assertEqual(db.get_key(7)["name"], "legacy")
        finally:
            db.DB_PATH = previous_path

    def test_settings_name_metadata_is_backfilled_and_not_returned_by_settings_api(self):
        db.set_settings({
            "webdav_server": "https://dav.example.test/",
            "_webdav_password": "not-exposed",
            "custom_setting": "value",
        })
        with db.connection() as conn:
            rows = {row["k"]: row["name"] for row in conn.execute(
                "SELECT k,name FROM tbl_settings WHERE k IN (?,?,?)",
                ("webdav_server", "_webdav_password", "custom_setting"))}
            columns = {row[1] for row in conn.execute("PRAGMA table_info(tbl_settings)")}
        self.assertEqual(columns, {"k", "v", "name"})
        self.assertEqual(rows, {
            "webdav_server": "WebDAV 服务器地址",
            "_webdav_password": "WebDAV 应用密码",
            "custom_setting": "自定义设置：custom_setting",
        })
        self.assertEqual(db.get_all_settings()["webdav_server"], "https://dav.example.test/")
        self.assertNotIn("name", db.get_public_settings())

    def test_table_name_collision_stops_initialization(self):
        collision_path = os.path.join(self.temp.name, "collision.db")
        conn = sqlite3.connect(collision_path)
        try:
            conn.execute("CREATE TABLE keys (id INTEGER PRIMARY KEY)")
            conn.execute("CREATE TABLE tbl_keys (id INTEGER PRIMARY KEY)")
            conn.commit()
        finally:
            conn.close()
        previous_path = db.DB_PATH
        try:
            db.DB_PATH = collision_path
            with self.assertRaisesRegex(RuntimeError, "both legacy and tbl_\\* tables exist"):
                db.init_db()
        finally:
            db.DB_PATH = previous_path

if __name__ == "__main__":
    unittest.main()

