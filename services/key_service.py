# -*- coding: utf-8 -*-
import core
import db
from services.task_service import TASKS


class KeyService:
    def list(self, public=True): return db.list_keys(public=public)
    def get(self, key_id, public=False): return db.get_key(key_id, public=public)
    def secret(self, key_id):
        entry = db.get_key(key_id)
        if not entry: raise KeyError('key not found')
        return {'id': entry['id'], 'api_key': entry.get('api_key') or '', 'api_key_masked': db.mask_api_key(entry.get('api_key'))}

    def delete(self, ids): return db.delete_keys(ids)
    def reorder(self, ids): return db.reorder_keys(ids)

    def _timeout(self):
        return int(db.get_all_settings().get("request_timeout_sec", 15))

    def _save_result(self, key_id, result):
        db.update_status(key_id, result["status"], result.get("latency_ms"), result.get("error"),
                         result.get("supports_anthropic"), result.get("supports_openai"), result.get("models"),
                         result.get("openai_status"), result.get("anthropic_status"))
        if result.get("model_status") and result["model_status"] != "unknown":
            db.update_model_status(key_id, result["model_status"], result.get("model_latency_ms"), result.get("model_error"))

    def check(self, key_id, health=False):
        entry = db.get_key(key_id)
        if not entry:
            raise KeyError("key not found")
        if not TASKS.acquire(key_id):
            raise RuntimeError("key is already being checked")
        try:
            if health:
                result = core.health_check(entry["base_url"], entry["api_key"],
                    bool(entry.get("supports_openai")), bool(entry.get("supports_anthropic")),
                    self._timeout(), entry.get("check_model", ""), entry.get("check_path", ""))
            else:
                result = core.classify(entry["base_url"], entry["api_key"], self._timeout(), entry.get("check_model", ""), entry.get("check_path", ""))
            self._save_result(key_id, result)
            return result
        finally:
            TASKS.release(key_id)

    def _check_unleased(self, key_id, health=False):
        entry = db.get_key(key_id)
        if not entry:
            raise KeyError("key not found")
        if health:
            result = core.health_check(entry["base_url"], entry["api_key"],
                    bool(entry.get("supports_openai")), bool(entry.get("supports_anthropic")),
                    self._timeout(), entry.get("check_model", ""), entry.get("check_path", ""))
        else:
            result = core.classify(entry["base_url"], entry["api_key"], self._timeout(), entry.get("check_model", ""), entry.get("check_path", ""))
        self._save_result(key_id, result)
        return result

    def batch_check(self, ids, health=False):
        concurrency = int(db.get_all_settings().get("concurrency", 8))
        return TASKS.create(ids, lambda key_id: self._check_unleased(key_id, health), concurrency)

    def add(self, payload):
        check_after = payload.pop("check_after_save", True)
        key_id = db.add_key(payload)
        result = self.check(key_id) if check_after else None
        return key_id, result

    def add_batch(self, items):
        ids, skipped_duplicate = db.add_keys_batch(items)
        task = self.batch_check(ids) if ids else None
        return ids, task, skipped_duplicate

    def update(self, key_id, payload):
        check_after = payload.pop("check_after_save", False)
        before = db.get_key(key_id)
        if not before:
            raise KeyError("key not found")
        db.update_key(key_id, payload)
        result = self.check(key_id) if check_after else None
        return db.get_key(key_id, public=True), result

    def check_model(self, key_id, model=None):
        entry = db.get_key(key_id)
        if not entry:
            raise KeyError("key not found")
        model = str(model or entry.get("check_model") or "").strip()
        if not model:
            raise ValueError("no model specified")
        if not TASKS.acquire(key_id):
            raise RuntimeError("key is already being checked")
        try:
            result = core.model_check(entry["base_url"], entry["api_key"], model,
                                      bool(entry.get("supports_openai")), bool(entry.get("supports_anthropic")), self._timeout())
            db.update_model_status(key_id, result["model_status"], result.get("model_latency_ms"), result.get("model_error"))
            if model != entry.get("check_model"):
                db.update_key(key_id, {"check_model": model})
            return result
        finally:
            TASKS.release(key_id)


KEYS = KeyService()
