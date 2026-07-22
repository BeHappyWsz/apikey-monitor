# -*- coding: utf-8 -*-
import core
import db
from services.task_service import TASKS


class KeyService:
    def list(self, public=True, sort="default"): return db.list_keys(public=public, sort=sort)
    def page(self, limit=50, cursor="", status_filter="all", search="", sort="default",
             protocol="all", adapter="all", has_model="all", tag=""):
        return db.list_keys_page(limit, cursor, status_filter, search, sort=sort,
                                 protocol=protocol, adapter=adapter, has_model=has_model, tag=tag)
    def get(self, key_id, public=False): return db.get_key(key_id, public=public)
    def secret(self, key_id):
        entry = db.get_key(key_id)
        if not entry: raise KeyError('key not found')
        return {'id': entry['id'], 'api_key': entry.get('api_key') or '', 'api_key_masked': db.mask_api_key(entry.get('api_key'))}

    def delete(self, ids): return db.delete_keys(ids)
    def reorder(self, ids): return db.reorder_keys(ids)
    def move_before(self, key_id, before_id=None): return db.move_key_before(key_id, before_id)

    def _settings(self):
        return db.get_all_settings()

    def _save_result(self, entry, result, settings):
        key_id = entry["id"]
        verified_model_limit = (
            result.get("status") == "up"
            and result.get("model_status") in (None, "unknown")
            and entry.get("model_status") == "rate_limited"
            and int(entry.get("model_verification_version") or 0) >= 1
        )
        if verified_model_limit:
            result = {
                **result,
                "status": "rate_limited",
                "latency_ms": entry.get("model_latency_ms"),
                "error": entry.get("model_last_error") or result.get("error"),
            }
        next_check_at = db.monitor_next_check_at(entry, result["status"], settings)
        db.update_status(key_id, result["status"], result.get("latency_ms"), result.get("error"),
                         result.get("supports_anthropic"), result.get("supports_openai"), result.get("models"),
                         result.get("openai_status"), result.get("anthropic_status"), next_check_at)
        if result.get("model_status") and result["model_status"] != "unknown":
            db.update_model_status(key_id, result["model_status"], result.get("model_latency_ms"),
                                   result.get("model_error"), adapter=result.get("model_probe_adapter") or "",
                                   next_check_at=db.strict_next_check_at(entry, settings))

    def _probe(self, entry, health):
        settings = self._settings()
        timeout = int(settings.get("requestTimeoutSec", 45))
        concurrency = int(settings.get("concurrency", 8))
        with TASKS.probe_slot(concurrency):
            if health:
                result = core.health_check(entry["base_url"], entry["api_key"],
                    bool(entry.get("supports_openai")), bool(entry.get("supports_anthropic")),
                    timeout, entry.get("check_model", ""), entry.get("check_path", ""))
            else:
                result = core.classify(entry["base_url"], entry["api_key"], timeout,
                    entry.get("check_model", ""), entry.get("check_path", ""))
        self._save_result(entry, result, settings)
        return result

    def check(self, key_id, health=False):
        entry = db.get_key(key_id)
        if not entry:
            raise KeyError("key not found")
        if not TASKS.acquire(key_id):
            raise RuntimeError("key is already being checked")
        try:
            return self._probe(entry, health)
        finally:
            TASKS.release(key_id)

    def _check_unleased(self, key_id, health=False):
        entry = db.get_key(key_id)
        if not entry:
            raise KeyError("key not found")
        return self._probe(entry, health)

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

    def _check_model_unleased(self, key_id, model=None):
        entry = db.get_key(key_id)
        if not entry:
            raise KeyError("key not found")
        model = str(model or entry.get("check_model") or "").strip()
        if not model:
            raise ValueError("no model specified")
        settings = self._settings()
        with TASKS.probe_slot(int(settings.get("concurrency", 8))):
            result = core.model_check(entry["base_url"], entry["api_key"], model,
                                      bool(entry.get("supports_openai")), bool(entry.get("supports_anthropic")),
                                      int(settings.get("requestTimeoutSec", 45)))
        if model != entry.get("check_model"):
            db.update_key(key_id, {"check_model": model})
            entry = {**entry, "check_model": model}
        db.update_model_status(key_id, result["model_status"], result.get("model_latency_ms"),
                               result.get("model_error"), adapter=result.get("model_probe_adapter") or "",
                               next_check_at=db.strict_next_check_at(entry, settings))
        if result.get("model_status") == "rate_limited":
            next_check_at = db.monitor_next_check_at(entry, "rate_limited", settings)
            # Status side-effect of strict verify does not count as a health run or duplicate history.
            db.update_status(key_id, "rate_limited", result.get("model_latency_ms"), result.get("model_error"),
                             next_check_at=next_check_at, bump_monitor_count=False, record_history=False)
        return result

    def check_model(self, key_id, model=None):
        if not TASKS.acquire(key_id):
            raise RuntimeError("key is already being checked")
        try:
            return self._check_model_unleased(key_id, model)
        finally:
            TASKS.release(key_id)

    def batch_check_model(self, ids):
        concurrency = int(self._settings().get("concurrency", 8))
        return TASKS.create(ids, lambda key_id: self._check_model_unleased(key_id), concurrency, kind="strict")

    def refresh_models(self, key_id):
        entry = db.get_key(key_id)
        if not entry:
            raise KeyError("key not found")
        if not TASKS.acquire(key_id):
            raise RuntimeError("key is already being checked")
        try:
            settings = self._settings()
            with TASKS.probe_slot(int(settings.get("concurrency", 8))):
                result = core.list_remote_models(entry["base_url"], entry["api_key"],
                    bool(entry.get("supports_openai")), bool(entry.get("supports_anthropic")),
                    int(settings.get("requestTimeoutSec", 45)), entry.get("check_path", ""))
            if result.get("error") and not result.get("models"):
                models = entry.get("models") or []
            else:
                models = db.update_models(key_id, result.get("models") or [])
            return {"id": key_id, "models": models, "count": len(models), "error": result.get("error") or ""}
        finally:
            TASKS.release(key_id)


KEYS = KeyService()
