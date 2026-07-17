# -*- coding: utf-8 -*-
"""Settings persistence and restart orchestration."""
import db
from api import validators
from services import restart_service


class SettingsService:
    def get(self):
        # Drop "_"-prefixed secrets/state (e.g. _webdav_password, _webdav_last_sync)
        # so they never reach the settings API surface.
        return {k: v for k, v in db.get_all_settings().items() if not k.startswith("_")}

    def validate(self, payload):
        return validators.settings_payload(payload, self.get())

    def save(self, payload):
        values = self.validate(payload)
        db.set_settings(values)
        return self.get()

    def restart(self, server):
        target = self.get()
        old = dict(server.runtime_settings)
        old.update({key: target.get(key, value) for key, value in old.items()
                    if key not in ("server_host", "server_port")})
        return restart_service.request_restart(server, old, target)


SETTINGS = SettingsService()
