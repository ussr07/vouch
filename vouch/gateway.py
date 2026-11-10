"""Read Vouch's usage and limits from Bifrost's governance API.

Bifrost tracks every call made with Vouch's virtual key (vk-vouch): requests and
tokens against daily limits, and spend priced at list rates against a daily
budget. This reads those numbers so the app can show them; it never changes them.
"""
import base64
import json
import os
import urllib.error
import urllib.request

BIFROST_ADMIN = os.environ.get("BIFROST_ADMIN_URL", "http://localhost:8080")
VIRTUAL_KEY_ID = "vk-vouch"


def usage(timeout: float = 5) -> dict:
    """Today's numbers, or {"available": False, "reason": ...} if Bifrost can't say."""
    user, password = os.environ.get("BIFROST_ADMIN_USERNAME"), os.environ.get("BIFROST_ADMIN_PASSWORD")
    if not (user and password):
        return {"available": False, "reason": "No Bifrost admin login in .env; run scripts/start_bifrost.py."}
    auth = base64.b64encode(f"{user}:{password}".encode()).decode()
    request = urllib.request.Request(f"{BIFROST_ADMIN}/api/governance/virtual-keys/{VIRTUAL_KEY_ID}",
                                     headers={"Authorization": f"Basic {auth}"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.load(response)
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        return {"available": False, "reason": f"Bifrost didn't answer ({type(e).__name__})."}
    vk = data.get("virtual_key", data) if isinstance(data, dict) else {}
    limit = vk.get("rate_limit") or {}
    budget = (vk.get("budgets") or [{}])[0]
    return {
        "available": True,
        "requests_used": limit.get("request_current_usage", 0),
        "requests_limit": limit.get("request_max_limit"),
        "tokens_used": limit.get("token_current_usage", 0),
        "tokens_limit": limit.get("token_max_limit"),
        "spend_usd": round(float(budget.get("current_usage") or 0), 5),
        "budget_usd": budget.get("max_limit"),
        "resets": limit.get("request_reset_duration"),
    }
