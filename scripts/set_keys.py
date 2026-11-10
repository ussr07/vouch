"""Ask for each API key (input hidden) and write them to .env.

Run from the project folder:  python scripts/set_keys.py
Press Enter without typing to keep a key that is already saved.
"""
from getpass import getpass
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
NAMES = ["TAVILY_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY"]

# Read whatever is already in .env so we don't wipe existing keys.
current = {}
if ENV_PATH.exists():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            current[key.strip()] = value.strip()

for name in NAMES:
    typed = getpass(f"Paste {name} (hidden, Enter to keep): ").strip().strip('"').strip("'")
    if typed:
        current[name] = typed

lines = ["# Real keys. This file is ignored by git, never commit it."]
lines += [f"{name}={current.get(name, '')}" for name in NAMES]
ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

for name in NAMES:
    print(f"{name}: {'saved' if current.get(name) else 'MISSING'}")
