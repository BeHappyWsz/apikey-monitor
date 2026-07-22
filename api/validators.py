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
    for field in ("name", "base_url", "api_key", "notes", "check_model", "check_path", "tags"):
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
        raise ValueError("uiRefreshIntervalSec must be 0 or at least 3")
    return number


def settings_payload(data, current=None):
    if not isinstance(data, dict):
        raise ValueError("json object required")
    current = current or {}
    host = str(data.get("serverHost", current.get("serverHost", "127.0.0.1"))).strip()
    if host not in ("127.0.0.1", "localhost", "0.0.0.0"):
        raise ValueError("unsupported serverHost")
    return {
        "serverHost": host,
        "serverPort": str(normalize_int(data.get("serverPort", current.get("serverPort", 7878)), 7878, 1024, 65535)),
        "globalMonitorEnabled": "1" if str(data.get("globalMonitorEnabled", current.get("globalMonitorEnabled", "1"))).lower() in ("1", "true") else "0",
        "globalIntervalSec": str(normalize_int(data.get("globalIntervalSec", current.get("globalIntervalSec", 300)), 300, 30, 86400)),
        "downRecheckIntervalSec": str(normalize_int(data.get("downRecheckIntervalSec", current.get("downRecheckIntervalSec", 120)), 120, 30, 86400)),
        "concurrency": str(normalize_int(data.get("concurrency", current.get("concurrency", 8)), 8, 1, 32)),
        "requestTimeoutSec": str(normalize_int(data.get("requestTimeoutSec", current.get("requestTimeoutSec", 45)), 45, 3, 120)),
        "autoClassifyOnAdd": "1" if str(data.get("autoClassifyOnAdd", current.get("autoClassifyOnAdd", "1"))).lower() in ("1", "true") else "0",
        "uiRefreshIntervalSec": str(_normalize_ui_refresh(data.get("uiRefreshIntervalSec", current.get("uiRefreshIntervalSec", 15)))),
        "strictMonitorEnabled": "1" if str(data.get("strictMonitorEnabled", current.get("strictMonitorEnabled", "0"))).lower() in ("1", "true") else "0",
        "strictIntervalSec": str(normalize_int(data.get("strictIntervalSec", current.get("strictIntervalSec", 21600)), 21600, 300, 604800)),
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


def user_enabled_payload(data):
    if not isinstance(data, dict) or "enabled" not in data:
        raise ValueError("enabled is required")
    value = data["enabled"]
    if isinstance(value, bool):
        return value
    if value in (0, 1, "0", "1"):
        return bool(int(value))
    raise ValueError("enabled must be a boolean")


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
