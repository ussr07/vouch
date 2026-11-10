"""Step 3b: make sure every article is about the SAME real-world entity.

"Mercury" can be a fintech bank, a record label or a basketball team.
Telling them apart needs reading, so the model sorts articles into groups,
but CODE makes the decision:
  - if the user said which one they mean (`about`), keep only that group;
  - if one group clearly dominates (75%+ of articles), keep it;
  - otherwise stop and ask the user to choose.
Every article set aside goes into the ledger with the entity it was about.
"""
from dataclasses import dataclass, field

from vouch.filters import Kept
from vouch.llm import ENTITY_MODEL, CallInfo, chat_json

DOMINANT_SHARE = 0.75
SNIPPET_CHARS = 250

SYSTEM = """You sort news articles by which real-world entity they are about.
Rules:
- Articles about the same organisation, including its subsidiaries, divisions,
  products and executives, belong to ONE entity.
- A person with the same name as another person is a DIFFERENT entity.
- Every article number must appear in exactly one entity.
- Labels are short and specific, e.g. "Mercury, the US fintech bank for startups".
- Reply with a single JSON object only."""


@dataclass
class EntityDecision:
    kept: list[Kept] = field(default_factory=list)
    set_aside: list[tuple[Kept, str]] = field(default_factory=list)   # (article, reason)
    choices: list[dict] = field(default_factory=list)                 # [{"label", "count"}]
    chosen_label: str | None = None
    groups_found: int = 0

    @property
    def needs_choice(self) -> bool:
        return bool(self.choices)


def build_prompt(name: str, kind: str, about: str, kept: list[Kept]) -> str:
    lines = [f"[{i}] {k.source.title}\n{' '.join(k.source.snippet.split())[:SNIPPET_CHARS]}"
             for i, k in enumerate(kept, start=1)]
    hint = (f'The user means: "{about}". Set "match" to the index (0-based) of the entity '
            f"that is this one, or null if none is.") if about else 'Set "match" to null.'
    return (f'Subject searched for: "{name}" ({kind}).\n{hint}\n\n'
            'Reply in this JSON shape:\n'
            '{"entities": [{"label": "...", "article_ids": [1, 2]}], "match": null}\n\n'
            "ARTICLES:\n" + "\n\n".join(lines))


def decide(raw: dict, kept: list[Kept], name: str, about: str = "") -> EntityDecision:
    """Pure function: turns the model's grouping into a decision. Easy to test."""
    out = EntityDecision()
    by_number = {i: k for i, k in enumerate(kept, start=1)}
    groups, claimed = [], set()
    for position, e in enumerate(raw.get("entities", []) or []):
        ids = [i for i in e.get("article_ids", [])
               if isinstance(i, int) and i in by_number and i not in claimed]
        claimed.update(ids)
        if ids:  # remember the model's position, so "match" still points correctly
            groups.append({"label": str(e.get("label", "")).strip() or name,
                           "ids": ids, "position": position})
    out.groups_found = len(groups)
    unclassified = [k for i, k in by_number.items() if i not in claimed]

    chosen = None
    if about:
        match = raw.get("match")
        chosen = next((g for g in groups if g["position"] == match), None)
    elif groups:
        largest = max(groups, key=lambda g: len(g["ids"]))
        if len(groups) == 1 or len(largest["ids"]) >= DOMINANT_SHARE * len(claimed):
            chosen = largest
        else:
            out.choices = [{"label": g["label"], "count": len(g["ids"])}
                           for g in sorted(groups, key=lambda g: -len(g["ids"]))]
            return out  # stop: the user has to pick

    for g in groups:
        if g is chosen:
            out.kept.extend(by_number[i] for i in g["ids"])
        else:
            reason = (f"about a different {name}: {g['label']}" if chosen
                      else f"doesn't match '{about}' (it's about {g['label']})")
            out.set_aside.extend((by_number[i], reason) for i in g["ids"])
    if chosen is not None and len(groups) == 1:
        # Only one entity exists, so an article the model forgot to assign has
        # nothing to be confused with: keep it. (Seen on live data: the model
        # skipped 3 clearly relevant Zerodha articles.)
        out.kept.extend(unclassified)
    else:
        out.set_aside.extend((k, f"couldn't tell which {name} it's about") for k in unclassified)
    out.chosen_label = chosen["label"] if chosen else None
    out.kept.sort(key=lambda k: k.published, reverse=True)
    return out


def resolve(name: str, kind: str, about: str, kept: list[Kept]) -> tuple[EntityDecision, CallInfo]:
    raw, info = chat_json(SYSTEM, build_prompt(name, kind, about, kept), max_tokens=3000,
                          model=ENTITY_MODEL)
    return decide(raw, kept, name, about), info
