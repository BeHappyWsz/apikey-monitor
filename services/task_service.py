# -*- coding: utf-8 -*-
import copy
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed


class TaskService:
    def __init__(self, ttl=3600):
        self.ttl = ttl
        self._tasks = {}
        self._leases = set()
        self._lock = threading.RLock()

    def _cleanup(self):
        cutoff = time.time() - self.ttl
        for task_id in list(self._tasks):
            task = self._tasks[task_id]
            if task.get("finished_at") is not None and task["finished_at"] < cutoff:
                self._tasks.pop(task_id, None)

    def get(self, task_id):
        with self._lock:
            self._cleanup()
            task = self._tasks.get(task_id)
            return copy.deepcopy(task) if task else None

    def acquire(self, key_id):
        with self._lock:
            if key_id in self._leases:
                return False
            self._leases.add(key_id)
            return True

    def release(self, key_id):
        with self._lock:
            self._leases.discard(key_id)

    def create(self, ids, worker, concurrency=8, kind="check"):
        task_id = f"{kind}-{uuid.uuid4().hex[:12]}"
        now = time.time()
        task = {"task_id": task_id, "kind": kind, "status": "queued", "total": len(ids),
                "completed": 0, "failed": 0, "skipped": 0, "errors": [],
                "created_at": now, "started_at": None, "finished_at": None}
        with self._lock:
            self._cleanup()
            self._tasks[task_id] = task
        thread = threading.Thread(target=self._run, args=(task_id, list(ids), worker, concurrency),
                                  name=task_id, daemon=True)
        thread.start()
        return copy.deepcopy(task)

    def _run(self, task_id, ids, worker, concurrency):
        with self._lock:
            task = self._tasks[task_id]
            task.update(status="running", started_at=time.time())
        def run_one(key_id):
            if not self.acquire(key_id):
                return "skipped", "already checking"
            try:
                worker(key_id)
                return "completed", ""
            except Exception as exc:
                return "failed", str(exc)[:180]
            finally:
                self.release(key_id)
        with ThreadPoolExecutor(max_workers=max(1, int(concurrency))) as executor:
            futures = {executor.submit(run_one, key_id): key_id for key_id in ids}
            for future in as_completed(futures):
                key_id = futures[future]
                state, error = future.result()
                with self._lock:
                    task = self._tasks[task_id]
                    task["completed"] += 1
                    if state == "failed":
                        task["failed"] += 1
                    elif state == "skipped":
                        task["skipped"] += 1
                    if error and len(task["errors"]) < 10:
                        task["errors"].append({"id": key_id, "message": error})
        with self._lock:
            task = self._tasks[task_id]
            if task["failed"] == task["total"] and task["total"]:
                status = "failed"
            elif task["failed"] or task["skipped"]:
                status = "partial_failed"
            else:
                status = "completed"
            task.update(status=status, finished_at=time.time())


TASKS = TaskService()
