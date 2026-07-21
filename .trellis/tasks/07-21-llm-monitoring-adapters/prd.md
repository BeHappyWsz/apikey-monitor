# Improve LLM monitoring adapter coverage

## Goal

Improve backend LLM monitoring so strict model verification works across more OpenAI-compatible gateway shapes, not only classic `/v1/chat/completions`.

## Requirements

- Detect whether a configured key/model can produce usable text through common LLM invocation shapes.
- Support OpenAI-compatible chat completions first, then fall back to OpenAI-compatible responses when chat is unavailable.
- Treat providers that only expose a response-style API as valid when they return generated text in a supported response envelope.
- Preserve existing Anthropic messages probing behavior and existing public API fields.
- Preserve existing status semantics: strict model `rate_limited` promotes the key's overall status to `rate_limited`; strict model success records `model_status=up`.
- Keep probe logic in `core/` and service orchestration in `services/key_service.py`; do not add dependencies or move network I/O into `db.py`.
- Tests must mock HTTP calls; no real LLM endpoints or secrets in tests.

## Non-Goals

- No UI redesign.
- No schema migration in this phase.
- No automatic full model-list batch tester in the web product.
- No provider-specific OAuth, SDKs, streaming, image/audio/video, or embedding checks.
- No persistent capability matrix beyond existing `status`, `model_status`, protocol statuses, and models.

## Acceptance Criteria

- [x] Strict verification still passes for existing OpenAI chat completion responses.
- [x] Strict verification passes for OpenAI-compatible responses payloads when chat completion is not available.
- [x] Strict verification can validate response text from at least the common `output_text` and `output[].content[].text` envelopes.
- [x] Chat 404/route-missing falls back to responses before returning failure.
- [x] 401/403 and 429 remain terminal and map to `auth_error` / `rate_limited`.
- [x] Existing Anthropic messages tests still pass.
- [x] Full backend test suite passes.

## Notes

- Context source: user added `skills/llm-api-tester`, which documents broader OpenAI-compatible endpoint testing and response edge cases.
