"""Start the Bifrost gateway with the keys from .env.

Run from the project folder:  python scripts/start_bifrost.py
Leave this terminal open; Bifrost runs until you press Ctrl+C.
Gateway: http://localhost:8080   Web UI: open the same address in a browser.
"""
import os
import secrets
import shutil
import subprocess
from pathlib import Path

from dotenv import load_dotenv

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
existing = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else ""
missing = [name for name in GENERATED if f"{name}=" not in existing]
if missing:
    with ENV_FILE.open("a", encoding="utf-8") as f:
        f.write("\n" + "".join(f"{name}={GENERATED[name]()}\n" for name in missing))
    print("Added to .env:", ", ".join(missing))

load_dotenv(ENV_FILE)  # puts GROQ_API_KEY, VOUCH_VK etc. into this process's environment

npx = shutil.which("npx")
if npx is None and os.name == "nt":   # Windows names it npx.cmd
    npx = shutil.which("npx.cmd")
if npx is None:
    raise SystemExit("npx not found. Install Node.js LTS and reopen the terminal.")

cmd = [npx, "-y", "@maximhq/bifrost", "-app-dir", str(ROOT / "bifrost"),
       "-port", "8080", "-log-style", "pretty"]
print("Starting Bifrost:", " ".join(cmd[1:]))
# Run inside bifrost/ so the "./config.db" and "./logs.db" paths in config.json land there.
subprocess.run(cmd, env=os.environ.copy(), cwd=ROOT / "bifrost", check=False)  # child inherits the keys
