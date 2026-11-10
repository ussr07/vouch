"""Make a full brief from the terminal and print it. Bifrost must be running.

Example:
    python scripts/try_brief.py "Infosys" company 2026-11-14 investor
Goals: sales, investor, partnership, hiring, general
"""
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from collections import Counter  # noqa: E402
from datetime import datetime  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
from vouch.pipeline import make_brief  # noqa: E402

name = sys.argv[1] if len(sys.argv) > 1 else "Infosys"
kind = sys.argv[2] if len(sys.argv) > 2 else "company"
meeting = datetime.fromisoformat(sys.argv[3]) if len(sys.argv) > 3 else datetime.now()
goal = sys.argv[4] if len(sys.argv) > 4 else "general"

b = make_brief(name, kind, meeting, goal)
c = b.checked
print(f"BRIEF: {b.name} | meeting {b.meeting_at.date()} | purpose: {b.goal}")
print(f"Window {b.run.window_start} to {b.run.window_end} | "
      f"{len(b.run.sources)} found -> {len(b.filtered.kept)} kept -> "
      f"{b.articles_shown_to_model} given to model -> {len(c.stories)} verified stories")
if b.model_call:
    m = b.model_call
    print(f"Model: {m.served_by} (fallback={m.used_fallback}) | "
          f"{m.prompt_tokens}+{m.completion_tokens} tokens | {m.seconds}s | total {b.seconds}s")

print("\nWHAT HAPPENED")
for i, s in enumerate(c.stories, 1):
    print(f" {i}. [{s.date}] {s.headline}  ({len(s.outlets)} outlet{'s' if len(s.outlets) > 1 else ''})")
    print(f"    {s.summary}")
    print(f"    PROOF: \"{s.quote}\" - {s.quote_source.source.url[:80]}")
print("\nTALKING POINTS")
for p in c.talking_points:
    print(f" - {p.text}  [story {', '.join(map(str, p.story_numbers))}]")
print("\nOPEN QUESTIONS")
for p in c.open_questions:
    print(f" - {p.text}  [story {', '.join(map(str, p.story_numbers))}]")

print("\nREJECTION LEDGER")
for reason, n in Counter(r.reason for r in b.filtered.rejected).most_common():
    print(f" {n} x article: {reason}")
for item, reason in c.removed:
    print(f" 1 x AI draft: {item!r}: {reason}")
