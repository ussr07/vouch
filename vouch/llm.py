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

# Right-sized models: the big model writes the brief; a small one sorts entities.
# On Groq's free tier each model has its OWN rate limit, so splitting the two
# calls across models avoids the 429s measured in eval/RESULTS.md.
PRIMARY_MODEL = os.environ.get("VOUCH_PRIMARY_MODEL", "groq/openai/gpt-oss-120b")
ENTITY_MODEL = os.environ.get("VOUCH_ENTITY_MODEL", "groq/openai/gpt-oss-20b")
# Tried in order if the requested model fails. Different providers and models
# have separate limits, so one of them is usually free.
FALLBACK_MODELS = os.environ.get(
    "VOUCH_FALLBACK_MODELS", "gemini/gemini-3.5-flash-lite,groq/qwen/qwen3.8-27b").split(",")

# Time limits: one request waits at most REQUEST_TIMEOUT seconds and is retried
# once (Bifrost already switches models on failure). Before, the library default
# of 2 retries with a 120 s timeout let a single brief hang for about 6 minutes.
REQUEST_TIMEOUT = 45
SLOW_ATTEMPT = 30   # if a first attempt took this long, don't spend another on bad JSON

# Every call carries Vouch's virtual key, so Bifrost applies Vouch's daily limits
# and budget (bifrost/config.json "governance") and its logs show which app called.
VIRTUAL_KEY = os.environ.get("VOUCH_VK", "")

_client = OpenAI(base_url=BIFROST_URL, api_key="handled-by-bifrost",
                 timeout=REQUEST_TIMEOUT, max_retries=1,
                 default_headers={"x-bf-vk": VIRTUAL_KEY} if VIRTUAL_KEY else None)


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
    parsed = json.loads(text[start:end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("model reply was JSON but not an object")
    return parsed


def chat_json(system: str, user: str, max_tokens: int = 6000,
              model: str | None = None, reasoning: str = "low",
              temperature: float = 0.2) -> tuple[dict, CallInfo]:
    """Ask for a JSON reply. Retries once if the reply isn't valid JSON."""
    last_error = None
    for _attempt in range(2):
        start = time.time()
        raw = _client.chat.completions.with_raw_response.create(
            model=model or PRIMARY_MODEL,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            max_tokens=max_tokens,
            temperature=temperature,
            response_format={"type": "json_object"},
            # gpt-oss models "think" before answering; low effort is enough for
            # these tasks and cuts hidden tokens. Models without it ignore it.
            extra_body={"fallbacks": [m for m in FALLBACK_MODELS if m != (model or PRIMARY_MODEL)],
                        "reasoning_effort": reasoning},
        )
        reply = raw.parse()
        if not reply.choices:
            raise RuntimeError("the model returned no answer")
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
            if reply.choices[0].finish_reason == "length":
                raise RuntimeError("the model's reply was cut off before it finished") from e
            if info.seconds > SLOW_ATTEMPT:
                break  # a second slow attempt would keep the person waiting too long
    raise RuntimeError(f"model did not return valid JSON twice: {last_error}")
