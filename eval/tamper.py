"""Corrupt verified stories the way a careless model might, and check verify() catches it.

Each corruption takes one story that PASSED the checks and changes exactly one thing.
A corruption is "caught" if verify() then removes that story.
"""
import copy
import re

from vouch.verify import verify


def _bump_number(text: str) -> str | None:
    m = re.search(r"\d+(?:\.\d+)?", text)
    if not m:
        return None
    old = m.group(0)
    new = str(int(float(old)) + 7) if "." not in old else f"{float(old) + 1.3:.1f}"
    return text[:m.start()] + new + text[m.end():]


def _paraphrase(text: str) -> str:
    """Swap word order and a common word: same meaning, not word for word."""
    words = text.split()
    if len(words) > 6:
        words[1], words[2] = words[2], words[1]
    return " ".join(words).replace(" the ", " a ", 1)


CORRUPTIONS = {
    "quote figure changed": lambda s, n: _set_quote(s, _bump_number(s["quote"]["text"])),
    "quote paraphrased": lambda s, n: _set_quote(s, _paraphrase(s["quote"]["text"])),
    "quote cites wrong article": lambda s, n: _wrong_article(s, n),
    "invented figure in summary": lambda s, n: {**s, "summary": s.get("summary", "") + " Revenue rose 913% this year."},
    "invented quote": lambda s, n: _set_quote(s, "The company said it expects to triple its workforce by next spring."),
}


def _set_quote(story, text):
    if not text or text == story["quote"]["text"]:
        return None  # this corruption doesn't apply (e.g. no number to change)
    s = copy.deepcopy(story)
    s["quote"]["text"] = text
    return s


def _wrong_article(story, n_articles):
    current = story["quote"]["article_id"]
    others = [i for i in range(1, n_articles + 1) if i != current and i not in story["article_ids"]]
    if not others:
        return None
    s = copy.deepcopy(story)
    s["quote"]["article_id"] = others[0]
    return s


def tamper_test(raw: dict, articles: list, subject: str, window_start) -> dict:
    """Returns {corruption: [caught, tried]} for every story that passed originally."""
    baseline = verify(raw, articles, subject, window_start)
    passed_headlines = {st.headline for st in baseline.stories}
    results = {name: [0, 0] for name in CORRUPTIONS}
    for story in raw.get("stories", []):
        if str(story.get("headline", "")).strip() not in passed_headlines:
            continue
        for name, corrupt in CORRUPTIONS.items():
            bad = corrupt(story, len(articles))
            if bad is None:
                continue
            check = verify({"stories": [bad]}, articles, subject, window_start)
            results[name][1] += 1
            results[name][0] += int(len(check.stories) == 0)
    return results
