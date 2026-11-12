"""Copy saved briefs into demo/briefs/ for the GitHub Pages demo.

Run from the project folder:  python scripts/export_demo.py <brief id> [<brief id> ...]
Each brief is written exactly as the server would return it, plus demo/briefs/index.json
(the list the demo's start page shows, in the order given).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from vouch import store  # noqa: E402  (after the path is set)

OUT = ROOT / "demo" / "briefs"


def main(ids: list[str]) -> None:
    if not ids:
        raise SystemExit("Give one or more brief ids, e.g. python scripts/export_demo.py 25282aee48cf")
    OUT.mkdir(parents=True, exist_ok=True)
    listed = {row["id"]: row for row in store.recent(200)}
    index = []
    for brief_id in ids:
        brief = store.get(brief_id)
        if brief is None or brief_id not in listed:
            raise SystemExit(f"No saved brief with id {brief_id}")
        (OUT / f"{brief_id}.json").write_text(json.dumps(brief, ensure_ascii=False), encoding="utf-8")
        row = listed[brief_id]
        index.append({"id": brief_id, "name": brief["subject"]["name"], "kind": row["kind"],
                      "goal": row["goal"], "meeting": row["meeting"], "verified": len(brief["stories"])})
        print(f"exported {brief_id}  {brief['subject']['name']}")
    (OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
