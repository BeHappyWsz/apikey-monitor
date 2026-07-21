# -*- coding: utf-8 -*-
"""OpenAI-compatible protocol probe."""
import json

from version import USER_AGENT

from core import http as http_mod
from core.protocol_base import MODEL_PROBE_MAX_TOKENS, _protocol_result, _record_http, model_response_error
from core.urls import candidate_urls, probe_urls


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


def probe(base, api_key, timeout, check_path=""):
    result = _protocol_result("openai")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
    }
    for url in probe_urls(base, "models", check_path):
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
    chat = _model_probe_adapter(
        base,
        "chat/completions",
        headers,
        {
            "model": model,
            "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
            "max_tokens": MODEL_PROBE_MAX_TOKENS,
            "stream": False,
        },
        timeout,
        "openai",
        "openai_chat",
    )
    if chat["http_status"] not in (0, 404):
        return chat
    responses = _model_probe_adapter(
        base,
        "responses",
        headers,
        {
            "model": model,
            "input": "Reply with exactly: OK",
            "max_output_tokens": MODEL_PROBE_MAX_TOKENS,
        },
        timeout,
        "openai_responses",
        "openai_responses",
    )
    return responses if responses["status"] != "down" else chat


def _model_probe_adapter(base, endpoint, headers, body, timeout, response_protocol, adapter):
    probe_result = _protocol_result("openai")
    probe_result["model_probe_adapter"] = adapter
    for url in candidate_urls(base, endpoint):
        code, raw, ms, err = http_mod._request("POST", url, headers, body, timeout)
        _record_http(probe_result, code, raw, ms, err, validation_400=True)
        if code == 200:
            validation_error = model_response_error(response_protocol, raw)
            if validation_error:
                probe_result.update(status="degraded", error=validation_error)
        if code not in (0, 404):
            break
    return probe_result
