# -*- coding: utf-8 -*-
"""In-process list-change fan-out for SSE clients."""
from __future__ import annotations

import threading
import time
from typing import Tuple

_lock = threading.Condition()
_seq = 0
_revision = ""


def snapshot() -> Tuple[int, str]:
    """Return (sequence, last_revision) without waiting."""
    with _lock:
        return _seq, _revision


def notify_list_changed(revision: str = "") -> int:
    """Publish a list mutation. Returns the new sequence number."""
    global _seq, _revision
    with _lock:
        _seq += 1
        if revision is not None and str(revision) != "":
            _revision = str(revision)
        _lock.notify_all()
        return _seq


def wait_list_change(last_seq: int, timeout: float = 25.0) -> Tuple[int, str]:
    """Block until sequence advances past last_seq or timeout.

    Returns the latest (sequence, revision). On timeout the sequence may be
    unchanged - callers should emit a heartbeat comment.
    """
    deadline = time.monotonic() + max(0.0, float(timeout))
    with _lock:
        while _seq == last_seq:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            _lock.wait(timeout=remaining)
        return _seq, _revision