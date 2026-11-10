"""Make one small real call to each service to prove the keys work.

Run from the project folder:  python scripts/check_services.py
Uses about 1 Tavily credit and two tiny model calls.
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from tavily import TavilyClient

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
ok = True


def report(name, fn):
    global ok
    try:
        print(f"[PASS] {name}: {fn()}")
    except Exception as e:  # show the real error, never hide it
        ok = False
        print(f"[FAIL] {name}: {type(e).__name__}: {str(e)[:300]}")


def tavily_check():
    client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    r = client.search("Infosys", topic="news", time_range="month", max_results=3)
    results = r.get("results", [])
    first = results[0] if results else {}
    return (f"{len(results)} results; first: {first.get('title', '')[:60]!r} "
            f"published_date={first.get('published_date')!r}")


def model_check(base_url, key_name, preferred):
    client = OpenAI(base_url=base_url, api_key=os.environ[key_name])
    available = [m.id for m in client.models.list().data]
    model = next((m for m in preferred if m in available), None)
    if model is None:
        return f"none of {preferred} available; sample: {available[:12]}"
    reply = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Reply with exactly: pong"}],
        max_tokens=300,  # reasoning models spend tokens "thinking" first
    )
    return f"model={model} reply={reply.choices[0].message.content.strip()!r}"


report("Tavily", tavily_check)
report("Groq", lambda: model_check(
    "https://api.groq.com/openai/v1", "GROQ_API_KEY",
    ["openai/gpt-oss-120b", "llama-3.3-70b-versatile", "openai/gpt-oss-20b"]))
report("Gemini", lambda: model_check(
    "https://generativelanguage.googleapis.com/v1beta/openai/", "GEMINI_API_KEY",
    ["models/gemini-3.5-flash-lite", "models/gemini-flash-lite-latest"]))
sys.exit(0 if ok else 1)
