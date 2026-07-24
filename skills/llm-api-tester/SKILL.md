---
name: llm-api-tester
description: 'Test LLM API endpoints and keys for connectivity, model availability, and chat capability. Use when user asks to "测试 API", "test API", check if an endpoint/key works, list available models, or verify which models can actually chat. Accepts base URL, API key (plaintext or base64-encoded), and runs parallel health checks. Outputs a categorized availability report.'
license: MIT
allowed-tools: Bash
---

# LLM API Tester

**UTILITY SKILL** — test any OpenAI-compatible LLM API endpoint.

## When to Use

- "测试一下这个 API" / "test this API"
- "这个 key 能用吗" / "is this key valid"
- "有哪些可用模型" / "what models are available"
- "哪些模型能对话" / "which models can actually chat"
- "测一下 GPT/Claude/Gemini 系列" / "test GPT/Claude/Gemini models"

## Input Format

User provides (in any order, space/comma/newline separated):

1. **API Key** — `sk-...` plaintext **OR** base64-encoded string.
   - Auto-detect: if the key doesn't start with `sk-` / `Bearer` / an alphanumeric API prefix, try base64-decoding it first.
   - If base64 decode produces a readable `sk-...` key, use the decoded value.
   - If both fail, ask user to clarify.
2. **Base URL** — e.g. `https://fuhuaedu.com`, `https://api.openai.com`.
   - Normalize: strip trailing `/`. Append `/v1` if not present for standard OpenAI paths.
   - Accept with or without `/v1` suffix.

## Workflow

### Step 1: Decode & Validate Key

```python
import base64
def decode_key(raw):
    raw = raw.strip()
    # Already looks like a normal key
    if raw.startswith("sk-") or raw.startswith("Bearer "):
        return raw.removeprefix("Bearer ").strip()
    # Try base64
    try:
        decoded = base64.b64decode(raw).decode("utf-8")
        if "sk-" in decoded or len(decoded) > 20:
            return decoded.strip()
    except Exception:
        pass
    return raw  # return as-is
```

### Step 2: List Models (quick connectivity check)

```bash
curl -s -X GET "$BASE/v1/models" \
  -H "Authorization: Bearer $KEY" \
  --max-time 30
```

- If returns JSON with `data` array → **endpoint & key valid** ✅
- If returns 401/403 → **key invalid** ❌
- If timeout → **endpoint unreachable** ❌

### Step 3: Batch Chat Test (parallel)

Run the built-in script for parallel health checks:

```bash
python3 "$(skill_dir)/scripts/test_api.py" \
  --base "https://fuhuaedu.com" \
  --key "sk-xxxx" \
  --mode chat
```

Modes:
- `models` — only list models (fast)
- `chat` — list + test every chat model with a simple prompt (parallel, ~30s for 50 models)
- `chat --filter gpt` — only test models matching a keyword
- `single --model gpt-4o --prompt "你好"` — test one model with custom prompt

### Step 4: Report

Categorize results into:
- ✅ **正常对话** — returned content
- 🟡 **仅推理** — only reasoning tokens, no content (needs higher max_tokens or different params)
- ❌ **不可用** — error (cooldown, quota exhausted, 429, upstream error, etc.)
- ⬜ **空/超时** — empty or timeout

Always report the **error code** for failed models so user knows if it's a temporary issue (cooldown/429) vs permanent (invalid model).

## Excluding Non-Chat Models

These keywords indicate non-chat models — exclude from chat testing:
`image`, `video`, `whisper`, `orpheus`, `seedance`, `imagine`, `tts`, `asr`, `embed`, `moderation`

## Output Template

```
## API 测试报告

**端点**: https://fuhuaedu.com
**Key**: sk-...xxxx ✅ 有效 / ❌ 无效
**模型总数**: 64 (对话类 51)

### ✅ 可正常对话 (N)
| 模型 | 回应示例 |
|------|---------|
| model-name | 你好！ |

### ❌ 不可用 (N)
| 模型 | 错误 |
|------|------|
| model-name | model_cooldown |

### 结论
- 主力推荐: ...
- 暂时不可用: ... (建议稍后重试)
```

## Edge Cases

- **Non-OpenAI-compatible APIs**: If `/v1/models` returns non-JSON or unexpected format, report the raw response and suggest the user verify the endpoint.
- **Rate limiting during test**: Script uses 0.2s delay + parallel workers (default 12). If 429s appear, reduce `--workers`.
- **Models that only output reasoning**: Some models (gpt-oss, step, sensenova) put everything in `reasoning` field. Report as 🟡 and note that increasing `max_tokens` or adding `"reasoning_effort":"low"` may help.
