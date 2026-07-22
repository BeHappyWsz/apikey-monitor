# -*- coding: utf-8 -*-
import os
import tempfile
import unittest

import db


class ThinListPayloadTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old_db = db.DB_PATH
        self._old_cfg = db.CONFIG_PATH
        db.DB_PATH = os.path.join(self._tmp.name, "thin.db")
        db.CONFIG_PATH = os.path.join(self._tmp.name, "config.json")
        db._list_generation = 0
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self._old_db
        db.CONFIG_PATH = self._old_cfg
        self._tmp.cleanup()

    def test_page_items_are_thin_detail_is_full(self):
        key_id = db.add_key({
            "name": "thin-demo",
            "base_url": "https://thin.example.com",
            "api_key": "sk-thin-demo-key-123456",
            "notes": "secret note body",
            "check_model": "gpt-test",
        })
        db.update_models(key_id, ["m1", "m2", "m3"])
        page = db.list_keys_page(limit=50, search="thin-demo")
        row = next(item for item in page["items"] if item["id"] == key_id)
        self.assertEqual(row.get("view"), "list")
        self.assertNotIn("models", row)
        self.assertNotIn("notes", row)
        self.assertEqual(row.get("models_count"), 3)
        self.assertTrue(row.get("has_notes"))
        full = db.get_key(key_id, public=True)
        self.assertEqual(full.get("view"), "full")
        self.assertEqual(full.get("models"), ["m1", "m2", "m3"])
        self.assertEqual(full.get("notes"), "secret note body")
        self.assertEqual(full.get("models_count"), 3)


if __name__ == "__main__":
    unittest.main()
