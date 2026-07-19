# -*- coding: utf-8 -*-
"""Anthropic-compatible protocol probe."""
from version import USER_AGENT

from core import http as http_mod
from core.protocol_base import _protocol_result, _record_http, model_response_error
from core.urls import candidate_urls, probe_urls


_MAX_ATTEMPTS = 3  # initial probe + up to 2 retries on transient failures


def _is_transient(code):
    """Failures worth retrying: timeout/connection error (0) or server 5xx."""
    return code == 0 or code >= 500


def probe(base, api_key, timeout, check_path=""):
    result = _protocol_result("anthropic")
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
    }
    body = {
        "model": "claude-3-5-haiku-20241022",
        "max_tokens": 1,
        "messages": [{"role": "user", "content": "hi"}],
    }
    # A real /messages generation can be slow or intermittently fail (5xx /
    # timeout) on reasoning gateways; retry transient failures so a working
    # endpoint is confirmed by a clean 200 rather than a single flaky attempt.
    # Definitive outcomes (200 / 4xx / 401 / 403 / 404) return at once.
    urls = probe_urls(base, "messages", check_path)
    for _ in range(_MAX_ATTEMPTS):
        for url in urls:
            code, raw, ms, err = http_mod._request("POST", url, headers, body, timeout)
            _record_http(result, code, raw, ms, err, validation_400=True)
            if code == 200:
                validation_error = model_response_error("anthropic", raw)
                if validation_error:
                    result.update(status="degraded", error=validation_error)
            if code != 404 and code != 0:
                break
        if result["status"] == "up" or not _is_transient(result["http_status"]):
            return result
    return result


def model_probe(base, api_key, model, timeout):
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
    }
    body = {
        "model": model,
        "max_tokens": 3,
        "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
    }
    probe_result = _protocol_result("anthropic")
    for url in candidate_urls(base, "messages"):
        code, raw, ms, err = http_mod._request("POST", url, headers, body, timeout)
        _record_http(probe_result, code, raw, ms, err, validation_400=True)
        if code == 200:
            validation_error = model_response_error("anthropic", raw)
            if validation_error:
                probe_result.update(status="degraded", error=validation_error)
        if code not in (0, 404):
            break
    return probe_result
