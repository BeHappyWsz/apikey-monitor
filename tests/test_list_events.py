# -*- coding: utf-8 -*-
"""Unit coverage for in-process list-revision event fan-out."""
import unittest

from services import list_events


class ListEventServiceTests(unittest.TestCase):
    def test_wait_list_change_returns_latest_notification(self):
        seq, _ = list_events.snapshot()
        self.assertGreater(list_events.notify_list_changed("test-revision"), seq)
        new_seq, revision = list_events.wait_list_change(seq, timeout=0)
        self.assertGreater(new_seq, seq)
        self.assertEqual(revision, "test-revision")


if __name__ == "__main__":
    unittest.main()
