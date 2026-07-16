# -*- coding: utf-8 -*-
import os
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
        with patch("core._request", side_effect=responses):
            result = core.classify("https://example.com", "sk-test")
        self.assertEqual(result["status"], "auth_error")
        self.assertTrue(result["supports_anthropic"])

    def test_mixed_protocol_auth_and_success_is_up(self):
        responses = [(401, "", 2, "HTTP 401"), (200, "{}", 3, None)]
        with patch("core._request", side_effect=responses):
            result = core.classify("https://example.com", "sk-test")
        self.assertEqual(result["status"], "up")
        self.assertTrue(result["supports_openai"])
        self.assertTrue(result["supports_anthropic"])

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
        with patch("core._request", side_effect=responses):
            result = core.classify("https://example.com", "sk-test")
        self.assertEqual(result["status"], "auth_error")

    def test_model_result_does_not_replace_protocol_status(self):
        responses = [(200, '{"data":[]}', 1, None), (404, "", 1, "HTTP 404"), (404, "", 1, "HTTP 404")]
        with patch("core._request", side_effect=responses), patch("core.model_check", return_value={
            "model_status": "auth_error", "model_latency_ms": 9, "model_error": "model rejected"}):
            result = core.classify("https://example.com", "sk-test", check_model="gpt-test")
        self.assertEqual(result["status"], "up")
        self.assertEqual(result["model_status"], "auth_error")


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




if __name__ == "__main__":
    unittest.main()
