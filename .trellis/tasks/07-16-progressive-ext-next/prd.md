# PRD: Progressive Extension Wave 2 (Parent)

## Source request

Continue progressive extensibility. **This wave implements only:**

1. ~~Third protocol end-to-end~~ → **deferred / future backlog** (not implemented now)
2. **Custom check path** (per-key)
3. **Frontend large-module split**

User directive (2026-07-16): skip third protocol; do #2 and #3 only; no confirmation gates.

## Task map

| Child | Dir | Status intent | Independently verifiable outcome |
|-------|-----|---------------|----------------------------------|
| Frontend module split | `07-16-frontend-module-split` | **Do now** | `static/app.js` responsibilities extracted without behavior change |
| Custom check path | `07-16-custom-check-path` | **Do now** | Per-key optional path used by probes when set |
| Third protocol E2E | `07-16-third-protocol-e2e` | **Parked / future** | Do **not** implement in this wave |

## Cross-child acceptance (this wave)

- Zero third-party Python deps retained.
- Existing `data.db` migrates additively only.
- List/detail APIs still mask secrets.
- Full unittest suite green after each child archive.
- Parent closes after **frontend split + custom check path** archived; third-protocol child remains planning/parked with PRD noting future work.
- Integration smoke: list keys UI still loads; edit can save `check_path`.

## Suggested order

1. **Frontend module split** — pure refactor first.
2. **Custom check path** — storage + probe + editor UI.
3. Third protocol — **out of scope**; leave backlog note only.

## What is "third protocol"?

Product today classifies **two** protocol families:

- **OpenAI-compatible** (`supports_openai`, Bearer auth, `/v1/models`, `/v1/chat/completions`)
- **Anthropic-compatible** (`supports_anthropic`, `x-api-key`, `/v1/messages`)

A **third protocol** would be another distinct API family (common candidate: **Google Gemini / Generative Language** with `x-goog-api-key`). Not chosen / not implemented this wave.

## Non-goals (parent this wave)

- Implementing Gemini or any third protocol flag/UI.
- Multi-user auth / SaaS.
- Full request template engine.

## Constraints

- Python 3.10+ stdlib; vanilla ESM frontend.
- Prefer additive migrations.
- Keep `import core` stable where possible.
