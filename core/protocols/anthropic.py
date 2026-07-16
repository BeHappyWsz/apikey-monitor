# -*- coding: utf-8 -*-
"""Anthropic-compatible protocol probe."""
from version import USER_AGENT

from core import http as http_mod
from core.protocol_base import _protocol_result, _record_http
from core.urls import candidate_urls


def probe(base, api_key, timeout):
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
        "messages": [{"role": "user", "content": "ping"}],
    }
    for url in candidate_urls(base, "messages"):
        code, raw, ms, err = http_mod._request("POST", url, headers, body, timeout)
        _record_http(result, code, raw, ms, err, validation_400=True)
        if code != 404 and code != 0:
            break
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
        "max_tokens": 1,
        "messages": [{"role": "user", "content": "hi"}],
    }
    probe_result = _protocol_result("anthropic")
    for url in candidate_urls(base, "messages"):
        code, raw, ms, err = http_mod._request("POST", url, headers, body, timeout)
        _record_http(probe_result, code, raw, ms, err, validation_400=True)
        if code not in (0, 404):
            break
    return probe_result
