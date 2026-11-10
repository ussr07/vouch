"""Run Vouch on a fixed list of subjects and record real numbers.

Run from the project folder (Bifrost must be running):
    python eval/run_eval.py
Writes eval/results.json and eval/RESULTS.md. Costs ~4 Tavily credits per new subject.
"""
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
from eval.tamper import tamper_test  # noqa: E402
from vouch.pipeline import make_brief  # noqa: E402

cfg = json.loads((ROOT / "eval" / "subjects.json").read_text(encoding="utf-8"))
meeting = datetime.fromisoformat(cfg["meeting_date"])
rows = []
tamper_totals, tamper_tried = Counter(), Counter()

for subj in cfg["subjects"]:
    print(f"... {subj['name']}", flush=True)
    try:
        b = make_brief(subj["name"], subj["kind"], meeting, subj["goal"])
    except Exception as e:  # record failures honestly instead of skipping them
        rows.append({**subj, "error": f"{type(e).__name__}: {e}"[:200]})
        continue
    drafted = len((b.draft_raw or {}).get("stories", []))
    story_removals = [r for _, r in b.checked.removed if "linked" not in r]
    row = {
        **subj,
        "asked_which_one": bool(b.entity and b.entity.needs_choice),
        "entity_groups": b.entity.groups_found if b.entity else 0,
        "found": len(b.run.sources), "kept_after_filters": len(b.filtered.kept),
        "set_aside_other_entity": len(b.entity.set_aside) if b.entity else 0,
        "stories_drafted": drafted, "stories_verified": len(b.checked.stories),
        "stories_removed": len(story_removals),
        "removal_reasons": dict(Counter(story_removals)),
        "older_event_flags": sum(1 for s in b.checked.stories if s.older_event),
        "multi_outlet_stories": sum(1 for s in b.checked.stories if len(s.outlets) > 1),
        "tokens": sum(c.prompt_tokens + c.completion_tokens for c in (b.model_call, b.entity_call) if c),
        "served_by": b.model_call.served_by if b.model_call else None,
        "fallback_used": any(c.used_fallback for c in (b.model_call, b.entity_call) if c),
        "seconds": b.seconds, "tavily_credits": b.run.credits_used,
    }
    if b.draft_raw:
        t = tamper_test(b.draft_raw, b.draft_articles, b.name, b.run.window_start)
        row["tamper"] = t
        for name, (caught, tried) in t.items():
            tamper_totals[name] += caught
            tamper_tried[name] += tried
    rows.append(row)

(ROOT / "eval" / "results.json").write_text(
    json.dumps({"run_at": datetime.now().isoformat(timespec="seconds"), "rows": rows,
                "tamper": {k: [tamper_totals[k], tamper_tried[k]] for k in tamper_tried}}, indent=2),
    encoding="utf-8")

ok = [r for r in rows if "error" not in r]
briefs = [r for r in ok if not r["asked_which_one"]]
drafted = sum(r["stories_drafted"] for r in briefs)
removed = sum(r["stories_removed"] for r in briefs)
md = [f"# Vouch evaluation\n\nRun on {datetime.now():%d %b %Y %H:%M}, meeting date {cfg['meeting_date']}. "
      "Expectations in `subjects.json` were written before running.\n",
      "## Per subject\n",
      "| Subject | Expected ambiguous | Asked which one | Found | Kept | Other-entity set aside | AI stories | Verified | Removed by checks | Older-event flags | Seconds | Tokens | Model |",
      "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
for r in rows:
    if "error" in r:
        md.append(f"| {r['name']} | {r['expect_ambiguous']} | error: {r['error']} |||||||||||")
        continue
    md.append(f"| {r['name']} | {'yes' if r['expect_ambiguous'] else 'no'} | {'yes' if r['asked_which_one'] else 'no'} | "
              f"{r['found']} | {r['kept_after_filters']} | {r['set_aside_other_entity']} | {r['stories_drafted']} | "
              f"{r['stories_verified']} | {r['stories_removed']} | {r['older_event_flags']} | {r['seconds']} | "
              f"{r['tokens']} | {r['served_by'] or '-'}{' (fallback)' if r['fallback_used'] else ''} |")
correct = sum(1 for r in ok if r["asked_which_one"] == r["expect_ambiguous"])
md += ["", "## Summary\n",
       f"- Ambiguity handled as expected: **{correct} of {len(ok)}** subjects.",
       f"- AI-drafted stories removed by the code checks: **{removed} of {drafted}**"
       + (f" ({removed / drafted:.0%})." if drafted else "."),
       f"- Errors: {len(rows) - len(ok)}.",
       "", "## Tamper test\n",
       "Every story that passed was corrupted one way at a time and re-checked.\n",
       "| Corruption | Caught |", "|---|---|"]
for k in tamper_tried:
    md.append(f"| {k} | {tamper_totals[k]} of {tamper_tried[k]} |")
md += ["", "Limits: a small set of well-covered subjects, one run each, judged by code rules. "
       "The checks prove quotes exist and figures appear in sources; they do not prove a summary's meaning is right."]
(ROOT / "eval" / "RESULTS.md").write_text("\n".join(md) + "\n", encoding="utf-8")
print("\n".join(md))
