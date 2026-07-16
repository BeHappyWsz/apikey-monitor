# -*- coding: utf-8 -*-
"""Background monitor that reuses KeyService and per-key leases."""
import threading
import time
import db
from services.key_service import KEYS

_stop = threading.Event()
_thread = None
_TICK = 10


def start():
    global _thread
    if _thread and _thread.is_alive(): return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="monitor", daemon=True)
    _thread.start()


def stop():
    _stop.set()
    if _thread and _thread.is_alive() and _thread is not threading.current_thread():
        _thread.join(timeout=3)


def _loop():
    while not _stop.is_set():
        try: tick()
        except Exception as exc: print("[monitor] tick error:", exc)
        _stop.wait(_TICK)


def tick():
    settings = db.get_all_settings()
    if settings.get("global_monitor_enabled") != "1": return
    due = db.get_due_keys(int(time.time()), int(settings.get("global_interval_sec", 300)),
                          int(settings.get("down_recheck_interval_sec", 120)))
    if due:
        KEYS.batch_check([item["id"] for item in due], health=True)
