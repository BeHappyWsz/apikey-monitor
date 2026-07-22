# -*- coding: utf-8 -*-
"""Background monitor that reuses KeyService and per-key leases."""
import threading
import time

import db
from services.key_service import KEYS
from services.task_service import TASKS

_stop = threading.Event()
_thread = None
_TICK = 10
# Cap due keys per tick to avoid thundering herd; rest wait for next tick.
_MAX_PER_TICK_FACTOR = 2
_inflight = False
_inflight_lock = threading.Lock()


def start():
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="monitor", daemon=True)
    _thread.start()


def stop():
    _stop.set()
    if _thread and _thread.is_alive() and _thread is not threading.current_thread():
        _thread.join(timeout=3)


def _loop():
    while not _stop.is_set():
        try:
            tick()
        except Exception as exc:
            print("[monitor] tick error:", exc)
        _stop.wait(_TICK)


def _wait_task(task_id, poll_sec=0.5):
    """Block until background task finishes or monitor is stopping."""
    if not task_id:
        return
    while not _stop.is_set():
        task = TASKS.get(task_id)
        if not task or task.get("finished_at") is not None:
            return
        if _stop.wait(poll_sec):
            return


def tick():
    """Run capped health and opt-in strict batches without overlapping ticks."""
    global _inflight
    with _inflight_lock:
        if _inflight:
            return
        _inflight = True
    try:
        settings = db.get_all_settings()
        if settings.get("globalMonitorEnabled") != "1":
            return
        concurrency = max(1, int(settings.get("concurrency", 8) or 8))
        max_per_tick = max(1, concurrency * _MAX_PER_TICK_FACTOR)
        due = db.get_due_keys(
            int(time.time()),
            int(settings.get("globalIntervalSec", 300)),
            int(settings.get("downRecheckIntervalSec", 120)),
            limit=max_per_tick,
        )
        if due:
            task = KEYS.batch_check([item["id"] for item in due], health=True)
            _wait_task(task.get("task_id") if isinstance(task, dict) else None)
        if settings.get("strictMonitorEnabled") == "1":
            strict_due = db.get_due_strict_keys(int(time.time()), limit=max_per_tick)
            if strict_due:
                task = KEYS.batch_check_model([item["id"] for item in strict_due])
                _wait_task(task.get("task_id") if isinstance(task, dict) else None)
    finally:
        with _inflight_lock:
            _inflight = False
