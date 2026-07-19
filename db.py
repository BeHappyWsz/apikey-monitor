# -*- coding: utf-8 -*-
"""SQLite and JSON configuration persistence."""
import json
import os
import re
import sqlite3
import time
from contextlib import contextmanager
import pymysql
import redis

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("APIKEYCONFIG_DB_PATH", os.path.join(BASE_DIR, "data.db"))
CONFIG_PATH = os.environ.get("APIKEYCONFIG_CONFIG_PATH", os.path.join(BASE_DIR, "config.json"))
_FALLBACK_DEFAULTS = {
    "server_host": "127.0.0.1", "server_port": "7878",
    "global_monitor_enabled": "1", "global_interval_sec": "300",
    "down_recheck_interval_sec": "120", "concurrency": "8",
    "request_timeout_sec": "45", "auto_classify_on_add": "1",
    "ui_refresh_interval_sec": "15",
}
_SETTING_NAMES = {
    "server_host": "服务监听地址",
    "server_port": "服务监听端口",
    "global_monitor_enabled": "全局监测开关",
    "global_interval_sec": "正常 Key 监测间隔（秒）",
    "down_recheck_interval_sec": "异常 Key 复检间隔（秒）",
    "concurrency": "监测并发数",
    "request_timeout_sec": "探测请求超时（秒）",
    "auto_classify_on_add": "新增 Key 自动识别开关",
    "ui_refresh_interval_sec": "前端列表刷新间隔（秒）",
    "webdav_server": "WebDAV 服务器地址",
    "webdav_username": "WebDAV 用户名",
    "webdav_remote_path": "WebDAV 远程备份路径",
    "_webdav_password": "WebDAV 应用密码",
    "_webdav_last_sync": "WebDAV 最近同步状态",
}


_list_generation = 0
_cache_client = None
_cache_signature = None
_cache_retry_at = 0
_CACHE_TTL_SECONDS = 60
_PUBLIC_KEY_CACHE_PREFIX = "apikey-monitor:public-key:"
_PUBLIC_SETTINGS_CACHE_KEY = "apikey-monitor:public-settings"
_TABLE_RENAMES = (
    ("keys", "tbl_keys"),
    ("settings", "tbl_settings"),
    ("users", "tbl_users"),
    ("sessions", "tbl_sessions"),
)


def _private_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as stream:
            data = json.load(stream)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _connection_value(cfg, name, default):
    """Read a private connection option, with container-friendly env override."""
    return os.environ.get(f"APIKEYCONFIG_{name}", cfg.get(f"_{name.lower()}", default))


def storage_backend():
    backend = str(os.environ.get("APIKEYCONFIG_STORAGE_BACKEND") or
                  _private_config().get("_storage_backend") or "sqlite").lower()
    if backend not in ("sqlite", "mysql"):
        raise ValueError("APIKEYCONFIG_STORAGE_BACKEND must be sqlite or mysql")
    return backend


def storage_description():
    """A non-secret, operator-facing description of the active primary store."""
    if storage_backend() == "sqlite":
        return f"sqlite:{DB_PATH}"
    cfg = _private_config()
    host = _connection_value(cfg, "MYSQL_HOST", "127.0.0.1")
    port = _connection_value(cfg, "MYSQL_PORT", 3306)
    database = _connection_value(cfg, "MYSQL_DATABASE", "apikey-monitor")
    return f"mysql:{host}:{port}/{database}"


def _cache():
    """Return the optional Redis client, without making Redis a dependency.

    Redis is currently enabled for the MySQL primary store only.  This keeps
    isolated SQLite tests and standalone SQLite deployments from accidentally
    sharing data through the configured Redis instance.  A failed connection
    is retried after a short delay so a Redis restart recovers automatically.
    """
    global _cache_client, _cache_signature, _cache_retry_at
    if storage_backend() != "mysql":
        return None
    cfg = _private_config()
    signature = (
        _connection_value(cfg, "REDIS_HOST", "127.0.0.1"),
        str(_connection_value(cfg, "REDIS_PORT", 6379)),
        str(_connection_value(cfg, "REDIS_DB", 0)),
        _connection_value(cfg, "REDIS_USERNAME", "") or "",
        _connection_value(cfg, "REDIS_PASSWORD", "") or "",
    )
    now = time.monotonic()
    if _cache_signature == signature and _cache_client is not None:
        return _cache_client
    if _cache_signature == signature and now < _cache_retry_at:
        return None
    try:
        client = redis.Redis(host=signature[0], port=int(signature[1]), db=int(signature[2]),
            username=signature[3] or None, password=signature[4] or None,
            decode_responses=True, socket_connect_timeout=1, socket_timeout=1)
        client.ping()
    except Exception:
        _cache_client = None
        _cache_signature = signature
        _cache_retry_at = now + 5
        return None
    _cache_client = client
    _cache_signature = signature
    _cache_retry_at = 0
    return _cache_client


def _cache_get(name):
    try:
        client = _cache()
        value = client.get(name) if client else None
        return json.loads(value) if value else None
    except Exception:
        return None


def _cache_set(name, value):
    try:
        client = _cache()
        if client:
            client.setex(name, _CACHE_TTL_SECONDS, json.dumps(value, ensure_ascii=False))
    except Exception:
        pass


def _invalidate_public_cache():
    try:
        client = _cache()
        if client:
            names = list(client.scan_iter(f"{_PUBLIC_KEY_CACHE_PREFIX}*"))
            names.append(_PUBLIC_SETTINGS_CACHE_KEY)
            if names: client.delete(*names)
    except Exception:
        pass


class _MyRow(dict):
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class _MyCursor:
    def __init__(self, cursor): self._cursor = cursor
    @staticmethod
    def _sql(sql): return sql.replace("?", "%s")
    def execute(self, sql, args=None): self._cursor.execute(self._sql(sql), args); return self
    def executemany(self, sql, args): self._cursor.executemany(self._sql(sql), args); return self
    def fetchone(self):
        row = self._cursor.fetchone()
        return _MyRow(row) if row else None
    def fetchall(self): return [_MyRow(row) for row in self._cursor.fetchall()]
    def __iter__(self): return iter(self.fetchall())
    @property
    def rowcount(self): return self._cursor.rowcount
    @property
    def lastrowid(self): return self._cursor.lastrowid


class _MyConnection:
    def __init__(self, conn): self._conn = conn
    def execute(self, sql, args=None):
        cursor = _MyCursor(self._conn.cursor())
        return cursor.execute(sql, args)
    def executemany(self, sql, args):
        cursor = _MyCursor(self._conn.cursor())
        return cursor.executemany(sql, args)
    def commit(self): self._conn.commit()
    def rollback(self): self._conn.rollback()
    def close(self): self._conn.close()


def _mysql_conn():
    cfg = _private_config()
    return _MyConnection(pymysql.connect(
        host=_connection_value(cfg, "MYSQL_HOST", "127.0.0.1"),
        port=int(_connection_value(cfg, "MYSQL_PORT", 3306)),
        user=_connection_value(cfg, "MYSQL_USERNAME", "root"),
        password=_connection_value(cfg, "MYSQL_PASSWORD", ""),
        database=_connection_value(cfg, "MYSQL_DATABASE", "apikey-monitor"),
        charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor, autocommit=False, connect_timeout=5))


def touch_list_generation():
    """Bump in-process generation so clients notice list mutations quickly."""
    global _list_generation
    _list_generation += 1
    _invalidate_public_cache()
    return _list_generation


def get_list_revision():
    """Cheap opaque revision for frontend short-circuit polling.

    Combines process-local generation with DB stamps so monitor status writes
    and CRUD both change the token without shipping the full key list.
    """
    with connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS c,
                   COALESCE(MAX(last_check_at), 0) AS max_lc,
                   COALESCE(MAX(model_last_check_at), 0) AS max_mlc,
                   COALESCE(MAX(id), 0) AS max_id,
                   COALESCE(SUM(sort_order), 0) AS sum_sort,
                   COALESCE(SUM(monitor_enabled), 0) AS mon
            FROM tbl_keys
            """
        ).fetchone()
    return (
        f"{_list_generation}:{row['c']}:{row['max_lc']}:{row['max_mlc']}:"
        f"{row['max_id']}:{row['sum_sort']}:{row['mon']}"
    )


def _load_defaults():
    """Read-only seed: tracked config.json if present, else hardcoded defaults.

    config.json is a shipped seed only — the runtime never writes it. init_db()
    seeds the settings table from here once on a fresh database; afterwards the
    table is the single source of truth and config.json is never rewritten.
    """
    if not os.path.isfile(CONFIG_PATH):
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


def get_bootstrap_admin_username():
    """Read the first-admin name from the shipped startup configuration only."""
    if not os.path.isfile(CONFIG_PATH):
        return "admin"
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as stream:
            value = json.load(stream).get("_bootstrap_admin_username", "admin")
    except Exception:
        return "admin"
    value = str(value or "").strip()
    return value or "admin"


def get_bootstrap_admin_password():
    if not os.path.isfile(CONFIG_PATH):
        return "ChangeMe!2026"
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as stream:
            value = json.load(stream).get("_bootstrap_admin_password", "ChangeMe!2026")
    except Exception:
        return "ChangeMe!2026"
    return str(value or "")


def get_conn():
    if storage_backend() == "mysql":
        return _mysql_conn()
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
    cols = {row[1] for row in conn.execute("PRAGMA table_info(tbl_keys)")}
    for col, decl in (("check_model", "TEXT DEFAULT ''"), ("model_status", "TEXT DEFAULT 'unknown'"),
                      ("model_latency_ms", "INTEGER"), ("model_last_check_at", "INTEGER"),
                      ("model_last_error", "TEXT DEFAULT ''"), ("sort_order", "INTEGER DEFAULT 0"), ("check_path", "TEXT DEFAULT ''")):
        if col not in cols:
            conn.execute(f"ALTER TABLE tbl_keys ADD COLUMN {col} {decl}")
    settings_cols = {row[1] for row in conn.execute("PRAGMA table_info(tbl_settings)")}
    if "name" not in settings_cols:
        conn.execute("ALTER TABLE tbl_settings ADD COLUMN name TEXT NOT NULL DEFAULT ''")
    _backfill_setting_names(conn)
    conn.execute("PRAGMA user_version=7")
    conn.execute("DELETE FROM tbl_settings WHERE k = 'webdav_last_sync'")
    _to_row = conn.execute("SELECT v FROM tbl_settings WHERE k='request_timeout_sec'").fetchone()
    if _to_row and str(_to_row["v"]) == "15":
        conn.execute("UPDATE tbl_settings SET v='45' WHERE k='request_timeout_sec'")
    user_cols = {row[1] for row in conn.execute("PRAGMA table_info(tbl_users)")}
    if "must_change_password" not in user_cols:
        conn.execute("ALTER TABLE tbl_users ADD COLUMN must_change_password INTEGER DEFAULT 0")
    if "enabled" not in user_cols:
        conn.execute("ALTER TABLE tbl_users ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1")


def _setting_name(key):
    key = str(key)
    return _SETTING_NAMES.get(key, f"自定义设置：{key}")


def _backfill_setting_names(conn):
    rows = conn.execute("SELECT k FROM tbl_settings").fetchall()
    conn.executemany("UPDATE tbl_settings SET name=? WHERE k=?",
                     [(_setting_name(row["k"]), row["k"]) for row in rows])


def _setting_rows(items):
    return [(key, str(value), _setting_name(key)) for key, value in items.items()]


def _sqlite_table_names(conn):
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _migrate_table_names_sqlite(conn):
    names = _sqlite_table_names(conn)
    collisions = [f"{old}/{new}" for old, new in _TABLE_RENAMES if old in names and new in names]
    if collisions:
        raise RuntimeError("database table-name migration stopped: both legacy and tbl_* tables exist: "
                           + ", ".join(collisions) + "; restore or reconcile from backup before retrying")
    for old, new in _TABLE_RENAMES:
        if old in names:
            conn.execute(f"ALTER TABLE {old} RENAME TO {new}")


def _mysql_table_names(conn):
    names = tuple(name for pair in _TABLE_RENAMES for name in pair)
    marks = ",".join("?" for _ in names)
    rows = conn.execute(
        f"SELECT table_name AS name FROM information_schema.tables "
        f"WHERE table_schema=DATABASE() AND table_name IN ({marks})", names)
    return {row["name"] for row in rows}


def _quote_mysql_identifier(name):
    return "`" + name.replace("`", "``") + "`"


def _migrate_table_names_mysql(conn):
    names = _mysql_table_names(conn)
    collisions = [f"{old}/{new}" for old, new in _TABLE_RENAMES if old in names and new in names]
    if collisions:
        raise RuntimeError("database table-name migration stopped: both legacy and tbl_* tables exist: "
                           + ", ".join(collisions) + "; restore or reconcile from backup before retrying")
    renames = [(old, new) for old, new in _TABLE_RENAMES if old in names]
    if renames:
        pairs = ", ".join(f"{_quote_mysql_identifier(old)} TO {_quote_mysql_identifier(new)}"
                          for old, new in renames)
        conn.execute(f"RENAME TABLE {pairs}")


def init_db():
    if storage_backend() == "mysql":
        _init_mysql()
        return
    with connection(write=True) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        _migrate_table_names_sqlite(conn)
        conn.execute("""CREATE TABLE IF NOT EXISTS tbl_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT DEFAULT '', base_url TEXT NOT NULL,
            api_key TEXT NOT NULL, supports_anthropic INTEGER DEFAULT 0,
            supports_openai INTEGER DEFAULT 0, models TEXT DEFAULT '[]', status TEXT DEFAULT 'unknown',
            latency_ms INTEGER, last_check_at INTEGER, last_error TEXT DEFAULT '',
            monitor_enabled INTEGER DEFAULT 1, interval_sec INTEGER, notes TEXT DEFAULT '',
            created_at INTEGER, check_model TEXT DEFAULT '', model_status TEXT DEFAULT 'unknown',
            model_latency_ms INTEGER, model_last_check_at INTEGER, model_last_error TEXT DEFAULT '',
            sort_order INTEGER DEFAULT 0, check_path TEXT DEFAULT ''
        )""")
        conn.execute("CREATE TABLE IF NOT EXISTS tbl_settings (k TEXT PRIMARY KEY, v TEXT, name TEXT NOT NULL DEFAULT '')")
        conn.execute("""CREATE TABLE IF NOT EXISTS tbl_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL, must_change_password INTEGER DEFAULT 0,
            enabled INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS tbl_sessions (
            token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES tbl_users(id) ON DELETE CASCADE,
            csrf_token TEXT NOT NULL, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL, last_seen_at INTEGER NOT NULL
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON tbl_sessions(expires_at)")
        _migrate(conn)
        if conn.execute("SELECT 1 FROM tbl_settings LIMIT 1").fetchone() is None:
            conn.executemany("INSERT INTO tbl_settings(k,v,name) VALUES(?,?,?)", _setting_rows(_load_defaults()))


def _init_mysql():
    with connection(write=True) as conn:
        _migrate_table_names_mysql(conn)
        statements = [
            """CREATE TABLE IF NOT EXISTS tbl_keys (id BIGINT PRIMARY KEY AUTO_INCREMENT,name TEXT,base_url TEXT NOT NULL,api_key TEXT NOT NULL,supports_anthropic TINYINT DEFAULT 0,supports_openai TINYINT DEFAULT 0,models LONGTEXT,status VARCHAR(32) DEFAULT 'unknown',latency_ms BIGINT,last_check_at BIGINT,last_error TEXT,monitor_enabled TINYINT DEFAULT 1,interval_sec BIGINT,notes TEXT,created_at BIGINT,check_model TEXT,model_status VARCHAR(32) DEFAULT 'unknown',model_latency_ms BIGINT,model_last_check_at BIGINT,model_last_error TEXT,sort_order BIGINT DEFAULT 0,check_path TEXT,INDEX idx_keys_monitor_due (monitor_enabled,last_check_at)) CHARACTER SET utf8mb4""",
            "CREATE TABLE IF NOT EXISTS tbl_settings (k VARCHAR(191) PRIMARY KEY,v LONGTEXT,name VARCHAR(255) NOT NULL DEFAULT '') CHARACTER SET utf8mb4",
            "CREATE TABLE IF NOT EXISTS tbl_users (id BIGINT PRIMARY KEY AUTO_INCREMENT,username VARCHAR(64) NOT NULL UNIQUE,password_hash TEXT NOT NULL,must_change_password TINYINT DEFAULT 0,enabled TINYINT NOT NULL DEFAULT 1,created_at BIGINT NOT NULL) CHARACTER SET utf8mb4",
            "CREATE TABLE IF NOT EXISTS tbl_sessions (token_hash CHAR(64) PRIMARY KEY,user_id BIGINT NOT NULL,csrf_token TEXT NOT NULL,created_at BIGINT NOT NULL,expires_at BIGINT NOT NULL,last_seen_at BIGINT NOT NULL,INDEX idx_sessions_expires_at(expires_at),FOREIGN KEY(user_id) REFERENCES tbl_users(id) ON DELETE CASCADE) CHARACTER SET utf8mb4",
        ]
        for statement in statements:
            conn.execute(statement)
        user_columns = {row["COLUMN_NAME"] for row in conn.execute(
            "SELECT COLUMN_NAME FROM information_schema.columns "
            "WHERE table_schema=DATABASE() AND table_name='tbl_users'")}
        if "must_change_password" not in user_columns:
            conn.execute("ALTER TABLE tbl_users ADD COLUMN must_change_password TINYINT DEFAULT 0")
        if "enabled" not in user_columns:
            conn.execute("ALTER TABLE tbl_users ADD COLUMN enabled TINYINT NOT NULL DEFAULT 1")
        settings_columns = {row["COLUMN_NAME"] for row in conn.execute(
            "SELECT COLUMN_NAME FROM information_schema.columns "
            "WHERE table_schema=DATABASE() AND table_name='tbl_settings'")}
        if "name" not in settings_columns:
            conn.execute("ALTER TABLE tbl_settings ADD COLUMN name VARCHAR(255) NOT NULL DEFAULT ''")
        _backfill_setting_names(conn)
        if conn.execute("SELECT 1 FROM tbl_settings LIMIT 1").fetchone() is None:
            conn.executemany("INSERT INTO tbl_settings(k,v,name) VALUES(?,?,?)", _setting_rows(_load_defaults()))


def get_all_settings():
    with connection() as conn:
        return {row["k"]: row["v"] for row in conn.execute("SELECT k,v FROM tbl_settings")}


def get_public_settings():
    """Return only browser-safe settings and cache that filtered payload."""
    cached = _cache_get(_PUBLIC_SETTINGS_CACHE_KEY)
    if cached is not None:
        return cached
    values = {key: value for key, value in get_all_settings().items()
              if not key.startswith("_")}
    _cache_set(_PUBLIC_SETTINGS_CACHE_KEY, values)
    return values


def set_settings(items):
    """Upsert settings rows. Runtime writes stay in the DB only — config.json
    is a read-only seed and is never rewritten."""
    normalized = {key: str(value) for key, value in items.items()}
    with connection(write=True) as conn:
        for key, value, name in _setting_rows(normalized):
            if storage_backend() == "mysql":
                conn.execute("INSERT INTO tbl_settings(k,v,name) VALUES(?,?,?) ON DUPLICATE KEY UPDATE v=VALUES(v),name=VALUES(name)",
                             (key, value, name))
            else:
                conn.execute("INSERT INTO tbl_settings(k,v,name) VALUES(?,?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v,name=excluded.name",
                             (key, value, name))
    _invalidate_public_cache()


def replace_settings(items):
    """Replace the whole settings table (used by restart orchestration)."""
    with connection(write=True) as conn:
        conn.execute("DELETE FROM tbl_settings")
        conn.executemany("INSERT INTO tbl_settings(k,v,name) VALUES(?,?,?)", _setting_rows(items))
    _invalidate_public_cache()


def count_users():
    with connection() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM tbl_users").fetchone()[0])


def get_user_by_username(username):
    with connection() as conn:
        row = conn.execute("SELECT id,username,password_hash,must_change_password,enabled,created_at FROM tbl_users WHERE username=?", (username,)).fetchone()
    return dict(row) if row else None


def get_user(user_id):
    with connection() as conn:
        row = conn.execute("SELECT id,username,must_change_password,enabled,created_at FROM tbl_users WHERE id=?", (user_id,)).fetchone()
    return dict(row) if row else None


def list_users():
    with connection() as conn:
        return [dict(row) for row in conn.execute("SELECT id,username,enabled,created_at FROM tbl_users ORDER BY id ASC")]


def create_user(username, password_hash, must_change_password=False, enabled=True):
    with connection(write=True) as conn:
        cur = conn.execute("INSERT INTO tbl_users(username,password_hash,must_change_password,enabled,created_at) VALUES(?,?,?,?,?)",
                           (username, password_hash, int(bool(must_change_password)), int(bool(enabled)), int(time.time())))
        return int(cur.lastrowid)


def update_user_password_hash(user_id, password_hash, must_change_password=None):
    with connection(write=True) as conn:
        if must_change_password is None:
            conn.execute("UPDATE tbl_users SET password_hash=? WHERE id=?", (password_hash, user_id))
        else:
            conn.execute("UPDATE tbl_users SET password_hash=?,must_change_password=? WHERE id=?",
                         (password_hash, int(bool(must_change_password)), user_id))


def set_user_enabled(user_id, enabled):
    """Change account availability and revoke its sessions when disabling it."""
    with connection(write=True) as conn:
        row = conn.execute("SELECT id FROM tbl_users WHERE id=?", (user_id,)).fetchone()
        if not row:
            return None
        enabled = int(bool(enabled))
        conn.execute("UPDATE tbl_users SET enabled=? WHERE id=?", (enabled, user_id))
        if not enabled:
            conn.execute("DELETE FROM tbl_sessions WHERE user_id=?", (user_id,))
    return get_user(user_id)


def create_session(token_hash, user_id, csrf_token, expires_at):
    now = int(time.time())
    with connection(write=True) as conn:
        conn.execute("INSERT INTO tbl_sessions(token_hash,user_id,csrf_token,created_at,expires_at,last_seen_at) VALUES(?,?,?,?,?,?)",
                     (token_hash, user_id, csrf_token, now, int(expires_at), now))


def get_session(token_hash):
    with connection() as conn:
        row = conn.execute("""SELECT s.token_hash,s.csrf_token,s.expires_at,s.last_seen_at,
                                   u.id AS user_id,u.username,u.must_change_password,u.enabled
                            FROM tbl_sessions s JOIN tbl_users u ON u.id=s.user_id
                            WHERE s.token_hash=?""", (token_hash,)).fetchone()
    return dict(row) if row else None


def touch_session(token_hash):
    with connection(write=True) as conn:
        conn.execute("UPDATE tbl_sessions SET last_seen_at=? WHERE token_hash=?", (int(time.time()), token_hash))


def delete_session(token_hash):
    with connection(write=True) as conn:
        conn.execute("DELETE FROM tbl_sessions WHERE token_hash=?", (token_hash,))


def delete_expired_sessions(now=None):
    with connection(write=True) as conn:
        return conn.execute("DELETE FROM tbl_sessions WHERE expires_at<=?", (int(now or time.time()),)).rowcount


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
    cache_name = f"{_PUBLIC_KEY_CACHE_PREFIX}list"
    if public:
        cached = _cache_get(cache_name)
        if cached is not None: return cached
    with connection() as conn:
        rows = [_row_to_dict(row) for row in conn.execute(
            "SELECT * FROM tbl_keys ORDER BY CASE WHEN sort_order=0 THEN 1 ELSE 0 END, sort_order ASC, id DESC")]
    if public:
        result = [public_key(row) for row in rows]
        _cache_set(cache_name, result)
        return result
    return rows


def get_key(key_id, public=False):
    cache_name = f"{_PUBLIC_KEY_CACHE_PREFIX}{int(key_id)}"
    if public:
        cached = _cache_get(cache_name)
        if cached is not None: return cached
    with connection() as conn:
        row = conn.execute("SELECT * FROM tbl_keys WHERE id=?", (key_id,)).fetchone()
        entry = _row_to_dict(row) if row else None
    if public:
        result = public_key(entry)
        if result: _cache_set(cache_name, result)
        return result
    return entry



def add_key(data):
    with connection(write=True) as conn:
        sort_order = _next_sort_order(conn)
        cur = conn.execute("""INSERT INTO tbl_keys
            (name,base_url,api_key,status,monitor_enabled,interval_sec,notes,created_at,check_model,sort_order,check_path)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (data.get("name", ""), data["base_url"], data["api_key"], "unknown",
             int(bool(data.get("monitor_enabled", 1))), data.get("interval_sec"), data.get("notes", ""),
             int(time.time()), data.get("check_model", ""), sort_order, data.get("check_path", "")))
        key_id = cur.lastrowid
    touch_list_generation()
    return key_id


def add_keys_batch(items):
    ids = []
    skipped_duplicate = 0
    with connection(write=True) as conn:
        existing = {(r["base_url"], r["api_key"]) for r in conn.execute("SELECT base_url,api_key FROM tbl_keys")}
        sort_order = _next_sort_order(conn)
        for item in items:
            marker = (item["base_url"], item["api_key"])
            if marker in existing:
                skipped_duplicate += 1
                continue
            existing.add(marker)
            cur = conn.execute("""INSERT INTO tbl_keys
            (name,base_url,api_key,status,monitor_enabled,interval_sec,notes,created_at,check_model,sort_order,check_path)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (item.get("name", ""), marker[0], marker[1], "unknown",
                 int(bool(item.get("monitor_enabled", 1))), item.get("interval_sec"), item.get("notes", ""),
                 int(time.time()), item.get("check_model", ""), sort_order, item.get("check_path", "")))
            ids.append(cur.lastrowid)
            sort_order += 10
        touch_list_generation()
    return ids, skipped_duplicate

def _next_sort_order(conn):
    value = conn.execute("SELECT MIN(sort_order) FROM tbl_keys").fetchone()[0]
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
            "SELECT id FROM tbl_keys ORDER BY CASE WHEN sort_order=0 THEN 1 ELSE 0 END, sort_order ASC, id DESC")]
        existing_set = set(existing)
        requested = [key_id for key_id in ordered_ids if key_id in existing_set]
        requested_set = set(requested)
        final_ids = requested + [key_id for key_id in existing if key_id not in requested_set]
        for index, key_id in enumerate(final_ids, start=1):
            conn.execute("UPDATE tbl_keys SET sort_order=? WHERE id=?", (index * 10, key_id))
    touch_list_generation()
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
        cur = conn.execute(f"UPDATE tbl_keys SET {', '.join(fields)} WHERE id=?", (*values, key_id))
        ok = cur.rowcount > 0
    if ok:
        touch_list_generation()
    return ok


def delete_keys(ids):
    if not ids:
        return 0
    with connection(write=True) as conn:
        marks = ",".join("?" for _ in ids)
        count = conn.execute(f"DELETE FROM tbl_keys WHERE id IN ({marks})", list(ids)).rowcount
    if count:
        touch_list_generation()
    return count


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
        conn.execute(f"UPDATE tbl_keys SET {', '.join(sets)} WHERE id=?", (*values, key_id))
    touch_list_generation()


def update_model_status(key_id, status, latency_ms, error):
    with connection(write=True) as conn:
        conn.execute("""UPDATE tbl_keys SET model_status=?, model_latency_ms=?, model_last_error=?,
                      model_last_check_at=? WHERE id=?""",
                     (status, latency_ms, (error or "")[:300], int(time.time()), key_id))
    touch_list_generation()


def get_due_keys(now, up_interval, down_interval, limit=None):
    """Return monitor-enabled keys that are due, oldest last_check_at first.

    limit: optional max rows (used by monitor tick cap / jitter-by-batch).
    """
    with connection() as conn:
        rows = conn.execute("SELECT * FROM tbl_keys WHERE monitor_enabled=1").fetchall()
    due = []
    for row in rows:
        item = _row_to_dict(row)
        interval = item.get("interval_sec") or (down_interval if item["status"] == "down" else up_interval)
        if now - (item.get("last_check_at") or 0) >= int(interval):
            due.append(item)
    due.sort(key=lambda item: (item.get("last_check_at") or 0, item.get("id") or 0))
    if limit is not None:
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = None
        if limit is not None and limit >= 0:
            due = due[:limit]
    return due
