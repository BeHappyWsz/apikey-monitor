# -*- coding: utf-8 -*-
"""Pure parsing, probing and export helpers for apiKeyConfig.

Public facade kept stable for `import core` callers. Implementation lives in
submodules; extension points are the registries in `core.protocols`,
`core.export.EXPORT_FORMATS`, and `core.parse.IMPORTERS`.
"""
from core.export import (
    EXPORT_FORMATS,
    SCHEMA_VERSION,
    build_sync_payload,
    dumps_sync_payload,
    export_batch,
    export_config,
    list_export_formats,
    parse_sync_payload,
)
from core.http import MAX_RESPONSE_BYTES, _read_limited, _request
from core.parse import IMPORTERS, parse_import_text, parse_paste
from core.probe import classify, health_check, model_check
from core.protocol_base import _extract_error_message, _protocol_result, _record_http
from core.protocols import (
    PROTOCOL_PROBES,
    _probe_anthropic,
    _probe_openai,
    get_protocol,
    list_protocol_names,
)
from core.urls import candidate_urls, join_api_path, normalize_base_url, normalize_check_path, probe_urls

# Historical private alias used by older tests/docs.
_candidate_urls = candidate_urls

__all__ = [
    "MAX_RESPONSE_BYTES",
    "normalize_base_url",
    "join_api_path",
    "candidate_urls",
    "normalize_check_path",
    "probe_urls",
    "parse_import_text",
    "parse_paste",
    "classify",
    "health_check",
    "model_check",
    "export_config",
    "export_batch",
    "build_sync_payload",
    "dumps_sync_payload",
    "parse_sync_payload",
    "SCHEMA_VERSION",
    "list_export_formats",
    "list_protocol_names",
    "get_protocol",
    "EXPORT_FORMATS",
    "IMPORTERS",
    "PROTOCOL_PROBES",
    "_request",
    "_read_limited",
    "_protocol_result",
    "_record_http",
    "_extract_error_message",
    "_probe_openai",
    "_probe_anthropic",
    "_candidate_urls",
]
