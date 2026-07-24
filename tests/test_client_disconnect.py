# -*- coding: utf-8 -*-
import io
import sys
import unittest

from api.handler import is_client_disconnect
from app import AppServer


class ClientDisconnectTests(unittest.TestCase):
    def test_is_client_disconnect_recognizes_windows_abort(self):
        self.assertTrue(is_client_disconnect(ConnectionAbortedError(10053, "aborted")))
        self.assertTrue(is_client_disconnect(ConnectionResetError()))
        self.assertTrue(is_client_disconnect(BrokenPipeError()))
        self.assertTrue(is_client_disconnect(OSError(22, "x", None, 10053)))
        self.assertFalse(is_client_disconnect(ValueError("nope")))

    def test_appserver_handle_error_swallows_abort_traceback(self):
        server = AppServer.__new__(AppServer)
        buf = io.StringIO()
        try:
            raise ConnectionAbortedError(10053, "software aborted an established connection")
        except ConnectionAbortedError:
            old = sys.stderr
            sys.stderr = buf
            try:
                server.handle_error(None, ("127.0.0.1", 52173))
            finally:
                sys.stderr = old
        self.assertEqual(buf.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
