# PRD: Strict model probe P0

## Goal
Reduce false negatives in strict model verification for reasoning-heavy OpenAI-compatible models, without changing monitor `health_check` behavior.

## Scope
- Raise model-probe token budget (`max_tokens` / `max_output_tokens`) from 3 to 32 for OpenAI chat, OpenAI responses, and Anthropic model probe.
- Accept non-empty `message.reasoning` / `message.reasoning_content` (and list-shaped content) as valid generated text for OpenAI chat validation.
- Leave connectivity-only Anthropic capability probe (`max_tokens: 1`) unchanged except shared validation helpers if reused.
- Do not add batch multi-model testing, error-code UI, or non-chat filters.

## Acceptance
1. OpenAI chat model_probe request uses max_tokens=32; responses uses max_output_tokens=32; Anthropic model_probe uses max_tokens=32.
2. HTTP 200 + empty content but non-empty reasoning fields → model_status up / verified.
3. HTTP 200 + empty/proxy payload still → degraded.
4. Existing fallback / rate-limit / anthropic text-block tests still pass.
