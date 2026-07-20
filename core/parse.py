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
_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*([\[{][\s\S]*?[\]}])\s*```", re.IGNORECASE)


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


def try_parse_fenced_json_import(text: str):
    """Accept a JSON backup embedded in explanatory Markdown or chat text."""
    out, seen = [], set()
    for block in _FENCED_JSON_RE.findall(str(text or "")):
        try:
            items = _normalize_import_items(json.loads(block))
        except json.JSONDecodeError:
            continue
        for item in items:
            marker = (item["base_url"], item["api_key"])
            if marker not in seen:
                seen.add(marker)
                out.append(item)
    return out or None


def _clean_base(url: str) -> str:
    try:
        return normalize_base_url(url)
    except ValueError:
        return ""


def _iter_key_tokens(line, allow_unlabeled_long=False):
    """Yield ``(match, value)`` for each key-like token in ``line``, in source order."""
    seen = set()
    for m in _BEARER_RE.finditer(line):
        v = m.group(1)
        if v not in seen and len(v) >= 12 and not _CONTROL_RE.search(v):
            seen.add(v)
            yield m, v
    for m in _ASSIGN_RE.finditer(line):
        key = m.group("key").lower()
        value = m.group("val").strip().strip("\"'`)]}")
        if "url" in key or "endpoint" in key or value.lower().startswith("http"):
            continue
        if not value or value in seen:
            continue
        if len(value) >= 12 and not _CONTROL_RE.search(value):
            seen.add(value)
            yield m, value
    for m in _SK_RE.finditer(line):
        v = m.group(0)
        if v not in seen:
            seen.add(v)
            yield m, v
    if allow_unlabeled_long:
        for m in _LONG_RE.finditer(line):
            v = m.group(0)
            if v in seen or v.lower().startswith("http"):
                continue
            if len(v) >= 12 and not _CONTROL_RE.search(v):
                seen.add(v)
                yield m, v


def _line_has_token(stripped):
    """Whether the line contains any URL or key-like token (long tokens count)."""
    if _URL_RE.search(stripped):
        return True
    if _BEARER_RE.search(stripped) or _SK_RE.search(stripped):
        return True
    for m in _ASSIGN_RE.finditer(stripped):
        key = m.group("key").lower()
        value = m.group("val").strip().strip("\"'`)]}")
        if not (("url" in key or "endpoint" in key) or value.lower().startswith("http")):
            return True
    if _LONG_RE.search(stripped):
        return True
    return False


def _split_paragraphs(text):
    """Group token-bearing lines into paragraphs.

    Blank lines, ``#`` comments, and lines that contain no URL or key-like
    token all act as paragraph boundaries. Plain prose interleaved between a
    URL and a token therefore breaks the pair — only physically adjacent
    token lines can form one.
    """
    paragraphs, current = [], []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or not _line_has_token(stripped):
            if current:
                paragraphs.append(current)
                current = []
        else:
            current.append(line)
    if current:
        paragraphs.append(current)
    return paragraphs


def parse_paste(text):
    """Parse free-form paste text into ``{base_url, api_key, name}`` candidates.

    Order-invariant, section-aware, adjacent pairing:

    * Text is split into paragraphs by blank lines (or `#` comments). A pair is
      only formed inside the same paragraph — empty lines are the only natural
      "distance" boundary, so chat text long random tokens don't grab URLs.
    * Within a paragraph, URL and key tokens are collected with their column
      offset and merged into one sorted stream.
    * Adjacent tokens in the stream are paired off: only ``(url, key)`` or
      ``(key, url)`` yields a candidate. Same-kind neighbours are skipped, so
      ``url, url, key`` produces one pair (the trailing ``key`` is dropped as
      unpaired) and ``key, key, url`` likewise produces one pair. This keeps
      the pairing strictly "next to each other" regardless of which one
      appeared first.
    """
    if not text or not text.strip():
        return []

    entries = []
    for paragraph_lines in _split_paragraphs(text):
        # Compute the start column of each line so positions stay comparable
        # when multiple lines live in one paragraph.
        line_offsets = []
        offset = 0
        for line in paragraph_lines:
            line_offsets.append(offset)
            offset += len(line) + 1  # +1 for newline

        url_seen = False
        tokens = []  # (pos, kind, value)
        for line_idx, line in enumerate(paragraph_lines):
            base = line_offsets[line_idx]
            for um in _URL_RE.finditer(line):
                raw = um.group(0).rstrip(".,;:!?)]}")
                cleaned = _clean_base(raw)
                if cleaned:
                    tokens.append((base + um.start(), "url", cleaned))
                    url_seen = True
            for km, value in _iter_key_tokens(line, allow_unlabeled_long=url_seen):
                tokens.append((base + km.start(), "key", value))

        tokens.sort(key=lambda t: t[0])
        # Adjacent pairing; order-independent; same-kind neighbours are skipped.
        i = 0
        while i + 1 < len(tokens):
            a, b = tokens[i], tokens[i + 1]
            if {a[1], b[1]} == {"url", "key"}:
                url_value = a[2] if a[1] == "url" else b[2]
                key_value = a[2] if a[1] == "key" else b[2]
                entries.append({"base_url": url_value, "api_key": key_value, "name": ""})
                i += 2
            else:
                i += 1

    seen, out = set(), []
    for item in entries:
        marker = (item["base_url"], item["api_key"])
        if marker not in seen:
            seen.add(marker)
            out.append(item)
    return out


IMPORTERS = (
    try_parse_json_import,
    try_parse_fenced_json_import,
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
