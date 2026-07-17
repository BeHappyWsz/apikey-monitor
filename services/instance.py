# -*- coding: utf-8 -*-
"""Single-instance lifecycle helpers (pid file under .runtime)."""
import atexit
import ctypes
import json
import os
import signal
import socket
import subprocess
import sys
import time

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNTIME_DIR = os.environ.get("APIKEYCONFIG_RUNTIME_DIR", os.path.join(ROOT_DIR, ".runtime"))
PID_FILE = os.path.join(RUNTIME_DIR, "server.pid")
_atexit_registered = False


def _pid_alive(pid):
    if pid is None or int(pid) <= 0:
        return False
    pid = int(pid)
    if os.name == "nt":
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == STILL_ACTIVE
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def can_bind(host, port):
    bind_host = "127.0.0.1" if host == "localhost" else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((bind_host, int(port)))
            return True
        except OSError:
            return False


def read_pid_record():
    try:
        with open(PID_FILE, "r", encoding="utf-8") as stream:
            data = json.load(stream)
        if not isinstance(data, dict):
            return None
        return data
    except Exception:
        return None


def write_pid_record(host, port):
    os.makedirs(RUNTIME_DIR, exist_ok=True)
    payload = {
        "pid": os.getpid(),
        "host": host,
        "port": int(port),
        "started_at": time.time(),
    }
    tmp = f"{PID_FILE}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, PID_FILE)
    _register_atexit()
    return payload


def clear_pid_record(only_if_self=True):
    record = read_pid_record()
    if record is None:
        try:
            if os.path.exists(PID_FILE):
                os.unlink(PID_FILE)
        except OSError:
            pass
        return
    if only_if_self and int(record.get("pid") or 0) != os.getpid():
        return
    try:
        if os.path.exists(PID_FILE):
            os.unlink(PID_FILE)
    except OSError:
        pass


def _register_atexit():
    global _atexit_registered
    if _atexit_registered:
        return
    atexit.register(lambda: clear_pid_record(only_if_self=True))
    _atexit_registered = True


def _terminate_pid(pid, timeout=8):
    pid = int(pid)
    if pid == os.getpid() or not _pid_alive(pid):
        return True
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            creationflags=flags,
        )
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            return not _pid_alive(pid)
        end = time.time() + timeout
        while time.time() < end and _pid_alive(pid):
            time.sleep(0.2)
        if _pid_alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
    end = time.time() + timeout
    while time.time() < end and _pid_alive(pid):
        time.sleep(0.15)
    return not _pid_alive(pid)


def ensure_single_instance(host, port, stop_previous=True):
    """Stop a previous instance recorded in the pid file, then verify bind.

    Returns a short log message (may be empty). Raises RuntimeError if the
    listen address stays occupied by a non-owned process.
    """
    messages = []
    record = read_pid_record()
    if record:
        old_pid = int(record.get("pid") or 0)
        if old_pid == os.getpid():
            return ""
        if _pid_alive(old_pid):
            if stop_previous:
                messages.append(f"stopping previous instance pid={old_pid}")
                print(f"[apiKeyConfig] 检测到已有实例 (pid={old_pid})，正在先关闭…")
                if not _terminate_pid(old_pid):
                    raise RuntimeError(f"failed to stop previous instance pid={old_pid}")
                messages.append("previous instance stopped")
            else:
                raise RuntimeError(f"another instance is running (pid={old_pid})")
        try:
            if os.path.exists(PID_FILE):
                os.unlink(PID_FILE)
                messages.append("cleared stale pid file")
        except OSError:
            pass

    # Wait briefly if port still draining after kill.
    end = time.time() + 5
    while time.time() < end and not can_bind(host, port):
        time.sleep(0.15)

    if not can_bind(host, port):
        raise RuntimeError(
            f"address already in use: {host}:{port} "
            "(not owned by this app or still releasing; stop the other process or change port)"
        )
    return "; ".join(messages)