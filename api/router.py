# -*- coding: utf-8 -*-
"""Exact API routing for the standard-library HTTP handler."""
import re
from urllib.parse import parse_qs

import core
import db
from api import validators
from services.key_service import KEYS
from services.task_service import TASKS
from services.settings_service import SETTINGS
from services.sync_service import SYNC
from services import restart_service
from core.webdav import WebDAVError

_KEY_RE = re.compile(r"^/api/keys/(\d+)$")
_KEY_ACTION_RE = re.compile(r"^/api/keys/(\d+)/(check|check_model|export|secret)$")
_TASK_RE = re.compile(r"^/api/tasks/([A-Za-z0-9_-]+)$")
_RESTART_RE = re.compile(r"^/api/system/restart/([A-Za-z0-9_-]+)$")


class ApiError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _id(match):
    return int(match.group(1))


def _sync_code(code):
    return {"config_error": "sync_not_configured", "auth_error": "webdav_auth_failed"}.get(code, "webdav_error")


def _sync_call(fn, *args):
    """Run a sync operation, mapping WebDAVError to a JSON error response."""
    try:
        return 200, fn(*args)
    except WebDAVError as exc:
        status = 400 if exc.code in ("config_error", "auth_error") else 502
        raise ApiError(status, _sync_code(exc.code), str(exc))
    except ValueError as exc:
        raise ApiError(400, "invalid_sync", str(exc))


def route(method, path, query, body, server):
    if method == "GET" and path == "/api/system/health":
        from version import APP_NAME, __version__
        return 200, {
            "status": "ok",
            "pid": __import__("os").getpid(),
            "host": server.runtime_settings["server_host"],
            "port": int(server.runtime_settings["server_port"]),
            "name": APP_NAME,
            "version": __version__,
        }
    if method == "GET" and path == "/api/keys":
        return 200, KEYS.list()
    if method == "GET" and path == "/api/keys/revision":
        return 200, {"revision": db.get_list_revision()}
    if method == "GET" and path == "/api/settings":
        return 200, SETTINGS.get()
    if method == "GET" and path == "/api/sync/config":
        return 200, SYNC.get_config()
    if method == "GET" and path == "/api/sync/status":
        return 200, SYNC.status()
    match = _TASK_RE.fullmatch(path)
    if method == "GET" and match:
        task = TASKS.get(match.group(1))
        if not task: raise ApiError(404, "task_not_found", "检测任务不存在或已过期")
        return 200, task
    match = _RESTART_RE.fullmatch(path)
    if method == "GET" and match:
        status = restart_service.get_status(match.group(1))
        if not status: raise ApiError(404, "restart_not_found", "重启任务不存在")
        return 200, status
    match = _KEY_RE.fullmatch(path)
    if method == "GET" and match:
        entry = KEYS.get(_id(match), public=True)
        if not entry: raise ApiError(404, "key_not_found", "Key 不存在")
        return 200, entry
    match = _KEY_ACTION_RE.fullmatch(path)
    if method == "GET" and match and match.group(2) == "export":
        entry = KEYS.get(_id(match), public=False)
        if not entry: raise ApiError(404, "key_not_found", "Key 不存在")
        fmt = parse_qs(query).get("fmt", [""])[0]
        try: text = core.export_config(entry, fmt)
        except ValueError as exc: raise ApiError(400, "invalid_export", str(exc))
        return 200, {"text": text}
    if method == "GET" and match and match.group(2) == "secret":
        try: return 200, KEYS.secret(_id(match))
        except KeyError: raise ApiError(404, "key_not_found", "Key 不存在")

    if method == "POST" and path == "/api/import/parse":
        return 200, {"candidates": core.parse_import_text((body or {}).get("text", ""))}
    if method == "POST" and path == "/api/keys":
        try: payload = validators.key_payload(body)
        except ValueError as exc: raise ApiError(400, "invalid_key", str(exc))
        key_id, result = KEYS.add(payload)
        return 201, {"id": key_id, **(result or {}), "entry": KEYS.get(key_id, public=True)}
    if method == "POST" and path == "/api/keys/batch":
        items = body.get("items") if isinstance(body, dict) else None
        if not isinstance(items, list): raise ApiError(400, "invalid_items", "items list required")
        if len(items) > validators.MAX_BATCH_ITEMS: raise ApiError(400, "too_many_items", "批量导入最多 1000 条")
        valid, invalid = [], 0
        for item in items:
            try: valid.append(validators.key_payload(item))
            except ValueError: invalid += 1
        ids, task, skipped_duplicate = KEYS.add_batch(valid)
        return 202, {"ids": ids, "count": len(ids), "skipped_invalid": invalid, "skipped_duplicate": skipped_duplicate, "task": task}
    if method == "POST" and path == "/api/keys/reorder":
        try: ids = validators.ids_payload(body)
        except ValueError as exc: raise ApiError(400, "invalid_ids", str(exc))
        return 200, {"ids": KEYS.reorder(ids)}
    if method == "POST" and path in ("/api/keys/batch_delete", "/api/keys/batch_check"):
        try: ids = validators.ids_payload(body)
        except ValueError as exc: raise ApiError(400, "invalid_ids", str(exc))
        if path.endswith("batch_delete"):
            return 200, {"deleted": KEYS.delete(ids)}
        return 202, KEYS.batch_check(ids)
    if method == "GET" and path == "/api/keys/export_all":
        entries = KEYS.list(public=False)
        try: text = core.export_batch(entries, "json")
        except ValueError as exc: raise ApiError(400, "invalid_export", str(exc))
        return 200, {"text": text, "count": len(entries), "fmt": "json"}
    if method == "POST" and path == "/api/keys/batch_export":
        try: ids = validators.ids_payload(body)
        except ValueError as exc: raise ApiError(400, "invalid_ids", str(exc))
        fmt = str((body or {}).get("fmt") or "json").lower()
        if fmt != "json":
            raise ApiError(400, "invalid_export", "batch export only supports json")
        entries = []
        for key_id in ids:
            entry = KEYS.get(key_id, public=False)
            if entry:
                entries.append(entry)
        try: text = core.export_batch(entries, fmt)
        except ValueError as exc: raise ApiError(400, "invalid_export", str(exc))
        return 200, {"text": text, "count": len(entries), "fmt": fmt}
    match = _KEY_ACTION_RE.fullmatch(path)
    if method == "POST" and match:
        key_id, action = _id(match), match.group(2)
        try:
            if action == "check": return 200, {"id": key_id, **KEYS.check(key_id)}
            if action == "check_model": return 200, {"id": key_id, **KEYS.check_model(key_id, (body or {}).get("model"))}
        except KeyError: raise ApiError(404, "key_not_found", "Key 不存在")
        except ValueError as exc: raise ApiError(400, "invalid_check", str(exc))
        except RuntimeError as exc: raise ApiError(409, "check_conflict", str(exc))
    if method == "POST" and path == "/api/settings":
        try: payload = SETTINGS.validate(body)
        except ValueError as exc: raise ApiError(400, "invalid_settings", str(exc))
        db.set_settings(payload)
        return 200, SETTINGS.get()
    if method == "POST" and path == "/api/sync/config":
        try: return 200, SYNC.save_config(body)
        except ValueError as exc: raise ApiError(400, "invalid_sync_config", str(exc))
    if method == "POST" and path == "/api/sync/test":
        return _sync_call(SYNC.test)
    if method == "POST" and path == "/api/sync/upload":
        return _sync_call(SYNC.upload)
    if method == "POST" and path == "/api/sync/download":
        mode = (body or {}).get("mode", "merge") if isinstance(body, dict) else "merge"
        return _sync_call(SYNC.download, mode)
    if method == "POST" and path == "/api/system/restart":
        try: status = SETTINGS.restart(server)
        except ValueError as exc: raise ApiError(409, "target_unavailable", str(exc))
        except RuntimeError as exc: raise ApiError(409, "restart_conflict", str(exc))
        return 202, status

    if method == "PUT" and (match := _KEY_RE.fullmatch(path)):
        try: payload = validators.key_payload(body, partial=True)
        except ValueError as exc: raise ApiError(400, "invalid_key", str(exc))
        try: entry, result = KEYS.update(_id(match), payload)
        except KeyError: raise ApiError(404, "key_not_found", "Key 不存在")
        except RuntimeError as exc: raise ApiError(409, "check_conflict", str(exc))
        response = dict(entry)
        response["_check"] = result
        return 200, response
    if method == "DELETE" and (match := _KEY_RE.fullmatch(path)):
        return 200, {"deleted": KEYS.delete([_id(match)])}
    raise ApiError(404, "not_found", "接口不存在")
