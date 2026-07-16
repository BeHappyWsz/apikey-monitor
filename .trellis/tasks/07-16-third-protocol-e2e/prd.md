# PRD: Third Protocol End-to-End (**PARKED / FUTURE**)

## Status

**Deferred.** Parent wave 2 implements only frontend module split + custom check path.
Do **not** start design/implement for this child until product picks the protocol.

## Parent

`07-16-progressive-ext-next`

## Goal (when unparked)

Add **one** third protocol beyond OpenAI and Anthropic, end-to-end: probe → DB → API → UI → optional export.

## What "protocol" means here

Not a network transport. A **vendor/API family** with distinct auth + endpoints:

| Protocol | Auth | Typical endpoints | DB flag today |
|----------|------|-------------------|---------------|
| OpenAI-compatible | `Authorization: Bearer` | `/v1/models`, `/v1/chat/completions` | `supports_openai` |
| Anthropic-compatible | `x-api-key` + `anthropic-version` | `/v1/messages` | `supports_anthropic` |
| **Third (TBD)** | e.g. `x-goog-api-key` | e.g. Gemini models list | new flag / registry entry |

## Open (blocking)

- **Which protocol?** Candidate A (recommended later): Google Gemini. Candidate B: Azure OpenAI (lower value). Candidate C: generic custom (overlaps `check_path`).

## Draft acceptance (when resumed)

1. Additive DB column or registry-backed flag for third protocol.
2. Classify/health detect and persist capability.
3. API public shape exposes flag without secrets.
4. UI shows protocol on cards.
5. Tests + docs.

## Non-goals

- Implementing anything in the current wave.
- More than one new protocol in one child when resumed.
