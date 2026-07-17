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


def protocol_names_to_probe(supports_openai=False, supports_anthropic=False, mode="discover"):
    """Select protocol names to probe.

    mode="discover": always all registered protocols (manual classify).
    mode="monitor": only known successful protocols; if none known, all
    (first-time / never succeeded). Never falls back to other protocols
    when a known one fails.
    """
    if mode == "discover":
        return [entry["name"] for entry in PROTOCOL_PROBES]
    known = []
    if supports_openai:
        known.append("openai")
    if supports_anthropic:
        known.append("anthropic")
    if known:
        # Preserve registry order among selected names.
        order = {entry["name"]: index for index, entry in enumerate(PROTOCOL_PROBES)}
        return sorted(known, key=lambda name: order.get(name, 999))
    return [entry["name"] for entry in PROTOCOL_PROBES]


def _run_probes(base, api_key, timeout, check_path, names):
    protocols = []
    for name in names:
        entry = get_protocol(name)
        protocols.append(entry["probe"](base, api_key, timeout, check_path))
    return protocols


def _result_from_protocols(protocols, supports_openai=False, supports_anthropic=False, probed_names=None, preserve_supports=False):
    status, latency, error = _aggregate(protocols)
    by_name = {p["protocol"]: p for p in protocols}
    openai = by_name.get("openai")
    anth = by_name.get("anthropic")
    probed = set(probed_names or by_name.keys())

    if preserve_supports:
        # Monitor path: keep known capability flags; only refresh status/latency/error.
        supports_openai_out = bool(supports_openai)
        supports_anthropic_out = bool(supports_anthropic)
    else:
        if "openai" in probed:
            supports_openai_out = bool(openai and openai.get("endpoint_exists"))
        else:
            supports_openai_out = bool(supports_openai)
        if "anthropic" in probed:
            supports_anthropic_out = bool(anth and anth.get("endpoint_exists"))
        else:
            supports_anthropic_out = bool(supports_anthropic)

    models = openai["models"] if openai else []
    return {
        "supports_openai": supports_openai_out,
        "supports_anthropic": supports_anthropic_out,
        "models": models,
        "status": status,
        "latency_ms": latency,
        "error": error,
        "protocols": protocols,
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

    names = protocol_names_to_probe(mode="discover")
    protocols = _run_probes(base, api_key, timeout, check_path, names)
    result = _result_from_protocols(protocols, probed_names=names)
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

    names = protocol_names_to_probe(supports_openai, supports_anthropic, mode="monitor")
    protocols = []
    for name in names:
        entry = get_protocol(name)
        model_probe = entry.get("model_probe")
        if model_probe:
            protocols.append(model_probe(base, api_key, model, timeout))
    status, latency, error = _aggregate(protocols or [_protocol_result("unknown")])
    result.update(model_status=status, model_latency_ms=latency, model_error=error)
    return result


def health_check(base_url, api_key, supports_openai=False, supports_anthropic=False, timeout=15, check_model="", check_path=""):
    """Lightweight scheduled probe: connectivity only (known protocols).

    Does **not** run model_check even when check_model is set — model probing is
    reserved for classify / manual model detection so monitor traffic stays cheap.
    check_model is accepted for call-site compatibility and ignored.
    """
    try:
        base = normalize_base_url(base_url)
    except ValueError as exc:
        return _empty_result(str(exc), supports_openai, supports_anthropic)

    names = protocol_names_to_probe(supports_openai, supports_anthropic, mode="monitor")
    protocols = _run_probes(base, api_key, timeout, check_path, names)
    # When capabilities are already known, preserve supports_* even if this tick fails
    # so we do not fall back into full-protocol rediscovery (policy A).
    preserve = bool(supports_openai or supports_anthropic)
    return _result_from_protocols(
        protocols,
        supports_openai=supports_openai,
        supports_anthropic=supports_anthropic,
        probed_names=names,
        preserve_supports=preserve,
    )
