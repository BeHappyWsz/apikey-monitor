# -*- coding: utf-8 -*-
"""Minimal HTTP client helpers for protocol probes."""
import json
import time
import urllib.error
import urllib.request

MAX_RESPONSE_BYTES = 1024 * 1024


def _read_limited(stream, limit=MAX_RESPONSE_BYTES):
    raw = stream.read(limit + 1)
    return raw[:limit]


def _request(method, url, headers, body=None, timeout=15):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = _read_limited(response).decode("utf-8", "replace")
            return response.status, raw, int((time.monotonic() - started) * 1000), None
    except urllib.error.HTTPError as exc:
        try:
            raw = _read_limited(exc).decode("utf-8", "replace")
        except Exception:
            raw = ""
        return exc.code, raw, int((time.monotonic() - started) * 1000), f"HTTP {exc.code}"
    except Exception as exc:
        return 0, "", int((time.monotonic() - started) * 1000), (str(exc)[:200] or "request error")
