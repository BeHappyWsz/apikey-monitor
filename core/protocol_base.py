# -*- coding: utf-8 -*-
"""Shared protocol probe result shaping."""
import json
import re

# Strict model-verification budget. Reasoning models often spend tokens on
# thinking before any visible content; keep modest for cost but above a few
# completion tokens (previous value of 3 caused false negatives).
MODEL_PROBE_MAX_TOKENS = 32

_AUTH_WORDS = ("auth", "api key", "api_key", "unauthorized", "forbidden", "credential", "token")
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
_TRUNCATED_FINISH_REASONS = frozenset({"length", "max_tokens"})


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
    reporting success. Keep the validation deliberately small and protocol
    specific so it proves that the requested chat/messages operation produced
    usable text without coupling the monitor to provider-specific optional fields.
    """
    return model_response_evidence(protocol, raw).get("error") or ""


def model_response_evidence(protocol, raw):
    """Inspect a model response body and return structured usability evidence.

    Returns:
      {
        "ok": bool,
        "error": str,            # empty when ok
        "visible_text": bool,    # non-think final answer present
        "reasoning_only": bool,  # only reasoning / think blocks
        "truncated": bool,       # finish/stop reason indicates token budget hit
      }
    """
    empty = {
        "ok": False,
        "error": "",
        "visible_text": False,
        "reasoning_only": False,
        "truncated": False,
    }
    try:
        payload = json.loads(raw)
    except Exception:
        empty["error"] = f"invalid {protocol} model response JSON"
        return empty
    if protocol == "openai":
        return _evidence_openai_chat(payload)
    if protocol == "openai_responses":
        return _evidence_openai_responses(payload)
    if protocol == "anthropic":
        return _evidence_anthropic(payload)
    empty["error"] = "unsupported strict model verification protocol"
    return empty


def _evidence_result(visible_text=False, reasoning_only=False, truncated=False, error=""):
    ok = not error and (visible_text or reasoning_only)
    return {
        "ok": ok,
        "error": "" if ok else (error or "invalid model response"),
        "visible_text": bool(visible_text),
        "reasoning_only": bool(reasoning_only) and not bool(visible_text),
        "truncated": bool(truncated),
    }


def _is_truncated_reason(value):
    if value is None:
        return False
    return str(value).strip().lower() in _TRUNCATED_FINISH_REASONS


def _content_as_text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        parts = []
        for key in ("text", "content"):
            text = _content_as_text(value.get(key))
            if text:
                parts.append(text)
        return "\n".join(parts)
    if isinstance(value, list):
        parts = []
        for item in value:
            text = _content_as_text(item)
            if text:
                parts.append(text)
        return "\n".join(parts)
    return ""


def _strip_think_blocks(text):
    return _THINK_BLOCK_RE.sub("", text or "").strip()


def _has_think_blocks(text):
    return bool(_THINK_BLOCK_RE.search(text or ""))


def _message_text_flags(message):
    """Return (visible_text, has_reasoning) for an OpenAI-style message object."""
    if not isinstance(message, dict):
        return False, False
    content_text = _content_as_text(message.get("content"))
    visible = bool(_strip_think_blocks(content_text))
    reasoning = _has_think_blocks(content_text)
    for key in ("reasoning", "reasoning_content", "thinking"):
        value = message.get(key)
        if isinstance(value, str) and value.strip():
            reasoning = True
            break
    return visible, reasoning


def _evidence_openai_chat(payload):
    choices = payload.get("choices") if isinstance(payload, dict) else None
    if not isinstance(choices, list) or not choices:
        return _evidence_result(error="invalid OpenAI completion response")

    saw_truncated_empty = False
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        truncated = _is_truncated_reason(choice.get("finish_reason"))
        visible, reasoning = _message_text_flags(choice.get("message"))
        if visible:
            return _evidence_result(visible_text=True, truncated=truncated)
        if reasoning:
            # Reasoning-only is still proof the model path works; keep accepted.
            return _evidence_result(reasoning_only=True, truncated=truncated)
        if truncated:
            saw_truncated_empty = True
    if saw_truncated_empty:
        return _evidence_result(truncated=True, error="truncated completion (max_tokens)")
    return _evidence_result(error="invalid OpenAI completion response")


def _responses_incomplete_truncated(payload):
    if not isinstance(payload, dict):
        return False
    status = str(payload.get("status") or "").strip().lower()
    if status != "incomplete":
        return False
    details = payload.get("incomplete_details")
    if isinstance(details, dict) and details.get("reason") is not None:
        return _is_truncated_reason(details.get("reason"))
    # Incomplete without a more specific reason is treated as budget pressure.
    return True


def _evidence_openai_responses(payload):
    if not isinstance(payload, dict):
        return _evidence_result(error="invalid OpenAI responses response")
    truncated = _responses_incomplete_truncated(payload)

    chunks = []
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        chunks.append(output_text)

    output = payload.get("output")
    has_item_reasoning = False
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            text = _content_as_text(item.get("content"))
            if text:
                chunks.append(text)
            for key in ("reasoning", "summary"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    has_item_reasoning = True
                    chunks.append(value)

    joined = "\n".join(chunks)
    visible = bool(_strip_think_blocks(joined))
    reasoning = has_item_reasoning or _has_think_blocks(joined)
    if visible:
        return _evidence_result(visible_text=True, truncated=truncated)
    if reasoning:
        return _evidence_result(reasoning_only=True, truncated=truncated)
    if truncated:
        return _evidence_result(truncated=True, error="truncated completion (max_tokens)")
    return _evidence_result(error="invalid OpenAI responses response")


def _evidence_anthropic(payload):
    if not isinstance(payload, dict):
        return _evidence_result(error="invalid Anthropic message response")
    blocks = payload.get("content")
    truncated = _is_truncated_reason(payload.get("stop_reason"))
    if not isinstance(blocks, list):
        if truncated:
            return _evidence_result(truncated=True, error="truncated completion (max_tokens)")
        return _evidence_result(error="invalid Anthropic message response")

    visible_parts = []
    reasoning = False
    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type") or "").strip().lower()
        if block_type == "text":
            text = block.get("text")
            if isinstance(text, str) and text.strip():
                visible_parts.append(text)
                if _has_think_blocks(text):
                    reasoning = True
        elif block_type in {"thinking", "redacted_thinking", "reasoning"}:
            if any(
                isinstance(block.get(key), str) and block.get(key).strip()
                for key in ("thinking", "text", "reasoning")
            ):
                reasoning = True

    joined = "\n".join(visible_parts)
    visible = bool(_strip_think_blocks(joined))
    if not reasoning and _has_think_blocks(joined):
        reasoning = True
    if visible:
        return _evidence_result(visible_text=True, truncated=truncated)
    if reasoning:
        return _evidence_result(reasoning_only=True, truncated=truncated)
    if truncated:
        return _evidence_result(truncated=True, error="truncated completion (max_tokens)")
    return _evidence_result(error="invalid Anthropic message response")


def _openai_message_has_text(message):
    """True when chat message has usable content or reasoning-only text."""
    visible, reasoning = _message_text_flags(message)
    return visible or reasoning


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