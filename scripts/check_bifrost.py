"""Prove that model calls work through the local Bifrost gateway.

Start Bifrost first (python scripts/start_bifrost.py), then in a second terminal:
    python scripts/check_bifrost.py

Test 1: normal call. Groq should answer.
Test 2: the primary model name is deliberately wrong, so Groq fails and
        Bifrost should fall back to Gemini on its own.
"""
import time

from openai import OpenAI

# Our code never sees provider keys: Bifrost holds them.
client = OpenAI(base_url="http://localhost:8080/v1", api_key="not-needed")

PRIMARY = "groq/openai/gpt-oss-120b"
FALLBACK = "gemini/gemini-3.5-flash-lite"


def ask(model, label):
    start = time.time()
    raw = client.chat.completions.with_raw_response.create(
        model=model,
        messages=[{"role": "user", "content": "Reply with exactly: pong"}],
        max_tokens=300,
        extra_body={"fallbacks": [FALLBACK]},  # Bifrost-specific field
    )
    reply = raw.parse()
    data = raw.http_response.json()
    routing = (data.get("extra_fields") or {}).get("routing_info") or {}
    print(f"{label}")
    print(f"  asked for : {model}")
    print(f"  served by : {routing.get('provider', '?')}/{routing.get('model', reply.model)}"
          f"  fallback={routing.get('is_fallback')}")
    print(f"  reply     : {(reply.choices[0].message.content or '').strip()!r}"
          f"  in {time.time() - start:.1f}s, {reply.usage.total_tokens if reply.usage else '?'} tokens")


ask(PRIMARY, "Test 1: normal call")
ask("groq/this-model-does-not-exist", "Test 2: forced failure, expect Gemini to take over")
