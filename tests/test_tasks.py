# -*- coding: utf-8 -*-
import time
import threading
import unittest
from services.task_service import TaskService


class TaskTests(unittest.TestCase):
    def test_progress_and_lease(self):
        service = TaskService(ttl=60)
        seen = []
        task = service.create([1, 2], lambda value: seen.append(value), concurrency=2)
        for _ in range(100):
            status = service.get(task["task_id"])
            if status["status"] in ("completed", "failed", "partial_failed"): break
            time.sleep(.01)
        self.assertEqual(status["completed"], 2)
        self.assertEqual(status["status"], "completed")
        self.assertEqual(sorted(seen), [1, 2])
        self.assertTrue(service.acquire(3))
        self.assertFalse(service.acquire(3))
        service.release(3)

    def test_probe_slots_share_one_limit(self):
        service = TaskService(ttl=60)
        entered = threading.Event()
        release = threading.Event()
        active = 0
        peak = 0
        guard = threading.Lock()

        def run():
            nonlocal active, peak
            with service.probe_slot(2):
                with guard:
                    active += 1
                    peak = max(peak, active)
                    if active == 2:
                        entered.set()
                release.wait(1)
                with guard:
                    active -= 1

        threads = [threading.Thread(target=run) for _ in range(3)]
        for thread in threads:
            thread.start()
        self.assertTrue(entered.wait(1))
        with guard:
            self.assertEqual(active, 2)
        release.set()
        for thread in threads:
            thread.join(1)
        self.assertEqual(peak, 2)


if __name__ == "__main__": unittest.main()
