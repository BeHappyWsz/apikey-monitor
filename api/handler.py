# -*- coding: utf-8 -*-
import json
import mimetypes
import os
import uuid
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit

from api.router import route, ApiError
from services.auth_service import AUTH
from services import list_events
import db
from api.validators import MAX_JSON_BODY, MAX_IMPORT_BODY
from version import USER_AGENT

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")

# Client closed the socket while we were writing a response.
# On Windows this commonly surfaces as ConnectionAbortedError (WinError 10053).
_CLIENT_DISCONNECT = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)


class Handler(BaseHTTPRequestHandler):
    server_version = USER_AGENT

    def log_message(self, fmt, *args):
        pass

    def _json(self, value, status=200, extra_headers=None):
        raw = json.dumps(value, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            for name, header_value in (extra_headers or {}).items():
                self.send_header(name, header_value)
            self._security_headers()
            self.end_headers()
            self.wfile.write(raw)
        except _CLIENT_DISCONNECT:
            # Client already gone; nothing useful left to report.
            pass

    def _error(self, status, code, message, request_id):
        self._json({"error": code, "message": message, "request_id": request_id}, status)

    def _body(self, path):
        try: length = int(self.headers.get("Content-Length", "0"))
        except ValueError: raise ApiError(400, "invalid_length", "Content-Length 无效")
        limit = MAX_IMPORT_BODY if path == "/api/import/parse" else MAX_JSON_BODY
        if length > limit: raise ApiError(413, "body_too_large", f"请求体超过 {limit // 1024}KB 限制")
        if not length: return {}
        try: return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception: raise ApiError(400, "invalid_json", "JSON 格式无效")

    def _dispatch(self, method):
        request_id = uuid.uuid4().hex[:12]
        parsed = urlsplit(self.path)
        try:
            body = self._body(parsed.path) if method in ("POST", "PUT") else None
            cookie = SimpleCookie()
            cookie.load(self.headers.get("Cookie", ""))
            request = {
                "cookies": {key: morsel.value for key, morsel in cookie.items()},
                "source_ip": self.client_address[0],
                "forwarded_proto": self.headers.get("X-Forwarded-Proto", ""),
                "csrf_token": self.headers.get("X-CSRF-Token", ""),
            }
            result = route(method, parsed.path, parsed.query, body, self.server, request)
            if len(result) == 3:
                status, payload, headers = result
            else:
                status, payload = result
                headers = None
            self._json(payload, status, headers)
        except ApiError as exc:
            self._error(exc.status, exc.code, exc.message, request_id)
        except _CLIENT_DISCONNECT:
            pass
        except Exception as exc:
            # Still answer with 500 when possible; disconnect during that write is ignored in _json.
            self._error(500, "internal_error", str(exc)[:200] or "服务器内部错误", request_id)


    def _sse_write(self, chunk):
        data = chunk if isinstance(chunk, (bytes, bytearray)) else str(chunk).encode("utf-8")
        self.wfile.write(data)
        self.wfile.flush()

    def _sse_keys_events(self):
        """Authenticated text/event-stream of list revision changes."""
        request_id = uuid.uuid4().hex[:12]
        headers_sent = False
        try:
            cookie = SimpleCookie()
            cookie.load(self.headers.get("Cookie", ""))
            cookies = {key: morsel.value for key, morsel in cookie.items()}
            session = AUTH.current(cookies.get("apikeymonitor_session", ""))
            if not session:
                self._error(401, "unauthenticated", "请先登录", request_id)
                return
            if session["user"].get("must_change_password"):
                self._error(403, "password_change_required", "请先修改初始密码", request_id)
                return

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self._security_headers()
            self.end_headers()
            headers_sent = True

            seq, _ = list_events.snapshot()
            revision = db.get_list_revision()
            payload = json.dumps({"revision": revision}, ensure_ascii=False)
            self._sse_write(f"event: revision\ndata: {payload}\n\n")

            # Long-lived stream: wake on list mutations or emit heartbeat comments.
            while True:
                new_seq, new_rev = list_events.wait_list_change(seq, timeout=20.0)
                if new_seq != seq:
                    seq = new_seq
                    rev = new_rev or db.get_list_revision()
                    payload = json.dumps({"revision": rev}, ensure_ascii=False)
                    self._sse_write(f"event: revision\ndata: {payload}\n\n")
                else:
                    self._sse_write(": ping\n\n")
        except _CLIENT_DISCONNECT:
            pass
        except Exception as exc:
            if not headers_sent:
                try:
                    # Once an SSE response starts, a JSON error would corrupt
                    # the event stream. The client will reconnect instead.
                    self._error(500, "internal_error", str(exc)[:200] or "服务器内部错误", request_id)
                except Exception:
                    pass

    def do_GET(self):
        parsed = urlsplit(self.path)
        if parsed.path == "/api/keys/events":
            self._sse_keys_events()
        elif parsed.path == "/" or parsed.path.startswith("/static/"):
            self._static("index.html" if parsed.path == "/" else parsed.path[len("/static/"):])
        else:
            self._dispatch("GET")
    def do_POST(self): self._dispatch("POST")
    def do_PUT(self): self._dispatch("PUT")
    def do_DELETE(self): self._dispatch("DELETE")

    def _static(self, relative):
        relative = relative.lstrip("/")
        path = os.path.abspath(os.path.join(STATIC_DIR, relative))
        try:
            if os.path.commonpath((STATIC_DIR, path)) != STATIC_DIR: raise ValueError
        except ValueError:
            self.send_error(403); return
        if not os.path.isfile(path): self.send_error(404); return
        with open(path, "rb") as stream: raw = stream.read()
        content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
        try:
            self.send_response(200)
            self.send_header("Content-Type", content_type + ("; charset=utf-8" if content_type.startswith("text/") or content_type.endswith("javascript") else ""))
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-cache")
            self._security_headers()
            self.end_headers()
            self.wfile.write(raw)
        except _CLIENT_DISCONNECT:
            pass

    def _security_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'")
