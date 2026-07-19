# -*- coding: utf-8 -*-
"""Quick unit checks for uiRefreshIntervalSec."""
import unittest
from api import validators


class UiRefreshSettingsTest(unittest.TestCase):
    def test_default_and_valid(self):
        out = validators.settings_payload({})
        self.assertEqual(out["uiRefreshIntervalSec"], "15")
        out = validators.settings_payload({"uiRefreshIntervalSec": "0"})
        self.assertEqual(out["uiRefreshIntervalSec"], "0")
        out = validators.settings_payload({"uiRefreshIntervalSec": "30"})
        self.assertEqual(out["uiRefreshIntervalSec"], "30")

    def test_rejects_too_small_nonzero(self):
        with self.assertRaises(ValueError):
            validators.settings_payload({"uiRefreshIntervalSec": "1"})
        with self.assertRaises(ValueError):
            validators.settings_payload({"uiRefreshIntervalSec": "2"})

    def test_rejects_too_large(self):
        with self.assertRaises(ValueError):
            validators.settings_payload({"uiRefreshIntervalSec": "3601"})


if __name__ == "__main__":
    unittest.main()
