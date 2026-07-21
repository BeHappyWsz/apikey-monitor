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
        "model_probe_adapter": "",
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


def model_response_error(protocol, raw):
    """Return a stable error unless a minimal generated-text response is valid.

    A transport-level 200 is insufficient for a strict usability check: some
    gateways return HTML, a proxy envelope, or an empty JSON object while
    reporting success.  Keep the validation deliberately small and protocol
    specific so it proves that the requested chat/messages operation produced
    text without coupling the monitor to provider-specific optional fields.
    """
    try:
        payload = json.loads(raw)
    except Exception:
        return f"invalid {protocol} model response JSON"
    if protocol == "openai":
        choices = payload.get("choices") if isinstance(payload, dict) else None
        if isinstance(choices, list):
            for choice in choices:
                message = choice.get("message") if isinstance(choice, dict) else None
                content = message.get("content") if isinstance(message, dict) else None
                if isinstance(content, str) and content.strip():
                    return ""
        return "invalid OpenAI completion response"
    if protocol == "openai_responses":
        if isinstance(payload, dict):
            output_text = payload.get("output_text")
            if isinstance(output_text, str) and output_text.strip():
                return ""
            output = payload.get("output")
            if isinstance(output, list):
                for item in output:
                    content = item.get("content") if isinstance(item, dict) else None
                    if _has_response_text(content):
                        return ""
        return "invalid OpenAI responses response"
    if protocol == "anthropic":
        blocks = payload.get("content") if isinstance(payload, dict) else None
        if isinstance(blocks, list):
            for block in blocks:
                if (isinstance(block, dict) and block.get("type") == "text"
                        and isinstance(block.get("text"), str) and block["text"].strip()):
                    return ""
        return "invalid Anthropic message response"
    return "unsupported strict model verification protocol"


def _has_response_text(value):
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        for key in ("text", "content"):
            if _has_response_text(value.get(key)):
                return True
    if isinstance(value, list):
        return any(_has_response_text(item) for item in value)
    return False
