# -*- coding: utf-8 -*-
"""OpenAI-compatible protocol probe."""
import json

from version import USER_AGENT

from core import http as http_mod
from core.protocol_base import _protocol_result, _record_http
from core.urls import candidate_urls


def _parse_models(raw):
    try:
        obj = json.loads(raw)
    except Exception:
        return []
    values = obj.get("data", obj) if isinstance(obj, dict) else obj
    found = []
    if isinstance(values, list):
        for value in values:
            model = value.get("id") if isinstance(value, dict) else value if isinstance(value, str) else None
            if model and model not in found:
                found.append(model)
    return found[:200]


def probe(base, api_key, timeout):
    result = _protocol_result("openai")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
    }
    for url in candidate_urls(base, "models"):
        code, raw, ms, err = http_mod._request("GET", url, headers, None, timeout)
        _record_http(result, code, raw, ms, err)
        if code != 404 and code != 0:
            if code == 200:
                result["models"] = _parse_models(raw)
            break
    return result


def model_probe(base, api_key, model, timeout):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
    }
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 1,
        "stream": False,
    }
    probe_result = _protocol_result("openai")
    for url in candidate_urls(base, "chat/completions"):
        code, raw, ms, err = http_mod._request("POST", url, headers, body, timeout)
        _record_http(probe_result, code, raw, ms, err, validation_400=True)
        if code not in (0, 404):
            break
    return probe_result
