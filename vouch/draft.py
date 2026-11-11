"""Step 4 of the pipeline: the model groups articles into stories and drafts the brief.

The model is only allowed to (a) point at article numbers and (b) copy a quote.
Dates, outlet counts and quote checking are done afterwards in code (verify.py).
"""
from datetime import date

from vouch.filters import Kept
from vouch.llm import CallInfo, chat_json

MAX_ARTICLES = 30      # the newest 30; snippets are shorter so the prompt stays inside free-tier limits
SNIPPET_CHARS = 600    # per article

GOALS = {
    "sales": "a sales conversation: find needs, priorities and timing",
    "investor": "an investor conversation: momentum, risks, financial signals",
    "partnership": "a partnership conversation: strategic fit and recent bets",
    "bizdev": "a business development conversation: growth plans, new markets and openings to work together",
    "hiring": "a hiring or job conversation: team changes, culture, direction",
    "general": "a general introductory meeting",
}

SYSTEM = """You prepare thorough pre-meeting briefings from news articles.
Cover every distinct event the articles report: a reader should not miss anything
important that happened to this subject in the window.
Rules you must follow:
- Use ONLY the numbered articles given. Never add facts from your own knowledge.
- Group articles that report the same event into ONE story, and list EVERY
  article number that reports that event in "article_ids" (often 2-7 articles).
- Each story needs a "quote": copy one sentence EXACTLY, character for character,
  from the article you cite. Do not shorten, fix or paraphrase it. Max 40 words.
  The quote must directly support the story's headline: if the story is about a
  figure, the quote must contain that figure.
- Only use figures that appear in the articles.
- If you cannot find an exact supporting sentence, leave the story out.
- Reply with a single JSON object only, no other text."""

SCHEMA = """{
  "stories": [
    {"id": 1, "headline": "short neutral headline, max 12 words",
     "summary": "1-2 sentences on what happened and why it matters",
     "category": "results | deal | product | people | legal | other",
     "article_ids": [3, 7],
     "quote": {"article_id": 3, "text": "exact sentence copied from article 3"}}
  ],
  "talking_points": [{"text": "a point to raise in the meeting", "story_ids": [1]}],
  "open_questions": [{"text": "a question to ask them", "story_ids": [2]}]
}"""


def build_prompt(name: str, kind: str, goal: str, meeting_day: date,
                 kept: list[Kept]) -> tuple[str, list[Kept]]:
    articles = kept[:MAX_ARTICLES]
    lines = []
    for i, k in enumerate(articles, start=1):
        snippet = " ".join(k.source.snippet.split())[:SNIPPET_CHARS]
        lines.append(f"[{i}] {k.published} | {k.source.title}\n{snippet}")
    user = (
        f"Subject: {name} ({kind})\n"
        f"Meeting date: {meeting_day}\n"
        f"Meeting purpose: {GOALS.get(goal, GOALS['general'])}\n\n"
        f"Write one story per distinct event, most important first: aim for 8-10 stories when "
        f"the articles report that many different events (fewer only if they don't). Then "
        f"6-8 talking points and 6-8 open questions tailored to the meeting purpose, spread "
        f"across different stories; every one must list in story_ids the stories it rests on.\n\n"
        f"Reply in this JSON shape:\n{SCHEMA}\n\n"
        f"ARTICLES:\n" + "\n\n".join(lines)
    )
    return user, articles


def draft(name: str, kind: str, goal: str, meeting_day: date,
          kept: list[Kept]) -> tuple[dict, list[Kept], CallInfo]:
    """Returns the model's raw draft, the exact articles it saw, and call info."""
    user, articles = build_prompt(name, kind, goal, meeting_day, kept)
    raw, info = chat_json(SYSTEM, user)
    return raw, articles, info
