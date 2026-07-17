# -*- coding: utf-8 -*-
import re
import core

MAX_JSON_BODY = 256 * 1024
MAX_IMPORT_BODY = 2 * 1024 * 1024
MAX_BATCH_ITEMS = 1000
MAX_IDS = 1000
DEFAULT_WEBDAV_FILE = "backup.json"


def normalize_int(value, default=None, min_value=None, max_value=None):
    if value in (None, ""):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError("invalid integer")
    if min_value is not None and number < min_value:
        raise ValueError(f"value must be at least {min_value}")
    if max_value is not None and number > max_value:
        raise ValueError(f"value must be at most {max_value}")
    return number


def key_payload(data, partial=False):
    if not isinstance(data, dict):
        raise ValueError("json object required")
    out = {}
    for field in ("name", "base_url", "api_key", "notes", "check_model", "check_path"):
        if field in data:
            value = str(data.get(field) or "").strip()
            if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", value):
                raise ValueError(f"{field} contains control characters")
            out[field] = value
    if not partial or "base_url" in out:
        out["base_url"] = core.normalize_base_url(out.get("base_url"))
    if "check_path" in out:
        out["check_path"] = core.normalize_check_path(out.get("check_path"))
    if "api_key" in out:
        if not out.get("api_key"):
            if partial:
                out.pop("api_key", None)
            else:
                raise ValueError("api_key required")
        elif "\r" in out["api_key"] or "\n" in out["api_key"]:
            raise ValueError("api_key contains control characters")
    elif not partial:
        raise ValueError("api_key required")
    if "monitor_enabled" in data:
        out["monitor_enabled"] = 1 if str(data.get("monitor_enabled")).lower() in ("1", "true") else 0
    if "interval_sec" in data:
        out["interval_sec"] = normalize_int(data.get("interval_sec"), None, 30, 86400)
    if "check_after_save" in data:
        out["check_after_save"] = bool(data.get("check_after_save"))
    return out



def _normalize_ui_refresh(value, default=15):
    """UI list poll interval seconds. 0 disables auto refresh; else 3-3600."""
    number = normalize_int(value, default, 0, 3600)
    if number is None:
        number = default
    if number != 0 and number < 3:
        raise ValueError("ui_refresh_interval_sec must be 0 or at least 3")
    return number


def settings_payload(data, current=None):
    if not isinstance(data, dict):
        raise ValueError("json object required")
    current = current or {}
    host = str(data.get("server_host", current.get("server_host", "127.0.0.1"))).strip()
    if host not in ("127.0.0.1", "localhost", "0.0.0.0"):
        raise ValueError("unsupported server_host")
    return {
        "server_host": host,
        "server_port": str(normalize_int(data.get("server_port", current.get("server_port", 7878)), 7878, 1024, 65535)),
        "global_monitor_enabled": "1" if str(data.get("global_monitor_enabled", current.get("global_monitor_enabled", "1"))).lower() in ("1", "true") else "0",
        "global_interval_sec": str(normalize_int(data.get("global_interval_sec", current.get("global_interval_sec", 300)), 300, 30, 86400)),
        "down_recheck_interval_sec": str(normalize_int(data.get("down_recheck_interval_sec", current.get("down_recheck_interval_sec", 120)), 120, 30, 86400)),
        "concurrency": str(normalize_int(data.get("concurrency", current.get("concurrency", 8)), 8, 1, 32)),
        "request_timeout_sec": str(normalize_int(data.get("request_timeout_sec", current.get("request_timeout_sec", 15)), 15, 3, 120)),
        "auto_classify_on_add": "1" if str(data.get("auto_classify_on_add", current.get("auto_classify_on_add", "1"))).lower() in ("1", "true") else "0",
        "ui_refresh_interval_sec": str(_normalize_ui_refresh(data.get("ui_refresh_interval_sec", current.get("ui_refresh_interval_sec", 15)))),
    }


def ids_payload(data):
    ids = data.get("ids") if isinstance(data, dict) else None
    if not isinstance(ids, list):
        raise ValueError("ids list required")
    if len(ids) > MAX_IDS:
        raise ValueError(f"too many ids (max {MAX_IDS})")
    out = []
    for value in ids:
        try:
            number = int(value)
        except (TypeError, ValueError):
            raise ValueError("ids must be integers")
        if number > 0 and number not in out:
            out.append(number)
    return out


def normalize_webdav_remote_path(value):
    remote_path = str(value or "").strip()
    if not remote_path:
        raise ValueError("远程路径不能为空")
    if remote_path.lower().endswith(".json"):
        return remote_path
    return remote_path.rstrip("/\\") + "/" + DEFAULT_WEBDAV_FILE


def webdav_config_payload(data, current=None):
    """Validate WebDAV sync settings. Empty password means "keep existing"."""
    if not isinstance(data, dict):
        raise ValueError("json object required")
    current = current or {}
    server = str(data.get("server", current.get("server", ""))).strip()
    low = server.lower()
    if not server:
        raise ValueError("WebDAV 服务器地址不能为空")
    if not (low.startswith("https://") or low.startswith("http://")):
        raise ValueError("WebDAV 服务器地址需以 http(s):// 开头")
    username = str(data.get("username", current.get("username", ""))).strip()
    if not username:
        raise ValueError("WebDAV 用户名不能为空")
    remote_path = normalize_webdav_remote_path(data.get("remote_path", current.get("remote_path", "")))
    password = str(data.get("password") or "")  # "" => caller keeps existing
    return {"server": server, "username": username, "remote_path": remote_path, "password": password}
