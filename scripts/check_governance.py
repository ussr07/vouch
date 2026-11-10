"""Check that Bifrost governance is active for Vouch: limits, usage and refusal.

Run from the project folder with Bifrost running:
    python scripts/check_governance.py          makes 2 tiny model calls
    python scripts/check_governance.py usage    only shows today's usage
    python scripts/check_governance.py limit    shows the 2-a-minute demo key being refused
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
BASE = "http://localhost:8080"
AUTH = base64.b64encode(f"{os.environ['BIFROST_ADMIN_USERNAME']}:{os.environ['BIFROST_ADMIN_PASSWORD']}".encode()).decode()


def admin_get(path):
    req = urllib.request.Request(BASE + path, headers={"Authorization": f"Basic {AUTH}"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def usage():
    vk = admin_get("/api/governance/virtual-keys/vk-vouch")
    vk = vk.get("virtual_key", vk)
    rl = vk.get("rate_limit") or {}
    return {k: rl.get(k) for k in ("request_current_usage", "request_max_limit",
                                    "token_current_usage", "token_max_limit")}


def call(key):
    body = json.dumps({"model": "groq/openai/gpt-oss-20b", "max_tokens": 50,
                       "messages": [{"role": "user", "content": "Reply with exactly: pong"}]}).encode()
    req = urllib.request.Request(BASE + "/v1/chat/completions", data=body, method="POST",
                                 headers={"Content-Type": "application/json", "x-bf-vk": key})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, "ok"
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")[:160]


if sys.argv[1:] == ["usage"]:   # python scripts/check_governance.py usage
    print(usage())
    raise SystemExit(0)

if sys.argv[1:] == ["limit"]:   # the demo key allows 2 requests a minute: the 3rd is refused
    for n in (1, 2, 3):
        print(f"Demo-key call {n}:", call(os.environ["VOUCH_DEMO_VK"]))
    raise SystemExit(0)

before = usage()
print("Vouch key limits and usage before:", before)
print("Call with Vouch's key:", call(os.environ["VOUCH_VK"]))
print("Call with a made-up key:", call("sk-bf-not-a-real-key"))
print("Usage after:", usage())
