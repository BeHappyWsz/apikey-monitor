# -*- coding: utf-8 -*-
"""Protocol selection (monitor vs discover) and single-instance helpers."""
import json
import os
import tempfile
import unittest
from unittest.mock import patch

import core
from core.protocols import anthropic as anthropic_mod
from services import instance as instance_svc


class ProtocolSelectionTests(unittest.TestCase):
    def test_protocol_names_monitor_known_only(self):
        self.assertEqual(core.probe.protocol_names_to_probe(True, False, mode="monitor"), ["openai"])
        self.assertEqual(core.probe.protocol_names_to_probe(False, True, mode="monitor"), ["anthropic"])
        self.assertEqual(core.probe.protocol_names_to_probe(True, True, mode="monitor"), ["openai", "anthropic"])
        self.assertEqual(core.probe.protocol_names_to_probe(False, False, mode="monitor"), ["openai", "anthropic"])
        self.assertEqual(core.probe.protocol_names_to_probe(mode="discover"), ["openai", "anthropic"])

    def test_health_refreshes_all_protocols(self):
        calls = []

        def fake_request(method, url, headers, body, timeout):
            calls.append(url)
            if "models" in url:
                return 200, '{"data":[]}', 1, None
            return 404, "", 1, "HTTP 404"

        with patch("core.http._request", side_effect=fake_request):
            result = core.health_check(
                "https://example.com", "sk-test", supports_openai=True, supports_anthropic=False
            )
        self.assertEqual(result["status"], "up")
        self.assertTrue(result["supports_openai"])
        self.assertFalse(result["supports_anthropic"])
        self.assertTrue(any("models" in url for url in calls))
        self.assertTrue(any("messages" in url for url in calls))

    def test_health_failure_clears_known_capability(self):
        calls = []

        def fake_request(method, url, headers, body, timeout):
            calls.append(url)
            return 0, "", None, "timeout"

        with patch("core.http._request", side_effect=fake_request):
            result = core.health_check(
                "https://example.com", "sk-test", supports_openai=True, supports_anthropic=False
            )
        self.assertEqual(result["status"], "down")
        self.assertFalse(result["supports_openai"])
        self.assertFalse(result["supports_anthropic"])
        self.assertTrue(any("models" in url for url in calls))
        self.assertTrue(any("messages" in url for url in calls))

    def test_health_replaces_stale_openai_with_anthropic(self):
        calls = []

        def fake_request(method, url, headers, body, timeout):
            calls.append(url)
            if "models" in url:
                return 404, "", 1, "HTTP 404"
            return 200, '{"content":[{"type":"text","text":"OK"}]}', 2, None

        with patch("core.http._request", side_effect=fake_request):
            result = core.health_check(
                "https://example.com", "sk-test", supports_openai=True, supports_anthropic=False
            )
        self.assertEqual(result["status"], "up")
        self.assertFalse(result["supports_openai"])
        self.assertTrue(result["supports_anthropic"])
        self.assertTrue(any("models" in url for url in calls))
        self.assertTrue(any("messages" in url for url in calls))

    def test_health_unknown_probes_all(self):
        calls = []

        def fake_request(method, url, headers, body, timeout):
            calls.append(url)
            if "models" in url:
                return 200, '{"data":[]}', 1, None
            return 404, "", 1, "HTTP 404"

        with patch("core.http._request", side_effect=fake_request):
            result = core.health_check(
                "https://example.com", "sk-test", supports_openai=False, supports_anthropic=False
            )
        self.assertEqual(result["status"], "up")
        self.assertTrue(result["supports_openai"])
        self.assertFalse(result["supports_anthropic"])
        self.assertTrue(any("models" in url for url in calls))
        self.assertTrue(any("messages" in url for url in calls))

    def test_classify_still_probes_all(self):
        calls = []

        def fake_request(method, url, headers, body, timeout):
            calls.append(url)
            if "models" in url:
                return 200, '{"data":[]}', 1, None
            return 404, "", 1, "HTTP 404"

        with patch("core.http._request", side_effect=fake_request):
            result = core.classify("https://example.com", "sk-test")
        self.assertEqual(result["status"], "up")
        self.assertTrue(any("models" in url for url in calls))
        self.assertTrue(any("messages" in url for url in calls))


    def test_health_skips_model_check_even_with_check_model(self):
        """Monitor path must not issue chat/model probes when check_model is set."""
        calls = []

        def fake_request(method, url, headers, body, timeout):
            calls.append(url)
            if "models" in url:
                return 200, '{"data":[]}', 1, None
            return 200, "{}", 1, None

        with patch("core.http._request", side_effect=fake_request):
            result = core.health_check(
                "https://example.com",
                "sk-test",
                supports_openai=True,
                supports_anthropic=False,
                check_model="gpt-4o",
            )
        self.assertEqual(result["status"], "up")
        self.assertEqual(result.get("model_status"), "unknown")
        # No chat-style model probe body; only connectivity (models list / messages for anthropic)
        self.assertTrue(all("chat/completions" not in url for url in calls))
        self.assertTrue(result.get("model_error") in (None, ""))

class AnthropicRetryTests(unittest.TestCase):
    """The anthropic capability probe retries transient failures (5xx / timeout)
    so a working but flaky endpoint is confirmed by a clean 200 rather than a
    single bad attempt."""

    def _fake(self, responses):
        calls = []
        seq = iter(responses)

        def request(method, url, headers, body, timeout):
            calls.append(url)
            try:
                return next(seq)
            except StopIteration:
                return (0, "", 1, "exhausted")

        return calls, request

    def test_retries_5xx_then_succeeds(self):
        calls, fake = self._fake([(502, "", 1, "HTTP 502"),
                                  (200, '{"content":[{"type":"text","text":"OK"}]}', 5, None)])
        with patch("core.http._request", side_effect=fake):
            result = anthropic_mod.probe("https://example.com", "sk", 15)
        self.assertEqual(result["status"], "up")
        self.assertEqual(result["http_status"], 200)
        self.assertGreater(len(calls), 1)

    def test_retries_timeout_then_succeeds(self):
        # both candidate URLs time out in attempt 1; retry succeeds on attempt 2
        calls, fake = self._fake([(0, "", 1, "timeout"), (0, "", 1, "timeout"),
                                  (200, '{"content":[{"type":"text","text":"OK"}]}', 5, None)])
        with patch("core.http._request", side_effect=fake):
            result = anthropic_mod.probe("https://example.com", "sk", 15)
        self.assertEqual(result["status"], "up")
        self.assertEqual(result["http_status"], 200)

    def test_persistent_5xx_gives_up_degraded(self):
        calls, fake = self._fake([(502, "", 1, "HTTP 502")] * 5)
        with patch("core.http._request", side_effect=fake):
            result = anthropic_mod.probe("https://example.com", "sk", 15)
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(len(calls), 3)  # initial + 2 retries, one URL each

    def test_no_retry_on_auth(self):
        calls, fake = self._fake([(401, "", 1, "HTTP 401")])
        with patch("core.http._request", side_effect=fake):
            result = anthropic_mod.probe("https://example.com", "sk", 15)
        self.assertEqual(result["status"], "auth_error")
        self.assertEqual(len(calls), 1)

    def test_no_retry_on_404(self):
        calls, fake = self._fake([(404, "", 1, "HTTP 404")] * 6)
        with patch("core.http._request", side_effect=fake):
            result = anthropic_mod.probe("https://example.com", "sk", 15)
        self.assertEqual(result["status"], "down")
        self.assertEqual(len(calls), 2)  # both candidate URLs once, no retry


class InstanceHelpersTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.runtime = os.path.join(self.temp.name, "runtime")
        os.makedirs(self.runtime, exist_ok=True)
        self._old = os.environ.get("APIKEYCONFIG_RUNTIME_DIR")
        os.environ["APIKEYCONFIG_RUNTIME_DIR"] = self.runtime
        # Reload module paths that cache RUNTIME_DIR at import time.
        import importlib
        import services.instance as mod
        importlib.reload(mod)
        self.mod = mod

    def tearDown(self):
        if self._old is None:
            os.environ.pop("APIKEYCONFIG_RUNTIME_DIR", None)
        else:
            os.environ["APIKEYCONFIG_RUNTIME_DIR"] = self._old
        import importlib
        import services.instance as mod
        importlib.reload(mod)
        self.temp.cleanup()

    def test_write_read_clear_pid(self):
        rec = self.mod.write_pid_record("127.0.0.1", 17999)
        self.assertEqual(rec["pid"], os.getpid())
        loaded = self.mod.read_pid_record()
        self.assertEqual(loaded["port"], 17999)
        self.mod.clear_pid_record(only_if_self=True)
        self.assertIsNone(self.mod.read_pid_record())

    def test_stale_pid_is_cleared(self):
        path = os.path.join(self.runtime, "server.pid")
        with open(path, "w", encoding="utf-8") as stream:
            json.dump({"pid": 99999999, "host": "127.0.0.1", "port": 17998}, stream)
        # ensure_single_instance should clear dead pid and allow bind on free port
        import socket
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        msg = self.mod.ensure_single_instance("127.0.0.1", port)
        self.assertFalse(os.path.exists(path))
        self.assertIn("stale", msg.lower() or "cleared" in msg)


if __name__ == "__main__":
    unittest.main()
