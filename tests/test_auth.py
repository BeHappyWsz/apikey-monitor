# -*- coding: utf-8 -*-
import os
import tempfile
import unittest

import db
from services.auth_service import AuthError, AuthService


class AuthServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_db, self.old_config = db.DB_PATH, db.CONFIG_PATH
        self.old_bootstrap = os.environ.get("APIKEYCONFIG_BOOTSTRAP_PASSWORD")
        db.DB_PATH = os.path.join(self.temp.name, "data.db")
        db.CONFIG_PATH = os.path.join(self.temp.name, "config.json")
        with open(db.CONFIG_PATH, "w", encoding="utf-8") as stream:
            stream.write('{"_bootstrap_admin_username":"admin","_bootstrap_admin_password":"correct-horse-battery-staple"}')
        os.environ.pop("APIKEYCONFIG_BOOTSTRAP_PASSWORD", None)
        db.init_db()
        self.auth = AuthService()

    def tearDown(self):
        db.DB_PATH, db.CONFIG_PATH = self.old_db, self.old_config
        if self.old_bootstrap is None:
            os.environ.pop("APIKEYCONFIG_BOOTSTRAP_PASSWORD", None)
        else:
            os.environ["APIKEYCONFIG_BOOTSTRAP_PASSWORD"] = self.old_bootstrap
        self.temp.cleanup()

    def test_bootstrap_hashes_password_and_issues_hashed_session(self):
        self.assertTrue(self.auth.ensure_bootstrap())
        user = db.get_user_by_username("admin")
        self.assertNotEqual(user["password_hash"], "correct-horse-battery-staple")
        result = self.auth.login("admin", "correct-horse-battery-staple", "127.0.0.1")
        self.assertNotIn(result["token"], str(db.get_session(self.auth._token_hash(result["token"]))))
        current = self.auth.current(result["token"])
        self.assertEqual(current["user"]["username"], "admin")
        self.assertTrue(self.auth.csrf_valid(current, result["csrf_token"]))
        self.auth.logout(result["token"])
        self.assertIsNone(self.auth.current(result["token"]))

    def test_user_validation_and_login_rate_limit(self):
        self.auth.ensure_bootstrap()
        with self.assertRaises(AuthError):
            self.auth.create_user("bad user", "short")
        created = self.auth.create_user("second.admin", "another-secure-password")
        self.assertEqual(created["username"], "second.admin")
        for _ in range(5):
            with self.assertRaises(AuthError) as ctx:
                self.auth.login("admin", "wrong-password", "127.0.0.1")
            self.assertEqual(ctx.exception.code, "invalid_login")
        with self.assertRaises(AuthError) as ctx:
            self.auth.login("admin", "wrong-password", "127.0.0.1")
        self.assertEqual(ctx.exception.code, "login_rate_limited")


if __name__ == "__main__":
    unittest.main()
