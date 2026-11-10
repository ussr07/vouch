"""Step 5 of the pipeline: check the model's draft in code.

A story survives only if:
  - it cites real article numbers, and
  - its quote appears word for word in the article it names.
Talking points and questions survive only if they point at a surviving story.
Everything removed goes into the ledger with a reason.
"""
import re
from dataclasses import dataclass, field
from datetime import date

from vouch.filters import Kept

# Different sites use curly or straight quotes and different dashes.
_CHAR_MAP = str.maketrans({
    "\u2018": "'", "\u2019": "'",           # curly single quotes
    "\u201c": '"', "\u201d": '"',           # curly double quotes
    "\u2010": "-", "\u2011": "-", "\u2013": "-", "\u2014": "-", "\u2212": "-",  # dashes
    "\u00a0": " ", "\u202f": " ",           # non-breaking spaces
})


def normalise(text: str) -> str:
    """Make cosmetic differences disappear, but nothing that changes meaning."""
    text = text.translate(_CHAR_MAP).lower()
    text = re.sub(r"[*_#>`]", "", text)          # markdown symbols in snippets
    return " ".join(text.split())                  # collapse spaces/newlines


def quote_found(quote: str, source_text: str) -> bool:
    q = normalise(quote).strip(" .\"'")
    return len(q.split()) >= 4 and q in normalise(source_text)


def numbers_in(text: str) -> set[str]:
    """Figures like 8%, $5.2 billion, 1,000, Rs 26 -> {'8', '5.2', '1000', '26'}."""
    return {n.replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)}


_STOPWORDS = {"about", "after", "their", "there", "these", "which", "while", "would",
              "could", "should", "other", "under", "where", "being", "company",
              "between", "through", "during", "against", "within", "without"}


def key_words(text: str, ignore: str = "") -> set[str]:
    """Meaningful words, cut to 5 letters so 'boosting'/'boosts' still match."""
    skip = set(normalise(ignore).split())
    words = re.findall(r"[a-z]{5,}", normalise(text))
    return {w[:5] for w in words if w not in _STOPWORDS and w not in skip}


@dataclass
class Story:
    headline: str
    summary: str
    category: str
    date: date               # computed in code: earliest article date
    outlets: list[str]       # computed in code: distinct sites reporting it
    sources: list[Kept]
    quote: str
    quote_source: Kept


@dataclass
class Point:
    text: str
    story_numbers: list[int]  # 1-based positions in the final story list


@dataclass
class Verified:
    stories: list[Story] = field(default_factory=list)
    talking_points: list[Point] = field(default_factory=list)
    open_questions: list[Point] = field(default_factory=list)
    removed: list[tuple[str, str]] = field(default_factory=list)  # (item, reason)


def _site(kept: Kept) -> str:
    host = re.sub(r"^https?://", "", kept.source.url).split("/")[0].lower()
    return re.sub(r"^(www\.|m\.|amp\.)", "", host)


def verify(raw: dict, articles: list[Kept], subject: str = "") -> Verified:
    out = Verified()
    by_number = {i: k for i, k in enumerate(articles, start=1)}
    story_id_to_position: dict[int, int] = {}

    for s in raw.get("stories", []) or []:
        headline = str(s.get("headline", "")).strip() or "(untitled)"
        ids = [i for i in s.get("article_ids", []) if isinstance(i, int) and i in by_number]
        quote = s.get("quote") or {}
        q_id, q_text = quote.get("article_id"), str(quote.get("text", ""))

        if not ids:
            out.removed.append((headline, "cites no real article"))
            continue
        if q_id not in by_number:
            out.removed.append((headline, "quote points at an article that doesn't exist"))
            continue
        if not quote_found(q_text, by_number[q_id].source.title + " " + by_number[q_id].source.snippet):
            out.removed.append((headline, "quote not found word for word in the cited article"))
            continue

        sources = [by_number[i] for i in dict.fromkeys(ids + [q_id])]
        claim = headline + " " + str(s.get("summary", ""))
        cited_text = " ".join(k.source.title + " " + k.source.snippet for k in sources)

        # Check 1: no invented figures. Every number in the claim must appear
        # somewhere in the articles this story cites.
        missing = sorted(numbers_in(claim) - numbers_in(cited_text))
        if missing:
            out.removed.append((headline, f"figure(s) {', '.join(missing)} not in any cited article"))
            continue

        # Check 2: the quote must actually relate to the claim, sharing at least
        # one figure or meaningful word (the subject's own name doesn't count).
        shares_number = numbers_in(claim) & numbers_in(q_text)
        shares_word = key_words(claim, ignore=subject) & key_words(q_text, ignore=subject)
        if not (shares_number or shares_word):
            out.removed.append((headline, "quote is real but doesn't back up this claim"))
            continue
        out.stories.append(Story(
            headline=headline,
            summary=str(s.get("summary", "")).strip(),
            category=str(s.get("category", "other")).strip(),
            date=min(k.published for k in sources),
            outlets=sorted({_site(k) for k in sources}),
            sources=sources,
            quote=q_text.strip(),
            quote_source=by_number[q_id],
        ))
        story_id_to_position[s.get("id")] = len(out.stories)

    for key, target in (("talking_points", out.talking_points),
                        ("open_questions", out.open_questions)):
        for p in raw.get(key, []) or []:
            text = str(p.get("text", "")).strip()
            linked = [story_id_to_position[i] for i in p.get("story_ids", [])
                      if i in story_id_to_position]
            if text and linked:
                target.append(Point(text, linked))
            elif text:
                out.removed.append((text[:70], "not linked to any verified story"))
    return out
