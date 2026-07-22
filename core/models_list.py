# -*- coding: utf-8 -*-
"""List remote models for a key (OpenAI-compatible /models first)."""
from core.protocols import openai as openai_proto
from core.urls import normalize_base_url


def list_remote_models(base_url, api_key, supports_openai=True, supports_anthropic=False, timeout=15, check_path=""):
    """Fetch provider model ids. Prefer OpenAI-compatible GET /models."""
    base = normalize_base_url(base_url)
    models = []
    error = ""
    # OpenAI-compatible listing works for most gateways even when Anthropic is also supported.
    if supports_openai or not supports_anthropic:
        result = openai_proto.probe(base, api_key, timeout, check_path or "")
        if result.get("status") == "up" and result.get("models"):
            models = list(result.get("models") or [])
        elif result.get("error"):
            error = str(result.get("error") or "")
        elif result.get("http_status") not in (None, 0, 200):
            error = f"HTTP {result.get('http_status')}"
    # Deduplicate preserve order
    out = []
    seen = set()
    for model in models:
        name = str(model or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return {"models": out[:500], "count": len(out), "error": error if not out else ""}
