# -*- coding: utf-8 -*-
"""Opt-in contract check for a real MySQL 8+/Redis 8+ deployment.

Set APIKEYCONFIG_TEST_MYSQL_REDIS=1 plus the normal storage connection
variables (or provide their private config.json seed) to run this test.  It
creates and removes only timestamped smoke records in the selected database.
"""
import hashlib
import os
import time
import unittest

import db


@unittest.skipUnless(os.environ.get("APIKEYCONFIG_TEST_MYSQL_REDIS") == "1",
                     "requires configured MySQL and Redis")
class MySqlRedisIntegrationTests(unittest.TestCase):
    def setUp(self):
        if db.storage_backend() != "mysql":
            self.skipTest("set APIKEYCONFIG_STORAGE_BACKEND=mysql")
        db.init_db()
        self.marker = f"mysql-redis-test-{time.time_ns()}"
        self.key_id = None
        self.user_id = None

    def tearDown(self):
        if self.key_id is not None:
            db.delete_keys([self.key_id])
        if self.user_id is not None:
            with db.connection(write=True) as conn:
                conn.execute("DELETE FROM tbl_users WHERE id=?", (self.user_id,))

    def test_schema_transaction_and_cache_contract(self):
        with db.connection() as conn:
            tables = {row[0] for row in conn.execute("SHOW TABLES")}
            setting_columns = {row["COLUMN_NAME"] for row in conn.execute(
                "SELECT COLUMN_NAME FROM information_schema.columns "
                "WHERE table_schema=DATABASE() AND table_name='tbl_settings'")}
        self.assertTrue({"tbl_keys", "tbl_settings", "tbl_users", "tbl_sessions"} <= tables)
        self.assertTrue({"k", "v", "name"} <= setting_columns)

        self.key_id = db.add_key({
            "name": self.marker,
            "base_url": "https://mysql-redis-contract.invalid",
            "api_key": "test-token-not-a-real-secret",
        })
        public = db.get_key(self.key_id, public=True)
        self.assertNotIn("api_key", public)
        cache = db._cache()
        self.assertIsNotNone(cache)
        cache_key = f"{db._PUBLIC_KEY_CACHE_PREFIX}{self.key_id}"
        self.assertGreater(cache.ttl(cache_key), 0)

        self.assertTrue(db.update_key(self.key_id, {"name": self.marker + "-updated"}))
        self.assertIsNone(cache.get(cache_key))
        self.assertEqual(db.get_key(self.key_id, public=True)["name"], self.marker + "-updated")

        self.user_id = db.create_user(self.marker, "$argon2id$test", must_change_password=True)
        token_hash = hashlib.sha256(self.marker.encode("utf-8")).hexdigest()
        db.create_session(token_hash, self.user_id, "csrf-test", int(time.time()) + 60)
        self.assertEqual(db.get_session(token_hash)["user_id"], self.user_id)

        with self.assertRaises(RuntimeError):
            with db.connection(write=True) as conn:
                conn.execute("INSERT INTO tbl_settings(k,v) VALUES(?,?)", (self.marker, "rollback"))
                raise RuntimeError("verify rollback")
        self.assertNotIn(self.marker, db.get_all_settings())


if __name__ == "__main__":
    unittest.main()
