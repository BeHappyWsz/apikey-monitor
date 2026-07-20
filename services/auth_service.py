# -*- coding: utf-8 -*-
"""Local administrator authentication, opaque sessions, and CSRF protection."""
import hashlib
import hmac
import os
import re
import secrets
import threading
import time

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

import db

_USERNAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,63}\Z")
_SESSION_SECONDS = 8 * 60 * 60
_LOGIN_WINDOW_SECONDS = 15 * 60
_LOGIN_MAX_ATTEMPTS = 5
_PASSWORD_MIN_LENGTH = 12


class AuthError(ValueError):
    """Expected authentication failure with a stable API error code."""

    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.status = code, status


class AuthService:
    def __init__(self):
        self._hasher = PasswordHasher()
        self._attempts = {}
        self._attempt_lock = threading.Lock()
        self._dummy_hash = self._hasher.hash("not-a-real-password")

    @staticmethod
    def _token_hash(token):
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize_username(value):
        username = str(value or "").strip()
        if not _USERNAME_RE.fullmatch(username):
            raise AuthError("invalid_username", "用户名需为 3-64 位字母、数字或 ._-", 400)
        return username

    @staticmethod
    def _validate_password(value):
        password = str(value or "")
        if len(password) < _PASSWORD_MIN_LENGTH:
            raise AuthError("invalid_password", "密码至少需要 12 个字符", 400)
        return password

    def ensure_bootstrap(self):
        """Create the first local administrator when the deployment supplied a secret."""
        if db.count_users():
            return False
        password = db.get_bootstrap_admin_password()
        username = self._normalize_username(db.get_bootstrap_admin_username())
        self._validate_password(password)
        try:
            db.create_user(username, self._hasher.hash(password), must_change_password=True)
        except Exception:
            # Another startup may have won the race; never expose a password in this path.
            if not db.count_users():
                raise
        return True

    def bootstrap_required(self):
        return not bool(db.count_users())

    def _attempt_key(self, username, source_ip):
        return f"{source_ip or '-'}:{username.lower()}"

    def _check_rate_limit(self, username, source_ip):
        key, now = self._attempt_key(username, source_ip), time.monotonic()
        with self._attempt_lock:
            attempts = [stamp for stamp in self._attempts.get(key, []) if now - stamp < _LOGIN_WINDOW_SECONDS]
            self._attempts[key] = attempts
            if len(attempts) >= _LOGIN_MAX_ATTEMPTS:
                raise AuthError("login_rate_limited", "登录尝试过于频繁，请稍后再试", 429)

    def _record_failed_attempt(self, username, source_ip):
        key, now = self._attempt_key(username, source_ip), time.monotonic()
        with self._attempt_lock:
            attempts = [stamp for stamp in self._attempts.get(key, []) if now - stamp < _LOGIN_WINDOW_SECONDS]
            attempts.append(now)
            self._attempts[key] = attempts

    def _clear_attempts(self, username, source_ip):
        with self._attempt_lock:
            self._attempts.pop(self._attempt_key(username, source_ip), None)

    def login(self, username, password, source_ip):
        username = str(username or "").strip()
        self._check_rate_limit(username, source_ip)
        user = db.get_user_by_username(username)
        candidate_hash = user["password_hash"] if user else self._dummy_hash
        try:
            verified = self._hasher.verify(candidate_hash, str(password or ""))
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            verified = False
        if not user or not verified:
            self._record_failed_attempt(username, source_ip)
            raise AuthError("invalid_login", "用户名或密码错误", 401)
        if not user.get("enabled", True):
            raise AuthError("account_disabled", "该账号已被禁用，请联系管理员", 403)
        self._clear_attempts(username, source_ip)
        if self._hasher.check_needs_rehash(candidate_hash):
            db.update_user_password_hash(user["id"], self._hasher.hash(str(password)))
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        db.delete_expired_sessions()
        db.create_session(self._token_hash(token), user["id"], csrf, int(time.time()) + _SESSION_SECONDS)
        return {"token": token, "csrf_token": csrf, "user": {"id": user["id"], "username": user["username"],
                "must_change_password": bool(user.get("must_change_password"))}}

    def current(self, token):
        if not token:
            return None
        digest = self._token_hash(token)
        session = db.get_session(digest)
        if not session:
            return None
        if not session.get("enabled", True):
            db.delete_session(digest)
            return None
        if int(session["expires_at"]) <= int(time.time()):
            db.delete_session(digest)
            return None
        db.touch_session(digest)
        return {"token_hash": digest, "csrf_token": session["csrf_token"],
                "user": {"id": session["user_id"], "username": session["username"],
                         "must_change_password": bool(session.get("must_change_password"))}}

    def logout(self, token):
        if token:
            db.delete_session(self._token_hash(token))

    def create_user(self, username, password):
        username, password = self._normalize_username(username), self._validate_password(password)
        if db.get_user_by_username(username):
            raise AuthError("username_taken", "用户名已存在", 409)
        user_id = db.create_user(username, self._hasher.hash(password))
        return db.get_user(user_id)

    def set_user_enabled(self, actor_user_id, user_id, enabled):
        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            raise AuthError("user_not_found", "用户不存在", 404)
        enabled = bool(enabled)
        if user_id == int(actor_user_id) and not enabled:
            raise AuthError("cannot_disable_self", "不能禁用当前登录账号", 400)
        user = db.set_user_enabled(user_id, enabled)
        if not user:
            raise AuthError("user_not_found", "用户不存在", 404)
        return user

    def change_password(self, user_id, old_password, new_password):
        user = db.get_user_by_username(db.get_user(user_id)["username"])
        try:
            valid = self._hasher.verify(user["password_hash"], str(old_password or ""))
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            valid = False
        if not valid:
            raise AuthError("invalid_login", "当前密码错误", 401)
        db.update_user_password_hash(user_id, self._hasher.hash(self._validate_password(new_password)), must_change_password=False)

    @staticmethod
    def csrf_valid(session, token):
        return bool(token) and hmac.compare_digest(str(session.get("csrf_token", "")), str(token))

    @staticmethod
    def session_cookie(token, secure=False, clear=False):
        parts = ["apikeymonitor_session=" + ("" if clear else token), "Path=/", "HttpOnly", "SameSite=Lax"]
        if clear:
            parts.append("Max-Age=0")
        else:
            parts.append(f"Max-Age={_SESSION_SECONDS}")
        if secure:
            parts.append("Secure")
        return "; ".join(parts)


AUTH = AuthService()
