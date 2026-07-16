# -*- coding: utf-8 -*-
"""Classify / health / model check orchestration over the protocol registry."""
from core.protocol_base import _protocol_result
from core.protocols import PROTOCOL_PROBES, get_protocol
from core.urls import normalize_base_url


def _aggregate(protocols):
    priority = ("up", "auth_error", "rate_limited", "degraded", "down")
    status = next((candidate for candidate in priority if any(p["status"] == candidate for p in protocols)), "unknown")
    relevant = [p for p in protocols if p["status"] == status]
    latency = next((p["latency_ms"] for p in relevant if p["latency_ms"] is not None), None)
    # Only surface errors from protocols that match the winning status.
    # Otherwise a secondary protocol failure (e.g. Anthropic 404 on an
    # OpenAI-only endpoint) keeps last_error/model_last_error populated
    # while overall status is already "up".
    errors = [f"{p['protocol']}: {p['error']}" for p in relevant if p.get("error")]
    return status, latency, "; ".join(errors)[:300]


def _empty_result(error, supports_openai=False, supports_anthropic=False):
    return {
        "supports_openai": supports_openai,
        "supports_anthropic": supports_anthropic,
        "models": [],
        "status": "down",
        "latency_ms": None,
        "error": error,
        "protocols": [],
        "model_status": "unknown",
        "model_latency_ms": None,
        "model_error": None,
    }


def classify(base_url, api_key, timeout=15, check_model="", check_path=""):
    try:
        base = normalize_base_url(base_url)
    except ValueError as exc:
        return _empty_result(str(exc))
    if not api_key:
        return _empty_result("missing api_key")

    protocols = [entry["probe"](base, api_key, timeout, check_path) for entry in PROTOCOL_PROBES]
    status, latency, error = _aggregate(protocols)
    by_name = {p["protocol"]: p for p in protocols}
    openai = by_name.get("openai")
    anth = by_name.get("anthropic")
    result = {
        "supports_openai": bool(openai and openai["endpoint_exists"]),
        "supports_anthropic": bool(anth and anth["endpoint_exists"]),
        "models": openai["models"] if openai else [],
        "status": status,
        "latency_ms": latency,
        "error": error,
        "protocols": protocols,
        "model_status": "unknown",
        "model_latency_ms": None,
        "model_error": None,
    }
    if check_model:
        check = model_check(
            base,
            api_key,
            check_model,
            result["supports_openai"],
            result["supports_anthropic"],
            timeout,
        )
        result.update(check)
    return result


def model_check(base_url, api_key, model, supports_openai=False, supports_anthropic=False, timeout=15):
    result = {"model_status": "unknown", "model_latency_ms": None, "model_error": None}
    try:
        base = normalize_base_url(base_url)
    except ValueError as exc:
        result.update(model_status="down", model_error=str(exc))
        return result
    if not api_key or not model:
        result.update(model_status="down", model_error="missing api_key or model")
        return result

    protocols = []
    if supports_openai or not (supports_openai or supports_anthropic):
        protocols.append(get_protocol("openai")["model_probe"](base, api_key, model, timeout))
    if supports_anthropic:
        protocols.append(get_protocol("anthropic")["model_probe"](base, api_key, model, timeout))
    status, latency, error = _aggregate(protocols or [_protocol_result("unknown")])
    result.update(model_status=status, model_latency_ms=latency, model_error=error)
    return result


def health_check(base_url, api_key, supports_openai=False, supports_anthropic=False, timeout=15, check_model="", check_path=""):
    try:
        base = normalize_base_url(base_url)
    except ValueError as exc:
        return _empty_result(str(exc), supports_openai, supports_anthropic)

    protocols = []
    openai_probe = get_protocol("openai")["probe"]
    anth_probe = get_protocol("anthropic")["probe"]

    if supports_openai or not (supports_openai or supports_anthropic):
        protocols.append(openai_probe(base, api_key, timeout, check_path))
    if supports_anthropic or not (supports_openai or supports_anthropic) or not any(p["status"] == "up" for p in protocols):
        protocols.append(anth_probe(base, api_key, timeout, check_path))
    if not any(p["protocol"] == "openai" for p in protocols) and not any(p["status"] == "up" for p in protocols):
        protocols.append(openai_probe(base, api_key, timeout, check_path))

    status, latency, error = _aggregate(protocols)
    openai = next((p for p in protocols if p["protocol"] == "openai"), None)
    anth = next((p for p in protocols if p["protocol"] == "anthropic"), None)
    result = {
        "supports_openai": openai["endpoint_exists"] if openai else supports_openai,
        "supports_anthropic": anth["endpoint_exists"] if anth else supports_anthropic,
        "models": openai["models"] if openai else [],
        "status": status,
        "latency_ms": latency,
        "error": error,
        "protocols": protocols,
        "model_status": "unknown",
        "model_latency_ms": None,
        "model_error": None,
    }
    if check_model:
        result.update(
            model_check(
                base,
                api_key,
                check_model,
                result["supports_openai"],
                result["supports_anthropic"],
                timeout,
            )
        )
    return result
