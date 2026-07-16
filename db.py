# -*- coding: utf-8 -*-
"""SQLite and JSON configuration persistence."""
import json
import os
import sqlite3
import tempfile
import time
from contextlib import contextmanager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("APIKEYCONFIG_DB_PATH", os.path.join(BASE_DIR, "data.db"))
CONFIG_PATH = os.environ.get("APIKEYCONFIG_CONFIG_PATH", os.path.join(BASE_DIR, "config.json"))
_FALLBACK_DEFAULTS = {
    "server_host": "127.0.0.1", "server_port": "7878",
    "global_monitor_enabled": "1", "global_interval_sec": "300",
    "down_recheck_interval_sec": "120", "concurrency": "8",
    "request_timeout_sec": "15", "auto_classify_on_add": "1",
    "ui_refresh_interval_sec": "5",
}


def _load_defaults():
    if not os.path.isfile(CONFIG_PATH):
        write_config_atomic(_FALLBACK_DEFAULTS)
        return dict(_FALLBACK_DEFAULTS)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as stream:
            data = json.load(stream)
    except Exception:
        return dict(_FALLBACK_DEFAULTS)
    out = dict(_FALLBACK_DEFAULTS)
    if isinstance(data, dict):
        out.update({key: str(value) for key, value in data.items() if not key.startswith("_")})
    return out


def write_config_atomic(data):
    payload = {"_comment": "apiKeyConfig runtime settings. The web UI updates this file atomically."}
    payload.update({key: str(value) for key, value in data.items() if not str(key).startswith("_")})
    directory = os.path.dirname(CONFIG_PATH) or "."
    fd, temp_path = tempfile.mkstemp(prefix="config-", suffix=".json.tmp", dir=directory, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, CONFIG_PATH)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


@contextmanager
def connection(write=False):
    conn = get_conn()
    try:
        yield conn
        if write:
            conn.commit()
    except Exception:
        if write:
            conn.rollback()
        raise
    finally:
        conn.close()


def _migrate(conn):
    cols = {row[1] for row in conn.execute("PRAGMA table_info(keys)")}
    for col, decl in (("check_model", "TEXT DEFAULT ''"), ("model_status", "TEXT DEFAULT 'unknown'"),
                      ("model_latency_ms", "INTEGER"), ("model_last_check_at", "INTEGER"),
                      ("model_last_error", "TEXT DEFAULT ''"), ("sort_order", "INTEGER DEFAULT 0"), ("check_path", "TEXT DEFAULT ''")):
        if col not in cols:
            conn.execute(f"ALTER TABLE keys ADD COLUMN {col} {decl}")
    conn.execute("PRAGMA user_version=3")


def init_db():
    with connection(write=True) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT DEFAULT '', base_url TEXT NOT NULL,
            api_key TEXT NOT NULL, supports_anthropic INTEGER DEFAULT 0,
            supports_openai INTEGER DEFAULT 0, models TEXT DEFAULT '[]', status TEXT DEFAULT 'unknown',
            latency_ms INTEGER, last_check_at INTEGER, last_error TEXT DEFAULT '',
            monitor_enabled INTEGER DEFAULT 1, interval_sec INTEGER, notes TEXT DEFAULT '',
            created_at INTEGER, check_model TEXT DEFAULT '', model_status TEXT DEFAULT 'unknown',
            model_latency_ms INTEGER, model_last_check_at INTEGER, model_last_error TEXT DEFAULT '',
            sort_order INTEGER DEFAULT 0, check_path TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS settings (k TEXT PRIMARY KEY, v TEXT);
        """)
        _migrate(conn)
        for key, value in _load_defaults().items():
            conn.execute("INSERT OR IGNORE INTO settings(k,v) VALUES(?,?)", (key, value))


def get_all_settings():
    with connection() as conn:
        return {row["k"]: row["v"] for row in conn.execute("SELECT k,v FROM settings")}


def set_settings(items, persist=True):
    normalized = {key: str(value) for key, value in items.items()}
    with connection(write=True) as conn:
        for key, value in normalized.items():
            conn.execute("INSERT INTO settings(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (key, value))
    if persist:
        merged = get_all_settings()
        write_config_atomic(merged)


def replace_settings(items):
    with connection(write=True) as conn:
        conn.execute("DELETE FROM settings")
        conn.executemany("INSERT INTO settings(k,v) VALUES(?,?)", [(key, str(value)) for key, value in items.items()])
    write_config_atomic(items)


def _row_to_dict(row):
    out = dict(row)
    try:
        out["models"] = json.loads(out.get("models") or "[]")
    except Exception:
        out["models"] = []
    return out


def mask_api_key(value):
    key = str(value or "")
    if len(key) < 12:
        return "••••••••"
    return f"{key[:5]}••••••{key[-4:]}"


def public_key(entry, include_secret=False):
    if not entry:
        return None
    out = dict(entry)
    secret = out.get("api_key") or ""
    out["api_key_masked"] = mask_api_key(secret)
    out["has_api_key"] = bool(secret)
    if include_secret:
        out["api_key"] = secret
    else:
        out.pop("api_key", None)
    return out


def list_keys(public=False):
    with connection() as conn:
        rows = [_row_to_dict(row) for row in conn.execute(
            "SELECT * FROM keys ORDER BY CASE WHEN sort_order=0 THEN 1 ELSE 0 END, sort_order ASC, id DESC")]
    if public:
        return [public_key(row) for row in rows]
    return rows


def get_key(key_id, public=False):
    with connection() as conn:
        row = conn.execute("SELECT * FROM keys WHERE id=?", (key_id,)).fetchone()
        entry = _row_to_dict(row) if row else None
    if public:
        return public_key(entry)
    return entry



def add_key(data):
    with connection(write=True) as conn:
        sort_order = _next_sort_order(conn)
        cur = conn.execute("""INSERT INTO keys
            (name,base_url,api_key,status,monitor_enabled,interval_sec,notes,created_at,check_model,sort_order,check_path)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (data.get("name", ""), data["base_url"], data["api_key"], "unknown",
             int(bool(data.get("monitor_enabled", 1))), data.get("interval_sec"), data.get("notes", ""),
             int(time.time()), data.get("check_model", ""), sort_order, data.get("check_path", "")))
        return cur.lastrowid


def add_keys_batch(items):
    ids = []
    skipped_duplicate = 0
    with connection(write=True) as conn:
        existing = {(r["base_url"], r["api_key"]) for r in conn.execute("SELECT base_url,api_key FROM keys")}
        sort_order = _next_sort_order(conn)
        for item in items:
            marker = (item["base_url"], item["api_key"])
            if marker in existing:
                skipped_duplicate += 1
                continue
            existing.add(marker)
            cur = conn.execute("""INSERT INTO keys
            (name,base_url,api_key,status,monitor_enabled,interval_sec,notes,created_at,check_model,sort_order,check_path)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (item.get("name", ""), marker[0], marker[1], "unknown",
                 int(bool(item.get("monitor_enabled", 1))), item.get("interval_sec"), item.get("notes", ""),
                 int(time.time()), item.get("check_model", ""), sort_order, item.get("check_path", "")))
            ids.append(cur.lastrowid)
            sort_order += 10
    return ids, skipped_duplicate

def _next_sort_order(conn):
    value = conn.execute("SELECT MIN(sort_order) FROM keys").fetchone()[0]
    if value is None:
        return 10
    next_value = int(value) - 10
    return -10 if next_value == 0 else next_value


def reorder_keys(ids):
    if not ids:
        return []
    ordered_ids = []
    for key_id in ids:
        key_id = int(key_id)
        if key_id > 0 and key_id not in ordered_ids:
            ordered_ids.append(key_id)
    with connection(write=True) as conn:
        existing = [row["id"] for row in conn.execute(
            "SELECT id FROM keys ORDER BY CASE WHEN sort_order=0 THEN 1 ELSE 0 END, sort_order ASC, id DESC")]
        existing_set = set(existing)
        requested = [key_id for key_id in ordered_ids if key_id in existing_set]
        requested_set = set(requested)
        final_ids = requested + [key_id for key_id in existing if key_id not in requested_set]
        for index, key_id in enumerate(final_ids, start=1):
            conn.execute("UPDATE keys SET sort_order=? WHERE id=?", (index * 10, key_id))
    return final_ids


def update_key(key_id, data):
    allowed = ("name", "base_url", "api_key", "monitor_enabled", "interval_sec", "notes", "check_model", "check_path")
    fields, values = [], []
    for col in allowed:
        if col in data:
            fields.append(f"{col}=?")
            values.append(data[col])
    if not fields:
        return False
    if "base_url" in data or "api_key" in data:
        fields.extend(["status='unknown'", "supports_openai=0", "supports_anthropic=0", "models='[]'",
                       "latency_ms=NULL", "last_check_at=NULL", "last_error=''", "model_status='unknown'",
                       "model_latency_ms=NULL", "model_last_check_at=NULL", "model_last_error=''"])
    with connection(write=True) as conn:
        cur = conn.execute(f"UPDATE keys SET {', '.join(fields)} WHERE id=?", (*values, key_id))
        return cur.rowcount > 0


def delete_keys(ids):
    if not ids:
        return 0
    with connection(write=True) as conn:
        marks = ",".join("?" for _ in ids)
        return conn.execute(f"DELETE FROM keys WHERE id IN ({marks})", list(ids)).rowcount


def update_status(key_id, status, latency_ms, error, supports_anthropic=None, supports_openai=None, models=None):
    sets = ["status=?", "latency_ms=?", "last_error=?", "last_check_at=?"]
    values = [status, latency_ms, (error or "")[:300], int(time.time())]
    if supports_anthropic is not None:
        sets.append("supports_anthropic=?"); values.append(int(bool(supports_anthropic)))
    if supports_openai is not None:
        sets.append("supports_openai=?"); values.append(int(bool(supports_openai)))
    if models is not None:
        sets.append("models=?"); values.append(json.dumps(models[:200], ensure_ascii=False))
    with connection(write=True) as conn:
        conn.execute(f"UPDATE keys SET {', '.join(sets)} WHERE id=?", (*values, key_id))


def update_model_status(key_id, status, latency_ms, error):
    with connection(write=True) as conn:
        conn.execute("""UPDATE keys SET model_status=?, model_latency_ms=?, model_last_error=?,
                      model_last_check_at=? WHERE id=?""",
                     (status, latency_ms, (error or "")[:300], int(time.time()), key_id))


def get_due_keys(now, up_interval, down_interval):
    with connection() as conn:
        rows = conn.execute("SELECT * FROM keys WHERE monitor_enabled=1").fetchall()
    due = []
    for row in rows:
        item = _row_to_dict(row)
        interval = item.get("interval_sec") or (down_interval if item["status"] == "down" else up_interval)
        if now - (item.get("last_check_at") or 0) >= int(interval):
            due.append(item)
    return due
