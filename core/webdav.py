# -*- coding: utf-8 -*-
"""Zero-dependency WebDAV client (urllib) for optional cloud sync.

Pure functions: callers pass credentials explicitly, so nothing secret is read
from the DB here. Transport/HTTP errors are normalised into ``WebDAVError`` with
redacted messages so credentials never surface in API/UI error text.

Public surface: ``build_url``, ``test_connection``, ``upload``, ``download``.
"""
import base64
import re
import urllib.error
import urllib.request
from urllib.parse import urlsplit, urlunsplit

MAX_REMOTE_BYTES = 8 * 1024 * 1024  # download size guard
_USER_AGENT = "apikey-monitor/sync"

_SEG_RE = re.compile(r"/{2,}")
_TRAVERSAL_RE = re.compile(r"(^|/)\.\.?(/|$)")

_HTTP_CODE = {
    401: "auth_error", 403: "auth_error",
    404: "not_found", 405: "bad_method", 409: "missing_parent",
}
_HTTP_MSG = {
    401: "WebDAV 认证失败（用户名 / 应用密码错误）",
    403: "WebDAV 拒绝访问",
    404: "远程文件不存在",
    405: "WebDAV 方法不被允许",
    409: "远程父目录不存在",
}


class WebDAVError(Exception):
    """Normalised WebDAV failure.

    ``code`` is one of: config_error, auth_error, not_found, bad_method,
    missing_parent, server_error, connection_error, http_error.
    """

    def __init__(self, code, message, status=0):
        super().__init__(message)
        self.code = code
        self.status = status


def _redact(text):
    """Strip userinfo (user:pass@) from anything that looks like a URL."""
    text = str(text or "")
    if "://" in text and "@" in text:
        head, sep, tail = text.partition("://")
        if sep and "@" in tail:
            text = head + "://" + tail.split("@", 1)[1]
    return text[:200] or "webdav error"


def build_url(server, remote_path):
    """Join a WebDAV server root and a relative remote path.

    Rejects absolute URLs, query/fragment, and ``..`` traversal in the remote
    path. Always returns an absolute http(s) URL with no credentials.
    """
    server = str(server or "").strip()
    remote_path = str(remote_path or "").strip()
    if not server or "://" not in server:
        raise WebDAVError("config_error", "WebDAV 服务器未配置或缺少 http(s)://")
    parts = urlsplit(server)
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        raise WebDAVError("config_error", "WebDAV 服务器地址无效")
    if parts.username or parts.password:
        raise WebDAVError("config_error", "WebDAV 服务器地址不得包含账号密码")
    if not remote_path:
        raise WebDAVError("config_error", "WebDAV 远程路径未配置")
    if "://" in remote_path:
        raise WebDAVError("config_error", "远程路径必须是相对路径")
    seg = remote_path if remote_path.startswith("/") else "/" + remote_path
    rp = urlsplit(seg)
    if rp.scheme or rp.netloc or rp.query or rp.fragment:
        raise WebDAVError("config_error", "远程路径必须是相对路径，且不含 query/fragment")
    if _TRAVERSAL_RE.search(seg):
        raise WebDAVError("config_error", "远程路径不允许包含 ..")
    seg = _SEG_RE.sub("/", seg)
    base_path = (parts.path or "").rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc, base_path + seg, "", ""))


def _auth_header(username, password):
    username = str(username or "")
    if not username:
        raise WebDAVError("config_error", "WebDAV 用户名未配置")
    token = base64.b64encode(f"{username}:{password or ''}".encode("utf-8")).decode("ascii")
    return "Basic " + token


def _request(method, url, auth, body=None, timeout=15, headers=None):
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", auth)
    req.add_header("User-Agent", _USER_AGENT)
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = response.read(MAX_REMOTE_BYTES + 1)[:MAX_REMOTE_BYTES]
            return response.status, dict(response.headers), payload
    except urllib.error.HTTPError as exc:
        code = _HTTP_CODE.get(exc.code, "server_error" if 500 <= exc.code < 600 else "http_error")
        raise WebDAVError(code, _HTTP_MSG.get(exc.code) or f"WebDAV {method} 失败：HTTP {exc.code}", exc.code)
    except urllib.error.URLError as exc:
        raise WebDAVError("connection_error", _redact(f"无法连接 WebDAV：{exc.reason}"))
    except WebDAVError:
        raise
    except Exception as exc:  # socket timeouts, connection resets, etc.
        raise WebDAVError("connection_error", _redact(f"WebDAV 请求失败：{exc}"))


def _head(url, auth, timeout):
    try:
        _, headers, _ = _request("HEAD", url, auth, timeout=timeout)
        return {"ok": True, "exists": True, "last_modified": headers.get("Last-Modified")}
    except WebDAVError as exc:
        if exc.code == "not_found":
            return {"ok": True, "exists": False, "last_modified": None}
        raise


def test_connection(server, username, password, remote_path, timeout=15):
    """Reach the remote and report whether the file exists (with Last-Modified).

    Returns ``{"ok": True, "exists": bool, "last_modified": str|None}``.
    Tries PROPFIND (Depth 0) first, falling back to HEAD when unsupported.
    """
    url = build_url(server, remote_path)
    auth = _auth_header(username, password)
    try:
        _, headers, _ = _request("PROPFIND", url, auth, timeout=timeout, headers={"Depth": "0"})
        return {"ok": True, "exists": True, "last_modified": headers.get("Last-Modified")}
    except WebDAVError as exc:
        if exc.code == "not_found":
            return {"ok": True, "exists": False, "last_modified": None}
        if exc.code == "bad_method":
            return _head(url, auth, timeout)
        raise


def upload(server, username, password, remote_path, data, timeout=30):
    """PUT ``data`` (bytes) to the remote path. Returns last-modified/etag info."""
    if not isinstance(data, (bytes, bytearray)):
        raise WebDAVError("config_error", "上传数据必须是字节")
    url = build_url(server, remote_path)
    auth = _auth_header(username, password)
    _, headers, _ = _request("PUT", url, auth, body=bytes(data), timeout=timeout,
                             headers={"Content-Type": "application/json; charset=utf-8"})
    return {"ok": True, "last_modified": headers.get("Last-Modified"), "etag": headers.get("ETag")}


def download(server, username, password, remote_path, timeout=30):
    """GET the remote file. Returns ``{"ok": True, "data": bytes, "last_modified": ...}``."""
    url = build_url(server, remote_path)
    auth = _auth_header(username, password)
    _, headers, payload = _request("GET", url, auth, timeout=timeout)
    return {"ok": True, "data": payload, "last_modified": headers.get("Last-Modified")}
