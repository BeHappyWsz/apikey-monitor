# -*- coding: utf-8 -*-
"""SQLite and JSON configuration persistence."""
import base64
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
    "serverHost": "127.0.0.1", "serverPort": "7878",
    "globalMonitorEnabled": "1", "globalIntervalSec": "300",
    "downRecheckIntervalSec": "120", "concurrency": "8",
    "requestTimeoutSec": "45", "autoClassifyOnAdd": "1",
    "uiRefreshIntervalSec": "15",
}
_SETTING_NAMES = {
    "serverHost": "服务监听地址",
    "serverPort": "服务监听端口",
    "globalMonitorEnabled": "全局监测开关",
    "globalIntervalSec": "正常 Key 监测间隔（秒）",
    "downRecheckIntervalSec": "异常 Key 复检间隔（秒）",
    "concurrency": "监测并发数",
    "requestTimeoutSec": "探测请求超时（秒）",
    "autoClassifyOnAdd": "新增 Key 自动识别开关",
    "uiRefreshIntervalSec": "前端列表刷新间隔（秒）",
    "webdavServer": "WebDAV 服务器地址",
    "webdavUsername": "WebDAV 用户名",
    "webdavRemotePath": "WebDAV 远程备份路径",
    "webdavPassword": "WebDAV 应用密码",
    "webdavLastSync": "WebDAV 最近同步状态",
}

# Settings stored in tbl_settings use descriptive names. Browser visibility is
# an explicit policy, never a side effect of a leading underscore.
_NON_PUBLIC_SETTING_KEYS = frozenset(("webdavPassword", "webdavLastSync"))


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


def _camel_case_setting_key(key):
    """Return the persisted camelCase form for a tbl_settings key."""
    raw = str(key or "")
    parts = [part for part in raw.strip("_").split("_") if part]
    if not parts:
        return raw
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


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
        out.update({_camel_case_setting_key(key): str(value)
                    for key, value in data.items() if not key.startswith("_")})
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
                      ("model_last_error", "TEXT DEFAULT ''"), ("model_verification_version", "INTEGER DEFAULT 0"),
                      ("next_check_at", "INTEGER DEFAULT 0"),
                      ("sort_order", "INTEGER DEFAULT 0"), ("check_path", "TEXT DEFAULT ''"),
                      ("openai_status", "TEXT DEFAULT 'unknown'"), ("anthropic_status", "TEXT DEFAULT 'unknown'"),
                      ("created_at", "INTEGER")):
        if col not in cols:
            conn.execute(f"ALTER TABLE tbl_keys ADD COLUMN {col} {decl}")
    # Stamp legacy rows that predate the created_at column with the current
    # time, so the dashboard has a usable reference for every entry.
    backfill_now = int(time.time())
    conn.execute("UPDATE tbl_keys SET created_at=? WHERE created_at IS NULL OR created_at=0",
                 (backfill_now,))
    settings_cols = {row[1] for row in conn.execute("PRAGMA table_info(tbl_settings)")}
    if "name" not in settings_cols:
        conn.execute("ALTER TABLE tbl_settings ADD COLUMN name TEXT NOT NULL DEFAULT ''")
    _migrate_setting_keys(conn)
    _backfill_setting_names(conn)
    conn.execute("PRAGMA user_version=13")
    _to_row = conn.execute("SELECT v FROM tbl_settings WHERE k='requestTimeoutSec'").fetchone()
    if _to_row and str(_to_row["v"]) == "15":
        conn.execute("UPDATE tbl_settings SET v='45' WHERE k='requestTimeoutSec'")
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


def _migrate_setting_keys(conn):
    """Normalize every persisted key; pre-existing camelCase rows win conflicts."""
    keys = {row["k"] for row in conn.execute("SELECT k FROM tbl_settings").fetchall()}
    for old_key in tuple(keys):
        new_key = _camel_case_setting_key(old_key)
        if new_key == old_key:
            continue
        if new_key in keys:
            conn.execute("DELETE FROM tbl_settings WHERE k=?", (old_key,))
        else:
            conn.execute("UPDATE tbl_settings SET k=? WHERE k=?", (new_key, old_key))
            keys.add(new_key)


def _setting_rows(items):
    normalized = {_camel_case_setting_key(key): str(value) for key, value in items.items()}
    return [(key, value, _setting_name(key)) for key, value in normalized.items()]


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
            supports_openai INTEGER DEFAULT 0, openai_status TEXT DEFAULT 'unknown', anthropic_status TEXT DEFAULT 'unknown',
            models TEXT DEFAULT '[]', status TEXT DEFAULT 'unknown',
            latency_ms INTEGER, last_check_at INTEGER, last_error TEXT DEFAULT '',
            monitor_enabled INTEGER DEFAULT 1, interval_sec INTEGER, notes TEXT DEFAULT '',
            created_at INTEGER, check_model TEXT DEFAULT '', model_status TEXT DEFAULT 'unknown',
            model_latency_ms INTEGER, model_last_check_at INTEGER, model_last_error TEXT DEFAULT '',
            model_verification_version INTEGER DEFAULT 0,
            next_check_at INTEGER DEFAULT 0,
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
        conn.execute("CREATE INDEX IF NOT EXISTS idx_keys_monitor_next ON tbl_keys(monitor_enabled,next_check_at,last_check_at,id)")
        if conn.execute("SELECT 1 FROM tbl_settings LIMIT 1").fetchone() is None:
            conn.executemany("INSERT INTO tbl_settings(k,v,name) VALUES(?,?,?)", _setting_rows(_load_defaults()))


def _init_mysql():
    with connection(write=True) as conn:
        _migrate_table_names_mysql(conn)
        statements = [
            """CREATE TABLE IF NOT EXISTS tbl_keys (id BIGINT PRIMARY KEY AUTO_INCREMENT,name TEXT,base_url TEXT NOT NULL,api_key TEXT NOT NULL,supports_anthropic TINYINT DEFAULT 0,supports_openai TINYINT DEFAULT 0,openai_status VARCHAR(32) DEFAULT 'unknown',anthropic_status VARCHAR(32) DEFAULT 'unknown',models LONGTEXT,status VARCHAR(32) DEFAULT 'unknown',latency_ms BIGINT,last_check_at BIGINT,last_error TEXT,monitor_enabled TINYINT DEFAULT 1,interval_sec BIGINT,notes TEXT,created_at BIGINT,check_model TEXT,model_status VARCHAR(32) DEFAULT 'unknown',model_latency_ms BIGINT,model_last_check_at BIGINT,model_last_error TEXT,model_verification_version TINYINT DEFAULT 0,next_check_at BIGINT DEFAULT 0,sort_order BIGINT DEFAULT 0,check_path TEXT,INDEX idx_keys_monitor_due (monitor_enabled,last_check_at),INDEX idx_keys_monitor_next (monitor_enabled,next_check_at,last_check_at,id)) CHARACTER SET utf8mb4""",
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
        key_columns = {row["COLUMN_NAME"] for row in conn.execute(
            "SELECT COLUMN_NAME FROM information_schema.columns "
            "WHERE table_schema=DATABASE() AND table_name='tbl_keys'")}
        for column in ("openai_status", "anthropic_status", "model_verification_version", "next_check_at", "created_at"):
            if column not in key_columns:
                declaration = (
                    "BIGINT DEFAULT 0" if column == "next_check_at"
                    else ("TINYINT DEFAULT 0" if column == "model_verification_version"
                          else ("VARCHAR(32) DEFAULT 'unknown'" if column in ("openai_status", "anthropic_status")
                                else "BIGINT"))
                )
                conn.execute(f"ALTER TABLE tbl_keys ADD COLUMN {column} {declaration}")
        # Stamp legacy rows missing a created_at value with the migration time
        # so the dashboard has a usable reference for every entry.
        backfill_now = int(time.time())
        conn.execute("UPDATE tbl_keys SET created_at=? WHERE created_at IS NULL OR created_at=0",
                     (backfill_now,))
        index_names = {row["INDEX_NAME"] for row in conn.execute(
            "SELECT INDEX_NAME FROM information_schema.statistics "
            "WHERE table_schema=DATABASE() AND table_name='tbl_keys'")}
        if "idx_keys_monitor_next" not in index_names:
            conn.execute("CREATE INDEX idx_keys_monitor_next ON tbl_keys(monitor_enabled,next_check_at,last_check_at,id)")
        settings_columns = {row["COLUMN_NAME"] for row in conn.execute(
            "SELECT COLUMN_NAME FROM information_schema.columns "
            "WHERE table_schema=DATABASE() AND table_name='tbl_settings'")}
        if "name" not in settings_columns:
            conn.execute("ALTER TABLE tbl_settings ADD COLUMN name VARCHAR(255) NOT NULL DEFAULT ''")
        _migrate_setting_keys(conn)
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
              if key not in _NON_PUBLIC_SETTING_KEYS and not key.startswith("_")}
    _cache_set(_PUBLIC_SETTINGS_CACHE_KEY, values)
    return values


def set_settings(items):
    """Upsert settings rows. Runtime writes stay in the DB only — config.json
    is a read-only seed and is never rewritten."""
    normalized = {_camel_case_setting_key(key): str(value) for key, value in items.items()}
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


def list_keys(public=False, sort="default"):
    sort = _normalize_sort(sort)
    cache_name = f"{_PUBLIC_KEY_CACHE_PREFIX}list"
    if public:
        cached = _cache_get(cache_name)
        if cached is not None: return cached
    order_by = _page_order_by(sort)
    with connection() as conn:
        rows = [_row_to_dict(row) for row in conn.execute(f"SELECT * FROM tbl_keys ORDER BY {order_by}")]
    if public:
        result = [public_key(row) for row in rows]
        _cache_set(cache_name, result)
        return result
    return rows


_PAGE_STATUSES = {
    "all": (), "up": ("up",), "down": ("down",), "auth_error": ("auth_error",),
    "unknown": ("unknown",), "issue": ("rate_limited", "degraded"),
    "problem": ("down", "auth_error", "rate_limited", "degraded", "unknown"),
}


_SORT_KEYS = ("default", "created_desc", "created_asc")
_SORT_ORDER_BY = {
    "default": "CASE WHEN sort_order=0 THEN 1 ELSE 0 END ASC, sort_order ASC, id DESC",
    "created_desc": "created_at DESC, id DESC",
    "created_asc": "created_at ASC, id ASC",
}


def _page_cursor_encode(sort, group, anchor, key_id):
    """Encode a stable cursor. ``group`` is 0 for manually ordered rows or 1 for
    auto rows; ``anchor`` is ``sort_order`` for ``default`` and ``created_at`` for
    the created_* sorts."""
    payload = {"s": str(sort), "g": int(group), "a": int(anchor), "k": int(key_id)}
    raw = json.dumps(payload, separators=(",", ":")).encode("ascii")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _page_cursor_decode(value, expected_sort=None):
    """Decode a cursor; raises ``ValueError`` if it is malformed or was issued
    by a different sort. Legacy list cursors are read as ``sort=default`` for
    backwards compatibility."""
    if not value:
        return None
    try:
        padded = str(value) + "=" * (-len(str(value)) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except Exception as exc:
        raise ValueError("invalid page cursor") from exc
    if isinstance(decoded, list) and len(decoded) == 3:
        if expected_sort and expected_sort != "default":
            raise ValueError("invalid page cursor")
        group, anchor, key_id = decoded
        sort = "default"
    elif isinstance(decoded, dict):
        sort = str(decoded.get("s") or "default")
        if expected_sort and sort != expected_sort:
            raise ValueError("invalid page cursor")
        group = decoded.get("g")
        anchor = decoded.get("a")
        key_id = decoded.get("k")
    else:
        raise ValueError("invalid page cursor")
    try:
        group, anchor, key_id = int(group), int(anchor), int(key_id)
    except (TypeError, ValueError):
        raise ValueError("invalid page cursor")
    if group not in (0, 1) or key_id <= 0:
        raise ValueError("invalid page cursor")
    return sort, group, anchor, key_id


def _page_order_by(sort):
    return _SORT_ORDER_BY.get(sort) or _SORT_ORDER_BY["default"]


def _normalize_sort(sort):
    value = str(sort or "default")
    if value not in _SORT_KEYS:
        raise ValueError("invalid sort")
    return value


def _page_conditions(status_filter="all", search=""):
    if status_filter not in _PAGE_STATUSES:
        raise ValueError("invalid status filter")
    conditions, values = [], []
    statuses = _PAGE_STATUSES[status_filter]
    if statuses:
        conditions.append("status IN (" + ",".join("?" for _ in statuses) + ")")
        values.extend(statuses)
    term = str(search or "").strip().lower()
    if term:
        like = f"%{term}%"
        conditions.append("(LOWER(COALESCE(name,'')) LIKE ? OR LOWER(COALESCE(base_url,'')) LIKE ? "
                          "OR LOWER(COALESCE(check_model,'')) LIKE ? OR LOWER(COALESCE(notes,'')) LIKE ? "
                          "OR LOWER(COALESCE(models,'')) LIKE ?)")
        values.extend([like] * 5)
    return conditions, values


def _page_summary(conn, conditions, values):
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    rows = conn.execute(f"SELECT status, COUNT(*) AS c FROM tbl_keys{where} GROUP BY status", values).fetchall()
    latency_row = conn.execute(f"SELECT AVG(latency_ms) AS average_latency_ms FROM tbl_keys{where}", values).fetchone()
    counts = {str(row["status"] or "unknown"): int(row["c"]) for row in rows}
    total = sum(counts.values())
    return {
        "all": total,
        "up": counts.get("up", 0),
        "down": counts.get("down", 0),
        "auth_error": counts.get("auth_error", 0),
        "unknown": counts.get("unknown", 0),
        "issue": counts.get("rate_limited", 0) + counts.get("degraded", 0),
        "problem": total - counts.get("up", 0),
        "avg_latency_ms": round(float(latency_row["average_latency_ms"])) if latency_row["average_latency_ms"] is not None else None,
    }


def list_keys_page(limit=50, cursor="", status_filter="all", search="", sort="default"):
    """Return one stable-order public page without shipping the entire key list."""
    sort = _normalize_sort(sort)
    limit = max(1, min(int(limit), 100))
    facet_conditions, facet_values = _page_conditions("all", search)
    base_conditions, base_values = _page_conditions(status_filter, search)
    cursor_parts = _page_cursor_decode(cursor, expected_sort=sort)
    conditions, values = list(base_conditions), list(base_values)
    order_by = _page_order_by(sort)
    if cursor_parts:
        decoded_sort, group, anchor, key_id = cursor_parts
        if decoded_sort != sort:
            raise ValueError("invalid page cursor")
        if sort == "default":
            conditions.append(
                "(CASE WHEN sort_order=0 THEN 1 ELSE 0 END>? OR "
                "(CASE WHEN sort_order=0 THEN 1 ELSE 0 END=? AND "
                "(sort_order>? OR (sort_order=? AND id<?))))"
            )
            values.extend([group, group, anchor, anchor, key_id])
        elif sort == "created_desc":
            # Order is created_at DESC, id DESC — the next row is strictly
            # smaller created_at, or equal created_at with a smaller id.
            conditions.append("(created_at<? OR (created_at=? AND id<?))")
            values.extend([anchor, anchor, key_id])
        else:  # created_asc — ASC, ASC
            conditions.append("(created_at>? OR (created_at=? AND id>?))")
            values.extend([anchor, anchor, key_id])
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    base_where = (" WHERE " + " AND ".join(base_conditions)) if base_conditions else ""
    with connection() as conn:
        rows = [_row_to_dict(row) for row in conn.execute(
            f"SELECT * FROM tbl_keys{where} ORDER BY {order_by} LIMIT ?",
            [*values, limit + 1]).fetchall()]
        summary = _page_summary(conn, facet_conditions, facet_values)
        total_row = conn.execute(f"SELECT COUNT(*) AS c FROM tbl_keys{base_where}", base_values).fetchone()
        total = int(total_row["c"])
    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = ""
    if has_more and items:
        last = items[-1]
        if sort == "default":
            next_cursor = _page_cursor_encode(sort,
                                             1 if int(last.get("sort_order") or 0) == 0 else 0,
                                             int(last.get("sort_order") or 0), int(last["id"]))
        else:
            next_cursor = _page_cursor_encode(sort, 0,
                                             int(last.get("created_at") or 0), int(last["id"]))
    return {"items": [public_key(row) for row in items], "next_cursor": next_cursor,
            "total": total,
            "summary": summary, "revision": get_list_revision()}


def move_key_before(key_id, before_id=None):
    """Move one key before another without requiring the browser to own all ids."""
    key_id = int(key_id)
    before_id = int(before_id) if before_id not in (None, "", 0) else None
    with connection(write=True) as conn:
        ids = [row["id"] for row in conn.execute(
            "SELECT id FROM tbl_keys ORDER BY CASE WHEN sort_order=0 THEN 1 ELSE 0 END, sort_order ASC, id DESC")]
        if key_id not in ids:
            return False
        ids.remove(key_id)
        if before_id is not None and before_id in ids:
            ids.insert(ids.index(before_id), key_id)
        else:
            ids.append(key_id)
        for index, item_id in enumerate(ids, start=1):
            conn.execute("UPDATE tbl_keys SET sort_order=? WHERE id=?", (index * 10, item_id))
    touch_list_generation()
    return True


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
        fields.extend(["status='unknown'", "supports_openai=0", "supports_anthropic=0", "openai_status='unknown'", "anthropic_status='unknown'", "models='[]'",
                       "latency_ms=NULL", "last_check_at=NULL", "last_error=''", "model_status='unknown'",
                       "model_latency_ms=NULL", "model_last_check_at=NULL", "model_last_error=''", "model_verification_version=0", "next_check_at=0"])
    elif "monitor_enabled" in data or "interval_sec" in data:
        # A newly enabled key or changed cadence should be reconsidered without
        # waiting for the previous schedule to expire.
        fields.append("next_check_at=0")
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


def update_status(key_id, status, latency_ms, error, supports_anthropic=None, supports_openai=None, models=None,
                  openai_status=None, anthropic_status=None, next_check_at=None):
    sets = ["status=?", "latency_ms=?", "last_error=?", "last_check_at=?"]
    values = [status, latency_ms, (error or "")[:300], int(time.time())]
    if supports_anthropic is not None:
        sets.append("supports_anthropic=?"); values.append(int(bool(supports_anthropic)))
    if supports_openai is not None:
        sets.append("supports_openai=?"); values.append(int(bool(supports_openai)))
    if models is not None:
        sets.append("models=?"); values.append(json.dumps(models[:200], ensure_ascii=False))
    if openai_status is not None:
        sets.append("openai_status=?"); values.append(openai_status)
    if anthropic_status is not None:
        sets.append("anthropic_status=?"); values.append(anthropic_status)
    if next_check_at is not None:
        sets.append("next_check_at=?"); values.append(int(next_check_at))
    with connection(write=True) as conn:
        conn.execute(f"UPDATE tbl_keys SET {', '.join(sets)} WHERE id=?", (*values, key_id))
    touch_list_generation()


def update_model_status(key_id, status, latency_ms, error, verification_version=1):
    with connection(write=True) as conn:
        conn.execute("""UPDATE tbl_keys SET model_status=?, model_latency_ms=?, model_last_error=?,
                      model_last_check_at=?, model_verification_version=? WHERE id=?""",
                     (status, latency_ms, (error or "")[:300], int(time.time()), verification_version, key_id))
    touch_list_generation()


def monitor_next_check_at(entry, status, settings, checked_at=None):
    """Calculate a paced next monitor time without retaining a failure counter.

    The status itself supplies a conservative, bounded backoff. A small
    deterministic jitter avoids an import of many keys creating a request herd
    on the same future second.
    """
    checked_at = int(time.time() if checked_at is None else checked_at)
    global_interval = max(30, int(settings.get("globalIntervalSec", 300) or 300))
    down_interval = max(30, int(settings.get("downRecheckIntervalSec", 120) or 120))
    interval = int(entry.get("interval_sec") or global_interval)
    if not entry.get("interval_sec") and status == "down":
        interval = down_interval
    if status == "degraded":
        interval = max(interval * 2, 600)
    elif status == "rate_limited":
        interval = max(interval * 4, 900)
    elif status == "auth_error":
        interval = max(interval * 12, 21600)
    spread = max(1, interval // 20)
    key_id = int(entry.get("id") or 0)
    jitter = ((key_id * 1103515245 + 12345) % (spread * 2 + 1)) - spread
    return checked_at + max(1, interval + jitter)


def get_due_keys(now, up_interval=None, down_interval=None, limit=None):
    """Return only due monitor rows through the indexed next-check schedule.

    `up_interval` and `down_interval` remain accepted for compatibility with
    existing callers; each result write now persists its own next due time.
    """
    try:
        cap = max(0, int(limit)) if limit is not None else 1000
    except (TypeError, ValueError):
        cap = 1000
    if not cap:
        return []
    with connection() as conn:
        rows = conn.execute(
            "SELECT * FROM tbl_keys WHERE monitor_enabled=1 AND next_check_at<=? "
            "ORDER BY next_check_at ASC,last_check_at ASC,id ASC LIMIT ?",
            (int(now), cap)).fetchall()
    return [_row_to_dict(row) for row in rows]
