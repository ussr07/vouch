"""Step 2 of the pipeline: search the web for the 30 days before a meeting.

This module only COLLECTS raw results. It does not decide what is true;
filtering and checking happen in later steps, in code we can test.
"""
import os
from concurrent.futures import ThreadPoolExecutor
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
    failed: list[tuple[str, str]] = field(default_factory=list)  # (angle, what went wrong)


EARLIEST_MEETING_YEAR = 2000   # news search is meaningless much earlier


def meeting_problem(meeting_at: datetime, today: date | None = None) -> str | None:
    """Why this meeting date can't be briefed, in plain words, or None if it's fine."""
    today = today or date.today()
    if meeting_at.year < EARLIEST_MEETING_YEAR:
        return f"Pick a meeting date from {EARLIEST_MEETING_YEAR} onwards."
    if (meeting_at.date() - today).days >= WINDOW_DAYS:
        return (f"That meeting is {WINDOW_DAYS} or more days away, so none of the {WINDOW_DAYS} days "
                f"before it have happened yet. Make the brief within {WINDOW_DAYS} days of the meeting.")
    return None


def window_for(meeting_at: datetime, today: date | None = None) -> tuple[date, date]:
    """The 30 days preceding the meeting, as the challenge brief specifies.

    Starts 30 days before the MEETING (not before today), and ends at the meeting,
    or today if the meeting is still ahead, because later news doesn't exist yet.
    """
    today = today or date.today()
    start = meeting_at.date() - timedelta(days=WINDOW_DAYS)
    return start, min(meeting_at.date(), today)


def search(name: str, kind: str, meeting_at: datetime, max_results: int = 8,
           about: str = "") -> SearchRun:
    if kind not in ANGLES:
        raise ValueError(f"kind must be one of {list(ANGLES)}, got {kind!r}")
    problem = meeting_problem(meeting_at)
    if problem:
        raise ValueError(problem)
    start, end = window_for(meeting_at)
    run = SearchRun(name=name, kind=kind, window_start=start, window_end=end)
    client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])

    def one_angle(template: str):
        """Returns (response, came_from_cache). Exceptions are caught by the caller."""
        params = {
            # "Mercury (startup bank) news" finds the right Mercury far more often
            "query": template.format(name=f"{name} ({about})" if about else name),
            "topic": "news",
            "search_depth": "basic",   # 1 credit; "advanced" costs 2
            "max_results": max_results,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        }
        cached = cache.get(params)
        if cached is not None:
            return cached, True
        response = client.search(**params)
        cache.put(params, response)
        return response, False

    # The searches are independent, so they run at the same time (about 4x faster).
    angles = list(ANGLES[kind].items())
    with ThreadPoolExecutor(max_workers=len(angles)) as pool:
        futures = [(angle, pool.submit(one_angle, template)) for angle, template in angles]

    errors = []
    for angle, future in futures:  # results kept in a fixed order, so briefs are repeatable
        try:
            response, from_cache = future.result()
        except Exception as e:  # one failed search must not sink the others
            errors.append(e)
            run.failed.append((angle, f"{type(e).__name__}: {e}"[:160]))
            continue
        if from_cache:
            run.cache_hits += 1
        else:
            run.credits_used += 1
        for r in response.get("results", []) if isinstance(response, dict) else []:
            if not isinstance(r, dict):
                continue
            run.sources.append(Source(
                url=str(r.get("url") or ""),
                title=str(r.get("title") or ""),
                snippet=str(r.get("content") or ""),
                published_date=r.get("published_date"),
                angle=angle,
                score=r.get("score") if isinstance(r.get("score"), (int, float)) else 0.0,
            ))
    if errors and len(errors) == len(angles):
        raise errors[0]  # every search failed: report the real cause (bad key, no credits...)
    return run
