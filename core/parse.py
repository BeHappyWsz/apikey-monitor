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
# Plain short identifiers (e.g. ``gpt``, ``grok-3``, ``claude_opus``) that act
# as provider/alias labels. They are not matched by any url/key regex above,
# so they survive only as candidate ``name`` tokens once the url/key span
# pass has claimed the surrounding characters.
_NAME_TOKEN_RE = re.compile(r"([A-Za-z][A-Za-z0-9_-]{1,11})")
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
            "tags": str(item.get("tags") or "").strip(),
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


def _iter_tokens(line, allow_unlabeled_long=False):
    """Yield ``(pos, kind, value)`` for each token in ``line``.

    ``kind`` is one of ``"url"``, ``"key"`` and ``"name"``. URL and key spans
    are scanned first so that the subsequent name pass never reads into a span
    already claimed by a longer regex match (e.g. ``https`` inside a URL is
    not also a name).
    """
    claimed_spans = []

    # URLs (caller hands the raw match; the surrounding punctuation stripper
    # lives there so it can also peek at base-urls without shaping them).
    for m in _URL_RE.finditer(line):
        cleaned = _clean_base(m.group(0).rstrip(".,;:!?)]}"))
        if cleaned:
            yield (m.start(), "url", cleaned)
            claimed_spans.append((m.start(), m.end()))

    # Bearer tokens, sk- prefixed keys, and assignment-shaped keys never
    # overlap a URL because of their explicit leading punctuation.
    def _emit_key(m_start, m_end, value):
        yield (m_start, "key", value)
        claimed_spans.append((m_start, m_end))

    for m in _BEARER_RE.finditer(line):
        v = m.group(1)
        if not _CONTROL_RE.search(v):
            yield (m.start(), "key", v)
            claimed_spans.append((m.start(), m.end()))

    for m in _ASSIGN_RE.finditer(line):
        key_name = m.group("key").lower()
        value = m.group("val").strip().strip("\"'`)]}")
        # Reserve the whole "key=value" range up front so name-token
        # scanning does not slice the assignment prefix into fragments.
        claimed_spans.append((m.start(), m.end()))
        if "url" in key_name or "endpoint" in key_name:
            if value and not _CONTROL_RE.search(value):
                cleaned = _clean_base(value.rstrip(".,;:!?)]}"))
                if cleaned:
                    yield (m.start(), "url", cleaned)
            continue
        if value.lower().startswith("http"):
            cleaned = _clean_base(value.rstrip(".,;:!?)]}"))
            if cleaned:
                yield (m.start(), "url", cleaned)
            continue
        if not value or _CONTROL_RE.search(value):
            continue
        yield (m.start(), "key", value)

    for m in _SK_RE.finditer(line):
        yield (m.start(), "key", m.group(0))
        claimed_spans.append((m.start(), m.end()))

    # Unlabeled long tokens only count once a URL has appeared earlier in
    # the same paragraph — they would otherwise drag chat noise into the
    # pair list.
    if allow_unlabeled_long:
        for m in _LONG_RE.finditer(line):
            yield (m.start(), "key", m.group(0))
            claimed_spans.append((m.start(), m.end()))

    # Names — short identifiers (2..12 chars) sitting outside any url/key
    # span. They give typical "gpt / sk-… / grok / sk-… / https://…"
    # copy-paste blocks a usable ``name`` field for each key.
    for nm in _NAME_TOKEN_RE.finditer(line):
        s, e = nm.start(), nm.end()
        if any(cs <= s and e <= ce for cs, ce in claimed_spans):
            continue
        yield (s, "name", nm.group(0))


def _line_has_token(stripped):
    """Whether the line carries any URL/key/name-like token."""
    if _URL_RE.search(stripped):
        return True
    if _BEARER_RE.search(stripped) or _SK_RE.search(stripped):
        return True
    for m in _ASSIGN_RE.finditer(stripped):
        key_name = m.group("key").lower()
        value = m.group("val").strip().strip("\"'`)]}")
        if not (("url" in key_name or "endpoint" in key_name) or value.lower().startswith("http")):
            return True
    if _LONG_RE.search(stripped):
        return True
    if _NAME_TOKEN_RE.search(stripped):
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

    Order-invariant, section-aware, forward matching:

    * Text is split into paragraphs by blank lines, ``#`` comments, or any
      line that carries no URL / key / name token. Plain prose interleaved
      between a URL and a key therefore breaks the pair — only tokens in the
      same paragraph may form a candidate.
    * Within a paragraph, URL / key / name tokens are merged into one stream
      sorted by column offset.
    * Each ``key`` token is paired with the **next URL that appears after
      it** in the stream. This naturally supports both:
        - one URL shared by many keys (``3 keys + 1 url`` gives 3 pairs),
        - one URL per key (``url_a url_b`` interleaved still resolves).
      Same-kind neighbours (``key, key`` or ``url, url``) are ignored.
    * Each emitted key carries the closest ``name`` token preceding it in
      the paragraph, so a copy like ``gpt / sk-… / grok / sk-… / https``
      produces entries with ``name="gpt"`` and ``name="grok"``.
    """
    if not text or not text.strip():
        return []

    entries = []
    for paragraph_lines in _split_paragraphs(text):
        line_offsets = []
        offset = 0
        for line in paragraph_lines:
            line_offsets.append(offset)
            offset += len(line) + 1  # +1 for newline

        # Unlabeled long tokens only count once the whole paragraph has
        # touched a URL; using a paragraph-level flag avoids the per-line
        # race where a URL and the surrounding text sit on the same line.
        paragraph_has_url = any(_URL_RE.search(line) for line in paragraph_lines)
        tokens = []
        for line_idx, line in enumerate(paragraph_lines):
            base = line_offsets[line_idx]
            for pos, kind, value in _iter_tokens(line, allow_unlabeled_long=paragraph_has_url):
                tokens.append((base + pos, kind, value))

        if not tokens:
            continue
        tokens.sort(key=lambda t: t[0])

        # Index the closest url on each side of every position. A key token
        # picks whichever neighbour is nearer; ties go to the preceding url
        # so classic `OPENAI_BASE_URL=... \n OPENAI_API_KEY=...` patterns
        # still resolve. This combines the two complementary semantics:
        #   - many keys share one URL (multiple keys, single trailing url
        #     gives every key that url because they're all "closer" to it
        #     than to nothing else);
        #   - many URLs serve many keys (interleaved ``key url key url``
        #     pairs each key with the nearest neighbouring URL).
        before_url = {}
        last_pos, last_value = None, None
        for pos, kind, value in tokens:
            before_url[pos] = (last_pos, last_value)
            if kind == "url":
                last_pos, last_value = pos, value
        after_url = {}
        last_pos, last_value = None, None
        for pos, kind, value in reversed(tokens):
            after_url[pos] = (last_pos, last_value)
            if kind == "url":
                last_pos, last_value = pos, value

        # Pre-compute the closest preceding name token so each key inherits
        # the nearest label even when many names appear together.
        running_name = ""
        name_by_pos = {}
        for pos, kind, value in tokens:
            name_by_pos[pos] = running_name
            if kind == "name":
                running_name = value

        for pos, kind, value in tokens:
            if kind != "key":
                continue
            b_pos, b_value = before_url[pos]
            a_pos, a_value = after_url[pos]
            b_distance = pos - b_pos if b_pos is not None else None
            a_distance = a_pos - pos if a_pos is not None else None
            chosen = None
            if b_distance is not None and (a_distance is None or b_distance <= a_distance):
                chosen = b_value
            elif a_distance is not None:
                chosen = a_value
            if chosen is None:
                continue
            entries.append({
                "base_url": chosen,
                "api_key": value,
                "name": name_by_pos[pos],
            })

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
