# Design: LLM Monitoring Adapters

## Current State

`core.probe.model_check()` delegates to protocol entries in `core/protocols/`. The OpenAI-compatible model probe only posts to `/v1/chat/completions`; Anthropic posts to `/v1/messages`. Response validation is centralized in `core.protocol_base.model_response_error()`, but it only knows OpenAI chat and Anthropic message envelopes.

This misses gateways that expose only `/v1/responses`, or gateways that return generated content in response-style output envelopes instead of chat `choices[].message.content`.

## Approach

Introduce adapter-level helpers inside `core/protocols/openai.py` without changing the public `core.model_check()` contract.

The OpenAI-compatible `model_probe()` will try invocation adapters in order:

1. `chat/completions` with the existing minimal prompt body.
2. `responses` with a minimal input body.

Each adapter keeps the existing HTTP status mapping through `_record_http()`. A definitive non-404/non-0 result stops that adapter. If chat returns 404 or no route response, responses is tried. Auth errors and rate limits stay terminal so the probe does not hide a real credential/quota outcome behind a fallback.

Response validation expands from `model_response_error(protocol, raw)` to support protocol variants:

- `openai`: existing `choices[].message.content`.
- `openai_responses`: `output_text`, `output[].content[].text`, and `output[].content[].content` string shapes.
- `anthropic`: existing `content[].text`.

No DB/API shape changes are needed because the resulting statuses remain `model_status`, `model_latency_ms`, and `model_last_error`.

## Data Flow

`KEYS.check_model()` -> `core.model_check()` -> OpenAI protocol `model_probe()` -> adapter attempts -> `_aggregate()` -> existing DB write path.

For classify-after-add with `check_model`, the same `core.classify()` path benefits because it calls `model_check()`.

## Error Handling

- 200 with invalid payload -> `degraded` with a clear validation error.
- 401/403 -> `auth_error`, no fallback.
- 429 -> `rate_limited`, no fallback.
- 404/0 from chat -> try responses.
- 404/0 from every adapter -> preserve the final down/unreachable result.

## Compatibility

Existing OpenAI and Anthropic behavior remains supported. The OpenAI `/models` capability probe is unchanged. The custom `check_path` remains limited to classify/health probes and does not apply to model invocation, matching current docs.

## Testing

Add unit coverage in `tests/test_core_db.py` for:

- chat still succeeds.
- chat 404 then responses succeeds.
- responses `output_text` succeeds.
- responses nested content succeeds.
- chat 429 does not fall back and remains rate-limited.

Run full `python -m unittest discover -s tests -v`.
