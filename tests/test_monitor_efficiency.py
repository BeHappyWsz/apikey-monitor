# -*- coding: utf-8 -*-
"""Efficiency helpers: list revision, due cap, health without model probe."""
import os
import tempfile
import time
import unittest
from unittest.mock import patch

import db
import monitor
import core


class ListRevisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "t.db")
        self.cfg_path = os.path.join(self.tmp.name, "c.json")
        self._old_db = os.environ.get("APIKEYCONFIG_DB_PATH")
        self._old_cfg = os.environ.get("APIKEYCONFIG_CONFIG_PATH")
        os.environ["APIKEYCONFIG_DB_PATH"] = self.db_path
        os.environ["APIKEYCONFIG_CONFIG_PATH"] = self.cfg_path
        # re-bind module paths
        db.DB_PATH = self.db_path
        db.CONFIG_PATH = self.cfg_path
        db._list_generation = 0
        db.init_db()

    def tearDown(self):
        if self._old_db is None:
            os.environ.pop("APIKEYCONFIG_DB_PATH", None)
        else:
            os.environ["APIKEYCONFIG_DB_PATH"] = self._old_db
        if self._old_cfg is None:
            os.environ.pop("APIKEYCONFIG_CONFIG_PATH", None)
        else:
            os.environ["APIKEYCONFIG_CONFIG_PATH"] = self._old_cfg
        self.tmp.cleanup()

    def test_revision_changes_on_status_update(self):
        kid = db.add_key({"name": "a", "base_url": "https://example.com", "api_key": "sk"})
        r1 = db.get_list_revision()
        db.update_status(kid, "up", 12, "")
        r2 = db.get_list_revision()
        self.assertNotEqual(r1, r2)

    def test_get_due_keys_limit_and_order(self):
        now = int(time.time())
        ids = []
        for i in range(5):
            kid = db.add_key({
                "name": f"k{i}",
                "base_url": f"https://example.com/{i}",
                "api_key": f"sk-{i}",
                "monitor_enabled": 1,
            })
            # older last_check_at first
            db.update_status(kid, "up", 1, "")
            # force last_check_at via direct SQL for deterministic order
            with db.connection(write=True) as conn:
                conn.execute("UPDATE tbl_keys SET last_check_at=?,next_check_at=? WHERE id=?",
                             (now - 1000 + i, now - 1000 + i, kid))
            ids.append(kid)
        due = db.get_due_keys(now, up_interval=60, down_interval=30, limit=2)
        self.assertEqual(len(due), 2)
        self.assertEqual(due[0]["id"], ids[0])
        self.assertEqual(due[1]["id"], ids[1])

    def test_next_check_schedule_applies_backoff_and_jitter(self):
        entry = {"id": 7, "interval_sec": None}
        settings = {"global_interval_sec": "300", "down_recheck_interval_sec": "120"}
        now = 10000
        up = db.monitor_next_check_at(entry, "up", settings, now)
        down = db.monitor_next_check_at(entry, "down", settings, now)
        limited = db.monitor_next_check_at(entry, "rate_limited", settings, now)
        auth = db.monitor_next_check_at(entry, "auth_error", settings, now)
        self.assertGreaterEqual(up, now + 285)
        self.assertLessEqual(up, now + 315)
        self.assertGreaterEqual(down, now + 114)
        self.assertLessEqual(down, now + 126)
        self.assertGreaterEqual(limited, now + 1140)
        self.assertGreater(auth, limited)

    def test_get_due_keys_uses_persisted_schedule(self):
        now = int(time.time())
        due_id = db.add_key({"base_url": "https://due.example", "api_key": "sk-due"})
        future_id = db.add_key({"base_url": "https://future.example", "api_key": "sk-future"})
        with db.connection(write=True) as conn:
            conn.execute("UPDATE tbl_keys SET next_check_at=? WHERE id=?", (now - 1, due_id))
            conn.execute("UPDATE tbl_keys SET next_check_at=? WHERE id=?", (now + 3600, future_id))
        self.assertEqual([entry["id"] for entry in db.get_due_keys(now, limit=10)], [due_id])


class MonitorTickGuardTests(unittest.TestCase):
    def test_tick_skips_when_inflight(self):
        monitor._inflight = True
        try:
            with patch("db.get_all_settings") as gs:
                monitor.tick()
                gs.assert_not_called()
        finally:
            monitor._inflight = False

    def test_tick_caps_batch_and_waits(self):
        monitor._inflight = False
        calls = []

        def fake_batch(ids, health=False):
            calls.append((list(ids), health))
            return {"task_id": "check-test", "status": "completed", "finished_at": time.time()}

        due = [{"id": i} for i in range(1, 20)]
        with patch("db.get_all_settings", return_value={
            "global_monitor_enabled": "1",
            "global_interval_sec": "300",
            "down_recheck_interval_sec": "120",
            "concurrency": "3",
        }), patch("db.get_due_keys", return_value=due) as gdue, \
             patch.object(monitor.KEYS, "batch_check", side_effect=fake_batch), \
             patch.object(monitor, "_wait_task"):
            monitor.tick()
            # limit = concurrency * 2 = 6
            gdue.assert_called()
            kwargs = gdue.call_args
            # positional or keyword limit
            if kwargs.kwargs:
                self.assertEqual(kwargs.kwargs.get("limit"), 6)
            else:
                self.assertEqual(kwargs.args[3], 6)
            self.assertEqual(len(calls), 1)
            self.assertTrue(calls[0][1] is True)


if __name__ == "__main__":
    unittest.main()
