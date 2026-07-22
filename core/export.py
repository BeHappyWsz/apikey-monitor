# -*- coding: utf-8 -*-
"""Config export formatters with an explicit format registry."""
import base64
import json
import re
from urllib.parse import quote, urlencode, urlsplit

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


def _reject_control(value, label="export value"):
    value = str(value or "")
    if _CONTROL_RE.search(value):
        raise ValueError(f"{label} contains control characters")
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
        "tags": entry.get("tags") or "",
    }


def display_name(entry, base=None):
    """Human-readable provider name for CCSwitch import.

    When ``check_model`` is set, append it so multiple providers with the same
    gateway label stay distinguishable in CC Switch (e.g. ``Demo · gpt-4o``).
    """
    name = str(entry.get("name") or "").strip()
    if not name:
        if base is None:
            base = normalize_base_url(entry.get("base_url"))
        name = urlsplit(base).hostname or "provider"
    name = _reject_control(name, "name")
    model = str(entry.get("check_model") or "").strip()
    if model:
        model = _reject_control(model, "check_model")
        suffix = f" · {model}"
        if not name.endswith(suffix) and name != model and not name.endswith(model):
            name = f"{name}{suffix}"
    return name


def provider_slug(entry, base=None):
    """TOML-safe model_providers.<slug> identifier (includes model when set)."""
    raw = display_name(entry, base)
    slug = re.sub(r"[^a-z0-9_]+", "_", raw.lower())
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug or "custom"


def claude_endpoint(base_url):
    """Claude/CCSwitch endpoint: base + /anthropic (no double suffix)."""
    base = normalize_base_url(base_url)
    path = (urlsplit(base).path or "").rstrip("/")
    if path.lower().endswith("/anthropic"):
        return base
    return join_api_path(base, "/anthropic")


def codex_endpoint(base_url):
    """Codex/CCSwitch endpoint: base + /v1 (join_api_path dedupes /v1)."""
    return join_api_path(normalize_base_url(base_url), "/v1")


def _check_model(entry):
    model = str(entry.get("check_model") or "").strip()
    if not model:
        return ""
    return _reject_control(model, "check_model")


def _codex_wire_api(entry):
    adapter = str(entry.get("model_probe_adapter") or "").strip()
    if adapter == "openai_responses":
        return "responses"
    return "chat"


def _toml_escape(value):
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _codex_config_toml(entry, base, key):
    endpoint = codex_endpoint(base)
    slug = provider_slug(entry, base)
    name = display_name(entry, base)
    wire = _codex_wire_api(entry)
    lines = [
        f"[model_providers.{slug}]",
        f'name = "{_toml_escape(name)}"',
        f'base_url = "{_toml_escape(endpoint)}"',
        f'wire_api = "{wire}"',
    ]
    model = _check_model(entry)
    if model:
        lines.extend(["", "[general]", f'model = "{_toml_escape(model)}"'])
    return "\n".join(lines) + "\n"


def _codex_paste_payload(entry, base, key):
    _reject_control(key, "api_key")
    return {
        "auth": {"OPENAI_API_KEY": key},
        "config": _codex_config_toml(entry, base, key).rstrip("\n"),
    }


def _claude_env_payload(entry, base, key):
    _reject_control(key, "api_key")
    env = {
        "ANTHROPIC_AUTH_TOKEN": key,
        "ANTHROPIC_BASE_URL": claude_endpoint(base),
    }
    model = _check_model(entry)
    if model:
        env["ANTHROPIC_MODEL"] = model
    return {"env": env}


def _fmt_claude(entry, base, key, openai_base):
    return json.dumps(_claude_env_payload(entry, base, key), ensure_ascii=False, indent=2) + "\n"


def _fmt_codex(entry, base, key, openai_base):
    return json.dumps(_codex_paste_payload(entry, base, key), ensure_ascii=False, indent=2) + "\n"


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


def build_ccswitch_deeplink(entry: dict, app: str) -> str:
    """Build a ccswitch:// deep link for one-click provider import.

    Claude uses URL params (name/endpoint/apiKey[/model]).
    Codex uses configFormat=json + Base64 config (includes wire_api).
    """
    app = str(app or "").lower().strip()
    if app not in ("claude", "codex"):
        raise ValueError("unsupported ccswitch app")
    base = normalize_base_url(entry.get("base_url"))
    key = _reject_control(str(entry.get("api_key") or ""), "api_key")
    name = display_name(entry, base)
    model = _check_model(entry)

    if app == "claude":
        endpoint = claude_endpoint(base)
        params = [
            ("resource", "provider"),
            ("app", "claude"),
            ("name", name),
            ("endpoint", endpoint),
            ("apiKey", key),
        ]
        if model:
            params.append(("model", model))
        # quote_via keeps keys readable; encode values safely
        query = urlencode(params, quote_via=quote)
        return f"ccswitch://v1/import?{query}"

    endpoint = codex_endpoint(base)
    payload = _codex_paste_payload(entry, base, key)
    config_b64 = base64.b64encode(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    params = [
        ("resource", "provider"),
        ("app", "codex"),
        ("name", name),
        ("configFormat", "json"),
        ("config", config_b64),
        ("endpoint", endpoint),
        ("apiKey", key),
    ]
    if model:
        params.append(("model", model))
    query = urlencode(params, quote_via=quote)
    return f"ccswitch://v1/import?{query}"


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
        base_url = item.get("base_url")
        api_key = item.get("api_key")
        if not base_url or not api_key:
            continue
        try:
            base = normalize_base_url(base_url)
        except ValueError:
            continue
        try:
            check_path = normalize_check_path(item.get("check_path") or "")
        except ValueError:
            check_path = ""
        out.append({
            "name": str(item.get("name") or "")[:200],
            "base_url": base,
            "api_key": str(api_key or ""),
            "check_model": str(item.get("check_model") or "")[:200],
            "check_path": check_path,
            "tags": str(item.get("tags") or "")[:640],
        })
    return out
