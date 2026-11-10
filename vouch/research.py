"""Step 2 of the pipeline: search the web for the 30 days before a meeting.

This module only COLLECTS raw results. It does not decide what is true;
filtering and checking happen in later steps, in code we can test.
"""
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from tavily import TavilyClient

from vouch import cache

WINDOW_DAYS = 30

# One search per angle. Separate searches beat one broad search because each
# angle gets its own slots in the results instead of news crowding out the rest.
ANGLES = {
    "company": {
        "news": "{name} news",
        "launches": "{name} launches new product OR announces",
        "people": "{name} appoints OR hires OR CEO OR executive",
        "deals": "{name} funding OR acquisition OR partnership OR deal",
    },
    "person": {
        "news": '"{name}" news',
        "role": '"{name}" joins OR appointed OR named OR steps down',
        "public": '"{name}" interview OR talk OR podcast OR said',
    },
}


@dataclass
class Source:
    """One search result, kept exactly as Tavily gave it."""
    url: str
    title: str
    snippet: str
    published_date: str | None  # Tavily's date if it gave one; None if not
    angle: str                  # which search found it
    score: float


@dataclass
class SearchRun:
    name: str
    kind: str
    window_start: date
    window_end: date
    sources: list[Source] = field(default_factory=list)
    credits_used: int = 0
    cache_hits: int = 0


def window_for(meeting_at: datetime, today: date | None = None) -> tuple[date, date]:
    """The 30 days before the meeting. The end can't be in the future."""
    today = today or date.today()
    end = min(meeting_at.date(), today)
    return end - timedelta(days=WINDOW_DAYS), end


def search(name: str, kind: str, meeting_at: datetime, max_results: int = 8,
           about: str = "") -> SearchRun:
    if kind not in ANGLES:
        raise ValueError(f"kind must be one of {list(ANGLES)}, got {kind!r}")
    start, end = window_for(meeting_at)
    run = SearchRun(name=name, kind=kind, window_start=start, window_end=end)
    client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])

    for angle, template in ANGLES[kind].items():
        params = {
            # "Mercury (startup bank) news" finds the right Mercury far more often
            "query": template.format(name=f"{name} ({about})" if about else name),
            "topic": "news",
            "search_depth": "basic",   # 1 credit; "advanced" costs 2
            "max_results": max_results,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        }
        response = cache.get(params)
        if response is not None:
            run.cache_hits += 1
        else:
            response = client.search(**params)
            cache.put(params, response)
            run.credits_used += 1

        for r in response.get("results", []):
            run.sources.append(Source(
                url=r.get("url", ""),
                title=r.get("title", ""),
                snippet=r.get("content", ""),
                published_date=r.get("published_date"),
                angle=angle,
                score=r.get("score", 0.0),
            ))
    return run
