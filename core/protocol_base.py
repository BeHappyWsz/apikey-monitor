# -*- coding: utf-8 -*-
"""Shared protocol probe result shaping."""
import json

_AUTH_WORDS = ("auth", "api key", "api_key", "unauthorized", "forbidden", "credential", "token")


def _extract_error_message(raw):
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            err = obj.get("error")
            if isinstance(err, dict) and err.get("message"):
                return str(err["message"])[:150]
            if obj.get("message"):
                return str(obj["message"])[:150]
            if isinstance(err, str):
                return err[:150]
    except Exception:
        pass
    return (raw or "")[:150]


def _protocol_result(name):
    return {
        "protocol": name,
        "endpoint_exists": False,
        "authenticated": False,
        "status": "down",
        "http_status": 0,
        "latency_ms": None,
        "models": [],
        "error": "unreachable",
    }


def _record_http(result, code, raw, ms, err, success_codes=(200,), validation_400=False):
    result.update(http_status=code, latency_ms=ms)
    if code in success_codes:
        result.update(endpoint_exists=True, authenticated=True, status="up", error="")
    elif code in (401, 403):
        result.update(endpoint_exists=True, status="auth_error", error=f"key rejected ({code})")
    elif code == 429:
        result.update(endpoint_exists=True, authenticated=True, status="rate_limited", error="rate limited (429)")
    elif code >= 500:
        result.update(endpoint_exists=True, status="degraded", error=err or f"HTTP {code}")
    elif code == 400 and validation_400:
        detail = _extract_error_message(raw)
        is_auth = any(word in detail.lower() for word in _AUTH_WORDS)
        result.update(
            endpoint_exists=True,
            authenticated=not is_auth,
            status="auth_error" if is_auth else "degraded",
            error=detail or "request validation failed (400)",
        )
    elif code and code != 404:
        result.update(endpoint_exists=True, status="degraded", error=err or f"HTTP {code}")
    elif err:
        result["error"] = err
