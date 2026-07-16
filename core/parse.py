# -*- coding: utf-8 -*-
"""Paste and JSON import parsers with a small importer registry."""
import json
import re

from core.urls import _CONTROL_RE, normalize_base_url

_URL_RE = re.compile(r"https?://[^\s\"'`,<>\]\)]+", re.IGNORECASE)
_ASSIGN_RE = re.compile(
    r"(?P<key>anthropic_base_url|openai_base_url|base_?url|api_?url|endpoint|url|"
    r"anthropic_api_key|anthropic_auth_token|openai_api_key|api_?key|secret|"
    r"authorization|token|key)\s*[:=]\s*[\"']?(?P<val>[^\s\"',;]+)", re.IGNORECASE,
)
_BEARER_RE = re.compile(r"[Bb]earer\s+([A-Za-z0-9_\-.]{16,})")
_SK_RE = re.compile(r"sk-[A-Za-z0-9_\-.]{8,}")
_LONG_RE = re.compile(r"(?<![A-Za-z0-9_\-.])[A-Za-z0-9_\-.]{40,}")


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
            "check_path": str(item.get("check_path") or "").strip(),
            "notes": str(item.get("notes") or "").strip(),
        })
    return out


def try_parse_json_import(text: str):
    """Return candidates if text is JSON export/backup; otherwise None to fall through."""
    raw = str(text or "").strip()
    if not raw or raw[0] not in "[{":
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    items = _normalize_import_items(data)
    if items:
        return items
    return None


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


IMPORTERS = (
    try_parse_json_import,
    parse_paste,
)


def parse_import_text(text: str):
    """Parse paste text or JSON export/backup into candidates via IMPORTERS registry."""
    if not text or not str(text).strip():
        return []
    raw = str(text).strip()
    for importer in IMPORTERS:
        if importer is parse_paste:
            return parse_paste(raw)
        result = importer(raw)
        if result is not None:
            return result
    return []
