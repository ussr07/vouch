"""Step 3 of the pipeline: decide in CODE which search results to keep.

Every rejected result goes into the ledger with a plain-English reason,
so the user (and the judges) can see exactly what was thrown away and why.
No AI is used here: these are rules you can read, test and explain.
"""
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

from vouch.research import SearchRun, Source

# Pages that are not news articles, even though the search returned them.
NOT_NEWS_HOSTS = {"tavily.com"}


@dataclass
class Kept:
    source: Source
    published: date


@dataclass
class Rejected:
    source: Source
    reason: str


@dataclass
class FilterResult:
    kept: list[Kept] = field(default_factory=list)
    rejected: list[Rejected] = field(default_factory=list)


def parse_date(raw: str | None) -> date | None:
    """Turn Tavily's date text into a real date. Returns None if it can't."""
    if not raw:
        return None
    try:  # news results look like "Fri, 23 Oct 2026 10:15:00 GMT"
        return parsedate_to_datetime(raw).date()
    except (TypeError, ValueError):
        pass
    try:  # some sources use ISO format: "2026-10-23" or "2026-10-23T10:15:00"
        return datetime.fromisoformat(raw.strip().replace("Z", "+00:00")).date()
    except ValueError:
        return None


def normalise_url(url: str) -> str:
    """Treat http/https, 'www.', 'm.' and trailing slashes as the same page."""
    parts = urlsplit(url.strip().lower())
    host = re.sub(r"^(www\.|m\.|amp\.)", "", parts.netloc)
    return host + parts.path.rstrip("/")


def mentions(name: str, text: str) -> bool:
    """True if the full name appears as whole words (case-insensitive).

    Whole words matters: 'Meta' must not match 'metadata'.
    """
    pattern = r"(?<!\w)" + re.escape(name.strip()) + r"(?!\w)"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def names_subject(run: SearchRun, source: Source) -> bool:
    """Is the subject named in the headline?

    Companies: the full name must be in the headline.
    People: headlines often use only the surname ("Nilekani says..."), so the
    surname in the headline counts if the full name appears in the text.
    Tested on live data: requiring the full name dropped 2 valid articles.
    """
    if mentions(run.name, source.title):
        return True
    parts = run.name.split()
    if run.kind == "person" and len(parts) > 1:
        return mentions(parts[-1], source.title) and mentions(run.name, source.snippet)
    return False


def filter_run(run: SearchRun) -> FilterResult:
    result = FilterResult()
    seen_urls: set[str] = set()

    # Highest-scoring first, so if two copies exist we keep the better match.
    for source in sorted(run.sources, key=lambda s: s.score, reverse=True):
        host = urlsplit(source.url).netloc.lower().removeprefix("www.")
        key = normalise_url(source.url)
        published = parse_date(source.published_date)

        if host in NOT_NEWS_HOSTS:
            reason = "not a news article (search engine's own profile page)"
        elif key in seen_urls:
            reason = "duplicate of a page already kept"
        elif published is None:
            reason = "no publish date, so it can't be placed in the 30-day window"
        elif not (run.window_start <= published <= run.window_end):
            reason = (f"published {published}, outside the window "
                      f"{run.window_start} to {run.window_end}")
        elif not names_subject(run, source):
            # Tested on live data: real articles name the subject in the headline,
            # while junk (aggregator pages, the company's own blog posts) only
            # mentions it in passing in the body text.
            if mentions(run.name, source.snippet):
                reason = f"'{run.name}' only mentioned in passing, not in the headline"
            else:
                reason = f"never mentions '{run.name}'"
        else:
            reason = None

        if reason:
            result.rejected.append(Rejected(source, reason))
        else:
            seen_urls.add(key)
            result.kept.append(Kept(source, published))

    result.kept.sort(key=lambda k: k.published, reverse=True)  # newest first
    return result
