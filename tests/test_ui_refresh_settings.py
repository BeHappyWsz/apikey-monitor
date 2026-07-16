# -*- coding: utf-8 -*-
"""Quick unit checks for ui_refresh_interval_sec."""
import unittest
from api import validators


class UiRefreshSettingsTest(unittest.TestCase):
    def test_default_and_valid(self):
        out = validators.settings_payload({})
        self.assertEqual(out["ui_refresh_interval_sec"], "5")
        out = validators.settings_payload({"ui_refresh_interval_sec": "0"})
        self.assertEqual(out["ui_refresh_interval_sec"], "0")
        out = validators.settings_payload({"ui_refresh_interval_sec": "30"})
        self.assertEqual(out["ui_refresh_interval_sec"], "30")

    def test_rejects_too_small_nonzero(self):
        with self.assertRaises(ValueError):
            validators.settings_payload({"ui_refresh_interval_sec": "1"})
        with self.assertRaises(ValueError):
            validators.settings_payload({"ui_refresh_interval_sec": "2"})

    def test_rejects_too_large(self):
        with self.assertRaises(ValueError):
            validators.settings_payload({"ui_refresh_interval_sec": "3601"})


if __name__ == "__main__":
    unittest.main()
