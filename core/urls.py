# -*- coding: utf-8 -*-
"""URL normalization helpers for API bases."""
import re
from urllib.parse import urlsplit, urlunsplit

_ENDPOINT_SUFFIXES = (
    "/v1/chat/completions", "/v1/messages", "/v1/responses", "/v1/models",
    "/chat/completions", "/messages", "/responses", "/models",
)
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


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


def normalize_check_path(value: str) -> str:
    """Validate optional relative check path (empty = default endpoints).

    Relative-only: no scheme/host/query/fragment. Stored with a leading slash.
    """
    value = str(value or "").strip()
    if not value:
        return ""
    if _CONTROL_RE.search(value):
        raise ValueError("check_path contains control characters")
    if len(value) > 256:
        raise ValueError("check_path is too long")
    low = value.lower()
    if "://" in value or low.startswith("http:") or low.startswith("https:"):
        raise ValueError("check_path must be relative (no scheme)")
    if value.startswith("//"):
        raise ValueError("check_path must be relative (no host)")
    if "?" in value or "#" in value:
        raise ValueError("check_path must not include query or fragment")
    if "\\" in value:
        raise ValueError("check_path must use forward slashes")
    if re.match(r"^[a-zA-Z]:", value):
        raise ValueError("check_path must be a URL path")
    path = value if value.startswith("/") else "/" + value
    path = re.sub(r"/{2,}", "/", path)
    return path


def candidate_urls(base_url, endpoint):
    """Return unique candidate absolute URLs for an endpoint under base_url."""
    urls = [
        join_api_path(base_url, "/v1/" + endpoint.lstrip("/")),
        join_api_path(base_url, "/" + endpoint.lstrip("/")),
    ]
    return list(dict.fromkeys(urls))


def probe_urls(base_url, endpoint, check_path=""):
    """URLs to try for a protocol probe; custom relative path overrides defaults."""
    custom = normalize_check_path(check_path)
    if custom:
        return [join_api_path(base_url, custom)]
    return candidate_urls(base_url, endpoint)
