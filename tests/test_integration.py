# -*- coding: utf-8 -*-
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_health(port, up=True, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/system/health", timeout=.5) as response:
                healthy = response.status == 200
        except Exception:
            healthy = False
        if healthy == up:
            return True
        time.sleep(.15)
    return False


def json_request(method, url, payload=None):
    raw = json.dumps(payload or {}).encode()
    request = urllib.request.Request(url, data=raw if method != "GET" else None,
                                     headers={"Content-Type": "application/json"}, method=method)
    with urllib.request.urlopen(request, timeout=3) as response:
        return response.status, json.loads(response.read())


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp.name, "data.db")
        self.config_path = os.path.join(self.temp.name, "config.json")
        self.runtime = os.path.join(self.temp.name, "runtime")
        self.env = os.environ.copy()
        self.env.update(APIKEYCONFIG_DB_PATH=self.db_path, APIKEYCONFIG_CONFIG_PATH=self.config_path,
                        APIKEYCONFIG_RUNTIME_DIR=self.runtime)
        self.processes = []

    def tearDown(self):
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired: process.kill()
        self.temp.cleanup()

    def start(self, port):
        process = subprocess.Popen([sys.executable, str(ROOT / "app.py"), "--host", "127.0.0.1",
                                    "--port", str(port), "--no-browser"], cwd=ROOT, env=self.env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.processes.append(process)
        self.assertTrue(wait_health(port), "temporary server did not become healthy")
        return process

    def test_api_smoke_and_request_limit(self):
        port = free_port(); self.start(port)
        status, data = json_request("GET", f"http://127.0.0.1:{port}/api/keys")
        self.assertEqual((status, data), (200, []))
        request = urllib.request.Request(f"http://127.0.0.1:{port}/api/settings", data=b"x"*(256*1024+1),
                                         headers={"Content-Type":"application/json"}, method="POST")
        with self.assertRaises(urllib.error.HTTPError) as ctx: urllib.request.urlopen(request, timeout=2)
        self.assertEqual(ctx.exception.code, 413)

    def test_successful_port_switch_releases_old_port(self):
        old_port, new_port = free_port(), free_port(); old_process = self.start(old_port)
        status, settings = json_request("GET", f"http://127.0.0.1:{old_port}/api/settings")
        settings.update(server_host="127.0.0.1", server_port=str(new_port))
        json_request("POST", f"http://127.0.0.1:{old_port}/api/settings", settings)
        _, restart = json_request("POST", f"http://127.0.0.1:{old_port}/api/system/restart", {})
        self.assertTrue(wait_health(old_port, up=False, timeout=15), "old port still responds")
        self.assertTrue(wait_health(new_port, timeout=25), "target port did not start")
        old_process.wait(timeout=10)
        self.assertIsNotNone(old_process.returncode)
        status_path = Path(self.runtime) / f"restart-{restart['restart_id']}.json"
        end=time.time()+10; final=None
        while time.time()<end:
            if status_path.exists(): final=json.loads(status_path.read_text(encoding="utf-8"))
            if final and final["status"]=="succeeded": break
            time.sleep(.2)
        self.assertEqual(final["status"], "succeeded")
        # Track the detached target for teardown.
        if final.get("target_pid"):
            self.processes.append(_PidProcess(final["target_pid"]))

    def test_target_failure_rolls_back_old_port(self):
        old_port, new_port = free_port(), free_port()
        self.env["APIKEYCONFIG_TEST_FAIL_TARGET"] = "1"
        old_process = self.start(old_port)
        _, settings = json_request("GET", f"http://127.0.0.1:{old_port}/api/settings")
        settings.update(server_host="127.0.0.1", server_port=str(new_port))
        json_request("POST", f"http://127.0.0.1:{old_port}/api/settings", settings)
        _, restart = json_request("POST", f"http://127.0.0.1:{old_port}/api/system/restart", {})
        self.assertTrue(wait_health(old_port, up=False, timeout=15), "old process did not shut down")
        old_process.wait(timeout=10)
        self.assertTrue(wait_health(old_port, up=True, timeout=30), "old port was not restored")
        self.assertTrue(wait_health(new_port, up=False, timeout=2), "failed target port unexpectedly stayed alive")
        status_path = Path(self.runtime) / f"restart-{restart['restart_id']}.json"
        end=time.time()+10; final=None
        while time.time()<end:
            if status_path.exists(): final=json.loads(status_path.read_text(encoding="utf-8"))
            if final and final["status"]=="rolled_back": break
            time.sleep(.2)
        self.assertEqual(final["status"], "rolled_back")
        if final.get("target_pid"):
            self.processes.append(_PidProcess(final["target_pid"]))


class _PidProcess:
    def __init__(self, pid): self.pid=pid
    def poll(self):
        result=subprocess.run(["tasklist","/FI",f"PID eq {self.pid}","/NH"],capture_output=True,text=True,
                              creationflags=subprocess.CREATE_NO_WINDOW)
        return None if str(self.pid) in result.stdout else 0
    def terminate(self):
        subprocess.run(["taskkill","/PID",str(self.pid),"/T","/F"],capture_output=True,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    def wait(self, timeout=None): return 0
    def kill(self): self.terminate()


if __name__ == "__main__": unittest.main()
