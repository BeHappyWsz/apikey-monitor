# -*- coding: utf-8 -*-
"""Config export formatters with an explicit format registry."""
import json
import re

from core.urls import _CONTROL_RE, join_api_path, normalize_base_url


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
