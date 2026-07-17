# -*- coding: utf-8 -*-
"""Config export formatters with an explicit format registry."""
import json
import re

from core.urls import _CONTROL_RE, join_api_path, normalize_base_url, normalize_check_path

SCHEMA_VERSION = 1
SYNC_APP = "apikey-monitor"


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
        "check_path": entry.get("check_path") or "",
    }


def _fmt_claude(entry, base, key, openai_base):
    return (
        "# Claude Code (Anthropic protocol)\n"
        "export ANTHROPIC_BASE_URL={}\n"
        "export ANTHROPIC_AUTH_TOKEN={}\n"
    ).format(_shell_quote(base), _shell_quote(key))


def _fmt_codex(entry, base, key, openai_base):
    return (
        "# Codex CLI (OpenAI protocol)\n"
        "export OPENAI_BASE_URL={}\n"
        "export OPENAI_API_KEY={}\n"
    ).format(_shell_quote(openai_base), _shell_quote(key))


def _fmt_env(entry, base, key, openai_base):
    return (
        f"OPENAI_BASE_URL={_env_value(openai_base)}\n"
        f"OPENAI_API_KEY={_env_value(key)}\n"
        f"ANTHROPIC_BASE_URL={_env_value(base)}\n"
        f"ANTHROPIC_AUTH_TOKEN={_env_value(key)}\n"
    )


def _fmt_powershell(entry, base, key, openai_base):
    return (
        f"$env:OPENAI_BASE_URL = {_ps_quote(openai_base)}\n"
        f"$env:OPENAI_API_KEY = {_ps_quote(key)}\n"
        f"$env:ANTHROPIC_BASE_URL = {_ps_quote(base)}\n"
        f"$env:ANTHROPIC_AUTH_TOKEN = {_ps_quote(key)}\n"
    )


def _fmt_json(entry, base, key, openai_base):
    return json.dumps(_export_entry_dict(entry), ensure_ascii=False, indent=2) + "\n"


EXPORT_FORMATS = {
    "claude": _fmt_claude,
    "codex": _fmt_codex,
    "env": _fmt_env,
    "powershell": _fmt_powershell,
    "json": _fmt_json,
}


def list_export_formats():
    return sorted(EXPORT_FORMATS.keys())


def export_config(entry: dict, fmt: str):
    base = normalize_base_url(entry.get("base_url"))
    key = str(entry.get("api_key") or "")
    fmt = str(fmt or "").lower()
    openai_base = join_api_path(base, "/v1")
    formatter = EXPORT_FORMATS.get(fmt)
    if formatter is None:
        raise ValueError("unsupported export format")
    return formatter(entry, base, key, openai_base)


def export_batch(entries, fmt: str = "json"):
    fmt = str(fmt or "json").lower()
    if fmt != "json":
        raise ValueError("batch export only supports json")
    payload = [_export_entry_dict(entry) for entry in entries]
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def build_sync_payload(entries, exported_at):
    """Versioned envelope used for cloud sync (superset of the bare backup array)."""
    return {
        "app": SYNC_APP,
        "schema": SCHEMA_VERSION,
        "exported_at": int(exported_at),
        "keys": [_export_entry_dict(entry) for entry in entries],
    }


def dumps_sync_payload(entries, exported_at):
    return json.dumps(build_sync_payload(entries, exported_at), ensure_ascii=False, indent=2) + "\n"


def _entry_keys(data):
    """Return the list of key dicts from an envelope / array / single object."""
    if isinstance(data, dict):
        keys = data.get("keys")
        if isinstance(keys, list):
            return keys
        if "base_url" in data or "api_key" in data:
            return [data]
        return []
    if isinstance(data, list):
        return data
    return []


def parse_sync_payload(text):
    """Parse a sync/backup blob into a list of normalized portable key dicts.

    Accepts: envelope ``{keys:[...]}``, a bare JSON array, or a single object.
    Entries without base_url+api_key are dropped; invalid base_url/check_path
    are normalized leniently (bad check_path cleared rather than dropping).
    """
    if isinstance(text, (bytes, bytearray)):
        text = text.decode("utf-8", "replace")
    data = json.loads(text)
    out = []
    for item in _entry_keys(data):
        if not isinstance(item, dict):
            continue
        base = str(item.get("base_url") or "").strip()
        api_key = str(item.get("api_key") or "")
        if not base or not api_key:
            continue
        try:
            base = normalize_base_url(base)
        except ValueError:
            continue
        try:
            check_path = normalize_check_path(item.get("check_path"))
        except ValueError:
            check_path = ""
        out.append({
            "name": str(item.get("name") or "")[:200],
            "base_url": base,
            "api_key": api_key,
            "check_model": str(item.get("check_model") or "")[:200],
            "check_path": check_path,
        })
    return out
