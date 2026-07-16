# -*- coding: utf-8 -*-
import time
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


if __name__ == "__main__": unittest.main()
