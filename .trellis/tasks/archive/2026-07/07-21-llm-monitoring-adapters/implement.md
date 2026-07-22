# Implementation Plan

1. Extend response validation in `core/protocol_base.py`.
   - Add `openai_responses` validation for `output_text` and nested `output.content.text` shapes.
   - Keep existing OpenAI chat and Anthropic validation unchanged.

2. Refactor OpenAI model probe in `core/protocols/openai.py`.
   - Split chat and responses request bodies into small helpers.
   - Try chat first.
   - Fall back to responses only on route-missing/unreachable conditions.
   - Keep 401/403/429 terminal.

3. Add focused tests in `tests/test_core_db.py`.
   - Validate fallback and response envelopes through mocked `core.http._request`.
   - Validate rate-limit does not fall through.

4. Run verification.
   - `python -m unittest tests.test_core_db.CoreTests -v`
   - `python -m unittest discover -s tests -v`

5. Finish.
   - Inspect diff.
   - Commit implementation only after tests pass.
