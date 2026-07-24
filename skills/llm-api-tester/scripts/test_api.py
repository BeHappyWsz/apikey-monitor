#!/usr/bin/env python3
"""
LLM API Tester — test any OpenAI-compatible endpoint.

Usage:
  # List models only
  python3 test_api.py --base https://api.example.com --key sk-xxx --mode models

  # Test all chat models (parallel)
  python3 test_api.py --base https://api.example.com --key sk-xxx --mode chat

  # Filter by keyword
  python3 test_api.py --base https://api.example.com --key sk-xxx --mode chat --filter gpt

  # Test a single model
  python3 test_api.py --base https://api.example.com --key sk-xxx --mode single --model gpt-4o --prompt "你好"

  # Key can be base64-encoded, auto-decoded
  python3 test_api.py --base https://api.example.com --key c2steHh4eA== --mode chat
"""
import argparse
import base64
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# Models with these keywords are NOT chat models
NON_CHAT_KEYWORDS = [
    "image", "video", "whisper", "orpheus", "seedance",
    "imagine", "tts", "asr", "embed", "moderation", "speech",
]


def decode_key(raw: str) -> str:
    """Auto-detect and decode base64-encoded keys."""
    raw = raw.strip()
    if raw.startswith("Bearer "):
        return raw[len("Bearer "):].strip()
    # Looks like a normal key already
    if raw.startswith("sk-") or (raw.isascii() and "-" in raw and len(raw) > 20):
        return raw
    # Try base64 decode
    try:
        decoded = base64.b64decode(raw, validate=True).decode("utf-8")
        if "sk-" in decoded or len(decoded) > 15:
            return decoded.strip()
    except Exception:
        pass
    return raw


def normalize_base(url: str) -> str:
    """Strip trailing slash."""
    return url.rstrip("/")


def curl_get(url: str, key: str, timeout: int = 30) -> dict:
    """GET request, return parsed JSON or raise."""
    r = subprocess.run(
        ["curl", "-s", "-X", "GET", url,
         "-H", f"Authorization: Bearer {key}",
         "--max-time", str(timeout)],
        capture_output=True, text=True, timeout=timeout + 5,
    )
    return json.loads(r.stdout)


def curl_chat(url: str, key: str, model: str, prompt: str,
              max_tokens: int = 80, timeout: int = 45) -> dict:
    """POST chat completion, return parsed JSON."""
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    })
    r = subprocess.run(
        ["curl", "-s", "-X", "POST", url,
         "-H", f"Authorization: Bearer {key}",
         "-H", "Content-Type: application/json",
         "--max-time", str(timeout),
         "-d", payload],
        capture_output=True, text=True, timeout=timeout + 5,
    )
    return json.loads(r.stdout)


def list_models(base: str, key: str) -> list:
    """Fetch model list. Raises on auth/connection errors."""
    data = curl_get(f"{base}/v1/models", key)
    if isinstance(data, dict) and "error" in data:
        err = data["error"]
        raise RuntimeError(f"{err.get('code','auth_error')}: {err.get('message','')}")
    if isinstance(data, dict) and "data" in data:
        return [m["id"] for m in data["data"]]
    raise RuntimeError(f"Unexpected response: {str(data)[:200]}")


def is_chat_model(model_id: str) -> bool:
    lid = model_id.lower()
    return not any(k in lid for k in NON_CHAT_KEYWORDS)


def test_one_chat(base: str, key: str, model: str, prompt: str) -> tuple:
    """Returns (model, status, code, info)."""
    try:
        d = curl_chat(f"{base}/v1/chat/completions", key, model, prompt)
    except subprocess.TimeoutExpired:
        return (model, "FAIL", "timeout", "")
    except json.JSONDecodeError:
        return (model, "FAIL", "bad_json", "")
    except Exception as e:
        return (model, "FAIL", "", str(e)[:60])

    if not isinstance(d, dict):
        return (model, "FAIL", "", str(d)[:60])
    if "error" in d:
        err = d["error"]
        return (model, "ERR", str(err.get("code", "")), str(err.get("message", ""))[:60])

    choices = d.get("choices", [])
    if not choices:
        return (model, "EMPTY", "", "no choices")
    msg = choices[0].get("message", {})
    content = (msg.get("content") or "").strip()
    if content:
        return (model, "OK", "", content[:50])
    elif msg.get("reasoning"):
        return (model, "OK*", "", "(仅reasoning,无content)")
    else:
        return (model, "EMPTY", "", f"finish={choices[0].get('finish_reason','')}")


def main():
    ap = argparse.ArgumentParser(description="LLM API Tester")
    ap.add_argument("--base", required=True, help="Base URL, e.g. https://api.example.com")
    ap.add_argument("--key", required=True, help="API key (plaintext or base64)")
    ap.add_argument("--mode", default="chat",
                    choices=["models", "chat", "single"],
                    help="models=只列表, chat=批量测试, single=测单个")
    ap.add_argument("--model", help="Model to test (single mode)")
    ap.add_argument("--prompt", default="用一句话说你好", help="Test prompt")
    ap.add_argument("--filter", default="", help="Filter models by keyword")
    ap.add_argument("--workers", type=int, default=12, help="Parallel workers")
    ap.add_argument("--max-tokens", type=int, default=80)
    args = ap.parse_args()

    base = normalize_base(args.base)
    key = decode_key(args.key)

    print(f"端点: {base}")
    print(f"Key: {key[:8]}...{key[-4:]} (len={len(key)})\n")

    # Step 1: list models
    try:
        models = list_models(base, key)
    except Exception as e:
        print(f"❌ 无法获取模型列表: {e}")
        sys.exit(1)

    chat_models = [m for m in models if is_chat_model(m)]
    non_chat = [m for m in models if not is_chat_model(m)]
    print(f"✅ Key 有效 — 共 {len(models)} 模型 (对话类 {len(chat_models)}, 非对话类 {len(non_chat)})")

    if args.filter:
        chat_models = [m for m in chat_models if args.filter.lower() in m.lower()]
        print(f"过滤 '{args.filter}': {len(chat_models)} 个匹配\n")
    else:
        print()

    if args.mode == "models":
        print("=== 所有模型 ===")
        for m in sorted(models):
            tag = "" if is_chat_model(m) else "  [非对话]"
            print(f"  {m}{tag}")
        return

    if args.mode == "single":
        if not args.model:
            print("❌ single 模式需要 --model")
            sys.exit(1)
        print(f"测试单个模型: {args.model}\n")
        m, status, code, info = test_one_chat(base, key, args.model, args.prompt)
        tag = {"OK": "✅", "OK*": "🟡", "ERR": "❌", "EMPTY": "⬜", "FAIL": "💥"}[status]
        print(f"{tag} {m}  {code}  {info}")
        return

    # chat mode: parallel batch test
    print(f"开始并行测试 {len(chat_models)} 个对话模型 (workers={args.workers})...\n")
    results = {}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(test_one_chat, base, key, m, args.prompt): m for m in chat_models}
        done = 0
        for fut in as_completed(futs):
            model, status, code, info = fut.result()
            results[model] = (status, code, info)
            done += 1
            tag = {"OK": "✅", "OK*": "🟡", "ERR": "❌", "EMPTY": "⬜", "FAIL": "💥"}[status]
            print(f"  [{done}/{len(chat_models)}] {tag} {model:45s} {code:22s} {info}", flush=True)

    # Summary
    ok = sorted([m for m in results if results[m][0] in ("OK", "OK*")])
    err = sorted([m for m in results if results[m][0] == "ERR"])
    other = sorted([m for m in results if results[m][0] in ("EMPTY", "FAIL")])

    print("\n" + "=" * 70)
    print(f"✅ 可正常对话: {len(ok)}")
    for m in ok:
        s, _, info = results[m]
        print(f"  {'✅' if s == 'OK' else '🟡'} {m:45s} {info}")

    if err:
        print(f"\n❌ 不可用: {len(err)}")
        for m in err:
            c = results[m][1]
            print(f"  ❌ {m:45s} {c}")

    if other:
        print(f"\n⬜💥 空或失败: {len(other)}")
        for m in other:
            print(f"  {results[m][0]:4s} {m:45s} {results[m][1]}")


if __name__ == "__main__":
    main()
