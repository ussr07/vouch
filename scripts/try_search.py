"""Run the search step for one subject and print what came back.

Example:
    python scripts/try_search.py "Infosys" company 2026-11-14
    python scripts/try_search.py "Nandan Nilekani" person 2026-11-14
"""
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows console + symbols like ₹
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv  # noqa: E402

from vouch.research import search  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

name = sys.argv[1] if len(sys.argv) > 1 else "Infosys"
kind = sys.argv[2] if len(sys.argv) > 2 else "company"
meeting = datetime.fromisoformat(sys.argv[3]) if len(sys.argv) > 3 else datetime.now()

run = search(name, kind, meeting)
total = len(run.sources)
unique = len({s.url for s in run.sources})
dated = sum(1 for s in run.sources if s.published_date)

print(f"Subject: {run.name} ({run.kind})   window: {run.window_start} to {run.window_end}")
print(f"Tavily credits used: {run.credits_used}   cache hits: {run.cache_hits}")
print(f"Results: {total} ({unique} unique URLs)   with a date: {dated}/{total}")
print("Per search:", dict(Counter(s.angle for s in run.sources)))
print()
for s in run.sources[:12]:
    print(f"[{s.angle:8}] {str(s.published_date)[:16]:16} {s.title[:70]}")
    print(f"           {s.url[:100]}")
