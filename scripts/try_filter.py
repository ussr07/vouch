"""Search, then filter, then print what was kept and the rejection ledger.

Example:  python scripts/try_filter.py "Infosys" company 2026-11-14
Reruns of the same search cost no credits (cached).
"""
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows console + symbols like ₹
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv  # noqa: E402

from vouch.filters import filter_run  # noqa: E402
from vouch.research import search  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

name = sys.argv[1] if len(sys.argv) > 1 else "Infosys"
kind = sys.argv[2] if len(sys.argv) > 2 else "company"
meeting = datetime.fromisoformat(sys.argv[3]) if len(sys.argv) > 3 else datetime.now()

run = search(name, kind, meeting)
result = filter_run(run)

print(f"{name}: {len(run.sources)} results -> kept {len(result.kept)}, "
      f"rejected {len(result.rejected)}   (credits used: {run.credits_used})\n")
print("KEPT (newest first)")
for k in result.kept:
    print(f"  {k.published}  {k.source.title[:80]}")
print("\nREJECTION LEDGER")
for reason, count in Counter(r.reason for r in result.rejected).most_common():
    print(f"  {count} x {reason}")
for r in result.rejected:
    print(f"    - {r.source.title[:60]!r}: {r.reason}")
