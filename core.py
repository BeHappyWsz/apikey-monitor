# -*- coding: utf-8 -*-
"""Pure parsing, probing and export helpers for apiKeyConfig."""
import json
import re
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit, urlunsplit
from version import USER_AGENT

MAX_RESPONSE_BYTES = 1024 * 1024
_URL_RE = re.compile(r"https?://[^\s\"'`,<>\]\)]+", re.IGNORECASE)
_ASSIGN_RE = re.compile(
    r"(?P<key>anthropic_base_url|openai_base_url|base_?url|api_?url|endpoint|url|"
    r"anthropic_api_key|anthropic_auth_token|openai_api_key|api_?key|secret|"
    r"authorization|token|key)\s*[:=]\s*[\"']?(?P<val>[^\s\"',;]+)", re.IGNORECASE,
)
_BEARER_RE = re.compile(r"[Bb]earer\s+([A-Za-z0-9_\-.]{16,})")
_SK_RE = re.compile(r"sk-[A-Za-z0-9_\-.]{8,}")
_LONG_RE = re.compile(r"(?<![A-Za-z0-9_\-.])[A-Za-z0-9_\-.]{40,}")
_ENDPOINT_SUFFIXES = (
    "/v1/chat/completions", "/v1/messages", "/v1/responses", "/v1/models",
    "/chat/completions", "/messages", "/responses", "/models",
)
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_AUTH_WORDS = ("auth", "api key", "api_key", "unauthorized", "forbidden", "credential", "token")


def normalize_base_url(value: str) -> str:
    """Validate and normalize an HTTP(S) base URL without destroying proxy prefixes."""
    value = str(value or "").strip()
    if not value:
        raise ValueError("base_url required")
    if _CONTROL_RE.search(value):
        raise ValueError("base_url contains control characters")
    parts = urlsplit(value)
    if parts.scheme.lower() not in ("http", "https"):
        raise ValueError("base_url must use http or https")
    if not parts.hostname:
        raise ValueError("base_url must include a valid host")
    try:
        port = parts.port
        if port is not None and not (1 <= port <= 65535):
            raise ValueError
    except ValueError:
        raise ValueError("base_url has an invalid port")
    if parts.username or parts.password:
        raise ValueError("base_url must not include credentials")
    path = re.sub(r"/{2,}", "/", parts.path or "").rstrip("/")
    low = path.lower()
    for suffix in _ENDPOINT_SUFFIXES:
        if low.endswith(suffix):
            path = path[:-len(suffix)].rstrip("/")
            break
    return urlunsplit((parts.scheme.lower(), parts.netloc, path, "", ""))


def join_api_path(base_url: str, path: str) -> str:
    """Join an API path and avoid duplicate /v1 while preserving proxy prefixes."""
    base = normalize_base_url(base_url)
    parts = urlsplit(base)
    base_path = (parts.path or "").rstrip("/")
    add = "/" + str(path or "").lstrip("/")
    if base_path.lower().endswith("/v1") and (add.lower() == "/v1" or add.lower().startswith("/v1/")):
        add = add[3:] or ""
    joined = (base_path + add) or "/"
    return urlunsplit((parts.scheme, parts.netloc, joined, "", ""))



def _normalize_import_items(data):
    """Normalize JSON backup / export payload into candidate entries."""
    if isinstance(data, dict):
        if isinstance(data.get("items"), list):
            data = data["items"]
        elif isinstance(data.get("keys"), list):
            data = data["keys"]
        else:
            data = [data]
    if not isinstance(data, list):
        return []
    out, seen = [], set()
    for item in data:
        if not isinstance(item, dict):
            continue
        base_raw = str(item.get("base_url") or item.get("url") or item.get("baseUrl") or "").strip()
        key = str(
            item.get("api_key")
            or item.get("key")
            or item.get("token")
            or item.get("auth_token")
            or item.get("apiKey")
            or ""
        ).strip()
        if not base_raw or not key:
            continue
        if "\r" in key or "\n" in key:
            continue
        try:
            base = normalize_base_url(base_raw)
        except ValueError:
            continue
        marker = (base, key)
        if marker in seen:
            continue
        seen.add(marker)
        out.append({
            "name": str(item.get("name") or "").strip(),
            "base_url": base,
            "api_key": key,
            "check_model": str(item.get("check_model") or item.get("model") or "").strip(),
            "notes": str(item.get("notes") or "").strip(),
        })
    return out


def parse_import_text(text: str):
    """Parse paste text or JSON export/backup into candidates."""
    if not text or not str(text).strip():
        return []
    raw = str(text).strip()
    if raw[0] in "[{":
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = None
        if data is not None:
            items = _normalize_import_items(data)
            if items:
                return items
    return parse_paste(raw)


def _candidate_urls(base_url, endpoint):
    urls = [join_api_path(base_url, "/v1/" + endpoint.lstrip("/")),
            join_api_path(base_url, "/" + endpoint.lstrip("/"))]
    return list(dict.fromkeys(urls))


def _clean_base(url: str) -> str:
    try:
        return normalize_base_url(url)
    except ValueError:
        return ""


def _find_keys(text: str):
    found = []
    found.extend(m.group(1) for m in _BEARER_RE.finditer(text))
    for m in _ASSIGN_RE.finditer(text):
        key, value = m.group("key").lower(), m.group("val").strip().strip("\"'")
        if "url" not in key and "endpoint" not in key and not value.lower().startswith("http"):
            found.append(value)
    found.extend(m.group(0) for m in _SK_RE.finditer(text))
    if not found:
        found.extend(m.group(0) for m in _LONG_RE.finditer(text) if not m.group(0).lower().startswith("http"))
    seen, out = set(), []
    for value in found:
        if len(value) >= 12 and value not in seen and not _CONTROL_RE.search(value):
            seen.add(value)
            out.append(value)
    return out


def parse_paste(text: str):
    if not text or not text.strip():
        return []
    entries, pending_url = [], None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        urls = [u for u in (_clean_base(v) for v in _URL_RE.findall(line)) if u]
        keys = _find_keys(line)
        line_url = urls[0] if urls else None
        if line_url and keys:
            entries.extend({"base_url": line_url, "api_key": key, "name": ""} for key in keys)
            pending_url = None
        elif line_url:
            pending_url = line_url
        elif keys and pending_url:
            entries.extend({"base_url": pending_url, "api_key": key, "name": ""} for key in keys)
            pending_url = None
    if not entries:
        urls = list(dict.fromkeys(filter(None, (_clean_base(v) for v in _URL_RE.findall(text)))))
        keys = _find_keys(text)
        if len(urls) == len(keys) and urls:
            entries.extend({"base_url": u, "api_key": k, "name": ""} for u, k in zip(urls, keys))
        elif len(urls) == 1:
            entries.extend({"base_url": urls[0], "api_key": k, "name": ""} for k in keys)
        elif len(keys) == 1:
            entries.extend({"base_url": u, "api_key": keys[0], "name": ""} for u in urls)
    seen, out = set(), []
    for item in entries:
        marker = (item["base_url"], item["api_key"])
        if marker not in seen:
            seen.add(marker)
            out.append(item)
    return out


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
    return {"protocol": name, "endpoint_exists": False, "authenticated": False,
            "status": "down", "http_status": 0, "latency_ms": None,
            "models": [], "error": "unreachable"}


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
        result.update(endpoint_exists=True, authenticated=not is_auth,
                      status="auth_error" if is_auth else "degraded",
                      error=detail or "request validation failed (400)")
    elif code and code != 404:
        result.update(endpoint_exists=True, status="degraded", error=err or f"HTTP {code}")
    elif err:
        result["error"] = err


def _probe_openai(base, api_key, timeout):
    result = _protocol_result("openai")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "User-Agent": USER_AGENT}
    for url in _candidate_urls(base, "models"):
        code, raw, ms, err = _request("GET", url, headers, None, timeout)
        _record_http(result, code, raw, ms, err)
        if code != 404 and code != 0:
            if code == 200:
                result["models"] = _parse_models(raw)
            break
    return result


def _probe_anthropic(base, api_key, timeout):
    result = _protocol_result("anthropic")
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json", "User-Agent": USER_AGENT}
    body = {"model": "claude-3-5-haiku-20241022", "max_tokens": 1, "messages": [{"role": "user", "content": "ping"}]}
    for url in _candidate_urls(base, "messages"):
        code, raw, ms, err = _request("POST", url, headers, body, timeout)
        _record_http(result, code, raw, ms, err, validation_400=True)
        if code != 404 and code != 0:
            break
    return result


def _aggregate(protocols):
    priority = ("up", "auth_error", "rate_limited", "degraded", "down")
    status = next((candidate for candidate in priority if any(p["status"] == candidate for p in protocols)), "unknown")
    relevant = [p for p in protocols if p["status"] == status]
    latency = next((p["latency_ms"] for p in relevant if p["latency_ms"] is not None), None)
    errors = [f"{p['protocol']}: {p['error']}" for p in protocols if p.get("error")]
    return status, latency, "; ".join(errors)[:300]


def classify(base_url, api_key, timeout=15, check_model=""):
    try:
        base = normalize_base_url(base_url)
    except ValueError as exc:
        return {"supports_openai": False, "supports_anthropic": False, "models": [], "status": "down",
                "latency_ms": None, "error": str(exc), "protocols": [], "model_status": "unknown",
                "model_latency_ms": None, "model_error": None}
    if not api_key:
        return {"supports_openai": False, "supports_anthropic": False, "models": [], "status": "down",
                "latency_ms": None, "error": "missing api_key", "protocols": [], "model_status": "unknown",
                "model_latency_ms": None, "model_error": None}
    protocols = [_probe_openai(base, api_key, timeout), _probe_anthropic(base, api_key, timeout)]
    status, latency, error = _aggregate(protocols)
    result = {"supports_openai": protocols[0]["endpoint_exists"],
              "supports_anthropic": protocols[1]["endpoint_exists"],
              "models": protocols[0]["models"], "status": status, "latency_ms": latency,
              "error": error, "protocols": protocols, "model_status": "unknown",
              "model_latency_ms": None, "model_error": None}
    if check_model:
        check = model_check(base, api_key, check_model,
                            result["supports_openai"], result["supports_anthropic"], timeout)
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
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "User-Agent": USER_AGENT}
        body = {"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1, "stream": False}
        probe = _protocol_result("openai")
        for url in _candidate_urls(base, "chat/completions"):
            code, raw, ms, err = _request("POST", url, headers, body, timeout)
            _record_http(probe, code, raw, ms, err, validation_400=True)
            if code not in (0, 404): break
        protocols.append(probe)
    if supports_anthropic:
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json", "User-Agent": USER_AGENT}
        body = {"model": model, "max_tokens": 1, "messages": [{"role": "user", "content": "hi"}]}
        probe = _protocol_result("anthropic")
        for url in _candidate_urls(base, "messages"):
            code, raw, ms, err = _request("POST", url, headers, body, timeout)
            _record_http(probe, code, raw, ms, err, validation_400=True)
            if code not in (0, 404): break
        protocols.append(probe)
    status, latency, error = _aggregate(protocols or [_protocol_result("unknown")])
    result.update(model_status=status, model_latency_ms=latency, model_error=error)
    return result


def health_check(base_url, api_key, supports_openai=False, supports_anthropic=False, timeout=15, check_model=""):
    try:
        base = normalize_base_url(base_url)
    except ValueError as exc:
        return {"supports_openai": supports_openai, "supports_anthropic": supports_anthropic, "models": [],
                "status": "down", "latency_ms": None, "error": str(exc), "protocols": [],
                "model_status": "unknown", "model_latency_ms": None, "model_error": None}
    protocols = []
    if supports_openai or not (supports_openai or supports_anthropic):
        protocols.append(_probe_openai(base, api_key, timeout))
    if supports_anthropic or not (supports_openai or supports_anthropic) or not any(p["status"] == "up" for p in protocols):
        protocols.append(_probe_anthropic(base, api_key, timeout))
    if not any(p["protocol"] == "openai" for p in protocols) and not any(p["status"] == "up" for p in protocols):
        protocols.append(_probe_openai(base, api_key, timeout))
    status, latency, error = _aggregate(protocols)
    openai = next((p for p in protocols if p["protocol"] == "openai"), None)
    anth = next((p for p in protocols if p["protocol"] == "anthropic"), None)
    result = {"supports_openai": openai["endpoint_exists"] if openai else supports_openai,
              "supports_anthropic": anth["endpoint_exists"] if anth else supports_anthropic,
              "models": openai["models"] if openai else [], "status": status,
              "latency_ms": latency, "error": error, "protocols": protocols,
              "model_status": "unknown", "model_latency_ms": None, "model_error": None}
    if check_model:
        result.update(model_check(base, api_key, check_model, result["supports_openai"], result["supports_anthropic"], timeout))
    return result


def _shell_quote(value):
    value = str(value or "")
    if _CONTROL_RE.search(value):
        raise ValueError("export value contains control characters")
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _ps_quote(value):
    value = str(value or "")
    if _CONTROL_RE.search(value):
        raise ValueError("export value contains control characters")
    return "'" + value.replace("'", "''") + "'"


def _env_value(value):
    value = str(value or "")
    if _CONTROL_RE.search(value):
        raise ValueError("export value contains control characters")
    if re.search(r'[\s#"\'\\]', value):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return value


def _export_entry_dict(entry):
    """Export only portable config fields (no internal status / id)."""
    base = normalize_base_url(entry.get("base_url"))
    return {
        "name": entry.get("name") or "",
        "base_url": base,
        "api_key": str(entry.get("api_key") or ""),
        "check_model": entry.get("check_model") or "",
    }


def export_config(entry: dict, fmt: str):
    base = normalize_base_url(entry.get("base_url"))
    key = str(entry.get("api_key") or "")
    fmt = str(fmt or "").lower()
    openai_base = join_api_path(base, "/v1")
    if fmt == "claude":
        return "# Claude Code (Anthropic protocol)\nexport ANTHROPIC_BASE_URL={}\nexport ANTHROPIC_AUTH_TOKEN={}\n".format(
            _shell_quote(base), _shell_quote(key))
    if fmt == "codex":
        return "# Codex CLI (OpenAI protocol)\nexport OPENAI_BASE_URL={}\nexport OPENAI_API_KEY={}\n".format(
            _shell_quote(openai_base), _shell_quote(key))
    if fmt == "env":
        return (
            f"OPENAI_BASE_URL={_env_value(openai_base)}\n"
            f"OPENAI_API_KEY={_env_value(key)}\n"
            f"ANTHROPIC_BASE_URL={_env_value(base)}\n"
            f"ANTHROPIC_AUTH_TOKEN={_env_value(key)}\n"
        )
    if fmt == "powershell":
        return (
            f"$env:OPENAI_BASE_URL = {_ps_quote(openai_base)}\n"
            f"$env:OPENAI_API_KEY = {_ps_quote(key)}\n"
            f"$env:ANTHROPIC_BASE_URL = {_ps_quote(base)}\n"
            f"$env:ANTHROPIC_AUTH_TOKEN = {_ps_quote(key)}\n"
        )
    if fmt == "json":
        return json.dumps(_export_entry_dict(entry), ensure_ascii=False, indent=2) + "\n"
    raise ValueError("unsupported export format")


def export_batch(entries, fmt: str = "json"):
    fmt = str(fmt or "json").lower()
    if fmt != "json":
        raise ValueError("batch export only supports json")
    payload = [_export_entry_dict(entry) for entry in entries]
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

