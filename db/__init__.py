# -*- coding: utf-8 -*-
"""Persistence package — drop-in replacement for the former db.py module.

Implementation lives in ``db._store``. Focused submodules (``db.keys``,
``db.settings``, ``db.auth``, ``db.connection``, …) re-export subsets by
responsibility. External code should keep using ``import db``.

Tests rebind ``db.DB_PATH`` / ``db.CONFIG_PATH`` / ``db._list_generation``;
the custom module type forwards those writes into ``db._store``.
"""
from __future__ import annotations

import sys
import types

from db import _store as _store_mod


class _DbModule(types.ModuleType):
    """Module proxy so attribute writes reach the implementation module."""

    def __getattr__(self, name: str):
        return getattr(object.__getattribute__(self, "_store_mod"), name)

    def __setattr__(self, name: str, value):
        if name in {
            "_store_mod", "__class__", "__dict__", "__name__", "__doc__",
            "__package__", "__loader__", "__spec__", "__file__", "__path__",
            "__cached__", "__builtins__",
        }:
            return types.ModuleType.__setattr__(self, name, value)
        setattr(object.__getattribute__(self, "_store_mod"), name, value)
        return types.ModuleType.__setattr__(self, name, value)

    def __dir__(self):
        names = set(types.ModuleType.__dir__(self))
        store = object.__getattribute__(self, "_store_mod")
        names.update(n for n in dir(store) if not n.startswith("__"))
        return sorted(names)


_module = _DbModule(__name__)
# Initialize required module attributes without going through __setattr__ proxy logic incorrectly
types.ModuleType.__setattr__(_module, "__name__", __name__)
types.ModuleType.__setattr__(_module, "__doc__", __doc__)
types.ModuleType.__setattr__(_module, "__package__", __package__)
types.ModuleType.__setattr__(_module, "__file__", __file__)
types.ModuleType.__setattr__(_module, "__path__", __path__)
types.ModuleType.__setattr__(_module, "__loader__", __loader__)
types.ModuleType.__setattr__(_module, "__spec__", __spec__)
types.ModuleType.__setattr__(_module, "_store_mod", _store_mod)

for _name in dir(_store_mod):
    if _name.startswith("__"):
        continue
    types.ModuleType.__setattr__(_module, _name, getattr(_store_mod, _name))

# Keep responsibility-oriented submodules available.
# Submodules stay importable as ``import db.keys`` etc. via package __path__.
# Do NOT bind ``db.connection`` to the submodule — it would shadow the
# public ``connection()`` context manager used throughout the app/tests.
import db.cache  # noqa: E402,F401
import db.config  # noqa: E402,F401
import db.connection  # noqa: E402,F401
import db.schema  # noqa: E402,F401
import db.settings  # noqa: E402,F401
import db.auth  # noqa: E402,F401
import db.keys  # noqa: E402,F401

sys.modules[__name__] = _module
