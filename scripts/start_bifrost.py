"""Start the Bifrost gateway with the keys from .env.

Run from the project folder:  python scripts/start_bifrost.py
Leave this terminal open; Bifrost runs until you press Ctrl+C.
Gateway: http://localhost:8080   Web UI: open the same address in a browser.
"""
import os
import shutil
import subprocess

from dotenv import load_dotenv

from make_keys import ENV_FILE, ROOT, ensure_keys   # scripts/ is on the path when run as a script

missing = ensure_keys()
if missing:
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
