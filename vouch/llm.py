"""All model calls go through the local Bifrost gateway.

Our code never holds a provider key: Bifrost has them. We ask for the primary
model and list a fallback; if Groq fails (rate limit, outage), Bifrost retries
on Gemini by itself and tells us so in the response.
"""
import json
import os
import re
import time
from dataclasses import dataclass

from openai import OpenAI

BIFROST_URL = os.environ.get("BIFROST_URL", "http://localhost:8080/v1")
PRIMARY_MODEL = os.environ.get("VOUCH_PRIMARY_MODEL", "groq/openai/gpt-oss-120b")
FALLBACK_MODELS = os.environ.get(
    "VOUCH_FALLBACK_MODELS", "gemini/gemini-3.5-flash-lite").split(",")

_client = OpenAI(base_url=BIFROST_URL, api_key="handled-by-bifrost", timeout=120)


@dataclass
class CallInfo:
    """What happened on one model call: shown in the UI and the README numbers."""
    served_by: str
    used_fallback: bool
    prompt_tokens: int
    completion_tokens: int
    seconds: float


def _extract_json(text: str) -> dict:
    """Models sometimes wrap JSON in ```json fences; strip them before parsing."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("model reply contained no JSON object")
    return json.loads(text[start:end + 1])


def chat_json(system: str, user: str, max_tokens: int = 6000) -> tuple[dict, CallInfo]:
    """Ask for a JSON reply. Retries once if the reply isn't valid JSON."""
    last_error = None
    for _attempt in range(2):
        start = time.time()
        raw = _client.chat.completions.with_raw_response.create(
            model=PRIMARY_MODEL,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            max_tokens=max_tokens,
            temperature=0.2,
            response_format={"type": "json_object"},
            extra_body={"fallbacks": FALLBACK_MODELS},
        )
        reply = raw.parse()
        routing = (raw.http_response.json().get("extra_fields") or {}).get("routing_info") or {}
        info = CallInfo(
            served_by=f"{routing.get('provider', '?')}/{routing.get('model', reply.model)}",
            used_fallback=bool(routing.get("is_fallback")),
            prompt_tokens=reply.usage.prompt_tokens if reply.usage else 0,
            completion_tokens=reply.usage.completion_tokens if reply.usage else 0,
            seconds=round(time.time() - start, 1),
        )
        try:
            return _extract_json(reply.choices[0].message.content or ""), info
        except (ValueError, json.JSONDecodeError) as e:
            last_error = e
    raise RuntimeError(f"model did not return valid JSON twice: {last_error}")
