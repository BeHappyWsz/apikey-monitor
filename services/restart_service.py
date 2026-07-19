# -*- coding: utf-8 -*-
import copy
import ctypes
import json
import os
import socket
import subprocess
import sys
import threading
import time
import uuid
import urllib.request

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
import db

_RESTART_LOCK = threading.Lock()
_STATUS_LOCK = threading.RLock()
_STATUS_DIR = os.environ.get("APIKEYCONFIG_RUNTIME_DIR", os.path.join(ROOT_DIR, ".runtime"))
_STATE = {}
TERMINAL = {"succeeded", "rolled_back", "failed", "no_change"}


def public_host(host):
    return "127.0.0.1" if host in ("0.0.0.0", "localhost") else host


def make_url(host, port):
    return f"http://{public_host(host)}:{int(port)}"


def can_bind(host, port):
    bind_host = "127.0.0.1" if host == "localhost" else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((bind_host, int(port)))
            return True
        except OSError:
            return False


def _status_path(restart_id):
    return os.path.join(_STATUS_DIR, f"restart-{restart_id}.json")


def _write_status(status):
    os.makedirs(_STATUS_DIR, exist_ok=True)
    path = _status_path(status["restart_id"])
    raw = json.dumps(status, ensure_ascii=False, indent=2)
    last_error = None
    for _ in range(12):
        tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}.tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp, path)
            return
        except OSError as exc:
            last_error = exc
            time.sleep(.025)
        finally:
            try:
                if os.path.exists(tmp): os.unlink(tmp)
            except OSError:
                pass
    # Status persistence must never prevent the server lifecycle from progressing.
    if last_error:
        print(f"[restart] status write warning: {last_error}", file=sys.stderr)


def set_status(restart_id, state, message="", **extra):
    with _STATUS_LOCK:
        status = _STATE.get(restart_id)
        if status is None:
            try:
                with open(_status_path(restart_id), "r", encoding="utf-8") as stream:
                    status = json.load(stream)
            except Exception:
                status = {"restart_id": restart_id, "created_at": time.time(), "steps": []}
            _STATE[restart_id] = status
        status.update(status=state, message=message, updated_at=time.time(), **extra)
        status["steps"].append({"status": state, "message": message, "at": time.time()})
        _write_status(status)
        return copy.deepcopy(status)


def get_status(restart_id):
    with _STATUS_LOCK:
        if restart_id in _STATE:
            return copy.deepcopy(_STATE[restart_id])
    try:
        with open(_status_path(restart_id), "r", encoding="utf-8") as stream:
            return json.load(stream)
    except Exception:
        return None


def request_restart(server, old_settings, target_settings):
    old_host, old_port = old_settings["serverHost"], int(old_settings["serverPort"])
    target_host, target_port = target_settings["serverHost"], int(target_settings["serverPort"])
    restart_id = uuid.uuid4().hex[:12]
    if (old_host, old_port) == (target_host, target_port):
        return set_status(restart_id, "no_change", "监听地址和端口未变化，无需重启",
                          old_url=make_url(old_host, old_port), target_url=make_url(target_host, target_port))
    if not _RESTART_LOCK.acquire(blocking=False):
        raise RuntimeError("restart already in progress")
    if not can_bind(target_host, target_port):
        db.replace_settings(old_settings)
        _RESTART_LOCK.release()
        raise ValueError("target address or port is already in use; old settings restored")
    status = set_status(restart_id, "validating", "目标端口校验通过",
                        old_url=make_url(old_host, old_port), target_url=make_url(target_host, target_port),
                        old_host=old_host, old_port=old_port, target_host=target_host, target_port=target_port,
                        old_pid=os.getpid(), target_pid=None)
    helper = [sys.executable, os.path.abspath(__file__), "--helper", restart_id,
              json.dumps(old_settings, ensure_ascii=False), json.dumps(target_settings, ensure_ascii=False), str(os.getpid())]
    creationflags = 0
    kwargs = {}
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
        kwargs["creationflags"] = creationflags
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(helper, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)
    def shutdown():
        try:
            set_status(restart_id, "shutting_down_old", "正在停止监测线程和旧 HTTP 服务")
            import monitor
            monitor.stop()
            time.sleep(0.2)
            server.shutdown()
        except Exception as exc:
            set_status(restart_id, "failed", f"旧服务关闭失败：{exc}")
            _RESTART_LOCK.release()
    threading.Thread(target=shutdown, name=f"restart-shutdown-{restart_id}", daemon=True).start()
    return status


def _pid_alive(pid):
    if pid <= 0:
        return False
    if os.name == "nt":
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
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


def _wait(condition, timeout, interval=.2):
    end = time.time() + timeout
    while time.time() < end:
        if condition(): return True
        time.sleep(interval)
    return False


def _healthy(url):
    try:
        with urllib.request.urlopen(url + "/api/system/health", timeout=1) as response:
            return response.status == 200
    except Exception:
        return False


def _wait_process_health(process, url, timeout):
    end = time.time() + timeout
    while time.time() < end:
        if process.poll() is not None:
            return False
        if _healthy(url):
            return True
        time.sleep(.5)
    return False


def _spawn(settings, restart_id, child_env=None):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    command = [sys.executable, os.path.join(root, "app.py"), "--host", settings["serverHost"],
               "--port", str(settings["serverPort"]), "--no-browser", "--restart-id", restart_id]
    kwargs = {"cwd": root, "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
              "stderr": subprocess.DEVNULL, "env": child_env}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(command, **kwargs)


def _terminate(process):
    if not process or process.poll() is not None: return
    try:
        process.terminate(); process.wait(timeout=4)
    except Exception:
        try: process.kill()
        except Exception: pass


def _fallback_env():
    env = os.environ.copy()
    env.pop("APIKEYCONFIG_TEST_FAIL_TARGET", None)
    return env


def helper_main(restart_id, old_settings, target_settings, old_pid):
    target_process = None
    try:
        set_status(restart_id, "waiting_old_port_release", "等待旧进程退出并确认旧端口已释放")
        old_host, old_port = old_settings["serverHost"], int(old_settings["serverPort"])
        if not _wait(lambda: not _pid_alive(old_pid), 15):
            raise RuntimeError("old process did not exit")
        if not _wait(lambda: can_bind(old_host, old_port), 10):
            raise RuntimeError("old port was not released")
        db.replace_settings(target_settings)
        set_status(restart_id, "starting_target", "正在启动目标端口")
        if os.environ.get("APIKEYCONFIG_TEST_FAIL_TARGET") == "1":
            target_process = subprocess.Popen([sys.executable, "-c", "raise SystemExit(9)"],
                                              stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                              stderr=subprocess.DEVNULL)
        else:
            target_process = _spawn(target_settings, restart_id)
        set_status(restart_id, "verifying_target", "正在验证目标服务", target_pid=target_process.pid)
        target_url = make_url(target_settings["serverHost"], target_settings["serverPort"])
        if _wait_process_health(target_process, target_url, 20):
            set_status(restart_id, "succeeded", "新端口启动成功", target_pid=target_process.pid)
            return
        _terminate(target_process)
        set_status(restart_id, "restoring_old_config", "目标端口启动失败，正在恢复旧配置")
        db.replace_settings(old_settings)
        set_status(restart_id, "starting_fallback", "正在重新启动旧端口")
        fallback = _spawn(old_settings, restart_id, _fallback_env())
        set_status(restart_id, "verifying_fallback", "正在验证旧端口", target_pid=fallback.pid)
        old_url = make_url(old_host, old_port)
        if _wait_process_health(fallback, old_url, 20):
            set_status(restart_id, "rolled_back", "新端口启动失败，已自动恢复旧端口", target_pid=fallback.pid)
        else:
            set_status(restart_id, "failed", "新旧端口均未能启动，请手动运行 app.py")
    except Exception as exc:
        _terminate(target_process)
        try:
            db.replace_settings(old_settings)
            fallback = _spawn(old_settings, restart_id, _fallback_env())
            old_url = make_url(old_settings["serverHost"], old_settings["serverPort"])
            if _wait_process_health(fallback, old_url, 20):
                set_status(restart_id, "rolled_back", f"重启异常，已恢复旧端口：{exc}", target_pid=fallback.pid)
                return
        except Exception:
            pass
        set_status(restart_id, "failed", f"重启失败：{exc}")


if __name__ == "__main__" and len(sys.argv) >= 6 and sys.argv[1] == "--helper":
    helper_main(sys.argv[2], json.loads(sys.argv[3]), json.loads(sys.argv[4]), int(sys.argv[5]))
