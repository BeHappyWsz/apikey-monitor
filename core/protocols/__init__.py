# -*- coding: utf-8 -*-
"""Protocol probe registry.

To add a protocol later:
1. Implement probe(base, api_key, timeout) (and optional model_probe) in a module.
2. Append an entry to PROTOCOL_PROBES below.
3. Wire any product-level flags/UI/API fields in a separate task if needed.
"""
from core.protocols import anthropic as anthropic_mod
from core.protocols import openai as openai_mod

# Ordered: classify runs probes in this order.
PROTOCOL_PROBES = (
    {"name": "openai", "probe": openai_mod.probe, "model_probe": openai_mod.model_probe},
    {"name": "anthropic", "probe": anthropic_mod.probe, "model_probe": anthropic_mod.model_probe},
)

_BY_NAME = {entry["name"]: entry for entry in PROTOCOL_PROBES}


def list_protocol_names():
    return [entry["name"] for entry in PROTOCOL_PROBES]


def get_protocol(name: str):
    try:
        return _BY_NAME[name]
    except KeyError as exc:
        raise KeyError(f"unknown protocol: {name}") from exc


def all_probes():
    return [entry["probe"] for entry in PROTOCOL_PROBES]


def _probe_openai(base, api_key, timeout):
    return get_protocol("openai")["probe"](base, api_key, timeout)


def _probe_anthropic(base, api_key, timeout):
    return get_protocol("anthropic")["probe"](base, api_key, timeout)
