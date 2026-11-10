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
from vouch.shapes import as_int, as_ints, as_text

DOMINANT_SHARE = 0.75
SNIPPET_CHARS = 250

SYSTEM = """A name can belong to several real-world entities (Mercury the bank,
Mercury the record label). For each article, decide WHICH entity with the
searched name it refers to. Group by that, NOT by the article's main topic.
Rules:
- An article about a competitor, partner or customer that mentions the searched
  name still belongs to the entity with that name it refers to.
- Articles about the same organisation, including its subsidiaries, divisions,
  products and executives, belong to ONE entity.
- A person with the same name as another person is a DIFFERENT entity.
- Every article number must appear in exactly one entity.
- Labels name the entity with the searched name, short and specific,
  e.g. "Mercury, the US fintech bank for startups".
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
    entities = raw.get("entities") if isinstance(raw, dict) else None
    for position, e in enumerate(entities if isinstance(entities, list) else []):
        if not isinstance(e, dict):
            continue  # keep positions aligned with the model's list for "match"
        ids = []
        for i in as_ints(e.get("article_ids")):
            if i in by_number and i not in claimed and i not in ids:
                ids.append(i)
        claimed.update(ids)
        if ids:  # remember the model's position, so "match" still points correctly
            groups.append({"label": as_text(e.get("label")) or name,
                           "ids": ids, "position": position})
    out.groups_found = len(groups)
    unclassified = [k for i, k in by_number.items() if i not in claimed]

    chosen = None
    if about:
        match = as_int(raw.get("match")) if isinstance(raw, dict) else None
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
                          model=ENTITY_MODEL, temperature=0)
    return decide(raw, kept, name, about), info
