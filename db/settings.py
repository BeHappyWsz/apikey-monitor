# -*- coding: utf-8 -*-
"""Settings key/value store."""
from db._store import (
    get_all_settings,
    get_public_settings,
    set_settings,
    replace_settings,
)

__all__ = [
    "get_all_settings", "get_public_settings", "set_settings", "replace_settings",
]
