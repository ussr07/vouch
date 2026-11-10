"""Start the Bifrost gateway with the keys from .env.

Run from the project folder:  python scripts/start_bifrost.py
Leave this terminal open; Bifrost runs until you press Ctrl+C.
Gateway: http://localhost:8080   Web UI: open the same address in a browser.
"""
import os
import shutil
import subprocess
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")  # puts GROQ_API_KEY etc. into this process's environment

npx = shutil.which("npx") or shutil.which("npx.cmd")
if npx is None:
    raise SystemExit("npx not found. Install Node.js LTS and reopen the terminal.")

cmd = [npx, "-y", "@maximhq/bifrost", "-app-dir", str(ROOT / "bifrost"),
       "-port", "8080", "-log-style", "pretty"]
print("Starting Bifrost:", " ".join(cmd[1:]))
subprocess.run(cmd, env=os.environ.copy(), check=False)  # child inherits the keys
