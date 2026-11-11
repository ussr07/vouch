"""Create Vouch's own Bifrost keys in .env, once. Existing values are never changed.

Run from the project folder:  python scripts/make_keys.py
(scripts/start_bifrost.py runs this for you; Docker users run it through the container,
see "Run with Docker" in the README.)
"""
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"

# Vouch's own Bifrost virtual key: the gateway applies a daily request, token and
# budget limit to every call made with it (bifrost/config.json, "governance").
# It is created once, here, and kept in .env, never in the code.
# The dashboard and management API need an admin login once governance is on;
# it is generated the same way. Model calls use only the virtual key.
GENERATED = {
    "VOUCH_VK": lambda: f"sk-bf-{secrets.token_hex(16)}",
    # a second key capped at 2 requests a minute, to show the limit being enforced
    "VOUCH_DEMO_VK": lambda: f"sk-bf-{secrets.token_hex(16)}",
    "BIFROST_ADMIN_USERNAME": lambda: "admin",
    "BIFROST_ADMIN_PASSWORD": lambda: secrets.token_urlsafe(18),
}


def has_value(text: str, name: str) -> bool:
    """True when .env already sets name to something (an empty "NAME=" doesn't count)."""
    return any(line.strip().startswith(f"{name}=") and line.split("=", 1)[1].strip()
               for line in text.splitlines())


def ensure_keys(env_file: Path = ENV_FILE) -> list[str]:
    """Adds whichever generated keys are missing; returns their names."""
    existing = env_file.read_text(encoding="utf-8") if env_file.exists() else ""
    missing = [name for name in GENERATED if not has_value(existing, name)]
    if missing:
        lines = [line for line in existing.splitlines()
                 if not any(line.strip() == f"{name}=" for name in missing)]  # drop empty placeholders
        lines += [f"{name}={GENERATED[name]()}" for name in missing]
        env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return missing


if __name__ == "__main__":
    added = ensure_keys()
    print("Added to .env:", ", ".join(added) if added else "nothing, every key is already set")
